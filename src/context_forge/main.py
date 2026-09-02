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
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--base-url", default=None)
    return parser


def parse_args() -> argparse.Namespace:
    return create_parser().parse_args()


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


def main() -> None:
    args = parse_args()

    if args.path is None:
        create_parser().print_help()
        return

    root_path: Path | None = None
    generation_config: ProviderConfig | None = None
    started_at = time.monotonic()

    try:
        root_path = resolve_project_path(args.path)
        database_path = root_path / ".context_forge.db"

        project = ProjectAnalyzer(
            root_path=root_path,
            database_path=database_path,
        ).analyze()

        try:
            task = input("Task: ").strip()
        except KeyboardInterrupt:
            print(file=sys.stderr)
            raise SystemExit(130) from None
        except EOFError:
            print("Error: Task input ended unexpectedly", file=sys.stderr)
            raise SystemExit(1) from None

        generation_config = build_provider_config(
            args,
            root_path,
        )

        log_generation_started(
            project_path=root_path,
            provider=generation_config.provider,
            model=generation_config.model,
        )

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
        if root_path is not None:
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
