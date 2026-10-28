from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from context_forge.comparison.models import ComparisonState
from context_forge.config.project import (
    PackageBoundaryPolicy,
    StructuralRule,
)
from context_forge.inspection import (
    format_pre_change_inspection_summary,
    inspect_pre_change,
)
from context_forge.models.project import Project
from context_forge.pipeline.analyzer import (
    ProjectAnalyzer,
    current_fingerprints,
)
from context_forge.pipeline.freshness import (
    WorkflowFreshness,
    WorkflowFreshnessGuard,
)
from context_forge.preflight import (
    build_preflight_report,
    format_preflight_summary,
)
from context_forge.query.architecture_report import (
    DEFAULT_REPORT_LIMIT,
    build_architecture_report,
)
from context_forge.query.changeset import (
    analyze_changeset,
)
from context_forge.query.health import (
    DEFAULT_HEALTH_LIMIT,
    build_health_report,
)
from context_forge.query.impact import (
    DEFAULT_IMPACT_LIMIT,
    DEFAULT_IMPACT_MAX_DEPTH,
    find_impact,
)
from context_forge.query.locator import (
    DEFAULT_EXCERPT_MAX_LINES,
    get_source_evidence,
    locate_and_get_evidence,
)
from context_forge.query.package_boundary import (
    analyze_package_boundaries,
)
from context_forge.query.path import (
    DEFAULT_PATH_MAX_DEPTH,
    DEFAULT_PATH_MAX_EXPANSIONS,
    find_relationship_path,
)
from context_forge.query.post_change import (
    PostChangeVerificationReport,
    run_post_change_verification,
)
from context_forge.query.project import ProjectQuery
from context_forge.query.regression_rules import (
    StructuralRulesReport,
    evaluate_structural_rules,
)
from context_forge.query.risk import (
    generate_change_risk_report,
)
from context_forge.query.unused import (
    DEFAULT_UNUSED_LIMIT,
    UnusedEntitiesReport,
    find_unused_candidates,
)
from context_forge.reporting import (
    ContextForgeError,
    DiagnosticItem,
    IncompleteAnalysisError,
    IndeterminateFreshnessError,
    MissingAnalysisError,
    OperationOutcome,
    RefreshFailedError,
    StaleAnalysisError,
)
from context_forge.storage.cache import (
    ExecutionRecord,
    RepositoryCacheMetadata,
    RepositoryIdentity,
)
from context_forge.storage.database import Database, project_database_path
from context_forge.storage.repository import ProjectRepository


def _add_output_format_argument(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Format output as human-readable text or machine-readable JSON (choices: text, json; default: text)",
    )


def _add_refresh_control_argument(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        default=False,
        help="Disable automatic background refresh when repository intelligence is stale",
    )


def _emit_json(payload: dict, file: Any = None) -> None:
    target = file if file is not None else sys.stdout
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=target)


CLI_LOGO: str = (
    " ██████╗ ██████╗ ███╗   ██╗████████╗███████╗██╗  ██╗████████╗\n"
    "██╔════╝██╔═══██╗████╗  ██║╚══██╔══╝██╔════╝╚██╗██╔╝╚══██╔══╝\n"
    "██║     ██║   ██║██╔██╗ ██║   ██║   █████╗   ╚███╔╝    ██║\n"
    "██║     ██║   ██║██║╚██╗██║   ██║   ██╔══╝   ██╔██╗    ██║\n"
    "╚██████╗╚██████╔╝██║ ╚████║   ██║   ███████╗██╔╝ ██╗   ██║\n"
    " ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚══════╝╚═╝  ╚═╝   ╚═╝\n"
    "\n"
    "███████╗ ██████╗ ██████╗  ██████╗ ███████╗\n"
    "██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝\n"
    "█████╗  ██║   ██║██████╔╝██║  ███╗█████╗\n"
    "██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝\n"
    "██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗\n"
    "╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
)


class NoTrailingPeriodHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def _expand_help(self, action: argparse.Action) -> str:
        text = super()._expand_help(action)
        if text.endswith(".") and not text.endswith(".."):
            text = text[:-1]
        return text


COMMAND_CATEGORIES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "repository analysis & cache",
        [
            ("analyze", "Analyze a repository and persist repository intelligence"),
            ("refresh", "Refresh repository analysis and cached intelligence"),
            ("status", "Show repository and analysis status"),
            ("cache", "Show repository cache state and freshness"),
            ("history", "Show repository execution history and observability records"),
            ("preflight", "Inspect repository preflight readiness and configuration"),
        ],
    ),
    (
        "context retrieval & memory",
        [
            (
                "context",
                "Retrieve deterministic context package for a development task",
            ),
            ("inspect", "Inspect persisted repository intelligence summary"),
            (
                "locate",
                "Locate repository symbols precisely with optional source evidence",
            ),
            ("memory", "Search and retrieve persistent repository memory"),
        ],
    ),
    (
        "architecture & relationships",
        [
            ("architecture", "Report repository architecture and structural findings"),
            ("path", "Find bounded relationship path between start and end entities"),
            (
                "package-boundaries",
                "Analyze dependencies crossing package boundaries and evaluate policies",
            ),
            (
                "health",
                "Report repository health, inventory metrics, and structural findings",
            ),
        ],
    ),
    (
        "change analysis & verification",
        [
            ("inspect-change", "Perform comprehensive pre-change inspection"),
            (
                "impact",
                "Analyze direct and transitive change impact for a file or symbol",
            ),
            (
                "changeset",
                "Analyze combined impact for a set of changed repository paths",
            ),
            ("risk", "Generate evidence-based change-risk report for changed paths"),
            (
                "rules",
                "Evaluate structural regression rules against repository architecture",
            ),
            ("post-change", "Run consolidated post-change verification"),
        ],
    ),
    (
        "diagnostics & utilities",
        [
            ("diagnostics", "Show persisted repository analysis diagnostics"),
            (
                "unused",
                "Identify entities with no detected incoming references or usage evidence",
            ),
            ("logo", "Display Context Forge ASCII logo and exit"),
        ],
    ),
]


class ContextForgeArgumentParser(argparse.ArgumentParser):
    _is_root: bool = False

    def format_help(self) -> str:
        if not self._is_root:
            return super().format_help()
        lines: list[str] = [
            f"usage: {self.prog} [-h] [--logo] <command> ...",
            "",
            "Deterministic repository intelligence and memory for software projects",
            "",
            "global options:",
            "  -h, --help            Show this help message and exit",
            "  --logo                Display Context Forge ASCII logo and exit",
            "",
            "command categories:",
        ]
        for cat_name, commands in COMMAND_CATEGORIES:
            lines.append(f"\n  {cat_name}:")
            for cmd, desc in commands:
                lines.append(f"    {cmd:<20}{desc}")
        lines.append("")
        lines.append(
            f"Run '{self.prog} <command> --help' for detailed help on a specific command"
        )
        lines.append("")
        return "\n".join(lines)


def create_parser() -> argparse.ArgumentParser:
    parser = ContextForgeArgumentParser(
        prog="context-forge",
        formatter_class=NoTrailingPeriodHelpFormatter,
        add_help=False,
    )
    parser._is_root = True
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this help message and exit",
    )
    parser.add_argument(
        "--logo",
        action="store_true",
        help="Display Context Forge ASCII logo and exit",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    subparsers.add_parser(
        "logo",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Display Context Forge ASCII logo and exit",
        description="Display Context Forge ASCII logo and exit",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Analyze a repository and persist repository intelligence",
        description="Analyze a repository and persist repository intelligence",
    )
    analyze_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to analyze (default: current directory)",
    )
    _add_output_format_argument(analyze_parser)

    refresh_parser = subparsers.add_parser(
        "refresh",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Refresh repository analysis and cached intelligence",
        description="Refresh repository analysis and cached intelligence",
    )
    refresh_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to refresh (default: current directory)",
    )
    _add_output_format_argument(refresh_parser)

    context_parser = subparsers.add_parser(
        "context",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Retrieve deterministic context package for a development task",
        description="Retrieve deterministic context package for a development task",
    )
    context_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to retrieve context from (default: current directory)",
    )
    context_parser.add_argument(
        "--task",
        default=None,
        help="Development task description or prompt to guide context extraction",
    )
    context_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="File path destination to write synthesized context package JSON",
    )
    _add_refresh_control_argument(context_parser)

    status_parser = subparsers.add_parser(
        "status",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Show repository and analysis status",
        description="Show repository and analysis status",
    )
    status_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to inspect (default: current directory)",
    )
    _add_output_format_argument(status_parser)

    cache_parser = subparsers.add_parser(
        "cache",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Show repository cache state and freshness",
        description="Show repository cache state and freshness",
    )
    cache_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to check cache freshness for (default: current directory)",
    )
    _add_output_format_argument(cache_parser)

    history_parser = subparsers.add_parser(
        "history",
        aliases=["execution-history"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Show command execution history and observability records",
        description="Show command execution history and observability records",
    )
    history_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to inspect execution history for (default: current directory)",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_HISTORY_LIMIT,
        help="Maximum number of execution history records to display (default: 10)",
    )
    _add_output_format_argument(history_parser)

    inspect_parser = subparsers.add_parser(
        "inspect",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Inspect persisted repository intelligence summary",
        description="Inspect persisted repository intelligence summary",
    )
    inspect_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to inspect intelligence for (default: current directory)",
    )
    _add_output_format_argument(inspect_parser)

    memory_parser = subparsers.add_parser(
        "memory",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Inspect and retrieve persistent repository memory",
        description="Inspect and retrieve persistent repository memory",
    )
    memory_subparsers = memory_parser.add_subparsers(
        dest="memory_command",
        required=True,
        metavar="<subcommand>",
        help="Persistent memory subcommand to execute",
    )

    memory_inspect_parser = memory_subparsers.add_parser(
        "inspect",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Inspect persisted repository intelligence summary",
        description="Inspect persisted repository intelligence summary",
    )
    memory_inspect_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to inspect (default: current directory)",
    )
    _add_output_format_argument(memory_inspect_parser)

    memory_search_parser = memory_subparsers.add_parser(
        "search",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Search persisted repository memory",
        description="Search persisted repository memory",
    )
    memory_search_parser.add_argument(
        "query",
        help="Search query matching file paths, directory paths, or symbol names",
    )
    memory_search_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to search in (default: current directory)",
    )
    _add_output_format_argument(memory_search_parser)
    _add_refresh_control_argument(memory_search_parser)

    memory_file_parser = memory_subparsers.add_parser(
        "file",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Retrieve a file and its defined symbols",
        description="Retrieve a file and its defined symbols",
    )
    memory_file_parser.add_argument(
        "file_path",
        help="Repository-relative path of the file to retrieve",
    )
    memory_file_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory containing the file (default: current directory)",
    )
    _add_output_format_argument(memory_file_parser)
    _add_refresh_control_argument(memory_file_parser)

    memory_symbol_parser = memory_subparsers.add_parser(
        "symbol",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Retrieve symbol definitions by exact name",
        description="Retrieve symbol definitions by exact name",
    )
    memory_symbol_parser.add_argument(
        "symbol_name",
        help="Exact name of the symbol to retrieve",
    )
    memory_symbol_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory containing the symbol (default: current directory)",
    )
    memory_symbol_parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="Filter symbol definitions by repository-relative file path",
    )
    memory_symbol_parser.add_argument(
        "--type",
        dest="symbol_type",
        default=None,
        help="Filter symbol definitions by kind such as class, function, or method",
    )
    memory_symbol_parser.add_argument(
        "--excerpt",
        action="store_true",
        default=False,
        help="Include bounded source code excerpt from current source file",
    )
    memory_symbol_parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_EXCERPT_MAX_LINES,
        help=f"Maximum lines included in source evidence excerpt (default: {DEFAULT_EXCERPT_MAX_LINES})",
    )
    _add_output_format_argument(memory_symbol_parser)
    _add_refresh_control_argument(memory_symbol_parser)

    memory_references_parser = memory_subparsers.add_parser(
        "references",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Show indexed references to a symbol",
        description="Show indexed references to a symbol",
    )
    memory_references_parser.add_argument(
        "symbol_name",
        help="Exact or qualified symbol name to locate inbound references for",
    )
    memory_references_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory containing the symbol (default: current directory)",
    )
    _add_output_format_argument(memory_references_parser)
    _add_refresh_control_argument(memory_references_parser)

    memory_relationships_parser = memory_subparsers.add_parser(
        "relationships",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Inspect indexed relationships for a file or symbol",
        description="Inspect indexed relationships for a file or symbol",
    )
    memory_relationships_parser.add_argument(
        "entity_name",
        help="Repository-relative file path, symbol name, or qualified name",
    )
    memory_relationships_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory containing the entity (default: current directory)",
    )
    memory_relationships_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Direction of relationships to include (choices: both, incoming, outgoing; default: both)",
    )
    memory_relationships_parser.add_argument(
        "--type",
        dest="relationship_type",
        choices=("defines", "contains", "imports", "references", "inherits"),
        default=None,
        help="Filter relationships by type (choices: defines, contains, imports, references, inherits)",
    )
    _add_output_format_argument(memory_relationships_parser)
    _add_refresh_control_argument(memory_relationships_parser)

    memory_dependencies_parser = memory_subparsers.add_parser(
        "dependencies",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Show direct dependencies and dependents for a file",
        description="Show direct dependencies and dependents for a file",
    )
    memory_dependencies_parser.add_argument(
        "file_path",
        help="Repository-relative path of the file to inspect",
    )
    memory_dependencies_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory containing the file (default: current directory)",
    )
    memory_dependencies_parser.add_argument(
        "--direction",
        choices=("both", "dependencies", "dependents"),
        default="both",
        help="Filter direct file dependencies (choices: both, dependencies, dependents; default: both)",
    )
    _add_output_format_argument(memory_dependencies_parser)
    _add_refresh_control_argument(memory_dependencies_parser)

    diagnostics_parser = subparsers.add_parser(
        "diagnostics",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Show persisted repository analysis diagnostics",
        description="Show persisted repository analysis diagnostics",
    )
    diagnostics_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to show analysis diagnostics for (default: current directory)",
    )
    _add_output_format_argument(diagnostics_parser)

    architecture_parser = subparsers.add_parser(
        "architecture",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Report repository architecture and structural findings",
        description="Report repository architecture and structural findings",
    )
    architecture_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to analyze architecture for (default: current directory)",
    )
    architecture_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_REPORT_LIMIT,
        help=f"Maximum items displayed per report section (default: {DEFAULT_REPORT_LIMIT})",
    )
    _add_output_format_argument(architecture_parser)
    _add_refresh_control_argument(architecture_parser)

    impact_parser = subparsers.add_parser(
        "impact",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Analyze direct and transitive change impact for a file or symbol target",
        description="Analyze direct and transitive change impact for a file or symbol target",
    )
    impact_parser.add_argument(
        "target",
        help="Repository-relative file path, symbol name, or qualified name to analyze impact for",
    )
    impact_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory containing the target (default: current directory)",
    )
    impact_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Direction of impact graph traversal (choices: both, incoming, outgoing; default: both)",
    )
    impact_parser.add_argument(
        "--type",
        dest="relationship_type",
        choices=("imports", "references", "inherits", "calls", "depends_on"),
        default=None,
        help="Filter traversed relationships by type",
    )
    impact_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_IMPACT_MAX_DEPTH,
        help=f"Maximum graph traversal depth for impact discovery (default: {DEFAULT_IMPACT_MAX_DEPTH})",
    )
    impact_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_IMPACT_LIMIT,
        help=f"Maximum affected entities displayed in the report (default: {DEFAULT_IMPACT_LIMIT})",
    )
    _add_output_format_argument(impact_parser)
    _add_refresh_control_argument(impact_parser)

    changeset_parser = subparsers.add_parser(
        "changeset",
        aliases=["change-set"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Analyze combined impact for a set of changed repository paths",
        description="Analyze combined impact for a set of changed repository paths\n\naliases: change-set",
    )
    changeset_parser.add_argument(
        "paths",
        nargs="+",
        help="One or more changed file paths to analyze together",
    )
    changeset_parser.add_argument(
        "--path",
        "-p",
        dest="project_path",
        type=Path,
        default=Path("."),
        help="Repository root directory containing changed files (default: current directory)",
    )
    changeset_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Direction of impact graph traversal (choices: both, incoming, outgoing; default: both)",
    )
    changeset_parser.add_argument(
        "--type",
        dest="relationship_type",
        choices=("imports", "references", "inherits", "calls", "depends_on"),
        default=None,
        help="Filter traversed relationships by type",
    )
    changeset_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_IMPACT_MAX_DEPTH,
        help=f"Maximum graph traversal depth for impact discovery (default: {DEFAULT_IMPACT_MAX_DEPTH})",
    )
    changeset_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_IMPACT_LIMIT,
        help=f"Maximum affected entities displayed in the report (default: {DEFAULT_IMPACT_LIMIT})",
    )
    changeset_parser.add_argument(
        "--checklist",
        action="store_true",
        default=False,
        help="Include verification checklist with test recommendations in output",
    )
    changeset_parser.add_argument(
        "--risk",
        action="store_true",
        default=False,
        help="Include evidence-based change risk report in output",
    )
    _add_output_format_argument(changeset_parser)
    _add_refresh_control_argument(changeset_parser)

    risk_parser = subparsers.add_parser(
        "risk",
        aliases=["change-risk"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Generate an evidence-based change-risk report for changed paths",
        description="Generate an evidence-based change-risk report for changed paths\n\naliases: change-risk",
    )
    risk_parser.add_argument(
        "paths",
        nargs="+",
        help="One or more changed file paths to assess risk for",
    )
    risk_parser.add_argument(
        "--path",
        "-p",
        dest="project_path",
        type=Path,
        default=Path("."),
        help="Repository root directory containing changed files (default: current directory)",
    )
    risk_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Direction of impact graph traversal (choices: both, incoming, outgoing; default: both)",
    )
    risk_parser.add_argument(
        "--type",
        dest="relationship_type",
        choices=("imports", "references", "inherits", "calls", "depends_on"),
        default=None,
        help="Filter traversed relationships by type",
    )
    risk_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_IMPACT_MAX_DEPTH,
        help=f"Maximum graph traversal depth for impact discovery (default: {DEFAULT_IMPACT_MAX_DEPTH})",
    )
    risk_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_IMPACT_LIMIT,
        help=f"Maximum affected entities displayed in the report (default: {DEFAULT_IMPACT_LIMIT})",
    )
    _add_output_format_argument(risk_parser)
    _add_refresh_control_argument(risk_parser)

    pkg_boundaries_parser = subparsers.add_parser(
        "package-boundaries",
        aliases=["package-boundary", "boundaries"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Analyze dependencies crossing package boundaries and evaluate boundary policies",
        description="Analyze dependencies crossing package boundaries and evaluate boundary policies\n\naliases: package-boundary, boundaries",
    )
    pkg_boundaries_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to evaluate boundary rules against (default: current directory)",
    )
    pkg_boundaries_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_REPORT_LIMIT,
        help=f"Maximum cross-package dependency violations displayed (default: {DEFAULT_REPORT_LIMIT})",
    )
    _add_output_format_argument(pkg_boundaries_parser)
    _add_refresh_control_argument(pkg_boundaries_parser)

    post_change_parser = subparsers.add_parser(
        "post-change",
        aliases=["verify-change", "post_change", "verify"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Run consolidated post-change verification across structural changes, tests, risk, boundaries, and rules",
        description="Run consolidated post-change verification across structural changes, tests, risk, boundaries, and rules\n\naliases: verify-change, post_change, verify",
    )
    post_change_parser.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="Changed file paths to verify; if omitted, automatically detects changes via Git status",
    )
    post_change_parser.add_argument(
        "--path",
        "-p",
        dest="project_path",
        type=Path,
        default=Path("."),
        help="Repository root directory to verify changes in (default: current directory)",
    )
    post_change_parser.add_argument(
        "--before",
        dest="before_state_path",
        type=Path,
        default=None,
        help="Baseline repository directory or snapshot representing state prior to changes",
    )
    post_change_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Direction of impact graph traversal (choices: both, incoming, outgoing; default: both)",
    )
    post_change_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_IMPACT_MAX_DEPTH,
        help=f"Maximum graph traversal depth for impact discovery (default: {DEFAULT_IMPACT_MAX_DEPTH})",
    )
    post_change_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_REPORT_LIMIT,
        help=f"Maximum verification items displayed per category (default: {DEFAULT_REPORT_LIMIT})",
    )
    _add_output_format_argument(post_change_parser)
    _add_refresh_control_argument(post_change_parser)

    rules_parser = subparsers.add_parser(
        "rules",
        aliases=["evaluate-rules", "check-rules"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Evaluate declarative structural regression rules against repository architecture",
        description="Evaluate declarative structural regression rules against repository architecture\n\naliases: evaluate-rules, check-rules",
    )
    rules_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to evaluate structural regression rules against (default: current directory)",
    )
    rules_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_REPORT_LIMIT,
        help=f"Maximum rule evaluation results displayed (default: {DEFAULT_REPORT_LIMIT})",
    )
    _add_output_format_argument(rules_parser)
    _add_refresh_control_argument(rules_parser)

    unused_parser = subparsers.add_parser(
        "unused",
        aliases=["unused-entities", "find-unused"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Identify entities with no detected incoming references or usage evidence",
        description="Identify entities with no detected incoming references or usage evidence\n\naliases: unused-entities, find-unused",
    )
    unused_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to scan for unused entity candidates (default: current directory)",
    )
    unused_parser.add_argument(
        "--kind",
        choices=(
            "all",
            "*",
            "function",
            "functions",
            "method",
            "methods",
            "class",
            "classes",
            "variable",
            "variables",
            "file",
            "files",
            "symbol",
            "symbols",
        ),
        default="all",
        help="Filter unused entities by kind (choices: all, function, method, class, variable, file, symbol; default: all)",
    )
    unused_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_UNUSED_LIMIT,
        help=f"Maximum unused candidates displayed per category (default: {DEFAULT_UNUSED_LIMIT})",
    )
    _add_output_format_argument(unused_parser)
    _add_refresh_control_argument(unused_parser)

    path_parser = subparsers.add_parser(
        "path",
        aliases=["query-path"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Find and report a bounded relationship path between start and end entities",
        description="Find and report a bounded relationship path between start and end entities\n\naliases: query-path",
    )
    path_parser.add_argument(
        "start",
        help="Starting entity as file path, symbol name, qualified name, or UUID",
    )
    path_parser.add_argument(
        "end",
        help="Destination entity as file path, symbol name, qualified name, or UUID",
    )
    path_parser.add_argument(
        "--path",
        "-p",
        dest="project_path",
        type=Path,
        default=Path("."),
        help="Repository root directory to traverse (default: current directory)",
    )
    path_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Direction of relationship traversal (choices: both, incoming, outgoing; default: both)",
    )
    path_parser.add_argument(
        "--type",
        dest="relationship_type",
        choices=("imports", "references", "inherits", "calls", "depends_on"),
        default=None,
        help="Filter traversed relationships by type",
    )
    path_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_PATH_MAX_DEPTH,
        help=f"Maximum graph traversal depth for shortest path search (default: {DEFAULT_PATH_MAX_DEPTH})",
    )
    path_parser.add_argument(
        "--max-expansions",
        type=int,
        default=DEFAULT_PATH_MAX_EXPANSIONS,
        help=f"Maximum graph nodes expanded before terminating search (default: {DEFAULT_PATH_MAX_EXPANSIONS})",
    )
    _add_output_format_argument(path_parser)
    _add_refresh_control_argument(path_parser)

    health_parser = subparsers.add_parser(
        "health",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Report repository health, inventory metrics, and structural findings",
        description="Report repository health, inventory metrics, and structural findings",
    )
    health_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root directory to compute health report for (default: current directory)",
    )
    health_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_HEALTH_LIMIT,
        help=f"Maximum structural health findings displayed per category (default: {DEFAULT_HEALTH_LIMIT})",
    )
    _add_output_format_argument(health_parser)

    preflight_parser = subparsers.add_parser(
        "preflight",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Perform read-only repository preflight readiness and configuration audit",
        description="Perform read-only repository preflight readiness and configuration audit",
    )
    preflight_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repository root directory to audit for preflight readiness (default: current directory)",
    )
    _add_output_format_argument(preflight_parser)

    locate_parser = subparsers.add_parser(
        "locate",
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Locate repository symbols precisely with optional source evidence",
        description="Locate repository symbols precisely with optional source evidence",
    )
    locate_parser.add_argument(
        "symbol_name",
        help="Exact or qualified symbol name to locate in repository",
    )
    locate_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repository root directory to locate symbols within (default: current directory)",
    )
    locate_parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="Filter symbol matches by repository-relative file path",
    )
    locate_parser.add_argument(
        "--type",
        dest="symbol_type",
        default=None,
        help="Filter symbol matches by kind such as class, function, or method",
    )
    locate_parser.add_argument(
        "--excerpt",
        action="store_true",
        default=False,
        help="Include bounded source code excerpt for located symbol",
    )
    locate_parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_EXCERPT_MAX_LINES,
        help=f"Maximum lines included in source evidence excerpt (default: {DEFAULT_EXCERPT_MAX_LINES})",
    )
    _add_output_format_argument(locate_parser)
    _add_refresh_control_argument(locate_parser)

    inspect_change_parser = subparsers.add_parser(
        "inspect-change",
        aliases=["pre-change"],
        formatter_class=NoTrailingPeriodHelpFormatter,
        help="Perform read-only pre-change inspection composing preflight, target resolution, freshness, evidence, and Git context",
        description="Perform read-only pre-change inspection composing preflight, target resolution, freshness, evidence, and Git context\n\naliases: pre-change",
    )
    inspect_change_parser.add_argument(
        "target",
        help="Target symbol name, qualified name, or file path to inspect before making changes",
    )
    inspect_change_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repository root directory to inspect pre-change state for (default: current directory)",
    )
    inspect_change_parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="Filter target symbol by repository-relative file path",
    )
    inspect_change_parser.add_argument(
        "--type",
        dest="symbol_type",
        default=None,
        help="Filter target symbol by kind such as class, function, or method",
    )
    inspect_change_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Direction of structural impact analysis (choices: both, incoming, outgoing; default: both)",
    )
    inspect_change_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_IMPACT_MAX_DEPTH,
        help=f"Maximum traversal depth for structural impact discovery (default: {DEFAULT_IMPACT_MAX_DEPTH})",
    )
    inspect_change_parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_EXCERPT_MAX_LINES,
        help=f"Maximum lines included in source evidence excerpt (default: {DEFAULT_EXCERPT_MAX_LINES})",
    )
    inspect_change_parser.add_argument(
        "--no-git",
        action="store_true",
        default=False,
        help="Disable Git working tree and status inspection",
    )
    _add_output_format_argument(inspect_change_parser)

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] not in {
        "analyze",
        "refresh",
        "context",
        "status",
        "cache",
        "history",
        "execution-history",
        "inspect",
        "memory",
        "diagnostics",
        "architecture",
        "impact",
        "changeset",
        "change-set",
        "path",
        "query-path",
        "health",
        "preflight",
        "locate",
        "inspect-change",
        "pre-change",
        "risk",
        "change-risk",
        "package-boundaries",
        "package-boundary",
        "boundaries",
        "post-change",
        "verify-change",
        "post_change",
        "verify",
        "rules",
        "evaluate-rules",
        "check-rules",
        "unused",
        "unused-entities",
        "find-unused",
        "logo",
        "--logo",
        "-h",
        "--help",
    }:
        # Default a bare repository path to the status command.
        argv = ["status", *argv]

    return create_parser().parse_args(argv)


def resolve_project_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()

    if not resolved.exists():
        raise ValueError(f"Project path does not exist: {resolved}")

    if not resolved.is_dir():
        raise ValueError(f"Project path is not a directory: {resolved}")

    return resolved


def analyze_project(root_path: Path):
    database_path = project_database_path(root_path)

    return ProjectAnalyzer(
        root_path=root_path,
        database_path=database_path,
    ).analyze()


def load_project_analysis(root_path: Path):
    database_path = project_database_path(root_path)
    if not database_path.exists():
        raise MissingAnalysisError(
            "No persisted analysis found; run 'context-forge analyze' first",
            path=str(database_path),
        )

    repository = ProjectRepository(Database(database_path))
    repository_key = RepositoryIdentity(root_path).key

    try:
        loaded = repository.load_analysis(repository_key)
    except sqlite3.OperationalError as exc:
        if "no such table: repository_cache" not in str(exc):
            raise

        raise MissingAnalysisError(
            "No persisted analysis found; run 'context-forge analyze' first",
            path=str(database_path),
        ) from None

    if loaded is None:
        raise MissingAnalysisError(
            "No persisted analysis found; run 'context-forge analyze' first",
            path=str(database_path),
        )

    project, metadata = loaded
    return repository, repository_key, project, metadata


def load_guarded_project(
    root_path: Path,
    *,
    allow_refresh: bool = False,
    database_path: Path | None = None,
) -> tuple[Project, RepositoryCacheMetadata, WorkflowFreshness]:
    db_path = database_path or project_database_path(root_path)
    repo = None
    proj = None
    meta = None

    if database_path is None:
        try:
            loaded_repo, _, proj, meta = load_project_analysis(root_path)
            repo = loaded_repo
        except (MissingAnalysisError, sqlite3.OperationalError, sqlite3.DatabaseError):
            pass
    elif db_path.exists():
        try:
            repository = ProjectRepository(Database(db_path))
            repository_key = RepositoryIdentity(root_path).key
            loaded = repository.load_analysis(repository_key)
            if loaded is not None:
                repo = repository
                proj, meta = loaded
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            pass

    guard = WorkflowFreshnessGuard(
        root_path,
        database_path=db_path,
        repository=repo,
    )
    freshness = guard.guard(
        allow_refresh=allow_refresh,
        project=proj,
        metadata=meta,
    )

    if (
        freshness.is_current
        and freshness.project is not None
        and freshness.metadata is not None
    ):
        return freshness.project, freshness.metadata, freshness

    if freshness.refreshed and not freshness.is_current:
        error_msg = freshness.refresh_error or (
            f"Refresh failed: analysis is {freshness.state.value} ({freshness.reason})"
        )
        raise RefreshFailedError(
            f"Repository refresh failed: {error_msg}",
            path=str(root_path),
            details={
                "refresh_error": error_msg,
                "state": freshness.state.value,
                "reason": freshness.reason,
                "status": freshness.analysis_status,
                "errors": list(freshness.analysis_errors),
            },
            outcome=freshness.outcome,
        )

    if freshness.refresh_error is not None:
        raise RefreshFailedError(
            f"Repository refresh failed: {freshness.refresh_error}",
            path=str(root_path),
            details={
                "refresh_error": freshness.refresh_error,
                "status": freshness.analysis_status,
                "errors": list(freshness.analysis_errors),
            },
            outcome=freshness.outcome,
        )

    if freshness.is_stale:
        raise StaleAnalysisError(
            f"Repository analysis is stale; run 'context-forge analyze {root_path}' first",
            path=str(root_path),
            details={"changes": freshness.to_dict().get("changes")},
        )
    if freshness.is_incomplete:
        raise IncompleteAnalysisError(
            f"Repository analysis is incomplete ({freshness.reason}); run 'context-forge analyze {root_path}' first",
            path=str(root_path),
            details={
                "errors": list(freshness.analysis_errors),
                "status": freshness.analysis_status,
            },
        )
    if freshness.reason == "missing_analysis":
        raise MissingAnalysisError(
            "No persisted analysis found; run 'context-forge analyze' first",
            path=str(root_path),
        )
    raise IndeterminateFreshnessError(
        f"Repository analysis freshness is indeterminate ({freshness.reason}); reanalysis is required",
        path=str(root_path),
    )


def load_fresh_project(
    root_path: Path,
    *,
    allow_refresh: bool = True,
    database_path: Path | None = None,
) -> tuple[Project, RepositoryCacheMetadata]:
    project, metadata, _ = load_guarded_project(
        root_path,
        allow_refresh=allow_refresh,
        database_path=database_path,
    )
    return project, metadata


def print_analysis_summary(project, output_format: str = "text") -> None:
    payload = {
        "analysis_status": str(project.analysis_status),
        "files": len(project.files),
        "relationships": len(project.relationships),
        "repository": str(project.root_path),
        "symbols": len(project.symbols),
    }

    if output_format == "json":
        _emit_json(payload)
        return

    print(f"Analyzed: {project.root_path}")
    print(f"Files: {len(project.files)}")
    print(f"Symbols: {len(project.symbols)}")
    print(f"Relationships: {len(project.relationships)}")
    print(f"Status: {project.analysis_status}")


def print_status_summary(
    project,
    metadata,
    freshness,
    output_format: str = "text",
) -> None:
    payload = {
        "analysis_errors": len(project.errors),
        "analysis_status": str(project.analysis_status),
        "cache_status": "fresh" if freshness.is_fresh else "stale",
        "files": len(project.files),
        "project": project.name,
        "project_type": project.project_type or "unknown",
        "relationships": len(project.relationships),
        "repository": str(project.root_path),
        "symbols": len(project.symbols),
    }

    if output_format == "json":
        _emit_json(payload)
        return

    print(f"Repository: {project.root_path}")
    print(f"Project: {project.name}")
    print(f"Analysis status: {project.analysis_status}")
    print(f"Project type: {project.project_type or 'unknown'}")
    print(f"Files: {len(project.files)}")
    print(f"Symbols: {len(project.symbols)}")
    print(f"Relationships: {len(project.relationships)}")
    print(f"Analysis errors: {len(project.errors)}")
    print()
    print(f"Cache status: {'fresh' if freshness.is_fresh else 'stale'}")


def print_cache_summary(
    repository_key,
    metadata,
    fingerprints,
    freshness,
    output_format: str = "text",
) -> None:
    changes = freshness.changes

    added = sorted(changes.added) if changes is not None else []
    modified = sorted(changes.modified) if changes is not None else []
    deleted = sorted(changes.deleted) if changes is not None else []

    payload = {
        "added_paths": added,
        "cache_status": "fresh" if freshness.is_fresh else "stale",
        "deleted_paths": deleted,
        "freshness_reason": freshness.reason,
        "modified_paths": modified,
        "repository": str(repository_key),
        "tracked_files": len(fingerprints),
    }

    if output_format == "json":
        _emit_json(payload)
        return

    print(f"Repository: {repository_key}")
    print(f"Cache status: {'fresh' if freshness.is_fresh else 'stale'}")
    print(f"Tracked files: {len(fingerprints)}")
    print(f"Freshness reason: {freshness.reason}")
    print(f"Added paths: {len(added)}")
    print(f"Modified paths: {len(modified)}")
    print(f"Deleted paths: {len(deleted)}")

    for label, paths in (
        ("Added paths:", added),
        ("Modified paths:", modified),
        ("Deleted paths:", deleted),
    ):
        if paths:
            print()
            print(label)
            for path in paths:
                print(f"  {path}")


def print_inspection_summary(
    project,
    output_format: str = "text",
) -> None:
    files = sorted(project.files, key=lambda item: item.path)
    symbols = sorted(
        project.symbols,
        key=lambda item: (
            item.file_id,
            item.start_line,
            item.name,
        ),
    )
    relationships = sorted(
        project.relationships,
        key=lambda item: (
            item.relationship_type.value,
            str(item.source_id),
            str(item.target_id),
        ),
    )

    if output_format == "json":
        _emit_json(
            {
                "files": [
                    {
                        "path": (
                            item.path.as_posix()
                            if hasattr(item.path, "as_posix")
                            else str(item.path)
                        ),
                    }
                    for item in files
                ],
                "relationships": [
                    {
                        "source_id": str(item.source_id),
                        "target_id": str(item.target_id),
                        "type": item.relationship_type.value,
                    }
                    for item in relationships
                ],
                "repository": str(project.root_path),
                "symbols": [
                    {
                        "end_line": item.end_line,
                        "kind": str(item.kind),
                        "name": item.name,
                        "qualified_name": item.qualified_name or item.name,
                        "start_line": item.start_line,
                    }
                    for item in symbols
                ],
            }
        )
        return

    print(f"Repository: {project.root_path}")
    print()

    print("Files:")
    for item in files:
        print(f"  {item.path}")

    print()
    print("Symbols:")
    for item in symbols:
        qualified_name = item.qualified_name or item.name
        print(
            f"  {qualified_name} [{item.kind}] lines {item.start_line}-{item.end_line}"
        )

    print()
    print("Relationships:")
    for item in relationships:
        print(f"  {item.relationship_type.value}: {item.source_id} -> {item.target_id}")


def print_diagnostics_summary(
    project,
    output_format: str = "text",
) -> None:
    errors = sorted(
        project.errors,
        key=lambda item: (
            str(item.path or ""),
            item.line if item.line is not None else -1,
            str(item.severity),
            item.message,
        ),
    )

    if output_format == "json":
        _emit_json(
            {
                "errors": [
                    {
                        "line": item.line,
                        "message": item.message,
                        "path": str(item.path) if item.path is not None else None,
                        "severity": str(item.severity),
                    }
                    for item in errors
                ],
                "repository": str(project.root_path),
            }
        )
        return

    print(f"Repository: {project.root_path}")
    print(f"Analysis errors: {len(project.errors)}")

    if not project.errors:
        print("No analysis errors.")
        return

    print()

    for error in project.errors:
        print(f"[{error.severity}] {error.message}")
        if error.path is not None:
            print(f"  Path: {error.path}")
        if error.line is not None:
            print(f"  Line: {error.line}")


def read_task(task: str | None) -> str:
    if task is not None:
        normalized = task.strip()
        if not normalized:
            raise ValueError("Task cannot be empty")
        return normalized

    try:
        normalized = input("Task: ").strip()
    except KeyboardInterrupt:
        print(file=sys.stderr)
        raise SystemExit(130) from None
    except EOFError:
        raise ValueError("Task input ended unexpectedly") from None

    if not normalized:
        raise ValueError("Task cannot be empty")

    return normalized


DEFAULT_HISTORY_LIMIT: int = 10


def print_history_summary(
    records: list[ExecutionRecord],
    root_path: Path,
    output_format: str = "text",
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> None:
    if output_format == "json":
        payload = {
            "executions": [rec.to_dict() for rec in records],
            "limit": limit,
            "repository": str(root_path),
            "total": len(records),
        }
        _emit_json(payload)
        return

    print(f"Repository: {root_path}")
    if not records:
        print("No execution history found.")
        return

    print(f"Executions ({len(records)}):")
    for rec in records:
        dur_str = (
            f"{rec.duration_seconds:.3f}s"
            if rec.duration_seconds is not None
            else "n/a"
        )
        print(
            f"  [{rec.started_at}] {rec.command} - {rec.outcome} ({dur_str}) id={rec.id}"
        )
        if rec.error_type or rec.error_message:
            err_msg = (
                f"{rec.error_type or 'Error'}: {rec.error_message}"
                if rec.error_message
                else rec.error_type
            )
            print(f"    Error: {err_msg}")


def run_history(
    path: Path,
    output_format: str = "text",
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> None:
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("History limit must be a positive integer")

    root_path = resolve_project_path(path)
    database_path = project_database_path(root_path)

    if not database_path.is_file():
        records: list[ExecutionRecord] = []
    else:
        repository = ProjectRepository(Database(database_path))
        records = repository.get_execution_history(
            repository_path=root_path,
            limit=limit,
        )

    print_history_summary(records, root_path, output_format, limit=limit)


def _record_execution_start(
    root_path: Path,
    command: str,
) -> tuple[ProjectRepository | None, str | None]:
    try:
        database_path = project_database_path(root_path)
        repo = ProjectRepository(Database(database_path))
        execution_id = repo.record_execution_start(
            command=command,
            repository_path=root_path,
        )
        return repo, execution_id
    except Exception:  # noqa: BLE001
        return None, None


def _record_execution_finish(
    repo: ProjectRepository | None,
    execution_id: str | None,
    outcome: str,
    duration_seconds: float | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    if repo is None or execution_id is None:
        return
    try:
        repo.record_execution_finish(
            execution_id=execution_id,
            outcome=outcome,
            duration_seconds=duration_seconds,
            error_type=error_type,
            error_message=error_message,
        )
    except Exception:  # noqa: BLE001
        return


def run_analyze(
    path: Path,
    output_format: str = "text",
    command: str = "analyze",
) -> None:
    from context_forge.operational_logging import (
        log_analysis_completed,
        log_analysis_failed,
        log_analysis_started,
    )

    root_path = resolve_project_path(path)
    started_at = time.monotonic()
    log_analysis_started(project_path=root_path)

    history_repo, execution_id = _record_execution_start(root_path, command)

    try:
        project = analyze_project(root_path)
        duration = time.monotonic() - started_at
        log_analysis_completed(
            project_path=root_path,
            duration_seconds=duration,
            files_count=len(project.files),
            symbols_count=len(project.symbols),
        )
        _record_execution_finish(
            history_repo,
            execution_id,
            outcome="success",
            duration_seconds=duration,
        )
        print_analysis_summary(project, output_format)
    except KeyboardInterrupt:
        duration = time.monotonic() - started_at
        _record_execution_finish(
            history_repo,
            execution_id,
            outcome="interrupted",
            duration_seconds=duration,
        )
        raise
    except Exception as exc:
        duration = time.monotonic() - started_at
        log_analysis_failed(
            project_path=root_path,
            duration_seconds=duration,
            error=exc,
        )
        _record_execution_finish(
            history_repo,
            execution_id,
            outcome="failed",
            duration_seconds=duration,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise


def run_status(path: Path, output_format: str = "text") -> None:
    root_path = resolve_project_path(path)
    repository, repository_key, project, metadata = load_project_analysis(root_path)

    fingerprints = current_fingerprints(project)

    freshness = repository.check_cache_freshness(
        repository_key,
        fingerprints,
    )

    print_status_summary(project, metadata, freshness, output_format)


def run_cache(path: Path, output_format: str = "text") -> None:
    root_path = resolve_project_path(path)
    repository, repository_key, project, metadata = load_project_analysis(root_path)

    fingerprints = current_fingerprints(project)

    freshness = repository.check_cache_freshness(
        repository_key,
        fingerprints,
    )

    print_cache_summary(
        repository_key, metadata, fingerprints, freshness, output_format
    )


def run_inspect(path: Path, output_format: str = "text") -> None:
    root_path = resolve_project_path(path)
    _, _, project, _ = load_project_analysis(root_path)

    print_inspection_summary(project, output_format)


def run_memory_search(
    query: str,
    path: Path,
    output_format: str = "text",
    *,
    allow_refresh: bool = True,
) -> None:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Search query cannot be empty")

    root = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root)
        if allow_refresh
        else load_fresh_project(root, allow_refresh=False)
    )
    results = ProjectQuery(project).search(normalized_query)

    if output_format == "json":
        _emit_json(
            {
                "query": normalized_query,
                "repository": str(root),
                "results": [
                    {
                        "name": result.name,
                        "path": (
                            str(result.path)
                            if getattr(result, "path", None) is not None
                            else None
                        ),
                        "qualified_name": getattr(result, "qualified_name", None),
                        "reason": getattr(result, "reason", None),
                        "score": float(result.score),
                        "type": getattr(
                            result.result_type,
                            "value",
                            result.result_type,
                        ),
                    }
                    for result in results
                ],
            }
        )
        return

    print(f"Repository: {root}")
    print(f"Query: {normalized_query}")
    print(f"Results: {len(results)}")

    if not results:
        print("No matches found.")
        return

    for result in results:
        display_name = result.qualified_name or result.name
        print(f"- [{result.result_type.value}] {display_name}")
        if result.path:
            print(f"  Path: {result.path}")
        print(f"  Score: {result.score:.2f}")
        if result.reason:
            print(f"  Match: {result.reason}")


def run_memory_file(
    file_path: str,
    path: Path,
    output_format: str = "text",
    *,
    allow_refresh: bool = True,
) -> None:
    normalized_file_path = file_path.strip()
    if not normalized_file_path:
        raise ValueError("File path cannot be empty")

    root = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root)
        if allow_refresh
        else load_fresh_project(root, allow_refresh=False)
    )
    query = ProjectQuery(project)
    file = query.get_file(normalized_file_path)

    if file is None:
        if output_format == "json":
            _emit_json(
                {
                    "file": None,
                    "repository": str(root),
                    "requested_path": normalized_file_path,
                }
            )
            return

        print(f"Repository: {root}")
        print(f"File: {normalized_file_path}")
        print("File not found.")
        return

    symbols = sorted(
        query.find_symbols_in_file(file.id),
        key=lambda symbol: (symbol.start_line, symbol.name),
    )

    if output_format == "json":
        _emit_json(
            {
                "file": {
                    "extension": file.extension,
                    "name": file.name,
                    "path": normalized_file_path,
                    "size": int(file.size),
                    "symbols": [
                        {
                            "end_line": int(symbol.end_line),
                            "kind": getattr(symbol.kind, "value", symbol.kind),
                            "name": symbol.name,
                            "qualified_name": symbol.qualified_name,
                            "signature": symbol.signature,
                            "start_line": int(symbol.start_line),
                        }
                        for symbol in symbols
                    ],
                    "type": getattr(
                        file.file_type,
                        "value",
                        file.file_type,
                    ),
                },
                "repository": str(root),
                "requested_path": normalized_file_path,
            }
        )
        return

    print(f"Repository: {root}")
    print(f"File: {normalized_file_path}")
    print(f"Name: {file.name}")
    print(f"Extension: {file.extension}")
    print(f"Type: {file.file_type.value}")
    print(f"Size: {file.size} bytes")
    print(f"Symbols: {len(symbols)}")

    if not symbols:
        print("No symbols defined in this file.")
        return

    for symbol in symbols:
        display_name = symbol.qualified_name or symbol.name
        print(f"- [{symbol.kind}] {display_name}")
        print(f"  Lines: {symbol.start_line}-{symbol.end_line}")
        if symbol.signature:
            print(f"  Signature: {symbol.signature}")


def run_memory_symbol(
    symbol_name: str,
    path: Path,
    output_format: str = "text",
    file_path: str | None = None,
    symbol_type: str | None = None,
    excerpt: bool = False,
    max_lines: int = DEFAULT_EXCERPT_MAX_LINES,
    *,
    allow_refresh: bool = True,
) -> None:
    normalized_name = symbol_name.strip()
    if not normalized_name:
        raise ValueError("Symbol name cannot be empty")

    root = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root)
        if allow_refresh
        else load_fresh_project(root, allow_refresh=False)
    )
    query = ProjectQuery(project)

    if "." in normalized_name:
        symbols = query.find_symbols_by_qualified_name(normalized_name)
        if not symbols:
            symbols = query.find_symbols(normalized_name)
    else:
        symbols = query.find_symbols(normalized_name)

    files_by_id = {file.id: file for file in project.files}

    if file_path is not None:
        raw_fp = file_path.strip().replace("\\", "/").removeprefix("./")
        if project.root_path is not None:
            as_p = Path(raw_fp)
            if as_p.is_absolute():
                try:
                    raw_fp = as_p.relative_to(project.root_path).as_posix()
                except ValueError:
                    pass
        is_basename = "/" not in raw_fp
        symbols = [
            s
            for s in symbols
            if s.file_id in files_by_id
            and (
                files_by_id[s.file_id].path.as_posix() == raw_fp
                or (is_basename and files_by_id[s.file_id].name == raw_fp)
            )
        ]

    if symbol_type is not None:
        target_kind = symbol_type.strip().lower()
        symbols = [s for s in symbols if s.kind.lower() == target_kind]

    symbols = sorted(
        symbols,
        key=lambda symbol: (
            files_by_id[symbol.file_id].path if symbol.file_id in files_by_id else "",
            symbol.start_line,
            symbol.name,
        ),
    )

    evidence_dict = None
    if excerpt and symbols:
        evidence = get_source_evidence(project, symbols[0], max_lines=max_lines)
        evidence_dict = evidence.to_dict()

    if output_format == "json":
        payload: dict[str, Any] = {
            "matches": [
                {
                    "end_line": int(symbol.end_line),
                    "kind": getattr(symbol.kind, "value", symbol.kind),
                    "name": symbol.name,
                    "path": (
                        str(files_by_id[symbol.file_id].path)
                        if symbol.file_id in files_by_id
                        else None
                    ),
                    "qualified_name": (symbol.qualified_name or symbol.name),
                    "signature": symbol.signature,
                    "start_line": int(symbol.start_line),
                }
                for symbol in symbols
            ],
            "query": normalized_name,
            "repository": str(root),
        }
        if excerpt:
            payload["excerpt"] = evidence_dict
        _emit_json(payload)
        return

    print(f"Repository: {root}")
    print(f"Symbol: {normalized_name}")
    print(f"Matches: {len(symbols)}")

    if not symbols:
        print("No matching symbol found.")
        return

    if len(symbols) > 1:
        print("Multiple definitions found:")

    for symbol in symbols:
        display_name = symbol.qualified_name or symbol.name
        print(f"- [{symbol.kind}] {display_name}")

        file = files_by_id.get(symbol.file_id)
        print(f"  Path: {file.path if file else 'Unknown'}")
        print(f"  Lines: {symbol.start_line}-{symbol.end_line}")

        if symbol.signature:
            print(f"  Signature: {symbol.signature}")

        if excerpt and evidence_dict is not None and symbol == symbols[0]:
            print(
                f"  Source excerpt (lines {evidence_dict['start_line']}-{evidence_dict['end_line']}):"
            )
            for line in evidence_dict["content"].splitlines():
                print(f"    {line}")
            if evidence_dict.get("is_truncated"):
                print(f"    [Truncated to {evidence_dict['total_lines']} lines]")
            if evidence_dict.get("status") == "stale_location":
                print(f"    Warning: {evidence_dict['message']}")


def run_locate(
    symbol_name: str,
    path: Path,
    output_format: str = "text",
    file_path: str | None = None,
    symbol_type: str | None = None,
    excerpt: bool = False,
    max_lines: int = DEFAULT_EXCERPT_MAX_LINES,
    *,
    allow_refresh: bool = True,
) -> None:
    root = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root)
        if allow_refresh
        else load_fresh_project(root, allow_refresh=False)
    )

    resolution, evidence = locate_and_get_evidence(
        project,
        symbol_name,
        file_path=file_path,
        symbol_type=symbol_type,
        max_lines=max_lines,
    )

    if output_format == "json":
        payload = {
            "schema_version": 1,
            "repository": str(root),
            "query": symbol_name,
            "status": resolution.status,
            "target": resolution.target.to_dict()
            if resolution.target is not None
            else None,
            "candidates": [c.to_dict() for c in resolution.candidates],
            "excerpt": evidence.to_dict()
            if (excerpt and evidence is not None)
            else None,
            "outcome": resolution.outcome.to_dict(),
        }
        _emit_json(payload)
        if not resolution.is_resolved:
            raise SystemExit(1)
        return

    print(f"Repository: {root}")
    print(f"Symbol query: {symbol_name}")
    print(f"Status: {resolution.status.upper()}")

    if resolution.is_resolved and resolution.target is not None:
        t = resolution.target
        print(f"Target: [{t.kind}] {t.qualified_name or t.name}")
        print(f"  File: {t.path}")
        print(f"  Lines: {t.start_line}-{t.end_line}")
        if t.signature:
            print(f"  Signature: {t.signature}")

        if excerpt:
            print()
            if evidence is not None and evidence.is_success:
                print(
                    f"Source excerpt ({evidence.path}:{evidence.start_line}-{evidence.end_line}):"
                )
                for line in evidence.content.splitlines():
                    print(f"  {line}")
                if evidence.is_truncated:
                    print(f"  [Truncated: showing {evidence.total_lines} lines]")
                if evidence.status == "stale_location":
                    print(f"  Warning: {evidence.message}")
            elif evidence is not None:
                print(f"Source excerpt unavailable: {evidence.message}")
    elif resolution.is_ambiguous:
        print(f"Message: {resolution.message}")
        print("Candidates:")
        for c in resolution.candidates:
            print(
                f"  - [{c.kind}] {c.qualified_name or c.name} ({c.path}:{c.start_line}-{c.end_line})"
            )
        raise SystemExit(1)
    else:
        print(f"Message: {resolution.message}")
        raise SystemExit(1)


def run_inspect_change(
    target: str,
    path: Path,
    output_format: str = "text",
    file_path: str | None = None,
    symbol_type: str | None = None,
    direction: str = "both",
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    max_lines: int = DEFAULT_EXCERPT_MAX_LINES,
    no_git: bool = False,
) -> None:
    result = inspect_pre_change(
        repository_path=path,
        target=target,
        file_path=file_path,
        symbol_type=symbol_type,
        direction=direction,
        max_depth=max_depth,
        max_excerpt_lines=max_lines,
        include_git=not no_git,
    )

    if output_format == "json":
        _emit_json(result.to_dict())
    else:
        for line in format_pre_change_inspection_summary(result):
            print(line)

    if result.is_blocked or result.is_failed:
        raise SystemExit(1)


def _find_memory_symbols(query: ProjectQuery, name: str):
    if "." in name:
        symbols = query.find_symbols_by_qualified_name(name)
        if symbols:
            return symbols

    return query.find_symbols(name)


def _relationship_type_name(relationship) -> str:
    relationship_type = relationship.relationship_type

    if hasattr(relationship_type, "value"):
        return relationship_type.value

    return str(relationship_type)


def _memory_symbol_payload(symbol, files_by_id: dict) -> dict:
    file = files_by_id.get(symbol.file_id)

    return {
        "kind": symbol.kind,
        "name": symbol.name,
        "qualified_name": symbol.qualified_name,
        "path": file.path.as_posix() if file is not None else None,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
    }


def _memory_entity_payload(
    entity_id,
    files_by_id: dict,
    symbols_by_id: dict,
) -> dict:
    file = files_by_id.get(entity_id)

    if file is not None:
        return {
            "kind": "file",
            "path": file.path.as_posix(),
        }

    symbol = symbols_by_id.get(entity_id)

    if symbol is not None:
        return {
            "kind": "symbol",
            **_memory_symbol_payload(symbol, files_by_id),
        }

    return {
        "kind": "unknown",
        "id": str(entity_id),
    }


def _memory_line_payload(metadata: dict) -> int | None:
    value = metadata.get("line")

    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _memory_reference_payload(
    relationship,
    files_by_id: dict,
) -> dict:
    source_file = files_by_id.get(relationship.source_id)
    metadata = relationship.metadata

    return {
        "path": (source_file.path.as_posix() if source_file is not None else None),
        "line": _memory_line_payload(metadata),
        "name": metadata.get("name"),
        "qualified_name": metadata.get("qualified_name"),
        "confidence": relationship.confidence,
        "relationship_type": _relationship_type_name(relationship),
    }


def _memory_relationship_payload(
    relationship,
    files_by_id: dict,
    symbols_by_id: dict,
) -> dict:
    metadata = relationship.metadata

    return {
        "type": _relationship_type_name(relationship),
        "source": _memory_entity_payload(
            relationship.source_id,
            files_by_id,
            symbols_by_id,
        ),
        "target": _memory_entity_payload(
            relationship.target_id,
            files_by_id,
            symbols_by_id,
        ),
        "confidence": relationship.confidence,
        "line": _memory_line_payload(metadata),
        "qualified_name": metadata.get("qualified_name"),
    }


def _relationship_line_number(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _relationship_entity_label(entity_id, files_by_id, symbols_by_id) -> str:
    file = files_by_id.get(entity_id)
    if file is not None:
        return f"[file] {file.path.as_posix()}"

    symbol = symbols_by_id.get(entity_id)
    if symbol is not None:
        name = symbol.qualified_name or symbol.name
        return f"[{symbol.kind}] {name}"

    return f"[unknown] {entity_id}"


def _print_matching_symbols(symbols, files_by_id) -> None:
    for symbol in sorted(
        symbols,
        key=lambda item: (
            files_by_id[item.file_id].path.as_posix()
            if item.file_id in files_by_id
            else "",
            item.start_line,
            item.name,
        ),
    ):
        file = files_by_id.get(symbol.file_id)
        print(f"  [{symbol.kind}] {symbol.qualified_name or symbol.name}")
        print(
            f"    Path: {file.path.as_posix()}"
            if file is not None
            else "    Path: Unknown"
        )
        print(f"    Lines: {symbol.start_line}-{symbol.end_line}")


def run_memory_references(
    symbol_name: str,
    path: Path,
    output_format: str = "text",
    *,
    allow_refresh: bool = True,
) -> None:
    normalized_name = symbol_name.strip()
    if not normalized_name:
        raise ValueError("Symbol name cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )
    query = ProjectQuery(project)

    symbols = _find_memory_symbols(query, normalized_name)
    files_by_id = {file.id: file for file in project.files}

    if output_format == "json":
        if not symbols:
            _emit_json(
                {
                    "repository": str(root_path),
                    "symbol": normalized_name,
                    "status": "not_found",
                    "matches": [],
                    "references": [],
                }
            )
            return

        if len(symbols) > 1:
            matches = sorted(
                symbols,
                key=lambda item: (
                    files_by_id[item.file_id].path.as_posix()
                    if item.file_id in files_by_id
                    else "",
                    item.start_line,
                    item.name,
                ),
            )
            _emit_json(
                {
                    "repository": str(root_path),
                    "symbol": normalized_name,
                    "status": "ambiguous",
                    "matches": [
                        _memory_symbol_payload(item, files_by_id) for item in matches
                    ],
                    "references": [],
                }
            )
            return

        symbol = symbols[0]
        relationships = query.get_incoming_relationships(
            symbol.id,
            relationship_type="references",
        )
        relationships = sorted(
            relationships,
            key=lambda item: (
                files_by_id[item.source_id].path.as_posix()
                if item.source_id in files_by_id
                else "",
                _relationship_line_number(item.metadata.get("line", "0")),
                item.id.hex,
            ),
        )

        _emit_json(
            {
                "repository": str(root_path),
                "symbol": normalized_name,
                "status": "ok",
                "matches": [_memory_symbol_payload(symbol, files_by_id)],
                "references": [
                    _memory_reference_payload(item, files_by_id)
                    for item in relationships
                ],
            }
        )
        return

    print(f"Repository: {root_path}")
    print(f"Symbol: {normalized_name}")
    print(f"Matches: {len(symbols)}")

    if not symbols:
        print("No matching symbol found.")
        return

    if len(symbols) > 1:
        print("Multiple definitions found:")
        _print_matching_symbols(symbols, files_by_id)
        print("Use a qualified name to narrow the results.")
        return

    symbol = symbols[0]
    relationships = query.get_incoming_relationships(
        symbol.id,
        relationship_type="references",
    )

    relationships = sorted(
        relationships,
        key=lambda item: (
            files_by_id[item.source_id].path.as_posix()
            if item.source_id in files_by_id
            else "",
            _relationship_line_number(item.metadata.get("line", "0")),
            item.id.hex,
        ),
    )

    print(f"References: {len(relationships)}")

    if not relationships:
        print("No indexed references found.")
        return

    for relationship in relationships:
        source_file = files_by_id.get(relationship.source_id)
        source_path = (
            source_file.path.as_posix() if source_file is not None else "Unknown"
        )

        print(f"  Path: {source_path}")

        line = relationship.metadata.get("line")
        if line is not None:
            print(f"    Line: {line}")

        name = relationship.metadata.get("name")
        if name is not None:
            print(f"    Reference: {name}")

        qualified_name = relationship.metadata.get("qualified_name")
        if qualified_name is not None:
            print(f"    Qualified name: {qualified_name}")

        print(f"    Confidence: {relationship.confidence:.2f}")


def run_memory_relationships(
    entity_name: str,
    path: Path,
    direction: str,
    relationship_type: str | None,
    output_format: str = "text",
    *,
    allow_refresh: bool = True,
) -> None:
    normalized_name = entity_name.strip()
    if not normalized_name:
        raise ValueError("Entity name cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )
    query = ProjectQuery(project)

    files_by_id = {file.id: file for file in project.files}
    symbols_by_id = {symbol.id: symbol for symbol in project.symbols}

    file = query.get_file(normalized_name)

    if file is not None:
        entity = file
        entity_kind = "file"
    else:
        symbols = _find_memory_symbols(query, normalized_name)

        if not symbols:
            if output_format == "json":
                _emit_json(
                    {
                        "repository": str(root_path),
                        "entity": normalized_name,
                        "entity_type": None,
                        "direction": direction,
                        "relationship_type": relationship_type,
                        "status": "not_found",
                        "relationships": [],
                    }
                )
                return

            print(f"Repository: {root_path}")
            print(f"Entity: {normalized_name}")
            print("Entity not found.")
            return

        if len(symbols) > 1:
            if output_format == "json":
                matches = sorted(
                    symbols,
                    key=lambda item: (
                        files_by_id[item.file_id].path.as_posix()
                        if item.file_id in files_by_id
                        else "",
                        item.start_line,
                        item.name,
                    ),
                )
                _emit_json(
                    {
                        "repository": str(root_path),
                        "entity": normalized_name,
                        "entity_type": "symbol",
                        "direction": direction,
                        "relationship_type": relationship_type,
                        "status": "ambiguous",
                        "matches": [
                            _memory_symbol_payload(item, files_by_id)
                            for item in matches
                        ],
                        "relationships": [],
                    }
                )
                return

            print(f"Repository: {root_path}")
            print(f"Entity: {normalized_name}")
            print(f"Multiple matching symbols found: {len(symbols)}")
            _print_matching_symbols(symbols, files_by_id)
            print("Use a qualified name to narrow the results.")
            return

        entity = symbols[0]
        entity_kind = "symbol"

    if direction == "incoming":
        relationships = query.get_incoming_relationships(
            entity.id,
            relationship_type=relationship_type,
        )
    elif direction == "outgoing":
        relationships = query.get_outgoing_relationships(
            entity.id,
            relationship_type=relationship_type,
        )
    else:
        relationships = query.get_relationships(
            entity.id,
            relationship_type=relationship_type,
        )

    if output_format == "json":
        relationships = sorted(
            relationships,
            key=lambda item: (
                _relationship_type_name(item),
                str(item.source_id),
                str(item.target_id),
                _relationship_line_number(item.metadata.get("line", "0")),
                item.id.hex,
            ),
        )

        entity_payload = (
            {"kind": "file", "path": entity.path.as_posix()}
            if entity_kind == "file"
            else {
                "kind": "symbol",
                **_memory_symbol_payload(entity, files_by_id),
            }
        )

        _emit_json(
            {
                "repository": str(root_path),
                "entity": entity_payload,
                "entity_name": normalized_name,
                "entity_type": entity_kind,
                "direction": direction,
                "relationship_type": relationship_type,
                "status": "ok",
                "relationships": [
                    _memory_relationship_payload(
                        item,
                        files_by_id,
                        symbols_by_id,
                    )
                    for item in relationships
                ],
            }
        )
        return

    print(f"Repository: {root_path}")
    print(f"Entity: {normalized_name}")
    print(f"Entity type: {entity_kind}")
    print(f"Direction: {direction}")

    if relationship_type is not None:
        print(f"Relationship type: {relationship_type}")

    print(f"Relationships: {len(relationships)}")

    if not relationships:
        print("No relationships found.")
        return

    for relationship in relationships:
        source = _relationship_entity_label(
            relationship.source_id,
            files_by_id,
            symbols_by_id,
        )
        target = _relationship_entity_label(
            relationship.target_id,
            files_by_id,
            symbols_by_id,
        )

        print(f"  [{_relationship_type_name(relationship)}] {source} -> {target}")
        print(f"    Confidence: {relationship.confidence:.2f}")

        line = relationship.metadata.get("line")
        if line is not None:
            print(f"    Line: {line}")

        qualified_name = relationship.metadata.get("qualified_name")
        if qualified_name is not None:
            print(f"    Qualified name: {qualified_name}")


def run_memory_dependencies(
    file_path: str,
    path: Path,
    direction: str = "both",
    output_format: str = "text",
    *,
    allow_refresh: bool = True,
) -> None:
    normalized_path = file_path.strip()
    if not normalized_path:
        raise ValueError("File path cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )
    query = ProjectQuery(project)

    file = query.get_file(normalized_path)

    if file is None:
        if output_format == "json":
            _emit_json(
                {
                    "repository": str(root_path),
                    "file": normalized_path,
                    "direction": direction,
                    "status": "not_found",
                    "dependencies": [],
                    "dependents": [],
                }
            )
            return

        print(f"Repository: {root_path}")
        print(f"File: {normalized_path}")
        print("File not found.")
        return

    dependencies = (
        query.get_direct_dependencies(file.id)
        if direction in ("both", "dependencies")
        else []
    )
    dependents = (
        query.get_direct_dependents(file.id)
        if direction in ("both", "dependents")
        else []
    )

    dependency_paths = sorted(item.path.as_posix() for item in dependencies)
    dependent_paths = sorted(item.path.as_posix() for item in dependents)

    if output_format == "json":
        _emit_json(
            {
                "repository": str(root_path),
                "file": file.path.as_posix(),
                "direction": direction,
                "status": "ok",
                "dependencies": dependency_paths,
                "dependents": dependent_paths,
            }
        )
        return

    print(f"Repository: {root_path}")
    print(f"File: {file.path.as_posix()}")
    print(f"Direction: {direction}")

    if direction in ("both", "dependencies"):
        print(f"Direct dependencies: {len(dependency_paths)}")
        for dependency_path in dependency_paths:
            print(f"  {dependency_path}")

    if direction in ("both", "dependents"):
        print(f"Direct dependents: {len(dependent_paths)}")
        for dependent_path in dependent_paths:
            print(f"  {dependent_path}")


def run_diagnostics(path: Path, output_format: str = "text") -> None:
    root_path = resolve_project_path(path)
    _, _, project, _ = load_project_analysis(root_path)

    print_diagnostics_summary(project, output_format)


def run_architecture(
    path: Path,
    output_format: str = "text",
    limit: int = DEFAULT_REPORT_LIMIT,
    *,
    allow_refresh: bool = True,
) -> None:
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    inventory = ProjectQuery(project).get_architecture_inventory()
    report = build_architecture_report(
        inventory,
        repository_path=root_path,
        limit=limit,
    )

    if output_format == "json":
        _emit_json(report)
        return

    print(f"Repository: {report['repository']}")
    print(f"Analysis status: {report['analysis']['status']}")
    print()
    print("Summary:")

    for name, count in report["counts"].items():
        print(f"  {name.replace('_', ' ').capitalize()}: {count}")

    print()
    print("Packages:")

    package_items = report["packages"]["items"]
    if not package_items:
        print("  None found.")
    else:
        for package in package_items:
            print(f"  {package['path']} ({package['module_count']} modules)")

            for module_path in package["modules"]:
                print(f"    - {module_path}")

            if package["modules_truncated"]:
                print("    ... package module list truncated")

    if report["packages"]["truncated"]:
        print(
            f"  ... showing {len(package_items)} of "
            f"{report['packages']['total']} packages"
        )

    print()
    print("Python modules:")

    module_items = report["modules"]["items"]
    if not module_items:
        print("  None found.")
    else:
        for module in module_items:
            print(
                f"  {module['path']} "
                f"(dependencies: {module['direct_dependency_count']}, "
                f"dependents: {module['direct_dependent_count']})"
            )

            for dependency in module["direct_dependencies"]:
                print(f"    imports -> {dependency}")

            if module["direct_dependencies_truncated"]:
                print("    ... dependency list truncated")

            for dependent in module["direct_dependents"]:
                print(f"    imported by <- {dependent}")

            if module["direct_dependents_truncated"]:
                print("    ... dependent list truncated")

    if report["modules"]["truncated"]:
        print(
            f"  ... showing {len(module_items)} of {report['modules']['total']} modules"
        )

    print()
    print("Resolved dependencies:")

    dependency_items = report["dependencies"]["items"]
    if not dependency_items:
        print("  None found.")
    else:
        for dependency in dependency_items:
            print(f"  {dependency['source']} -> {dependency['target']}")

    if report["dependencies"]["truncated"]:
        print(
            f"  ... showing {len(dependency_items)} of "
            f"{report['dependencies']['total']} dependencies"
        )

    print()
    print("Dependency cycles:")

    cycle_items = report["cycles"]["items"]
    if not cycle_items:
        print("  None detected.")
    else:
        for index, cycle in enumerate(cycle_items, start=1):
            print(f"  Cycle {index}:")
            for module_path in cycle["modules"]:
                print(f"    Module: {module_path}")
            if cycle.get("modules_truncated"):
                print(
                    f"    ... showing {len(cycle['modules'])} of "
                    f"{cycle['module_count']} modules"
                )
            for dependency in cycle["dependencies"]:
                print(f"    Evidence: {dependency['source']} -> {dependency['target']}")
            if cycle.get("dependencies_truncated"):
                print(
                    f"    ... showing {len(cycle['dependencies'])} of "
                    f"{cycle['dependency_count']} dependencies"
                )

    if report["cycles"]["truncated"]:
        print(f"  ... showing {len(cycle_items)} of {report['cycles']['total']} cycles")

    print()
    print("Unresolved imports:")

    unresolved_items = report["unresolved_imports"]["items"]
    if not unresolved_items:
        print("  None recorded.")
    else:
        for item in unresolved_items:
            imported_name = (
                f" (name: {item['imported_name']})" if item["imported_name"] else ""
            )
            source = item["source_path"] or "unknown source"
            print(f"  {source}: {item['module_name']}{imported_name}")

    if report["unresolved_imports"]["truncated"]:
        print(
            f"  ... showing {len(unresolved_items)} of "
            f"{report['unresolved_imports']['total']} unresolved imports"
        )

    print()
    print("Structural findings:")

    finding_items = report["findings"]["items"]
    if not finding_items:
        print("  None recorded.")
    else:
        for finding in finding_items:
            location = finding["source_path"] or "unknown location"
            print(f"  [{finding['type']}] {location}: {finding['message']}")

    if report["findings"]["truncated"]:
        print(
            f"  ... showing {len(finding_items)} of "
            f"{report['findings']['total']} findings"
        )

    print()
    print("Limitations:")

    for limitation in report["limitations"]:
        print(f"  - {limitation}")

    if report["analysis"]["errors"]:
        print()
        print("Analysis errors:")
        for error in report["analysis"]["errors"]:
            print(f"  - {error}")


def print_health_summary(report: dict[str, Any]) -> None:
    print(f"Repository: {report['repository']}")
    if report.get("project"):
        print(
            f"Project: {report['project']['name']} "
            f"({report['project']['project_type']})"
        )

    print()
    print("Analysis state:")
    print(f"  Status: {report['analysis']['status']}")
    cache = report["cache"]
    print(f"  Cache status: {cache['status']}")
    if cache.get("reason"):
        print(f"  Freshness reason: {cache['reason']}")
    print(f"  Analysis errors: {report['analysis']['error_count']}")

    print()
    print("Inventory:")
    for name, count in report["inventory"].items():
        label = name.replace("_", " ").capitalize()
        val_str = str(count) if count is not None else "unavailable"
        print(f"  {label}: {val_str}")

    print()
    print("Findings summary:")
    for name, count in report["findings"]["summary"].items():
        label = name.replace("_", " ").capitalize()
        val_str = str(count) if count is not None else "unavailable"
        print(f"  {label}: {val_str}")

    unresolved_items = report["findings"]["unresolved_imports"]["items"]
    cycle_items = report["findings"]["dependency_cycles"]["items"]
    integrity_items = report["findings"]["structural_integrity"]["items"]

    if unresolved_items:
        print()
        print("Unresolved imports:")
        for item in unresolved_items:
            source = f" ({item['source_path']})" if item.get("source_path") else ""
            module = item["module_name"]
            if item.get("imported_name"):
                module = f"{module}.{item['imported_name']}"
            print(f"  - {module}{source}")
        if report["findings"]["unresolved_imports"]["truncated"]:
            print(
                f"  ... showing {len(unresolved_items)} of "
                f"{report['findings']['unresolved_imports']['total']} unresolved imports"
            )

    if cycle_items:
        print()
        print("Dependency cycles:")
        for cycle in cycle_items:
            modules_str = ", ".join(cycle["modules"])
            print(
                f"  - Cycle ({cycle['module_count']} modules, "
                f"{cycle['dependency_count']} dependencies): {modules_str}"
            )
        if report["findings"]["dependency_cycles"]["truncated"]:
            print(
                f"  ... showing {len(cycle_items)} of "
                f"{report['findings']['dependency_cycles']['total']} cycles"
            )

    if integrity_items:
        print()
        print("Structural integrity findings:")
        for finding in integrity_items:
            print(f"  - [{finding['type']}] {finding['message']}")
        if report["findings"]["structural_integrity"]["truncated"]:
            print(
                f"  ... showing {len(integrity_items)} of "
                f"{report['findings']['structural_integrity']['total']} findings"
            )

    if report["analysis"]["errors"]:
        print()
        print("Analysis errors:")
        for error in report["analysis"]["errors"]:
            print(f"  - {error}")

    print()
    print("Limitations:")
    for limitation in report["limitations"]:
        print(f"  - {limitation}")


def run_health(
    path: Path,
    output_format: str = "text",
    limit: int = DEFAULT_HEALTH_LIMIT,
) -> None:
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    repository, repository_key, project, metadata = load_project_analysis(root_path)

    fingerprints = current_fingerprints(project)
    freshness = repository.check_cache_freshness(
        repository_key,
        fingerprints,
    )

    report = build_health_report(
        project=project,
        repository_path=root_path,
        metadata=metadata,
        freshness=freshness,
        limit=limit,
    )

    if output_format == "json":
        _emit_json(report)
        return

    print_health_summary(report)


def print_preflight_summary(report: dict[str, Any]) -> None:
    for line in format_preflight_summary(report):
        print(line)


def run_preflight(
    path: Path,
    output_format: str = "text",
) -> None:
    report = build_preflight_report(path)

    if output_format == "json":
        _emit_json(report)
    else:
        print_preflight_summary(report)

    if report["readiness"] == "blocked":
        raise SystemExit(1)


def run_impact(
    target: str,
    path: Path,
    direction: str = "both",
    relationship_type: str | None = None,
    limit: int = DEFAULT_IMPACT_LIMIT,
    output_format: str = "text",
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    *,
    allow_refresh: bool = True,
) -> None:
    if not target or not target.strip():
        raise ValueError("Target cannot be empty")
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")
    if isinstance(max_depth, bool) or max_depth < 1:
        raise ValueError("Traversal depth must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    types_filter = {relationship_type} if relationship_type else None
    result = find_impact(
        project,
        target.strip(),
        direction=direction,
        relationship_types=types_filter,
        max_depth=max_depth,
        limit=limit,
    )

    if output_format == "json":
        _emit_json(result.to_dict())
        return

    print(f"Repository: {root_path}")
    print(f"Target query: {target.strip()}")

    if result.status == "not_found":
        print("Status: Target not found.")
        print(f"Message: {result.message}")
        return

    if result.status == "ambiguous":
        print("Status: Ambiguous target.")
        print(f"Message: {result.message}")
        print(f"Candidates ({len(result.candidates)}):")
        for candidate in result.candidates:
            loc = (
                f"{candidate.path}:{candidate.start_line}"
                if candidate.path
                else "unknown"
            )
            qual = f" ({candidate.qualified_name})" if candidate.qualified_name else ""
            print(f"  - [{candidate.kind}] {candidate.name}{qual} at {loc}")
        return

    assert result.target is not None
    tgt = result.target
    qual = f" ({tgt.qualified_name})" if tgt.qualified_name else ""
    print(f"Resolved target: [{tgt.kind}] {tgt.name}{qual} ({tgt.path})")
    print(f"Direction: {result.direction}")
    print(f"Traversal depth: {result.max_depth} (reached: {result.depth_reached})")
    print(
        f"Impacted components: {result.total} "
        f"({result.direct_count} direct, {result.indirect_count} indirect)"
    )
    print()

    direct_items = [it for it in result.items if it.classification == "direct"]
    indirect_items = [it for it in result.items if it.classification == "indirect"]

    print("Direct impact:")
    if not direct_items:
        print("  None detected.")
    else:
        for item in direct_items:
            loc = f" ({item.related_path})" if item.related_path else ""
            print(
                f"  [{item.direction}] {item.relationship_type}: "
                f"{item.related_name} [{item.related_kind}]{loc}"
            )

    if result.max_depth > 1:
        print()
        print("Indirect impact:")
        if not indirect_items:
            print("  None detected.")
        else:
            for item in indirect_items:
                loc = f" ({item.related_path})" if item.related_path else ""
                print(
                    f"  [depth {item.depth}] [{item.direction}] {item.relationship_type}: "
                    f"{item.related_name} [{item.related_kind}]{loc}"
                )
                if item.path:
                    segments: list[str] = []
                    for idx, step in enumerate(item.path):
                        if idx == 0:
                            start_label = (
                                step.from_path
                                if step.from_kind == "file" and step.from_path
                                else (
                                    f"{step.from_path}:{step.from_name}"
                                    if step.from_path
                                    else step.from_name
                                )
                            )
                            segments.append(start_label)
                        end_label = (
                            step.to_path
                            if step.to_kind == "file" and step.to_path
                            else (
                                f"{step.to_path}:{step.to_name}"
                                if step.to_path
                                else step.to_name
                            )
                        )
                        segments.append(f"-[{step.relationship_type}]-> {end_label}")
                    print(f"    Path: {' '.join(segments)}")

    if result.truncated:
        print(f"  ... showing {len(result.items)} of {result.total} items")

    print()
    print("Limitations:")
    for limitation in result.limitations:
        print(f"  - {limitation}")


def _load_project_package_policy(root_path: Path) -> PackageBoundaryPolicy | None:
    from context_forge.config.loading import load_project_configuration

    cfg = load_project_configuration(root_path)
    if cfg.packages and (
        cfg.packages.rules or cfg.packages.default_policy != "unrestricted"
    ):
        return cfg.packages
    return None


def _load_project_structural_rules(
    root_path: Path,
) -> tuple[StructuralRule, ...] | None:
    from context_forge.config.loading import load_project_configuration

    cfg = load_project_configuration(root_path)
    if cfg.rules:
        return cfg.rules
    return None


def run_changeset(
    paths: list[str],
    path: Path,
    direction: str = "both",
    relationship_type: str | None = None,
    limit: int = DEFAULT_IMPACT_LIMIT,
    output_format: str = "text",
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    *,
    checklist: bool = False,
    risk: bool = False,
    allow_refresh: bool = True,
) -> None:
    if not paths:
        raise ValueError("Paths list cannot be empty")
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")
    if isinstance(max_depth, bool) or max_depth < 1:
        raise ValueError("Traversal depth must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    types_filter = {relationship_type} if relationship_type else None
    result = analyze_changeset(
        project,
        paths,
        direction=direction,
        relationship_types=types_filter,
        max_depth=max_depth,
        limit=limit,
        include_checklist=checklist,
    )

    risk_report = None
    if risk:
        policy = _load_project_package_policy(root_path)
        risk_report = generate_change_risk_report(
            project,
            paths,
            direction=direction,
            relationship_types=types_filter,
            max_depth=max_depth,
            limit=limit,
            policy=policy,
        )

    if output_format == "json":
        payload = result.to_dict()
        if risk_report is not None:
            payload["change_risk"] = risk_report.to_dict()
        _emit_json(payload)
        return

    print(f"Repository: {root_path}")
    print(
        f"Change-set paths ({len(result.supplied_paths)}): {', '.join(result.supplied_paths)}"
    )
    resolved_count = sum(1 for r in result.resolved_inputs if r.is_resolved)
    unresolved_count = len(result.resolved_inputs) - resolved_count
    print(f"Path resolution: {resolved_count} resolved, {unresolved_count} unresolved")

    if unresolved_count > 0:
        print()
        print("Unresolved paths:")
        for r in result.resolved_inputs:
            if not r.is_resolved:
                print(f"  - {r.original_input} [{r.status}]: {r.reason}")

    print()
    print(
        f"Overall impact: {result.total} affected component(s) "
        f"({result.direct_count} direct, {result.downstream_count} downstream)"
    )

    direct_items = result.direct_items
    downstream_items = result.downstream_items

    print()
    print("Direct impact:")
    if not direct_items:
        print("  None detected.")
    else:
        for item in direct_items:
            loc = f" ({item.path})" if item.path else ""
            roots_str = ", ".join(item.roots)
            print(f"  - {item.name} [{item.kind}]{loc} (from: {roots_str})")

    print()
    print("Downstream impact:")
    if not downstream_items:
        print("  None detected.")
    else:
        for item in downstream_items:
            loc = f" ({item.path})" if item.path else ""
            roots_str = ", ".join(item.roots)
            print(
                f"  - [depth {item.min_depth}] {item.name} [{item.kind}]{loc} (from: {roots_str})"
            )
            if item.shortest_path:
                segments: list[str] = []
                for idx, step in enumerate(item.shortest_path):
                    if idx == 0:
                        start_label = step.from_path or step.from_name
                        segments.append(start_label)
                    end_label = step.to_path or step.to_name
                    segments.append(f"-[{step.relationship_type}]-> {end_label}")
                print(f"    Path: {' '.join(segments)}")

    if result.relevant_tests:
        print()
        print(f"Relevant tests ({len(result.relevant_tests)}):")
        for test in result.relevant_tests:
            print(f"  - {test.test_file_path}: {test.evidence}")
    else:
        print()
        print("Relevant tests:")
        print("  None confirmed from available repository relationship evidence.")

    if result.limitations:
        print()
        print("Limitations:")
        for lim in result.limitations:
            print(f"  - {lim}")

    if checklist and result.verification_checklist:
        chk = result.verification_checklist
        print()
        print("Verification checklist:")
        print(
            f"  Analysis status: {chk.analysis_status} (freshness: {chk.freshness_state})"
        )
        print(f"  Disclaimer: {chk.disclaimer}")

        print()
        print(
            f"Category A: Detected structural tests ({len(chk.detected_structural_tests)}):"
        )
        if not chk.detected_structural_tests:
            print("  None detected.")
        else:
            for it in chk.detected_structural_tests:
                cmd_str = f" [{it.suggested_command}]" if it.suggested_command else ""
                print(f"  - [{it.execution_status}]{cmd_str} {it.action}")
                print(f"    Rationale: {it.rationale}")
                for ev in it.supporting_evidence:
                    print(f"    Evidence: {ev}")

        print()
        print(f"Category B: Heuristic recommendations ({len(chk.heuristic_tests)}):")
        if not chk.heuristic_tests:
            print("  None detected.")
        else:
            for it in chk.heuristic_tests:
                cmd_str = f" [{it.suggested_command}]" if it.suggested_command else ""
                print(f"  - [{it.execution_status}]{cmd_str} {it.action}")
                print(f"    Rationale: {it.rationale}")
                for ev in it.supporting_evidence:
                    print(f"    Evidence: {ev}")

        print()
        print(
            f"Category C: Additional verification ({len(chk.additional_verifications)}):"
        )
        if not chk.additional_verifications:
            print("  None detected.")
        else:
            for it in chk.additional_verifications:
                cmd_str = f" [{it.suggested_command}]" if it.suggested_command else ""
                print(f"  - [{it.execution_status}]{cmd_str} {it.action}")
                print(f"    Rationale: {it.rationale}")

        print()
        print(f"Category D: Unverified areas ({len(chk.unverified_areas)}):")
        if not chk.unverified_areas:
            print("  None detected.")
        else:
            for it in chk.unverified_areas:
                print(f"  - [{it.execution_status}] {it.action}")
                print(f"    Rationale: {it.rationale}")

    if risk and risk_report:
        print()
        print("Change-risk report:")
        print(
            f"  Analysis status: {risk_report.analysis_status} (freshness: {risk_report.freshness_state})"
        )
        print(
            f"  Directly affected: {risk_report.directly_affected_count}, Downstream: {risk_report.downstream_affected_count}"
        )
        print(
            f"  Cross-package relationships: {risk_report.cross_package_impact_count}"
        )
        print()
        print(f"Inferred concerns ({len(risk_report.inferred_concerns)}):")
        if not risk_report.inferred_concerns:
            print("  None identified.")
        else:
            for c in risk_report.inferred_concerns:
                print(f"  - [{c.severity.value.upper()}] ({c.category}) {c.summary}")
                print(f"    Rationale: {c.rationale}")
                if c.recommended_action:
                    print(f"    Recommended action: {c.recommended_action}")
        if risk_report.missing_evidence:
            print()
            print("Missing evidence:")
            for m in risk_report.missing_evidence:
                print(f"  - [{m.category}] {m.description}")
        print()
        print(f"Disclaimer: {risk_report.disclaimer}")


def run_risk(
    paths: list[str],
    path: Path,
    direction: str = "both",
    relationship_type: str | None = None,
    limit: int = DEFAULT_IMPACT_LIMIT,
    output_format: str = "text",
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    *,
    allow_refresh: bool = True,
) -> None:
    if not paths:
        raise ValueError("Paths list cannot be empty")
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")
    if isinstance(max_depth, bool) or max_depth < 1:
        raise ValueError("Traversal depth must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    policy = _load_project_package_policy(root_path)

    types_filter = {relationship_type} if relationship_type else None
    report = generate_change_risk_report(
        project,
        paths,
        direction=direction,
        relationship_types=types_filter,
        max_depth=max_depth,
        limit=limit,
        policy=policy,
    )

    if output_format == "json":
        _emit_json(report.to_dict())
        return

    print(f"Repository: {root_path}")
    print(
        f"Change inputs ({len(report.change_inputs)}): {', '.join(report.change_inputs)}"
    )
    print(
        f"Analysis status: {report.analysis_status} (freshness: {report.freshness_state})"
    )
    print()
    print("Summary:")
    print(f"  Directly affected components: {report.directly_affected_count}")
    print(f"  Downstream affected components: {report.downstream_affected_count}")
    print(f"  Associated test suites: {report.associated_tests_count}")
    print(f"  Unassociated targets: {report.unassociated_targets_count}")
    print(f"  Cross-package impact relationships: {report.cross_package_impact_count}")
    print(f"  Total observed facts: {len(report.observed_facts)}")
    print(f"  Total inferred concerns: {len(report.inferred_concerns)}")

    print()
    print("Inferred concerns:")
    if not report.inferred_concerns:
        print("  None identified.")
    else:
        for c in report.inferred_concerns:
            print(f"  - [{c.severity.value.upper()}] ({c.category}) {c.summary}")
            print(f"    Rationale: {c.rationale}")
            if c.recommended_action:
                print(f"    Recommended action: {c.recommended_action}")
            for ev in c.supporting_evidence:
                print(f"    Evidence: {ev}")

    print()
    print("Observed facts:")
    if not report.observed_facts:
        print("  None observed.")
    else:
        facts_to_show = (
            report.observed_facts[:limit] if limit else report.observed_facts
        )
        for f in facts_to_show:
            print(f"  - [{f.category}] {f.statement}")
        if limit and len(report.observed_facts) > limit:
            print(f"  ... showing {limit} of {len(report.observed_facts)} facts")

    if report.missing_evidence:
        print()
        print("Missing evidence / Limitations:")
        for m in report.missing_evidence:
            print(f"  - [{m.category}] {m.description}")
            print(f"    Impact: {m.impact_on_assessment}")

    print()
    print(f"Disclaimer: {report.disclaimer}")


def run_package_boundaries(
    path: Path,
    output_format: str = "text",
    limit: int = DEFAULT_REPORT_LIMIT,
    *,
    allow_refresh: bool = True,
) -> None:
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    policy = _load_project_package_policy(root_path)

    report = analyze_package_boundaries(
        project,
        policy=policy,
        limit=limit,
    )

    if output_format == "json":
        _emit_json(report.to_dict())
        return

    print(f"Repository: {root_path}")
    print(f"Packages detected ({len(report.packages)}):")
    if not report.packages:
        print("  None detected (no directories containing '__init__.py').")
    else:
        for pkg in report.packages:
            print(f"  - {pkg}")

    print()
    print(f"Cross-package dependencies ({report.total_cross_package_count}):")
    if not report.cross_package_dependencies:
        print("  None detected.")
    else:
        for dep in report.cross_package_dependencies:
            status_tag = (
                f" [{dep.policy_status}]" if dep.policy_status != "unrestricted" else ""
            )
            print(
                f"  - [{dep.direction}]{status_tag} {dep.source_package} ({dep.source_file_path}) "
                f"-[{dep.relationship_type}]-> {dep.target_package} ({dep.target_file_path})"
            )
            if dep.violation_reason:
                print(f"    Violation: {dep.violation_reason}")
        if report.truncated:
            print(
                f"  ... showing {len(report.cross_package_dependencies)} of "
                f"{report.total_cross_package_count} items"
            )

    print()
    print(f"Repeated cross-package patterns ({len(report.repeated_patterns)}):")
    if not report.repeated_patterns:
        print("  None detected.")
    else:
        for pat in report.repeated_patterns:
            print(
                f"  - {pat.source_package} -[{pat.relationship_type}]-> "
                f"{pat.target_package}: {pat.count} dependency(ies)"
            )

    if report.unclassified_dependencies:
        print()
        print(f"Unclassified dependencies ({len(report.unclassified_dependencies)}):")
        for u in report.unclassified_dependencies[:limit]:
            print(
                f"  - {u.source_file_path} -[{u.relationship_type}]-> {u.target_file_path}: {u.reason}"
            )
        if len(report.unclassified_dependencies) > limit:
            print(
                f"  ... showing {limit} of {len(report.unclassified_dependencies)} "
                "unclassified dependencies"
            )

    if report.policy_violations:
        print()
        print(f"Policy violations ({len(report.policy_violations)}):")
        for v in report.policy_violations:
            print(f"  - [VIOLATION] Rule '{v.rule_id}': {v.message}")
            print(f"    Evidence: {v.evidence}")

    if report.limitations:
        print()
        print("Limitations:")
        for lim in report.limitations:
            print(f"  - {lim}")


def _print_rules_report(report: StructuralRulesReport) -> None:
    print(f"Repository: {report.repository_path}")
    print(
        f"Structural Rules Evaluated ({len(report.results)}): "
        f"{report.no_violations_count} clean, {report.violations_count} violation(s), "
        f"{report.unevaluable_count} unevaluable"
    )
    print(f"Status: {report.outcome.status.value.upper()} - {report.outcome.message}")

    if report.violations:
        print()
        print(f"Violations ({len(report.violations)}):")
        for v in report.violations:
            loc = (
                f" at {v.source_path}:{v.line}"
                if v.line
                else (f" at {v.source_path}" if v.source_path else "")
            )
            print(f"  - [VIOLATION] Rule '{v.rule_id}'{loc}: {v.message}")
            for ev in v.evidence:
                print(f"    Evidence: {ev}")

    if report.no_violation_items:
        print()
        print(f"No Violations Detected ({len(report.no_violation_items)}):")
        for p in report.no_violation_items:
            print(f"  - [PASS] Rule '{p.rule_id}': {p.message}")

    if report.unevaluable_items:
        print()
        print(f"Unevaluable Rules ({len(report.unevaluable_items)}):")
        for u in report.unevaluable_items:
            print(f"  - [UNEVALUABLE] Rule '{u.rule_id}': {u.message}")

    if report.limitations:
        print()
        print("Limitations:")
        for lim in report.limitations:
            print(f"  - {lim}")


def run_rules(
    path: Path,
    output_format: str = "text",
    limit: int = DEFAULT_REPORT_LIMIT,
    *,
    allow_refresh: bool = True,
) -> None:
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    rules = _load_project_structural_rules(root_path) or ()
    policy = _load_project_package_policy(root_path)

    report = evaluate_structural_rules(
        project,
        rules=rules,
        limit=limit,
        package_policy=policy,
    )

    if output_format == "json":
        _emit_json(report.to_dict())
        return

    _print_rules_report(report)


def _print_unused_report(report: UnusedEntitiesReport) -> None:
    print(f"Repository: {report.repository_path}")
    print(
        f"Unused Entities Analysis: {report.summary.total_entities_analyzed} analyzed, "
        f"{report.summary.candidates_count} candidate(s), {report.summary.unassessable_count} unassessable"
    )
    print(f"Status: {report.outcome.status.value.upper()} - {report.outcome.message}")

    if report.summary.by_kind:
        print()
        print("Candidates by kind:")
        for kind, count in sorted(report.summary.by_kind.items()):
            print(f"  - {kind}: {count}")

    if report.candidates:
        print()
        print(f"Apparent unused candidates ({len(report.candidates)}):")
        for c in report.candidates:
            loc = f" at {c.path}:{c.start_line}" if c.start_line else f" at {c.path}"
            print(f"  - [{c.kind.upper()}] {c.name}{loc}")
            print(f"    Reason: {c.reason}")
            for ev in c.evidence:
                print(f"    Evidence: {ev}")
        if len(report.candidates) < report.summary.candidates_count:
            print(
                f"  ... showing {len(report.candidates)} of {report.summary.candidates_count} candidate(s)"
            )

    if report.unassessable:
        print()
        print(f"Unassessable entities ({len(report.unassessable)}):")
        for u in report.unassessable:
            loc = f" at {u.path}:{u.start_line}" if u.start_line else f" at {u.path}"
            print(f"  - [{u.kind.upper()}] {u.name}{loc}: {u.reason}")
        if len(report.unassessable) < report.summary.unassessable_count:
            print(
                f"  ... showing {len(report.unassessable)} of {report.summary.unassessable_count} unassessable entity(ies)"
            )

    if report.limitations:
        print()
        print("Limitations & Caveats:")
        for lim in report.limitations:
            print(f"  - {lim}")


def run_unused(
    path: Path,
    output_format: str = "text",
    kind: str = "all",
    limit: int = DEFAULT_UNUSED_LIMIT,
    *,
    allow_refresh: bool = True,
) -> None:
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    report = find_unused_candidates(
        project,
        kind=kind,
        limit=limit,
    )

    if output_format == "json":
        _emit_json(report.to_dict())
        return

    _print_unused_report(report)


def _print_post_change_report(report: PostChangeVerificationReport) -> None:
    print(f"Repository: {report.repository_path}")
    print(f"Post-Change Verification: {report.outcome.status.value.upper()}")
    print(f"Message: {report.outcome.message}")
    print(
        f"Freshness: {report.freshness_state} (Refreshed: {'yes' if report.refreshed else 'no'})"
    )
    print(f"Structural Comparison: {report.comparison_status}")

    print()
    print(f"Change Set ({len(report.change_set)} file(s)):")
    for cp in report.change_set:
        print(f"  - {cp}")

    if report.summary:
        s = report.summary
        print()
        print("Summary:")
        print(f"  Directly affected components: {s.directly_affected_count}")
        print(f"  Downstream affected components: {s.downstream_affected_count}")
        print(f"  Associated tests identified: {s.associated_tests_count}")
        print(f"  Suggested checks (unexecuted): {s.suggested_checks_count}")
        print(f"  Package boundary violations: {s.package_violations_count}")
        print(f"  Rule violations: {s.rule_violations_count}")
        print(f"  Unevaluable rules: {s.rule_unevaluable_count}")
        print(f"  Risk concerns: {s.risk_concerns_count}")

    if report.suggested_checks:
        print()
        print(
            f"Suggested Verification Checks ({len(report.suggested_checks)}, unexecuted):"
        )
        for sc in report.suggested_checks:
            tgt = f" ({sc.target})" if sc.target else ""
            print(f"  - [{sc.category}] {sc.action}{tgt}")
            if sc.command:
                print(f"    Command: {sc.command}")

    if report.change_risk and report.change_risk.inferred_concerns:
        print()
        print(f"Change-Risk Concerns ({len(report.change_risk.inferred_concerns)}):")
        for c in report.change_risk.inferred_concerns:
            summary = getattr(c, "summary", None) or getattr(c, "title", "Risk concern")
            rationale = getattr(c, "rationale", None) or getattr(c, "detail", "")
            print(f"  - [{c.severity.value.upper()}] {summary}: {rationale}")

    if report.package_boundaries and report.package_boundaries.policy_violations:
        print()
        print(
            f"Package Policy Violations ({len(report.package_boundaries.policy_violations)}):"
        )
        for pv in report.package_boundaries.policy_violations:
            print(f"  - [VIOLATION] Rule '{pv.rule_id}': {pv.message}")

    if report.regression_rules and report.regression_rules.violations:
        print()
        print(
            f"Structural Rule Violations ({len(report.regression_rules.violations)}):"
        )
        for rv in report.regression_rules.violations:
            loc = f" at {rv.source_path}:{rv.line}" if rv.line else ""
            print(f"  - [VIOLATION] Rule '{rv.rule_id}'{loc}: {rv.message}")

    if report.limitations:
        print()
        print("Limitations:")
        for lim in report.limitations:
            print(f"  - {lim}")


def run_post_change(
    paths: Sequence[str | Path] | None,
    path: Path,
    before_state_path: Path | None = None,
    direction: str = "both",
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    limit: int = DEFAULT_REPORT_LIMIT,
    output_format: str = "text",
    *,
    allow_refresh: bool = True,
) -> None:
    if isinstance(max_depth, bool) or max_depth < 1:
        raise ValueError("Traversal depth must be a positive integer")
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _metadata = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    before_state = None
    if before_state_path is not None:
        before_root = resolve_project_path(before_state_path)
        before_proj, before_meta = load_fresh_project(before_root, allow_refresh=False)
        before_state = ComparisonState(
            project=before_proj,
            metadata=before_meta,
            repository_path=before_root,
        )

    rules = _load_project_structural_rules(root_path) or ()
    policy = _load_project_package_policy(root_path)

    report = run_post_change_verification(
        project,
        paths=paths,
        before_state=before_state,
        rules=rules,
        package_policy=policy,
        allow_refresh=allow_refresh,
        limit=limit,
        max_depth=max_depth,
        direction=direction,
    )

    if output_format == "json":
        _emit_json(report.to_dict())
        return

    _print_post_change_report(report)


def run_path(
    start: str,
    end: str,
    path: Path,
    direction: str = "both",
    relationship_type: str | None = None,
    max_depth: int = DEFAULT_PATH_MAX_DEPTH,
    max_expansions: int | None = DEFAULT_PATH_MAX_EXPANSIONS,
    output_format: str = "text",
    *,
    allow_refresh: bool = True,
) -> None:
    if not start or not start.strip():
        raise ValueError("Start target cannot be empty")
    if not end or not end.strip():
        raise ValueError("End target cannot be empty")
    if isinstance(max_depth, bool) or max_depth < 1:
        raise ValueError("Traversal depth must be a positive integer")
    if max_expansions is not None and (
        isinstance(max_expansions, bool) or max_expansions < 1
    ):
        raise ValueError("Expansion limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = (
        load_fresh_project(root_path)
        if allow_refresh
        else load_fresh_project(root_path, allow_refresh=False)
    )

    types_filter = {relationship_type} if relationship_type else None
    result = find_relationship_path(
        project,
        start.strip(),
        end.strip(),
        direction=direction,
        relationship_types=types_filter,
        max_depth=max_depth,
        max_expansions=max_expansions,
    )

    if output_format == "json":
        _emit_json(result.to_dict())
        return

    print(f"Repository: {root_path}")
    print(f"Query: path between '{start.strip()}' and '{end.strip()}'")
    print(f"Direction: {result.direction}")

    if not result.start_resolution or not result.start_resolution.is_resolved:
        msg = (
            result.start_resolution.message if result.start_resolution else "Unresolved"
        )
        print(f"Start endpoint resolution failed: {msg}")
        if result.start_resolution and result.start_resolution.is_ambiguous:
            print(f"Start candidates ({len(result.start_resolution.candidates)}):")
            for c in result.start_resolution.candidates:
                loc = f"{c.path}:{c.start_line}" if c.path else "unknown"
                print(f"  - [{c.kind}] {c.name} at {loc}")

    if not result.end_resolution or not result.end_resolution.is_resolved:
        msg = result.end_resolution.message if result.end_resolution else "Unresolved"
        print(f"End endpoint resolution failed: {msg}")
        if result.end_resolution and result.end_resolution.is_ambiguous:
            print(f"End candidates ({len(result.end_resolution.candidates)}):")
            for c in result.end_resolution.candidates:
                loc = f"{c.path}:{c.start_line}" if c.path else "unknown"
                print(f"  - [{c.kind}] {c.name} at {loc}")

    if (
        not result.start_resolution
        or not result.start_resolution.is_resolved
        or not result.end_resolution
        or not result.end_resolution.is_resolved
    ):
        return

    assert result.start_target is not None
    assert result.end_target is not None
    print(
        f"Start: [{result.start_target.kind}] {result.start_target.name} ({result.start_target.path})"
    )
    print(
        f"End: [{result.end_target.kind}] {result.end_target.name} ({result.end_target.path})"
    )
    print()

    if result.path_found:
        print(f"Status: Path found (length: {result.length} hop(s))")
        if result.length == 0:
            print("  Start and end endpoints are identical; zero-edge path.")
        else:
            print("Path steps:")
            for idx, step in enumerate(result.steps, 1):
                loc_info = (
                    f"line {step.source_line}"
                    if step.source_line is not None
                    else "no line info"
                )
                from_loc = f" ({step.from_path})" if step.from_path else ""
                to_loc = f" ({step.to_path})" if step.to_path else ""
                print(
                    f"  {idx}. [{step.traversal_direction}] {step.relationship_type} ({loc_info}): "
                    f"{step.from_name}[{step.from_kind}]{from_loc} -> "
                    f"{step.to_name}[{step.to_kind}]{to_loc}"
                )
    elif result.is_exhaustive:
        print("Status: No path exists (exhaustive search).")
        print(f"Message: {result.message}")
    else:
        print(f"Status: Inconclusive search ({result.status}).")
        print(f"Message: {result.message}")

    if result.limitations:
        print()
        print("Limitations:")
        for lim in result.limitations:
            print(f"  - {lim}")


def run_context(args: argparse.Namespace) -> None:
    from context_forge.application import build_context_service
    from context_forge.context.serialization import ContextPackageSerializer

    root_path = resolve_project_path(args.path)
    allow_refresh = not getattr(args, "no_refresh", False)
    project, _ = load_fresh_project(root_path, allow_refresh=allow_refresh)
    task = read_task(args.task)

    service = build_context_service()
    package = service.retrieve_context(project, task)
    serialized = ContextPackageSerializer().serialize(package)

    if args.output is None:
        print()
        print(serialized)
    else:
        try:
            args.output.write_text(
                serialized + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise ValueError(
                f"Could not write context output to {args.output}: {exc}"
            ) from exc


def _dispatch_command(args: argparse.Namespace) -> None:
    allow_refresh = not getattr(args, "no_refresh", False)

    post_change_handler = lambda: run_post_change(
        getattr(args, "paths", []),
        getattr(args, "project_path", Path(".")),
        before_state_path=getattr(args, "before_state_path", None),
        direction=getattr(args, "direction", "both"),
        max_depth=getattr(args, "max_depth", DEFAULT_IMPACT_MAX_DEPTH),
        limit=getattr(args, "limit", DEFAULT_REPORT_LIMIT),
        output_format=getattr(args, "format", "text"),
        allow_refresh=allow_refresh,
    )
    rules_handler = lambda: run_rules(
        getattr(args, "path", Path(".")),
        output_format=getattr(args, "format", "text"),
        limit=getattr(args, "limit", DEFAULT_REPORT_LIMIT),
        allow_refresh=allow_refresh,
    )
    unused_handler = lambda: run_unused(
        getattr(args, "path", Path(".")),
        output_format=getattr(args, "format", "text"),
        kind=getattr(args, "kind", "all"),
        limit=getattr(args, "limit", DEFAULT_UNUSED_LIMIT),
        allow_refresh=allow_refresh,
    )

    handlers = {
        "analyze": lambda: (
            run_analyze(args.path, args.format, command="analyze")
            if args.format == "json"
            else run_analyze(args.path, command="analyze")
        ),
        "refresh": lambda: (
            run_analyze(args.path, args.format, command="refresh")
            if args.format == "json"
            else run_analyze(args.path, command="refresh")
        ),
        "history": lambda: run_history(
            args.path,
            args.format,
            args.limit,
        ),
        "execution-history": lambda: run_history(
            args.path,
            args.format,
            args.limit,
        ),
        "status": lambda: run_status(args.path, args.format),
        "cache": lambda: run_cache(args.path, args.format),
        "inspect": lambda: (
            run_inspect(args.path, args.format)
            if args.format == "json"
            else run_inspect(args.path)
        ),
        "diagnostics": lambda: run_diagnostics(args.path, args.format),
        ("memory", "inspect"): lambda: (
            run_inspect(args.path, args.format)
            if args.format == "json"
            else run_inspect(args.path)
        ),
        ("memory", "search"): lambda: (
            run_memory_search(
                args.query,
                args.path,
                args.format,
                allow_refresh=allow_refresh,
            )
            if args.format == "json"
            else run_memory_search(
                args.query,
                args.path,
                allow_refresh=allow_refresh,
            )
        ),
        ("memory", "file"): lambda: (
            run_memory_file(
                args.file_path,
                args.path,
                args.format,
                allow_refresh=allow_refresh,
            )
            if args.format == "json"
            else run_memory_file(
                args.file_path,
                args.path,
                allow_refresh=allow_refresh,
            )
        ),
        ("memory", "symbol"): lambda: run_memory_symbol(
            args.symbol_name,
            args.path,
            args.format,
            getattr(args, "file_path", None),
            getattr(args, "symbol_type", None),
            getattr(args, "excerpt", False),
            getattr(args, "max_lines", DEFAULT_EXCERPT_MAX_LINES),
            allow_refresh=allow_refresh,
        ),
        ("memory", "references"): lambda: (
            run_memory_references(
                args.symbol_name,
                args.path,
                args.format,
                allow_refresh=allow_refresh,
            )
            if args.format == "json"
            else run_memory_references(
                args.symbol_name,
                args.path,
                allow_refresh=allow_refresh,
            )
        ),
        ("memory", "relationships"): lambda: (
            run_memory_relationships(
                args.entity_name,
                args.path,
                args.direction,
                args.relationship_type,
                args.format,
                allow_refresh=allow_refresh,
            )
            if args.format == "json"
            else run_memory_relationships(
                args.entity_name,
                args.path,
                args.direction,
                args.relationship_type,
                allow_refresh=allow_refresh,
            )
        ),
        ("memory", "dependencies"): lambda: run_memory_dependencies(
            args.file_path,
            args.path,
            args.direction,
            args.format,
            allow_refresh=allow_refresh,
        ),
        "context": lambda: run_context(args),
        "architecture": lambda: run_architecture(
            args.path,
            args.format,
            args.limit,
            allow_refresh=allow_refresh,
        ),
        "impact": lambda: run_impact(
            args.target,
            args.path,
            args.direction,
            args.relationship_type,
            args.limit,
            args.format,
            args.max_depth,
            allow_refresh=allow_refresh,
        ),
        "changeset": lambda: run_changeset(
            args.paths,
            getattr(args, "project_path", Path(".")),
            args.direction,
            args.relationship_type,
            args.limit,
            args.format,
            args.max_depth,
            checklist=getattr(args, "checklist", False),
            risk=getattr(args, "risk", False),
            allow_refresh=allow_refresh,
        ),
        "change-set": lambda: run_changeset(
            args.paths,
            getattr(args, "project_path", Path(".")),
            args.direction,
            args.relationship_type,
            args.limit,
            args.format,
            args.max_depth,
            checklist=getattr(args, "checklist", False),
            risk=getattr(args, "risk", False),
            allow_refresh=allow_refresh,
        ),
        "risk": lambda: run_risk(
            args.paths,
            getattr(args, "project_path", Path(".")),
            args.direction,
            args.relationship_type,
            args.limit,
            args.format,
            args.max_depth,
            allow_refresh=allow_refresh,
        ),
        "change-risk": lambda: run_risk(
            args.paths,
            getattr(args, "project_path", Path(".")),
            args.direction,
            args.relationship_type,
            args.limit,
            args.format,
            args.max_depth,
            allow_refresh=allow_refresh,
        ),
        "package-boundaries": lambda: run_package_boundaries(
            getattr(args, "path", Path(".")),
            args.format,
            args.limit,
            allow_refresh=allow_refresh,
        ),
        "package-boundary": lambda: run_package_boundaries(
            getattr(args, "path", Path(".")),
            args.format,
            args.limit,
            allow_refresh=allow_refresh,
        ),
        "boundaries": lambda: run_package_boundaries(
            getattr(args, "path", Path(".")),
            args.format,
            args.limit,
            allow_refresh=allow_refresh,
        ),
        "post-change": post_change_handler,
        "verify-change": post_change_handler,
        "post_change": post_change_handler,
        "verify": post_change_handler,
        "rules": rules_handler,
        "evaluate-rules": rules_handler,
        "check-rules": rules_handler,
        "unused": unused_handler,
        "unused-entities": unused_handler,
        "find-unused": unused_handler,
        "logo": lambda: print(CLI_LOGO),
        "path": lambda: run_path(
            args.start,
            args.end,
            getattr(args, "project_path", Path(".")),
            args.direction,
            args.relationship_type,
            args.max_depth,
            args.max_expansions,
            args.format,
            allow_refresh=allow_refresh,
        ),
        "query-path": lambda: run_path(
            args.start,
            args.end,
            getattr(args, "project_path", Path(".")),
            args.direction,
            args.relationship_type,
            args.max_depth,
            args.max_expansions,
            args.format,
            allow_refresh=allow_refresh,
        ),
        "health": lambda: run_health(
            args.path,
            args.format,
            args.limit,
        ),
        "preflight": lambda: run_preflight(
            args.path,
            args.format,
        ),
        "locate": lambda: run_locate(
            args.symbol_name,
            args.path,
            args.format,
            getattr(args, "file_path", None),
            getattr(args, "symbol_type", None),
            getattr(args, "excerpt", False),
            getattr(args, "max_lines", DEFAULT_EXCERPT_MAX_LINES),
            allow_refresh=allow_refresh,
        ),
        "inspect-change": lambda: run_inspect_change(
            args.target,
            args.path,
            args.format,
            getattr(args, "file_path", None),
            getattr(args, "symbol_type", None),
            getattr(args, "direction", "both"),
            getattr(args, "max_depth", DEFAULT_IMPACT_MAX_DEPTH),
            getattr(args, "max_lines", DEFAULT_EXCERPT_MAX_LINES),
            getattr(args, "no_git", False),
        ),
        "pre-change": lambda: run_inspect_change(
            args.target,
            args.path,
            args.format,
            getattr(args, "file_path", None),
            getattr(args, "symbol_type", None),
            getattr(args, "direction", "both"),
            getattr(args, "max_depth", DEFAULT_IMPACT_MAX_DEPTH),
            getattr(args, "max_lines", DEFAULT_EXCERPT_MAX_LINES),
            getattr(args, "no_git", False),
        ),
    }

    if args.command == "memory":
        command_key = (args.command, args.memory_command)
    else:
        command_key = args.command

    handler = handlers.get(command_key)

    if handler is None:
        raise ValueError(f"Unsupported command: {args.command}")

    handler()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if getattr(args, "logo", False):
        if args.command is not None:
            create_parser().error(
                f"argument --logo: not allowed with command '{args.command}'"
            )
        print(CLI_LOGO)
        return

    if args.command == "logo":
        print(CLI_LOGO)
        return

    if args.command is None:
        create_parser().print_help()
        return

    try:
        _dispatch_command(args)
    except KeyboardInterrupt:
        print(file=sys.stderr)
        raise SystemExit(130) from None
    except (
        ContextForgeError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        TypeError,
        ValueError,
    ) as exc:
        output_format = getattr(args, "format", "text")
        if output_format == "json":
            if isinstance(exc, ContextForgeError):
                outcome = exc.outcome
            else:
                diag = DiagnosticItem.error(
                    str(exc),
                    code="OPERATIONAL_ERROR",
                )
                outcome = OperationOutcome.failed(
                    str(exc),
                    diagnostics=(diag,),
                )
            _emit_json(outcome.to_dict(), file=sys.stderr)
        else:
            print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
