from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

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
from context_forge.query.project import ProjectQuery
from context_forge.reporting import (
    ContextForgeError,
    DiagnosticItem,
    IncompleteAnalysisError,
    IndeterminateFreshnessError,
    MissingAnalysisError,
    OperationOutcome,
    StaleAnalysisError,
)
from context_forge.storage.cache import (
    RepositoryCacheMetadata,
    RepositoryIdentity,
)
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def _add_output_format_argument(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )


def _emit_json(payload: dict, file: Any = None) -> None:
    target = file if file is not None else sys.stdout
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), file=target)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-forge",
        description=(
            "Deterministic repository intelligence and memory for software projects."
        ),
    )

    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a repository and persist repository intelligence.",
    )
    analyze_parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    _add_output_format_argument(analyze_parser)

    refresh_parser = subparsers.add_parser(
        "refresh", help="Refresh repository analysis and cached intelligence."
    )
    refresh_parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    _add_output_format_argument(refresh_parser)

    context_parser = subparsers.add_parser(
        "context",
        help="Retrieve deterministic context package for a development task.",
    )
    context_parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    context_parser.add_argument(
        "--task",
        default=None,
        help="Development task description.",
    )
    context_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write context package JSON to a file.",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Show repository and analysis status.",
    )
    status_parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    _add_output_format_argument(status_parser)

    cache_parser = subparsers.add_parser(
        "cache",
        help="Show repository cache state and freshness.",
    )
    cache_parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    _add_output_format_argument(cache_parser)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect persisted repository intelligence.",
    )
    inspect_parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    _add_output_format_argument(inspect_parser)

    memory_parser = subparsers.add_parser(
        "memory",
        help="Inspect and retrieve persistent repository memory.",
    )
    memory_subparsers = memory_parser.add_subparsers(
        dest="memory_command",
        required=True,
    )

    memory_inspect_parser = memory_subparsers.add_parser(
        "inspect",
        help="Inspect persisted repository intelligence.",
    )
    memory_inspect_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )
    _add_output_format_argument(memory_inspect_parser)
    memory_search_parser = memory_subparsers.add_parser(
        "search",
        help="Search persisted repository memory.",
    )
    memory_search_parser.add_argument(
        "query",
        help="Search for a file, directory, or symbol.",
    )
    memory_search_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )
    _add_output_format_argument(memory_search_parser)
    memory_file_parser = memory_subparsers.add_parser(
        "file",
        help="Retrieve a file and its defined symbols.",
    )
    memory_file_parser.add_argument(
        "file_path",
        help="Repository-relative path of the file to retrieve.",
    )
    memory_file_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    _add_output_format_argument(memory_file_parser)

    memory_symbol_parser = memory_subparsers.add_parser(
        "symbol",
        help="Retrieve symbol definitions by exact name.",
    )
    memory_symbol_parser.add_argument(
        "symbol_name",
        help="Exact name of the symbol to retrieve.",
    )
    memory_symbol_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    memory_symbol_parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="Filter symbol by file path.",
    )
    memory_symbol_parser.add_argument(
        "--type",
        dest="symbol_type",
        default=None,
        help="Filter symbol by type/kind (e.g., class, function, method).",
    )
    memory_symbol_parser.add_argument(
        "--excerpt",
        action="store_true",
        default=False,
        help="Include bounded source evidence excerpt from current source file.",
    )
    memory_symbol_parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_EXCERPT_MAX_LINES,
        help="Maximum lines for source excerpt (default: 50).",
    )
    _add_output_format_argument(memory_symbol_parser)

    memory_references_parser = memory_subparsers.add_parser(
        "references",
        help="Show indexed references to a symbol.",
    )
    memory_references_parser.add_argument(
        "symbol_name",
        help="Exact symbol name or qualified name.",
    )
    memory_references_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    _add_output_format_argument(memory_references_parser)

    memory_relationships_parser = memory_subparsers.add_parser(
        "relationships",
        help="Inspect indexed relationships for a file or symbol.",
    )
    memory_relationships_parser.add_argument(
        "entity_name",
        help="Repository-relative file path, symbol name, or qualified name.",
    )
    memory_relationships_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    memory_relationships_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Relationship direction (default: both).",
    )
    memory_relationships_parser.add_argument(
        "--type",
        dest="relationship_type",
        choices=("defines", "contains", "imports", "references", "inherits"),
        default=None,
        help=(
            "Filter by a currently supported relationship type. "
            "'calls' and 'depends_on' are not currently generated."
        ),
    )
    _add_output_format_argument(memory_relationships_parser)

    memory_dependencies_parser = memory_subparsers.add_parser(
        "dependencies",
        help="Show direct dependencies and dependents for a file.",
    )
    memory_dependencies_parser.add_argument(
        "file_path",
        help="Repository-relative path of the file to inspect.",
    )
    memory_dependencies_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    memory_dependencies_parser.add_argument(
        "--direction",
        choices=("both", "dependencies", "dependents"),
        default="both",
        help="Which direct dependency relationships to show (default: both).",
    )
    _add_output_format_argument(memory_dependencies_parser)

    diagnostics_parser = subparsers.add_parser(
        "diagnostics",
        help="Show persisted repository analysis diagnostics.",
    )
    diagnostics_parser.add_argument("path", nargs="?", type=Path, default=Path("."))
    _add_output_format_argument(diagnostics_parser)

    architecture_parser = subparsers.add_parser(
        "architecture",
        help="Report repository architecture and structural findings.",
    )
    architecture_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    architecture_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_REPORT_LIMIT,
        help=(
            "Maximum number of items displayed per report section "
            f"(default: {DEFAULT_REPORT_LIMIT})."
        ),
    )
    _add_output_format_argument(architecture_parser)

    impact_parser = subparsers.add_parser(
        "impact",
        help="Analyze direct and transitive change impact for a file or symbol target.",
    )
    impact_parser.add_argument(
        "target",
        help="Repository-relative file path, symbol name, or qualified name.",
    )
    impact_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    impact_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Relationship direction to analyze (default: both).",
    )
    impact_parser.add_argument(
        "--type",
        dest="relationship_type",
        choices=("imports", "references", "inherits", "calls", "depends_on"),
        default=None,
        help="Filter by relationship type.",
    )
    impact_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_IMPACT_MAX_DEPTH,
        help=f"Maximum traversal depth for impact analysis (default: {DEFAULT_IMPACT_MAX_DEPTH}).",
    )
    impact_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_IMPACT_LIMIT,
        help=f"Maximum number of items displayed (default: {DEFAULT_IMPACT_LIMIT}).",
    )
    _add_output_format_argument(impact_parser)

    health_parser = subparsers.add_parser(
        "health",
        help="Report repository health, inventory metrics, and structural findings.",
    )
    health_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
        help="Repository root path.",
    )
    health_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_HEALTH_LIMIT,
        help=(
            "Maximum number of findings displayed per category "
            f"(default: {DEFAULT_HEALTH_LIMIT})."
        ),
    )
    _add_output_format_argument(health_parser)

    preflight_parser = subparsers.add_parser(
        "preflight",
        help="Perform read-only repository preflight readiness and configuration audit.",
    )
    preflight_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repository root path (default: current directory).",
    )
    _add_output_format_argument(preflight_parser)

    locate_parser = subparsers.add_parser(
        "locate",
        help="Locate repository symbols precisely with optional source evidence.",
    )
    locate_parser.add_argument(
        "symbol_name",
        help="Symbol name or qualified name to locate.",
    )
    locate_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repository root path (default: current directory).",
    )
    locate_parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="Filter symbol by file path.",
    )
    locate_parser.add_argument(
        "--type",
        dest="symbol_type",
        default=None,
        help="Filter symbol by type/kind (e.g., class, function, method).",
    )
    locate_parser.add_argument(
        "--excerpt",
        action="store_true",
        default=False,
        help="Include bounded source evidence excerpt from current source file.",
    )
    locate_parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_EXCERPT_MAX_LINES,
        help="Maximum lines for source excerpt (default: 50).",
    )
    _add_output_format_argument(locate_parser)

    inspect_change_parser = subparsers.add_parser(
        "inspect-change",
        aliases=["pre-change"],
        help="Perform read-only pre-change inspection composing preflight, target resolution, freshness, evidence, and Git context.",
    )
    inspect_change_parser.add_argument(
        "target",
        help="Target symbol name or qualified name to inspect.",
    )
    inspect_change_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        type=Path,
        help="Repository root path (default: current directory).",
    )
    inspect_change_parser.add_argument(
        "--file",
        dest="file_path",
        default=None,
        help="Filter symbol by file path.",
    )
    inspect_change_parser.add_argument(
        "--type",
        dest="symbol_type",
        default=None,
        help="Filter symbol by type/kind (e.g., class, function, method).",
    )
    inspect_change_parser.add_argument(
        "--direction",
        choices=("both", "incoming", "outgoing"),
        default="both",
        help="Traversal direction for structural impact (default: both).",
    )
    inspect_change_parser.add_argument(
        "--depth",
        "--max-depth",
        dest="max_depth",
        type=int,
        default=DEFAULT_IMPACT_MAX_DEPTH,
        help=f"Maximum traversal depth for structural impact (default: {DEFAULT_IMPACT_MAX_DEPTH}).",
    )
    inspect_change_parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_EXCERPT_MAX_LINES,
        help=f"Maximum lines for source excerpt (default: {DEFAULT_EXCERPT_MAX_LINES}).",
    )
    inspect_change_parser.add_argument(
        "--no-git",
        action="store_true",
        default=False,
        help="Disable Git context inspection.",
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
        "inspect",
        "memory",
        "diagnostics",
        "architecture",
        "impact",
        "health",
        "preflight",
        "locate",
        "inspect-change",
        "pre-change",
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
    database_path = root_path / ".context_forge.db"

    return ProjectAnalyzer(
        root_path=root_path,
        database_path=database_path,
    ).analyze()


def load_project_analysis(root_path: Path):
    database_path = root_path / ".context_forge.db"
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


def load_fresh_project(root_path: Path):
    repository, repository_key, project, metadata = load_project_analysis(root_path)

    fingerprints = current_fingerprints(project)

    freshness = repository.check_cache_freshness(
        repository_key,
        fingerprints,
    )

    if not freshness.is_fresh:
        raise StaleAnalysisError(
            f"Repository analysis is stale; run "
            f"'context-forge analyze {root_path}' first",
            path=str(root_path),
        )
    return project, metadata


def load_guarded_project(
    root_path: Path,
    *,
    allow_refresh: bool = False,
    database_path: Path | None = None,
) -> tuple[Project, RepositoryCacheMetadata, WorkflowFreshness]:
    guard = WorkflowFreshnessGuard(root_path, database_path=database_path)
    freshness = guard.guard(allow_refresh=allow_refresh)

    if (
        freshness.is_current
        and freshness.project is not None
        and freshness.metadata is not None
    ):
        return freshness.project, freshness.metadata, freshness

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
            f"No persisted analysis found; run 'context-forge analyze {root_path}' first",
            path=str(root_path),
        )
    raise IndeterminateFreshnessError(
        f"Repository analysis freshness is indeterminate ({freshness.reason}); reanalysis is required",
        path=str(root_path),
    )


load_generation_project = load_fresh_project


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


def run_analyze(path: Path, output_format: str = "text") -> None:
    from context_forge.operational_logging import (
        log_analysis_completed,
        log_analysis_failed,
        log_analysis_started,
    )

    root_path = resolve_project_path(path)
    started_at = time.monotonic()
    log_analysis_started(project_path=root_path)

    try:
        project = analyze_project(root_path)
        log_analysis_completed(
            project_path=root_path,
            duration_seconds=time.monotonic() - started_at,
            files_count=len(project.files),
            symbols_count=len(project.symbols),
        )
        print_analysis_summary(project, output_format)
    except Exception as exc:
        log_analysis_failed(
            project_path=root_path,
            duration_seconds=time.monotonic() - started_at,
            error=exc,
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
) -> None:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Search query cannot be empty")

    root = resolve_project_path(path)
    project, _ = load_fresh_project(root)
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
) -> None:
    normalized_file_path = file_path.strip()
    if not normalized_file_path:
        raise ValueError("File path cannot be empty")

    root = resolve_project_path(path)
    project, _ = load_fresh_project(root)
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
) -> None:
    normalized_name = symbol_name.strip()
    if not normalized_name:
        raise ValueError("Symbol name cannot be empty")

    root = resolve_project_path(path)
    project, _ = load_fresh_project(root)
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
) -> None:
    root = resolve_project_path(path)
    project, _ = load_fresh_project(root)

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
) -> None:
    normalized_name = symbol_name.strip()
    if not normalized_name:
        raise ValueError("Symbol name cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)
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
) -> None:
    normalized_name = entity_name.strip()
    if not normalized_name:
        raise ValueError("Entity name cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)
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
) -> None:
    normalized_path = file_path.strip()
    if not normalized_path:
        raise ValueError("File path cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)
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
) -> None:
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)

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
) -> None:
    if not target or not target.strip():
        raise ValueError("Target cannot be empty")
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")
    if isinstance(max_depth, bool) or max_depth < 1:
        raise ValueError("Traversal depth must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)

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


def run_context(args: argparse.Namespace) -> None:
    from context_forge.application import build_context_service
    from context_forge.context.serialization import ContextPackageSerializer

    root_path = resolve_project_path(args.path)
    project, _ = load_fresh_project(root_path)
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
    handlers = {
        "analyze": lambda: run_analyze(args.path, args.format),
        "refresh": lambda: (
            run_analyze(args.path, args.format)
            if args.format == "json"
            else run_analyze(args.path)
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
            run_memory_search(args.query, args.path, args.format)
            if args.format == "json"
            else run_memory_search(args.query, args.path)
        ),
        ("memory", "file"): lambda: (
            run_memory_file(args.file_path, args.path, args.format)
            if args.format == "json"
            else run_memory_file(args.file_path, args.path)
        ),
        ("memory", "symbol"): lambda: run_memory_symbol(
            args.symbol_name,
            args.path,
            args.format,
            getattr(args, "file_path", None),
            getattr(args, "symbol_type", None),
            getattr(args, "excerpt", False),
            getattr(args, "max_lines", DEFAULT_EXCERPT_MAX_LINES),
        ),
        ("memory", "references"): lambda: (
            run_memory_references(
                args.symbol_name,
                args.path,
                args.format,
            )
            if args.format == "json"
            else run_memory_references(
                args.symbol_name,
                args.path,
            )
        ),
        ("memory", "relationships"): lambda: (
            run_memory_relationships(
                args.entity_name,
                args.path,
                args.direction,
                args.relationship_type,
                args.format,
            )
            if args.format == "json"
            else run_memory_relationships(
                args.entity_name,
                args.path,
                args.direction,
                args.relationship_type,
            )
        ),
        ("memory", "dependencies"): lambda: run_memory_dependencies(
            args.file_path,
            args.path,
            args.direction,
            args.format,
        ),
        "context": lambda: run_context(args),
        "architecture": lambda: run_architecture(
            args.path,
            args.format,
            args.limit,
        ),
        "impact": lambda: run_impact(
            args.target,
            args.path,
            args.direction,
            args.relationship_type,
            args.limit,
            args.format,
            args.max_depth,
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


def main() -> None:
    args = parse_args()

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
