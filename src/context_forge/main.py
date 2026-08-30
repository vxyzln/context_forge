from pathlib import Path

from context_forge.application import build_generation_service
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.provider import ProviderConfig


def main() -> None:
    root_path = Path.cwd()
    database_path = root_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=root_path,
        database_path=database_path,
    ).analyze()

    task = input("Task: ").strip()

    service = build_generation_service()

    response = service.generate(
        project=project, task=task, config=ProviderConfig(model="deterministic")
    )

    print()
    print(response.content)


if __name__ == "__main__":
    main()
