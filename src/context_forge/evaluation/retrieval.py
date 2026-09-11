from dataclasses import dataclass

from context_forge.context.candidate import ContextCandidate
from context_forge.evaluation.ground_truth import (
    ExpectedEntity,
    RetrievalGroundTruth,
)
from context_forge.evaluation.metrics import MetricResult
from context_forge.models.project import Project
from context_forge.task.repository_grounding import RepositoryGrounding


@dataclass(frozen=True)
class RetrievalEvaluationResult:
    """Evaluation result for retrieval and repository task grounding."""

    retrieval: MetricResult
    grounding: MetricResult

    @property
    def precision(self) -> float:
        return self._aggregate(
            self.retrieval.precision,
            self.grounding.precision,
        )

    @property
    def recall(self) -> float:
        return self._aggregate(
            self.retrieval.recall,
            self.grounding.recall,
        )

    @property
    def f1(self) -> float:
        return self._aggregate(
            self.retrieval.f1,
            self.grounding.f1,
        )

    @staticmethod
    def _aggregate(*values: float) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)


class RetrievalEvaluator:
    """Evaluate repository retrieval and task-grounding quality."""

    def evaluate(
        self,
        project: Project,
        candidates: tuple[ContextCandidate, ...] | list[ContextCandidate],
        grounding: RepositoryGrounding,
        ground_truth: RetrievalGroundTruth,
    ) -> RetrievalEvaluationResult:
        expected_retrieval = {
            self._expected_entity_key(entity)
            for entity in ground_truth.retrieved_entities
        }
        expected_grounding = {
            self._expected_entity_key(entity)
            for entity in ground_truth.grounded_entities
        }

        actual_retrieval = {
            self._entity_key(project, candidate.entity_id)
            for candidate in candidates
            if self._entity_exists(project, candidate.entity_id)
        }

        actual_grounding = {
            self._entity_key(project, entity_id)
            for entity_id in grounding.related_entity_ids
            if self._entity_exists(project, entity_id)
        }

        return RetrievalEvaluationResult(
            retrieval=self._metric(
                expected_retrieval,
                actual_retrieval,
            ),
            grounding=self._metric(
                expected_grounding,
                actual_grounding,
            ),
        )

    @staticmethod
    def _metric(
        expected: set[str],
        actual: set[str],
    ) -> MetricResult:
        return MetricResult(
            expected=len(expected),
            actual=len(actual),
            matched=len(expected & actual),
        )

    @staticmethod
    def _expected_entity_key(entity: ExpectedEntity) -> str:
        return f"{entity.kind}:{entity.value}"

    @classmethod
    def _entity_key(
        cls,
        project: Project,
        entity_id: object,
    ) -> str:
        for file in project.files:
            if file.id == entity_id:
                return f"file:{file.path.as_posix()}"

        for symbol in project.symbols:
            if symbol.id == entity_id:
                qualified_name = symbol.qualified_name or symbol.name
                return f"symbol:{qualified_name}"

        for directory in project.directories:
            if directory.id == entity_id:
                return f"directory:{directory.path.as_posix()}"

        return f"unknown:{entity_id}"

    @staticmethod
    def _entity_exists(
        project: Project,
        entity_id: object,
    ) -> bool:
        for file in project.files:
            if file.id == entity_id:
                return True

        for symbol in project.symbols:
            if symbol.id == entity_id:
                return True

        for directory in project.directories:
            if directory.id == entity_id:
                return True

        return False
