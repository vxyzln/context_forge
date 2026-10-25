from task_mgmt.models.task import Task
from task_mgmt.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, entity: Task) -> None:
        self._tasks[entity.task_id] = entity

    def get(self, identifier: str) -> Task | None:
        return self._tasks.get(identifier)

    def list_all(self) -> list[Task]:
        return list(self._tasks.values())

    def list_by_project(self, project_id: str) -> list[Task]:
        return [t for t in self._tasks.values() if t.project_id == project_id]

    def list_by_assignee(self, assignee_id: str) -> list[Task]:
        return [t for t in self._tasks.values() if t.assignee_id == assignee_id]
