"""Deterministic, read-only repository preflight readiness and configuration audit."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

from context_forge.config.audit import audit_configuration
from context_forge.config.defaults import DEFAULTS
from context_forge.config.global_config import global_config_path
from context_forge.parser.detector import LanguageDetector
from context_forge.parser.language import Language
from context_forge.parser.python import PythonParser
from context_forge.parser.registry import ParserRegistry
from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)
from context_forge.scanner.repository import RepositoryScanner


def _default_parser_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(PythonParser())
    return registry


def is_git_repository(root_path: Path) -> bool:
    """Return True if root_path contains valid Git metadata (.git dir or worktree file)."""
    git_entry = root_path / ".git"
    if git_entry.is_dir():
        return True
    if git_entry.is_file():
        try:
            content = git_entry.read_text(encoding="utf-8", errors="replace")
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("gitdir:"):
                    target = line[len("gitdir:") :].strip()
                    if not target:
                        return False
                    target_path = Path(target)
                    if not target_path.is_absolute():
                        target_path = (root_path / target_path).resolve()
                    return target_path.exists()
                return False
        except OSError:
            return False
    return False


def build_preflight_report(
    repository_path: str | Path = ".",
    *,
    global_config_file: Path | None = None,
    parser_registry: ParserRegistry | None = None,
) -> dict[str, Any]:
    """Perform a strictly read-only preflight readiness and configuration audit.

    Evaluates repository-root accessibility, configuration layers/precedence,
    discovered file inventory, detected vs supported languages, and analysis
    readiness without performing analysis, creating databases, or mutating state.
    """
    raw_path = Path(repository_path).expanduser()
    all_diagnostics: list[DiagnosticItem] = []
    limitations: list[str] = []

    # 1. Repository-root validation
    if not raw_path.exists():
        msg = f"Repository path does not exist: {raw_path}"
        diag = DiagnosticItem.blocker(
            msg,
            code="REPOSITORY_NOT_FOUND",
            path=str(raw_path),
            source="filesystem",
        )
        all_diagnostics.append(diag)
        outcome = OperationOutcome.blocked(
            msg,
            diagnostics=tuple(all_diagnostics),
            limitations=(msg,),
        )
        return {
            "schema_version": 1,
            "repository": str(raw_path).replace("\\", "/"),
            "readiness": "blocked",
            "repository_status": {
                "exists": False,
                "is_directory": False,
                "is_accessible": False,
                "is_git_repository": False,
            },
            "configuration": {
                "status": "unavailable",
                "sources": {
                    "project_config_path": None,
                    "project_config_present": False,
                    "global_config_path": (
                        str(global_config_file).replace("\\", "/")
                        if global_config_file is not None
                        else str(global_config_path()).replace("\\", "/")
                    ),
                    "global_config_present": False,
                },
                "resolved": None,
                "precedence": {},
                "diagnostics": [],
            },
            "inventory": {
                "directories": 0,
                "files": 0,
                "source_files": 0,
            },
            "languages": [],
            "analysis_readiness": {
                "database_path": DEFAULTS.database_path,
                "has_persisted_analysis": False,
            },
            "outcome": outcome.to_dict(),
            "limitations": [msg],
        }

    if not raw_path.is_dir():
        msg = f"Repository path is not a directory: {raw_path}"
        diag = DiagnosticItem.blocker(
            msg,
            code="REPOSITORY_NOT_A_DIRECTORY",
            path=str(raw_path),
            source="filesystem",
        )
        all_diagnostics.append(diag)
        outcome = OperationOutcome.blocked(
            msg,
            diagnostics=tuple(all_diagnostics),
            limitations=(msg,),
        )
        return {
            "schema_version": 1,
            "repository": str(raw_path).replace("\\", "/"),
            "readiness": "blocked",
            "repository_status": {
                "exists": True,
                "is_directory": False,
                "is_accessible": True,
                "is_git_repository": False,
            },
            "configuration": {
                "status": "unavailable",
                "sources": {
                    "project_config_path": None,
                    "project_config_present": False,
                    "global_config_path": (
                        str(global_config_file).replace("\\", "/")
                        if global_config_file is not None
                        else str(global_config_path()).replace("\\", "/")
                    ),
                    "global_config_present": False,
                },
                "resolved": None,
                "precedence": {},
                "diagnostics": [],
            },
            "inventory": {
                "directories": 0,
                "files": 0,
                "source_files": 0,
            },
            "languages": [],
            "analysis_readiness": {
                "database_path": DEFAULTS.database_path,
                "has_persisted_analysis": False,
            },
            "outcome": outcome.to_dict(),
            "limitations": [msg],
        }

    resolved_path = raw_path.resolve()

    # Check accessibility (read & execute)
    try:
        os.listdir(resolved_path)
    except (OSError, PermissionError) as exc:
        msg = f"Repository path is inaccessible: {exc}"
        diag = DiagnosticItem.blocker(
            msg,
            code="REPOSITORY_INACCESSIBLE",
            path=resolved_path.as_posix(),
            source="filesystem",
        )
        all_diagnostics.append(diag)
        outcome = OperationOutcome.blocked(
            msg,
            diagnostics=tuple(all_diagnostics),
            limitations=(msg,),
        )
        return {
            "schema_version": 1,
            "repository": resolved_path.as_posix(),
            "readiness": "blocked",
            "repository_status": {
                "exists": True,
                "is_directory": True,
                "is_accessible": False,
                "is_git_repository": False,
            },
            "configuration": {
                "status": "unavailable",
                "sources": {
                    "project_config_path": None,
                    "project_config_present": False,
                    "global_config_path": (
                        str(global_config_file).replace("\\", "/")
                        if global_config_file is not None
                        else str(global_config_path()).replace("\\", "/")
                    ),
                    "global_config_present": False,
                },
                "resolved": None,
                "precedence": {},
                "diagnostics": [],
            },
            "inventory": {
                "directories": 0,
                "files": 0,
                "source_files": 0,
            },
            "languages": [],
            "analysis_readiness": {
                "database_path": DEFAULTS.database_path,
                "has_persisted_analysis": False,
            },
            "outcome": outcome.to_dict(),
            "limitations": [msg],
        }

    # 2. Git status assessment (read-only fact)
    is_git = is_git_repository(resolved_path)
    if not is_git:
        limitations.append(
            "Directory is not a Git repository; Git-specific inspection features will be unavailable."
        )

    # 3. Configuration audit (precedence: project > global > default)
    config_audit = audit_configuration(
        resolved_path,
        global_config_path_override=global_config_file,
    )
    all_diagnostics.extend(config_audit.diagnostics)

    # 4. Read-only discovery and scanner inventory
    try:
        scanner = RepositoryScanner(resolved_path)
        scanned_project = scanner.scan()
    except OSError as exc:
        msg = f"Failed to scan repository: {exc}"
        diag = DiagnosticItem.blocker(
            msg,
            code="SCAN_ERROR",
            path=resolved_path.as_posix(),
            source="scanner",
        )
        all_diagnostics.append(diag)
        outcome = OperationOutcome.blocked(
            msg,
            diagnostics=tuple(all_diagnostics),
            limitations=tuple(limitations),
        )
        return {
            "schema_version": 1,
            "repository": resolved_path.as_posix(),
            "readiness": "blocked",
            "repository_status": {
                "exists": True,
                "is_directory": True,
                "is_accessible": True,
                "is_git_repository": is_git,
            },
            "configuration": config_audit.to_dict(),
            "inventory": {
                "directories": 0,
                "files": 0,
                "source_files": 0,
            },
            "languages": [],
            "analysis_readiness": {
                "database_path": (
                    config_audit.resolved.database_path
                    if config_audit.resolved is not None
                    else DEFAULTS.database_path
                ),
                "has_persisted_analysis": False,
            },
            "outcome": outcome.to_dict(),
            "limitations": list(limitations),
        }

    directory_count = len(scanned_project.directories)
    file_count = len(scanned_project.files)

    # 5. Language detection and parser capabilities
    detector = LanguageDetector()
    registry = (
        parser_registry if parser_registry is not None else _default_parser_registry()
    )

    lang_counts: Counter[Language] = Counter()
    for file_model in scanned_project.files:
        lang = detector.detect(resolved_path / file_model.path)
        lang_counts[lang] += 1

    languages_payload: list[dict[str, Any]] = []
    source_file_count = 0
    supported_source_count = 0

    for lang in sorted(lang_counts.keys(), key=lambda l: l.value):
        count = lang_counts[lang]
        if lang == Language.UNKNOWN:
            continue

        is_supported = registry.has(lang)
        source_file_count += count
        if is_supported:
            supported_source_count += count
        else:
            all_diagnostics.append(
                DiagnosticItem.warning(
                    f"Detected {count} {lang.value} source file(s), but no {lang.value} parser is registered",
                    code="UNSUPPORTED_LANGUAGE",
                    source="parser",
                    details={"language": lang.value, "file_count": count},
                )
            )
            limitations.append(
                f"Language '{lang.value}' is not supported for AST parsing; {count} file(s) will not be indexed."
            )

        languages_payload.append(
            {
                "name": lang.value,
                "supported": is_supported,
                "file_count": count,
            }
        )

    if file_count == 0:
        all_diagnostics.append(
            DiagnosticItem.info(
                "Repository contains no files",
                code="EMPTY_REPOSITORY",
                source="scanner",
            )
        )
        limitations.append("Repository contains no files.")
    elif source_file_count > 0 and supported_source_count == 0:
        all_diagnostics.append(
            DiagnosticItem.warning(
                "No supported source files found in repository",
                code="NO_SUPPORTED_SOURCES",
                source="parser",
            )
        )
        limitations.append("No source files matching supported languages were found.")

    # 6. Scope and exclusions note
    limitations.append(
        "Standard directories (.git, .venv, __pycache__, etc.) are excluded from inspection."
    )

    # 7. Analysis readiness (strictly read-only existence check)
    db_rel = (
        config_audit.resolved.database_path
        if config_audit.resolved is not None
        else DEFAULTS.database_path
    )
    db_file = resolved_path / db_rel
    has_persisted = db_file.is_file()
    if not has_persisted:
        limitations.append(
            f"No persisted analysis database found at '{db_rel}'; run 'context-forge analyze' before running queries."
        )

    # 8. Readiness determination
    has_blocker = any(d.severity == DiagnosticSeverity.BLOCKER for d in all_diagnostics)
    has_error = any(d.severity == DiagnosticSeverity.ERROR for d in all_diagnostics)
    has_warning = any(d.severity == DiagnosticSeverity.WARNING for d in all_diagnostics)

    if has_blocker:
        readiness = "blocked"
        status = OperationStatus.BLOCKED
        blocker_msg = next(
            d.message
            for d in all_diagnostics
            if d.severity == DiagnosticSeverity.BLOCKER
        )
        message = f"Repository preflight blocked: {blocker_msg}"
    elif has_error:
        readiness = "blocked"
        status = OperationStatus.FAILED
        err_msg = next(
            d.message for d in all_diagnostics if d.severity == DiagnosticSeverity.ERROR
        )
        message = f"Repository preflight failed: {err_msg}"
    elif has_warning or len(limitations) > 0:
        readiness = "ready_with_limitations"
        status = OperationStatus.SUCCESS
        message = "Repository is ready for inspection with limitations"
    else:
        readiness = "ready"
        status = OperationStatus.SUCCESS
        message = "Repository is ready for inspection"

    outcome = OperationOutcome(
        status=status,
        message=message,
        diagnostics=tuple(all_diagnostics),
        limitations=tuple(limitations),
    )

    return {
        "schema_version": 1,
        "repository": resolved_path.as_posix(),
        "readiness": readiness,
        "repository_status": {
            "exists": True,
            "is_directory": True,
            "is_accessible": True,
            "is_git_repository": is_git,
        },
        "configuration": config_audit.to_dict(),
        "inventory": {
            "directories": directory_count,
            "files": file_count,
            "source_files": source_file_count,
        },
        "languages": languages_payload,
        "analysis_readiness": {
            "database_path": db_rel,
            "has_persisted_analysis": has_persisted,
        },
        "outcome": outcome.to_dict(),
        "limitations": limitations,
    }


def format_preflight_summary(report: dict[str, Any]) -> list[str]:
    """Format a preflight report into clear, human-readable text lines."""
    lines: list[str] = []
    lines.append(f"Repository: {report['repository']}")
    readiness_label = report["readiness"].replace("_", " ").upper()
    lines.append(f"Readiness: {readiness_label}")
    lines.append("")

    lines.append("Repository status:")
    status = report["repository_status"]
    lines.append(f"  Exists: {status['exists']}")
    lines.append(f"  Directory: {status['is_directory']}")
    lines.append(f"  Accessible: {status['is_accessible']}")
    lines.append(f"  Git repository: {status['is_git_repository']}")
    lines.append("")

    lines.append("Configuration:")
    cfg = report["configuration"]
    lines.append(f"  Status: {cfg['status']}")
    resolved = cfg.get("resolved")
    precedence = cfg.get("precedence") or {}
    if resolved is not None:
        if "database_path" in resolved:
            lines.append(
                f"  Database path: {resolved['database_path']} "
                f"({precedence.get('database_path', 'default')})"
            )
        if "max_context_units" in resolved:
            lines.append(
                f"  Max context units: {resolved['max_context_units']} "
                f"({precedence.get('max_context_units', 'default')})"
            )
    sources = cfg.get("sources", {})
    p_path = sources.get("project_config_path") or "none"
    p_present = sources.get("project_config_present", False)
    lines.append(f"  Project config: {p_path} (present: {p_present})")
    g_path = sources.get("global_config_path") or "none"
    g_present = sources.get("global_config_present", False)
    lines.append(f"  Global config: {g_path} (present: {g_present})")
    lines.append("")

    lines.append("Inventory:")
    inv = report["inventory"]
    lines.append(f"  Directories: {inv['directories']}")
    lines.append(f"  Files: {inv['files']}")
    lines.append(f"  Source files: {inv['source_files']}")
    lines.append("")

    if report.get("languages"):
        lines.append("Languages:")
        for lang in report["languages"]:
            supp = "supported" if lang["supported"] else "unsupported"
            lines.append(
                f"  - {lang['name'].capitalize()}: {lang['file_count']} file(s) ({supp})"
            )
        lines.append("")

    lines.append("Analysis readiness:")
    ar = report["analysis_readiness"]
    has_db = "found" if ar["has_persisted_analysis"] else "missing"
    lines.append(f"  Persisted database: {ar['database_path']} ({has_db})")

    outcome = report.get("outcome", {})
    diagnostics = outcome.get("diagnostics", [])
    blockers = [d for d in diagnostics if d.get("severity") == "blocker"]
    warnings = [d for d in diagnostics if d.get("severity") == "warning"]

    if blockers:
        lines.append("")
        lines.append("Blockers:")
        for b in blockers:
            code_str = f" ({b['code']})" if b.get("code") else ""
            lines.append(f"  [BLOCKER]{code_str} {b['message']}")

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            code_str = f" ({w['code']})" if w.get("code") else ""
            lines.append(f"  [WARNING]{code_str} {w['message']}")

    if report.get("limitations"):
        lines.append("")
        lines.append("Limitations:")
        for lim in report["limitations"]:
            lines.append(f"  - {lim}")

    return lines
