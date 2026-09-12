from dataclasses import dataclass

from context_forge.context.candidate import ContextCandidate
from context_forge.context.selection_service import (
    ContextSelectionResult,
)
from context_forge.evaluation.ground_truth import ExpectedEntity
from context_forge.evaluation.metrics import MetricResult
from context_forge.models.project import Project


@dataclass(frozen=True)
class SelectionEvaluationResult:
    selection: MetricResult

    @property
    def precision(self) -> float:
        return self.selection.precision

    @property
    def recall(self) -> float:
        return self.selection.recall

    @property
    def f1(self) -> float:
        return self.selection.f1


class SelectionEvaluator:
    """Evaluate intelligent context selection against repository ground truth."""

    def evaluate(
        self,
        project: Project,
        candidates: list[ContextCandidate],
        result: ContextSelectionResult,
        ground_truth: tuple[ExpectedEntity, ...],
    ) -> SelectionEvaluationResult:
        expected = {self._expected_entity_key(entity) for entity in ground_truth}

        actual = {
            key
            for item in result.candidates
            if (
                key := self._known_entity_key(
                    project,
                    item.candidate.entity_id,
                )
            )
            is not None
        }

        candidate_keys = {
            key
            for candidate in candidates
            if (
                key := self._known_entity_key(
                    project,
                    candidate.entity_id,
                )
            )
            is not None
        }

        actual &= candidate_keys

        return SelectionEvaluationResult(
            selection=self._metric(expected, actual),
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

    @staticmethod
    def _known_entity_key(
        project: Project,
        entity_id: object,
    ) -> str | None:
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

        return None
