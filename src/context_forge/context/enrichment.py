from abc import ABC, abstractmethod

from context_forge.context.models import ContextUnit
from context_forge.models.project import Project


class ContextEnricher(ABC):
    @abstractmethod
    def enrich(
        self,
        project: Project,
        unit: ContextUnit,
    ) -> ContextUnit:
        """Enrich a context unit with deterministic facts and evidencd"""
