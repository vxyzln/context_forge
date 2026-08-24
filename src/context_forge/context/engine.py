from abc import ABC, abstractmethod

from context_forge.context.models import ContextPackage
from context_forge.context.retrieval import ContextRetriever
from context_forge.models.project import Project


class ContextEngine(ABC):
    @abstractmethod
    def build(self, project: Project, task: str) -> ContextPackage:
        """Build a context package for a project task."""
        raise NotImplementedError


class DefaultContextEngine(ContextEngine):
    def __init__(self, retriever: ContextRetriever) -> None:
        self.retriever = retriever

    def build(self, project: Project, task: str) -> ContextPackage:
        if not task.strip():
            raise ValueError("Task cannot be empty")
        units = tuple(self.retriever.retrieve(project, task))

        return ContextPackage(task=task.strip(), units=units)
