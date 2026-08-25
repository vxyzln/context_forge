from abc import ABC, abstractmethod

from context_forge.context.candidates import CandidateGenerator
from context_forge.context.expansion import GraphExpander
from context_forge.context.models import ContextPackage
from context_forge.context.package import ContextPackageBuilder
from context_forge.context.ranking import DeterministicRanker
from context_forge.context.selection import ContextSelector
from context_forge.models.project import Project


class ContextEngine(ABC):
    @abstractmethod
    def build(self, project: Project, task: str) -> ContextPackage:
        """Build a context package for a project task."""
        raise NotImplementedError


class DefaultContextEngine(ContextEngine):
    def __init__(
        self,
        candidate_generator: CandidateGenerator,
        ranker: DeterministicRanker,
        selector: ContextSelector,
        expander: GraphExpander,
        package_builder: ContextPackageBuilder,
    ) -> None:
        self.candidate_generator = candidate_generator
        self.ranker = ranker
        self.selector = selector
        self.expander = expander
        self.package_builder = package_builder

    def build(self, project: Project, task: str) -> ContextPackage:
        if not task.strip():
            raise ValueError("Task cannot be empty")

        candidates = self.candidate_generator.generate(project, task)

        ranked = self.ranker.rank(candidates, {})

        selected = self.selector.select(ranked)

        expanded = self.expander.expand(project, selected)

        return self.package_builder.build(task, expanded)
