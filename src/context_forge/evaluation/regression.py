from dataclasses import dataclass

from context_forge.evaluation.metrics import MetricResult


@dataclass(frozen=True)
class EvaluationCaseResult:
    repository_id: str
    task_id: str
    metric: MetricResult

    @property
    def f1(self) -> float:
        return self.metric.f1


@dataclass(frozen=True)
class EvaluationSummary:
    results: tuple[EvaluationCaseResult, ...]

    @property
    def case_count(self) -> int:
        return len(self.results)

    @property
    def repository_ids(self) -> tuple[str, ...]:
        return tuple(sorted({result.repository_id for result in self.results}))

    @property
    def repository_count(self) -> int:
        return len(self.repository_ids)

    @property
    def mean_f1(self) -> float:
        if not self.results:
            return 0.0
        return sum(result.f1 for result in self.results) / len(self.results)


@dataclass(frozen=True)
class RegressionResult:
    repository_id: str
    task_id: str
    current_f1: float
    baseline_f1: float
    delta: float
    regressed: bool


class RegressionEvaluator:
    """Aggregate evaluation results and detect metric regressions."""

    def summarize(
        self,
        results: tuple[EvaluationCaseResult, ...],
    ) -> EvaluationSummary:
        self._validate_unique_cases(results)
        return EvaluationSummary(results=results)

    def compare(
        self,
        current: EvaluationSummary,
        baseline: EvaluationSummary,
        *,
        tolerance: float = 0.0,
    ) -> tuple[RegressionResult, ...]:
        if tolerance < 0:
            raise ValueError("Regression tolerance must not be negative")

        baseline_by_case = {
            (result.repository_id, result.task_id): result.f1
            for result in baseline.results
        }

        comparisons: list[RegressionResult] = []

        for result in current.results:
            case_id = (result.repository_id, result.task_id)
            if case_id not in baseline_by_case:
                continue

            baseline_f1 = baseline_by_case[case_id]
            delta = result.f1 - baseline_f1

            comparisons.append(
                RegressionResult(
                    repository_id=result.repository_id,
                    task_id=result.task_id,
                    current_f1=result.f1,
                    baseline_f1=baseline_f1,
                    delta=delta,
                    regressed=delta < -tolerance,
                )
            )

        return tuple(comparisons)

    @staticmethod
    def _validate_unique_cases(
        results: tuple[EvaluationCaseResult, ...],
    ) -> None:
        case_ids = [(result.repository_id, result.task_id) for result in results]

        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Evaluation case IDs must be unique")
