from dataclasses import dataclass, field
from datetime import UTC, datetime

from task_mgmt.models.enums import TaskPriority, TaskStatus


@dataclass
class Task:
    task_id: str
    project_id: str
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: str | None = None
    deadline: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
