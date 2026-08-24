from abc import ABC, abstractmethod

from context_forge.context.models import ContextUnit
from context_forge.models.project import Project


class ContextRetriever(ABC):
    @abstractmethod
    def retrieve(self, project: Project, query: str) -> list[ContextUnit]:
        """Retrieve candidate context units for a queryy."""
        raise NotImplementedError
