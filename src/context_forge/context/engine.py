from abc import ABC, abstractmethod

from context_forge.context.models import ContextPackage
from context_forge.models.project import Project


class ContextEngine(ABC):
    @abstractmethod
    def build(self, project: Project, task: str) -> ContextPackage:
        """Build a context package for a project task."""
        raise NotImplementedError
