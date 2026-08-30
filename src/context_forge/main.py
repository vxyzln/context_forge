import argparse
import sys
from pathlib import Path

from context_forge.application import build_generation_service
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
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434",
    )

    return parser.parse_args()


def resolve_project_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()

    if not resolved.exists():
        raise ValueError(f"Project path does not exist: {resolved}")

    if not resolved.is_dir():
        raise ValueError(f"Project path is not a directory: {resolved}")

    return resolved


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

        generation_config = ProviderConfig(
            provider=args.provider,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            base_url=args.base_url,
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
