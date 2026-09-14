from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from context_forge.evaluation.metrics import MetricResult
from context_forge.evaluation.models import EvaluationSet
from context_forge.evaluation.regression import (
    EvaluationCaseResult,
    EvaluationSummary,
    RegressionEvaluator,
)

BASELINE_SCHEMA_VERSION = 1
DEFAULT_BASELINE_PATH = Path("evaluation/baseline.json")


@dataclass(frozen=True)
class BaselineCoverage:
    expected_case_count: int
    actual_case_count: int
    missing_cases: tuple[tuple[str, str], ...]
    unexpected_cases: tuple[tuple[str, str], ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_cases and not self.unexpected_cases


@dataclass(frozen=True)
class EvaluationBaseline:
    results: tuple[EvaluationCaseResult, ...]

    @property
    def summary(self) -> EvaluationSummary:
        return RegressionEvaluator().summarize(self.results)

    @property
    def case_count(self) -> int:
        return len(self.results)

    @property
    def mean_f1(self) -> float:
        return self.summary.mean_f1

    def coverage(self, evaluation_set: EvaluationSet) -> BaselineCoverage:
        expected = {
            (repository.id, task.id)
            for repository in evaluation_set.repositories
            for task in repository.tasks
        }
        actual = {(result.repository_id, result.task_id) for result in self.results}

        return BaselineCoverage(
            expected_case_count=len(expected),
            actual_case_count=len(actual),
            missing_cases=tuple(sorted(expected - actual)),
            unexpected_cases=tuple(sorted(actual - expected)),
        )

    def to_dict(self) -> dict[str, Any]:
        results = sorted(
            self.results,
            key=lambda result: (result.repository_id, result.task_id),
        )

        return {
            "schema_version": BASELINE_SCHEMA_VERSION,
            "results": [
                {
                    "repository_id": result.repository_id,
                    "task_id": result.task_id,
                    "metric": {
                        "expected": result.metric.expected,
                        "actual": result.metric.actual,
                        "matched": result.metric.matched,
                    },
                }
                for result in results
            ],
        }

    def to_json(self) -> str:
        return (
            json.dumps(
                self.to_dict(),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationBaseline:
        if not isinstance(data, dict):
            raise TypeError("baseline data must be an object")

        if data.get("schema_version") != BASELINE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported baseline schema version: {data.get('schema_version')!r}"
            )

        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise TypeError("baseline results must be a list")

        results: list[EvaluationCaseResult] = []

        for raw_result in raw_results:
            if not isinstance(raw_result, dict):
                raise TypeError("each baseline result must be an object")

            repository_id = raw_result.get("repository_id")
            task_id = raw_result.get("task_id")
            metric = raw_result.get("metric")

            if not isinstance(repository_id, str) or not repository_id:
                raise ValueError("repository_id must be a non-empty string")

            if not isinstance(task_id, str) or not task_id:
                raise ValueError("task_id must be a non-empty string")

            if not isinstance(metric, dict):
                raise TypeError("metric must be an object")

            expected = metric.get("expected")
            actual = metric.get("actual")
            matched = metric.get("matched")

            if not all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in (expected, actual, matched)
            ):
                raise ValueError("metric counts must be integers")

            if expected < 0 or actual < 0 or matched < 0:
                raise ValueError("metric counts must be non-negative")

            if matched > expected or matched > actual:
                raise ValueError("matched count cannot exceed expected or actual count")

            results.append(
                EvaluationCaseResult(
                    repository_id=repository_id,
                    task_id=task_id,
                    metric=MetricResult(
                        expected=expected,
                        actual=actual,
                        matched=matched,
                    ),
                )
            )

        summary = RegressionEvaluator().summarize(tuple(results))

        return cls(results=summary.results)

    @classmethod
    def from_json(cls, content: str) -> EvaluationBaseline:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid baseline JSON") from exc

        return cls.from_dict(data)


class BaselineStore:
    def save(
        self,
        baseline: EvaluationBaseline,
        path: Path = DEFAULT_BASELINE_PATH,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(baseline.to_json(), encoding="utf-8")

    def load(
        self,
        path: Path = DEFAULT_BASELINE_PATH,
    ) -> EvaluationBaseline:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"unable to read baseline: {path}") from exc

        return EvaluationBaseline.from_json(content)
