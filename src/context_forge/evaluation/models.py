from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluationTask:
    id: str
    description: str
    expected_paths: tuple[Path, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationRepository:
    id: str
    name: str
    root_path: Path
    tasks: tuple[EvaluationTask, ...] = ()
    description: str = ""
    language: str = "python"


@dataclass(frozen=True)
class EvaluationSet:
    repositories: tuple[EvaluationRepository, ...]

    def __post_init__(self) -> None:
        repository_ids = [repository.id for repository in self.repositories]

        if len(repository_ids) != len(set(repository_ids)):
            raise ValueError("Evaluation repository IDs must be unique")

    def get_repository(self, repository_id: str) -> EvaluationRepository | None:
        for repository in self.repositories:
            if repository.id == repository_id:
                return repository

        return None

    @property
    def repository_count(self) -> int:
        return len(self.repositories)

    @property
    def task_count(self) -> int:
        return sum(len(repository.tasks) for repository in self.repositories)
