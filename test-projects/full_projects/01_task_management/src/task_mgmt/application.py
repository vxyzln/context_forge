from task_mgmt.reporting.summary import ProjectReporter
from task_mgmt.repositories.project_repo import ProjectRepository
from task_mgmt.repositories.task_repo import TaskRepository
from task_mgmt.repositories.user_repo import UserRepository
from task_mgmt.services.project_service import ProjectService
from task_mgmt.services.task_service import TaskService
from task_mgmt.services.user_service import UserService


class TaskManagementApp:
    def __init__(self) -> None:
        self.user_repo = UserRepository()
        self.project_repo = ProjectRepository()
        self.task_repo = TaskRepository()

        self.users = UserService(self.user_repo)
        self.projects = ProjectService(self.project_repo)
        self.tasks = TaskService(self.task_repo, self.user_repo)
        self.reporter = ProjectReporter(self.project_repo, self.task_repo)

    def bootstrap_sample_data(self) -> None:
        self.users.create_user("u1", "alice", "alice@example.com")
        self.users.create_user("u2", "bob", "bob@example.com")
        self.projects.create_project("p1", "Platform V1", "Core backend services")
        self.tasks.create_task("t1", "p1", "Design schema", assignee_id="u1")
        self.tasks.create_task("t2", "p1", "Implement models", assignee_id="u2")
