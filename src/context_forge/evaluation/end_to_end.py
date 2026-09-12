from dataclasses import dataclass

from context_forge.context.package import ContextPackage
from context_forge.evaluation.ground_truth import ExpectedEntity
from context_forge.evaluation.metrics import MetricResult
from context_forge.models.project import Project


@dataclass(frozen=True)
class EndToEndEvaluationResult:
    context: MetricResult
    within_budget: bool
    deterministic: bool

    @property
    def precision(self) -> float:
        return self.context.precision

    @property
    def recall(self) -> float:
        return self.context.recall

    @property
    def f1(self) -> float:
        return self.context.f1


class EndToEndEvaluator:
    """Evaluate the final context produced for a development task."""

    def evaluate(
        self,
        project: Project,
        package: ContextPackage,
        ground_truth: tuple[ExpectedEntity, ...],
        *,
        budget: int | None = None,
        deterministic: bool = True,
    ) -> EndToEndEvaluationResult:
        expected = {self._expected_entity_key(entity) for entity in ground_truth}

        actual = {
            key
            for unit in package.units
            if (key := self._entity_key(project, unit.entity_id)) is not None
        }

        return EndToEndEvaluationResult(
            context=self._metric(expected, actual),
            within_budget=(budget is None or len(package.units) <= budget),
            deterministic=deterministic,
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
    def _entity_key(
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
