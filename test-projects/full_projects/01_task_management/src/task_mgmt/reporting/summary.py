from collections import Counter

from task_mgmt.models.enums import TaskStatus
from task_mgmt.repositories.project_repo import ProjectRepository
from task_mgmt.repositories.task_repo import TaskRepository


class ProjectReporter:
    def __init__(
        self, project_repo: ProjectRepository, task_repo: TaskRepository
    ) -> None:
        self.project_repo = project_repo
        self.task_repo = task_repo

    def summarize_project(self, project_id: str) -> dict[str, object]:
        project = self.project_repo.get(project_id)
        if not project:
            return {"error": f"Project '{project_id}' not found"}

        tasks = self.task_repo.list_by_project(project_id)
        status_counts = Counter(t.status.value for t in tasks)

        completed = status_counts.get(TaskStatus.DONE.value, 0)
        total = len(tasks)
        completion_rate = (completed / total * 100.0) if total > 0 else 0.0

        return {
            "project_id": project.project_id,
            "project_name": project.name,
            "status": project.status.value,
            "total_tasks": total,
            "completion_rate_pct": round(completion_rate, 1),
            "by_status": dict(status_counts),
        }
