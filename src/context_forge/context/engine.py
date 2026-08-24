from abc import ABC, abstractmethod

from context_forge.context.candidates import CandidateGenerator
from context_forge.context.models import ContextPackage, ContextUnit
from context_forge.context.ranking import DeterministicRanker
from context_forge.context.retrieval import ContextRetriever
from context_forge.context.signals import RelevanceSignals
from context_forge.models.project import Project


class ContextEngine(ABC):
    @abstractmethod
    def build(self, project: Project, task: str) -> ContextPackage:
        """Build a context package for a project task."""
        raise NotImplementedError


class DefaultContextEngine(ContextEngine):
    def __init__(
        self,
        retriever: ContextRetriever,
        candidate_generator: CandidateGenerator | None = None,
        ranker: DeterministicRanker | None = None,
    ) -> None:
        self.retriever = retriever
        self.candidate_generator = candidate_generator
        self.ranker = ranker or DeterministicRanker()

    def build(self, project: Project, task: str) -> ContextPackage:
        normalized_task = task.strip()

        if not normalized_task:
            raise ValueError("Task cannot be empty")

        if self.candidate_generator is not None:
            candidates = self.candidate_generator.generate(
                project,
                normalized_task,
            )
        else:
            units = self.retriever.retrieve(project, normalized_task)
            candidates = [
                ContextUnit(
                    entity_id=unit.entity_id,
                    unit_type=unit.unit_type,
                    relevance=unit.relevance,
                    signals=unit.signals,
                    facts=unit.facts,
                    inferences=unit.inferences,
                )
                for unit in units
            ]

            return ContextPackage(
                task=normalized_task,
                units=tuple(candidates),
            )

        signals = {candidate.entity_id: RelevanceSignals() for candidate in candidates}

        ranked = self.ranker.rank(candidates, signals)

        units = tuple(
            ContextUnit(
                entity_id=candidate.entity_id,
                unit_type=candidate.unit_type,
                relevance=candidate.score,
            )
            for candidate in ranked
        )

        return ContextPackage(
            task=normalized_task,
            units=units,
        )
