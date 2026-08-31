import argparse
import sys
from pathlib import Path

from context_forge.application import build_generation_service
from context_forge.config import (
    load_global_configuration,
    load_project_configuration,
    resolve_configuration,
)
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.provider import ProviderConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="context-forge",
        description="Generate context-forge responses for software projects.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--base-url", default=None)

    return parser.parse_args()


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
        provider=args.provider if args.provider is not None else resolved.provider,
        model=args.model if args.model is not None else resolved.model,
        temperature=args.temperature
        if args.temperature is not None
        else resolved.temperature,
        max_tokens=args.max_tokens
        if args.max_tokens is not None
        else resolved.max_tokens,
        base_url=args.base_url if args.base_url is not None else resolved.base_url,
    )


def main() -> None:
    args = parse_args()

    try:
        root_path = resolve_project_path(args.path)
        database_path = root_path / ".context_forge.db"

        project = ProjectAnalyzer(
            root_path=root_path,
            database_path=database_path,
        ).analyze()

        task = input("Task: ").strip()

        generation_config = build_provider_config(
            args,
            root_path,
        )

        service = build_generation_service(generation_config)

        response = service.generate(
            project=project,
            task=task,
            config=generation_config,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None

    print()
    print(response.content)


if __name__ == "__main__":
    main()
