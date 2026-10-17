import argparse
import sqlite3
import sys
import time
from pathlib import Path

from context_forge.pipeline.analyzer import (
    ProjectAnalyzer,
    current_fingerprints,
)
from context_forge.query.project import ProjectQuery
from context_forge.storage.cache import RepositoryIdentity
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


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

    refresh_parser = subparsers.add_parser(
        "refresh", help="Refresh repository analysis and cached intelligence."
    )
    refresh_parser.add_argument("path", nargs="?", type=Path, default=Path("."))

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

    cache_parser = subparsers.add_parser(
        "cache",
        help="Show repository cache state and freshness.",
    )
    cache_parser.add_argument("path", nargs="?", type=Path, default=Path("."))

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect persisted repository intelligence.",
    )
    inspect_parser.add_argument("path", nargs="?", type=Path, default=Path("."))

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

    diagnostics_parser = subparsers.add_parser(
        "diagnostics",
        help="Show persisted repository analysis diagnostics.",
    )
    diagnostics_parser.add_argument("path", nargs="?", type=Path, default=Path("."))

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


def print_analysis_summary(project) -> None:
    print(f"Analyzed: {project.root_path}")
    print(f"Files: {len(project.files)}")
    print(f"Symbols: {len(project.symbols)}")
    print(f"Relationships: {len(project.relationships)}")
    print(f"Status: {project.analysis_status}")


def print_status_summary(project, metadata, freshness) -> None:
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
) -> None:
    print(f"Repository: {repository_key}")
    print(f"Cache status: {'fresh' if freshness.is_fresh else 'stale'}")
    print(f"Cache schema version: {metadata.cache_schema_version}")
    print(f"Analyzer version: {metadata.analyzer_version}")
    print(f"Tracked files: {len(fingerprints)}")

    changes = freshness.changes

    print(f"Freshness reason: {freshness.reason}")

    if changes is None:
        print("Added paths: 0")
        print("Modified paths: 0")
        print("Deleted paths: 0")
        return

    print(f"Added paths: {len(changes.added)}")
    print(f"Modified paths: {len(changes.modified)}")
    print(f"Deleted paths: {len(changes.deleted)}")

    if changes.added:
        print()
        print("Added paths:")
        for path in sorted(changes.added):
            print(f"  {path}")

    if changes.modified:
        print()
        print("Modified paths:")
        for path in sorted(changes.modified):
            print(f"  {path}")

    if changes.deleted:
        print()
        print("Deleted paths:")
        for path in sorted(changes.deleted):
            print(f"  {path}")


def print_inspection_summary(project) -> None:
    print(f"Repository: {project.root_path}")
    print()

    print("Files:")
    for file in sorted(project.files, key=lambda item: item.path):
        print(f"  {file.path}")

    print()
    print("Symbols:")
    for symbol in sorted(
        project.symbols,
        key=lambda item: (
            item.file_id,
            item.start_line,
            item.name,
        ),
    ):
        qualified_name = symbol.qualified_name or symbol.name
        print(
            f"  {qualified_name}"
            f" [{symbol.kind}]"
            f" lines {symbol.start_line}-{symbol.end_line}"
        )

    print()
    print("Relationships:")
    for relationship in sorted(
        project.relationships,
        key=lambda item: (
            item.relationship_type.value,
            str(item.source_id),
            str(item.target_id),
        ),
    ):
        print(
            f"  {relationship.relationship_type.value}"
            f": {relationship.source_id}"
            f" -> {relationship.target_id}"
        )


def print_diagnostics_summary(project) -> None:
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


def run_analyze(path: Path) -> None:
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
        print_analysis_summary(project)
    except Exception as exc:
        log_analysis_failed(
            project_path=root_path,
            duration_seconds=time.monotonic() - started_at,
            error=exc,
        )
        raise


def run_status(path: Path) -> None:
    root_path = resolve_project_path(path)
    repository, repository_key, project, metadata = load_project_analysis(root_path)

    fingerprints = current_fingerprints(project)

    freshness = repository.check_cache_freshness(
        repository_key,
        fingerprints,
    )

    print_status_summary(
        project,
        metadata,
        freshness,
    )


def run_cache(path: Path) -> None:
    root_path = resolve_project_path(path)
    repository, repository_key, project, metadata = load_project_analysis(root_path)

    fingerprints = current_fingerprints(project)

    freshness = repository.check_cache_freshness(
        repository_key,
        fingerprints,
    )

    print_cache_summary(
        repository_key,
        metadata,
        fingerprints,
        freshness,
    )


def run_inspect(path: Path) -> None:
    root_path = resolve_project_path(path)
    _, _, project, _ = load_project_analysis(root_path)

    print_inspection_summary(project)


def run_memory_search(query: str, path: Path) -> None:
    normalized_query = query.strip()

    if not normalized_query:
        raise ValueError("Search query cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)
    results = ProjectQuery(project).search(normalized_query)

    print(f"Repository: {root_path}")
    print(f"Query: {normalized_query}")
    print(f"Results: {len(results)}")

    if not results:
        print("No matches found.")
        return

    for result in results:
        display_name = result.qualified_name or result.name

        print(f"  [{result.result_type.value}] {display_name}")

        if result.path is not None:
            print(f"    Path: {result.path}")

        print(f"    Score: {result.score:.2f}")

        if result.reason is not None:
            print(f"    Match: {result.reason}")


def run_memory_file(file_path: str, path: Path) -> None:
    normalized_file_path = file_path.strip()

    if not normalized_file_path:
        raise ValueError("File path cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)
    query = ProjectQuery(project)

    file = query.get_file(normalized_file_path)

    print(f"Repository: {root_path}")
    print(f"File: {normalized_file_path}")

    if file is None:
        print("File not found.")
        return

    print(f"Name: {file.name}")
    print(f"Extension: {file.extension}")
    print(f"Type: {file.file_type.value}")
    print(f"Size: {file.size} bytes")

    symbols = sorted(
        query.find_symbols_in_file(file.id),
        key=lambda symbol: (symbol.start_line, symbol.name),
    )

    print(f"Symbols: {len(symbols)}")

    if not symbols:
        print("No symbols defined in this file.")
        return

    for symbol in symbols:
        display_name = symbol.qualified_name or symbol.name

        print(f"  [{symbol.kind}] {display_name}")
        print(f"    Lines: {symbol.start_line}-{symbol.end_line}")

        if symbol.signature is not None:
            print(f"    Signature: {symbol.signature}")


def run_memory_symbol(symbol_name: str, path: Path) -> None:
    normalized_name = symbol_name.strip()

    if not normalized_name:
        raise ValueError("Symbol name cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)
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
            files_by_id[symbol.file_id].path.as_posix()
            if symbol.file_id in files_by_id
            else "",
            symbol.start_line,
            symbol.name,
        ),
    )

    print(f"Repository: {root_path}")
    print(f"Symbol: {normalized_name}")
    print(f"Matches: {len(symbols)}")

    if not symbols:
        print("No matching symbol found.")
        return

    if len(symbols) > 1:
        print("Multiple definitions found:")

    for symbol in symbols:
        display_name = symbol.qualified_name or symbol.name
        file = files_by_id.get(symbol.file_id)

        print(f"  [{symbol.kind}] {display_name}")

        if file is not None:
            print(f"    Path: {file.path.as_posix()}")
        else:
            print("    Path: Unknown")

        print(f"    Lines: {symbol.start_line}-{symbol.end_line}")

        if symbol.signature is not None:
            print(f"    Signature: {symbol.signature}")


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


def run_memory_references(symbol_name: str, path: Path) -> None:
    normalized_name = symbol_name.strip()
    if not normalized_name:
        raise ValueError("Symbol name cannot be empty")

    root_path = resolve_project_path(path)
    project, _ = load_fresh_project(root_path)
    query = ProjectQuery(project)

    symbols = _find_memory_symbols(query, normalized_name)
    files_by_id = {file.id: file for file in project.files}

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

        print(f"Repository: {root_path}")
        print(f"Entity: {normalized_name}")

        if not symbols:
            print("Entity not found.")
            return

        if len(symbols) > 1:
            print(f"Multiple matching symbols found: {len(symbols)}")
            _print_matching_symbols(symbols, files_by_id)
            print("Use a qualified name to narrow the results.")
            return

        entity = symbols[0]
        entity_kind = "symbol"

    print(f"Repository: {root_path}")
    print(f"Entity: {normalized_name}")
    print(f"Entity type: {entity_kind}")
    print(f"Direction: {direction}")

    if relationship_type is not None:
        print(f"Relationship type: {relationship_type}")

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


def run_diagnostics(path: Path) -> None:
    root_path = resolve_project_path(path)
    _, _, project, _ = load_project_analysis(root_path)

    print_diagnostics_summary(project)


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
        "analyze": lambda: run_analyze(args.path),
        "refresh": lambda: run_analyze(args.path),
        "status": lambda: run_status(args.path),
        "cache": lambda: run_cache(args.path),
        "inspect": lambda: run_inspect(args.path),
        "diagnostics": lambda: run_diagnostics(args.path),
        ("memory", "inspect"): lambda: run_inspect(args.path),
        ("memory", "search"): lambda: run_memory_search(
            args.query,
            args.path,
        ),
        ("memory", "file"): lambda: run_memory_file(
            args.file_path,
            args.path,
        ),
        ("memory", "symbol"): lambda: run_memory_symbol(
            args.symbol_name,
            args.path,
        ),
        ("memory", "references"): lambda: run_memory_references(
            args.symbol_name,
            args.path,
        ),
        ("memory", "relationships"): lambda: run_memory_relationships(
            args.entity_name,
            args.path,
            args.direction,
            args.relationship_type,
        ),
        "context": lambda: run_context(args),
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
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
