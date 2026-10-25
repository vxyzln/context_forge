from dataclasses import dataclass, field
from datetime import UTC, datetime

from task_mgmt.models.enums import ProjectStatus


@dataclass
class Project:
    project_id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
