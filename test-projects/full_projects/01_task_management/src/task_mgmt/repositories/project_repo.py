from task_mgmt.models.project import Project
from task_mgmt.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}

    def add(self, entity: Project) -> None:
        self._projects[entity.project_id] = entity

    def get(self, identifier: str) -> Project | None:
        return self._projects.get(identifier)

    def list_all(self) -> list[Project]:
        return list(self._projects.values())
