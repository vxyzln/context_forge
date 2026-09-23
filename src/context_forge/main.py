import argparse
import sys
import time
from pathlib import Path

from context_forge.application import build_generation_service
from context_forge.config import (
    load_global_configuration,
    load_project_configuration,
    resolve_configuration,
)
from context_forge.operational_logging import (
    log_generation_completed,
    log_generation_failed,
    log_generation_started,
)
from context_forge.pipeline.analyzer import (
    ProjectAnalyzer,
    current_fingerprints,
)
from context_forge.provider import OllamaRuntime, ProviderConfig
from context_forge.storage.cache import RepositoryIdentity
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-forge",
        description="Generate context-forge responses for software projects.",
    )

    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a repository and persist repository intelligence.",
    )
    analyze_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a response using persisted repository intelligence.",
    )
    generate_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )
    generate_parser.add_argument("--provider", default=None)
    generate_parser.add_argument("--model", default=None)
    generate_parser.add_argument("--temperature", type=float, default=None)
    generate_parser.add_argument("--max-tokens", type=int, default=None)
    generate_parser.add_argument("--base-url", default=None)
    generate_parser.add_argument("--task", default=None)

    status_parser = subparsers.add_parser(
        "status",
        help="Show repository and analysis status.",
    )
    status_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )

    cache_parser = subparsers.add_parser(
        "cache",
        help="Show repository cache state and freshness.",
    )
    cache_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect persisted repository intelligence.",
    )
    inspect_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )

    diagnostics_parser = subparsers.add_parser(
        "diagnostics",
        help="Show persisted repository analysis diagnostics.",
    )
    diagnostics_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )

    runtime_parser = subparsers.add_parser(
        "runtime", help="Check Ollama runtime and model availability."
    )
    runtime_parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("."),
    )
    runtime_parser.add_argument("--model", default=None)
    runtime_parser.add_argument("--base-url", default=None)

    return parser


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]

    # Preserve the existing `context-forge .` workflow.
    if argv and argv[0] not in {
        "analyze",
        "generate",
        "status",
        "cache",
        "inspect",
        "diagnostics",
        "runtime",
        "-h",
        "--help",
    }:
        argv = ["generate", *argv]

    return create_parser().parse_args(argv)


def resolve_project_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()

    if not resolved.exists():
        raise ValueError(f"Project path does not exist: {resolved}")

    if not resolved.is_dir():
        raise ValueError(f"Project path is not a directory: {resolved}")

    return resolved


def build_provider_config(
    args: argparse.Namespace,
    project_root: Path,
) -> ProviderConfig:
    global_config = load_global_configuration()
    project_config = load_project_configuration(project_root)
    resolved = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    return ProviderConfig(
        provider=(args.provider if args.provider is not None else resolved.provider),
        model=args.model if args.model is not None else resolved.model,
        temperature=(
            args.temperature if args.temperature is not None else resolved.temperature
        ),
        max_tokens=(
            args.max_tokens if args.max_tokens is not None else resolved.max_tokens
        ),
        base_url=(args.base_url if args.base_url is not None else resolved.base_url),
    )


def build_runtime_config(
    args: argparse.Namespace,
    project_root: Path,
) -> ProviderConfig:
    global_config = load_global_configuration()
    project_config = load_project_configuration(project_root)
    resolved = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    return ProviderConfig(
        provider="ollama",
        model=args.model if args.model is not None else resolved.model,
        temperature=resolved.temperature,
        max_tokens=resolved.max_tokens,
        base_url=(args.base_url if args.base_url is not None else resolved.base_url),
    )


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
    loaded = repository.load_analysis(repository_key)

    if loaded is None:
        raise ValueError(
            "No persisted analysis found; run 'context-forge analyze' first"
        )

    project, metadata = loaded
    return repository, repository_key, project, metadata


def load_generation_project(root_path: Path):
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


def print_runtime_summary(status) -> None:
    print(f"Ollama runtime: {'available' if status.available else 'unavailable'}")
    print(f"Base URL: {status.base_url}")
    print(f"Model: {status.model}")
    print(f"Model status: {'available' if status.model_available else 'unavailable'}")
    print(f"Ready: {'yes' if status.ready else 'no'}")
    print(f"Reason: {status.reason}")


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
    root_path = resolve_project_path(path)
    project = analyze_project(root_path)
    print_analysis_summary(project)


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


def run_diagnostics(path: Path) -> None:
    root_path = resolve_project_path(path)
    _, _, project, _ = load_project_analysis(root_path)

    print_diagnostics_summary(project)


def print_generation_response(response: object) -> None:
    content = getattr(response, "content", None)

    if not isinstance(content, str):
        raise TypeError("Generation response content must be a string")

    print()
    print(content)


def run_generate(args: argparse.Namespace) -> None:
    root_path: Path | None = None
    generation_config: ProviderConfig | None = None
    started_at = time.monotonic()
    generation_started = False

    try:
        root_path = resolve_project_path(args.path)
        project, _ = load_generation_project(root_path)
        task = read_task(args.task)

        generation_config = build_provider_config(
            args,
            root_path,
        )

        log_generation_started(
            project_path=root_path,
            provider=generation_config.provider,
            model=generation_config.model,
        )
        generation_started = True

        service = build_generation_service(generation_config)

        response = service.generate(
            project=project,
            task=task,
            config=generation_config,
        )

        log_generation_completed(
            project_path=root_path,
            provider=generation_config.provider,
            model=generation_config.model,
            duration_seconds=time.monotonic() - started_at,
        )

    except (RuntimeError, TypeError, ValueError) as exc:
        if root_path is not None and generation_started:
            log_generation_failed(
                project_path=root_path,
                provider=(
                    generation_config.provider
                    if generation_config is not None
                    else None
                ),
                model=(
                    generation_config.model if generation_config is not None else None
                ),
                duration_seconds=time.monotonic() - started_at,
                error=exc,
            )

        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    print_generation_response(response)


def run_runtime(path: Path, args: argparse.Namespace) -> None:
    root_path = resolve_project_path(path)
    config = build_runtime_config(args, root_path)

    runtime = OllamaRuntime(
        base_url=config.base_url,
        timeout=config.transport.timeout,
    )
    status = runtime.check(config.model)

    print_runtime_summary(status)

    if not status.ready:
        raise RuntimeError(f"Ollama runtime check failed: {status.reason}")


def main() -> None:
    args = parse_args()

    if args.command is None:
        create_parser().print_help()
        return

    if args.command == "analyze":
        try:
            run_analyze(args.path)
        except (RuntimeError, TypeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == "status":
        try:
            run_status(args.path)
        except (RuntimeError, TypeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == "cache":
        try:
            run_cache(args.path)
        except (RuntimeError, TypeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == "inspect":
        try:
            run_inspect(args.path)
        except (RuntimeError, TypeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == "diagnostics":
        try:
            run_diagnostics(args.path)
        except (RuntimeError, TypeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return

    if args.command == "runtime":
        try:
            run_runtime(args.path, args)
        except (RuntimeError, TypeError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from None
        return

    run_generate(args)
----
