import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from context_forge.pipeline.analyzer import (
    ProjectAnalyzer,
    current_fingerprints,
)
from context_forge.query.architecture_report import (
    DEFAULT_REPORT_LIMIT,
    build_architecture_report,
)
from context_forge.query.impact import (
    DEFAULT_IMPACT_LIMIT,
    find_direct_impact,
)
from context_forge.query.project import ProjectQuery
from context_forge.storage.cache import RepositoryIdentity
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


def _emit_json(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


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
        help="Analyze direct change impact for a file or symbol target.",
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
        "--limit",
        type=int,
        default=DEFAULT_IMPACT_LIMIT,
        help=f"Maximum number of items displayed (default: {DEFAULT_IMPACT_LIMIT}).",
    )
    _add_output_format_argument(impact_parser)

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]

    # Default a bare project path to `status`
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
        "-h",
        "--help",
    }:
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
    repository = ProjectRepository(Database(database_path))
    repository_key = RepositoryIdentity(root_path).key

    try:
        loaded = repository.load_analysis(repository_key)
    except sqlite3.OperationalError as exc:
        if "no such table: repository_cache" not in str(exc):
            raise

        raise ValueError(
            "No persisted analysis found; run 'context-forge analyze' first"
        ) from None

    if loaded is None:
        raise ValueError(
            "No persisted analysis found; run 'context-forge analyze' first"
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
        raise ValueError(
            f"Repository analysis is stale; run "
            f"'context-forge analyze {root_path}' first"
        )
    return project, metadata


# Backward compatibility alias for any existing callers
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
        "analyzer_version": metadata.analyzer_version,
        "cache_schema_version": metadata.cache_schema_version,
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
    print(f"Cache schema version: {metadata.cache_schema_version}")
    print(f"Analyzer version: {metadata.analyzer_version}")


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
        "analyzer_version": metadata.analyzer_version,
        "cache_schema_version": metadata.cache_schema_version,
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
    print(f"Cache schema version: {metadata.cache_schema_version}")
    print(f"Analyzer version: {metadata.analyzer_version}")
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
                        "path": item.path,
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

    symbols = sorted(
        symbols,
        key=lambda symbol: (
            files_by_id[symbol.file_id].path if symbol.file_id in files_by_id else "",
            symbol.start_line,
            symbol.name,
        ),
    )

    if output_format == "json":
        _emit_json(
            {
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
        )
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

    # An exact repository-relative file path takes precedence.
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
    """Print a deterministic architecture report for a fresh analysis."""
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


def run_impact(
    target: str,
    path: Path,
    direction: str = "both",
    relationship_type: str | None = None,
    limit: int = DEFAULT_IMPACT_LIMIT,
    output_format: str = "text",
) -> None:
    if not target or not target.strip():
        raise ValueError("Target cannot be empty")
    if isinstance(limit, bool) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)

    types_filter = {relationship_type} if relationship_type else None
    result = find_direct_impact(
        project,
        target.strip(),
        direction=direction,
        relationship_types=types_filter,
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
    print(f"Relationships: {result.total}")
    print()

    if not result.items:
        print("Direct impact:")
        print("  None detected.")
    else:
        print("Direct impact:")
        for item in result.items:
            loc = f" ({item.related_path})" if item.related_path else ""
            print(
                f"  [{item.direction}] {item.relationship_type}: "
                f"{item.related_name} [{item.related_kind}]{loc}"
            )

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
        ("memory", "symbol"): lambda: (
            run_memory_symbol(args.symbol_name, args.path, args.format)
            if args.format == "json"
            else run_memory_symbol(args.symbol_name, args.path)
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
        OSError,
        RuntimeError,
        sqlite3.Error,
        TypeError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
