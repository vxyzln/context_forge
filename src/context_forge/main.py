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
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.provider import ProviderConfig


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
        help="Analyze a repository and generate a response.",
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
    generate_parser.add_argument(
        "--task",
        default=None,
        help="Task to generate a response for.",
    )

    return parser


def parse_args() -> argparse.Namespace:
    argv = sys.argv[1:]

    # Preserve the existing `context-forge .` workflow.
    if argv and argv[0] not in {"analyze", "generate", "-h", "--help"}:
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


def analyze_project(root_path: Path):
    database_path = root_path / ".context_forge.db"

    return ProjectAnalyzer(
        root_path=root_path,
        database_path=database_path,
    ).analyze()


def print_analysis_summary(project) -> None:
    print(f"Analyzed: {project.root_path}")
    print(f"Files: {len(project.files)}")
    print(f"Symbols: {len(project.symbols)}")
    print(f"Relationships: {len(project.relationships)}")
    print(f"Status: {project.analysis_status}")


def run_analyze(path: Path) -> None:
    root_path = resolve_project_path(path)
    project = analyze_project(root_path)
    print_analysis_summary(project)


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


def run_generate(args: argparse.Namespace) -> None:
    root_path: Path | None = None
    generation_config: ProviderConfig | None = None
    started_at = time.monotonic()
    generation_started = False

    try:
        root_path = resolve_project_path(args.path)
        project = analyze_project(root_path)

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

    print()
    print(response.content)


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

    run_generate(args)
