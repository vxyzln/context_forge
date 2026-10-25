from task_mgmt.models.enums import ProjectStatus
from task_mgmt.models.project import Project
from task_mgmt.repositories.project_repo import ProjectRepository
from task_mgmt.validation.rules import validate_not_empty


class ProjectService:
    def __init__(self, project_repo: ProjectRepository) -> None:
        self.project_repo = project_repo

    def create_project(
        self, project_id: str, name: str, description: str = ""
    ) -> Project:
        validate_not_empty(project_id, "project_id")
        validate_not_empty(name, "name")
        project = Project(project_id=project_id, name=name, description=description)
        self.project_repo.add(project)
        return project

    def archive_project(self, project_id: str) -> bool:
        project = self.project_repo.get(project_id)
        if not project:
            return False
        project.status = ProjectStatus.ARCHIVED
        return True
