from datetime import UTC, datetime

from task_mgmt.models.enums import TaskPriority, TaskStatus
from task_mgmt.models.task import Task
from task_mgmt.repositories.task_repo import TaskRepository
from task_mgmt.repositories.user_repo import UserRepository
from task_mgmt.validation.rules import ValidationError, validate_not_empty

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.TODO: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.REVIEW, TaskStatus.CANCELLED},
    TaskStatus.REVIEW: {TaskStatus.DONE, TaskStatus.IN_PROGRESS},
    TaskStatus.DONE: set(),
    TaskStatus.CANCELLED: set(),
}


class TaskService:
    def __init__(self, task_repo: TaskRepository, user_repo: UserRepository) -> None:
        self.task_repo = task_repo
        self.user_repo = user_repo

    def create_task(
        self,
        task_id: str,
        project_id: str,
        title: str,
        priority: TaskPriority = TaskPriority.MEDIUM,
        assignee_id: str | None = None,
        deadline: datetime | None = None,
    ) -> Task:
        validate_not_empty(task_id, "task_id")
        validate_not_empty(project_id, "project_id")
        validate_not_empty(title, "title")

        if assignee_id and not self.user_repo.get(assignee_id):
            raise ValidationError(f"Assignee with id '{assignee_id}' does not exist")

        task = Task(
            task_id=task_id,
            project_id=project_id,
            title=title,
            priority=priority,
            assignee_id=assignee_id,
            deadline=deadline,
        )
        self.task_repo.add(task)
        return task

    def transition_status(self, task_id: str, new_status: TaskStatus) -> Task:
        task = self.task_repo.get(task_id)
        if not task:
            raise ValidationError(f"Task '{task_id}' not found")

        allowed = ALLOWED_TRANSITIONS.get(task.status, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Invalid transition from {task.status.value} to {new_status.value}"
            )

        task.status = new_status
        task.updated_at = datetime.now(UTC)
        return task
