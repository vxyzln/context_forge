from pathlib import Path

from context_forge.pipeline.analyzer import ProjectAnalyzer


def main() -> None:
    root_path = Path.cwd()
    database_path = root_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=root_path,
        database_path=database_path,
    ).analyze()

    print(f"Analyzed: {project.name}")
    print(f"Files: {len(project.files)}")
    print(f"Symbols: {len(project.symbols)}")
    print(f"Relationships: {len(project.relationships)}")


if __name__ == "__main__":
    main()
