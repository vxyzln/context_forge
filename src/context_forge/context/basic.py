from context_forge.context.engine import ContextEngine
from context_forge.context.models import ContextPackage
from context_forge.models.project import Project


class BasicContextEngine(ContextEngine):
    def build(self, project: Project, task: str) -> ContextPackage:
        if not task.strip():
            raise ValueError("Task cannot be empty")

        return ContextPackage(task=task.strip())
