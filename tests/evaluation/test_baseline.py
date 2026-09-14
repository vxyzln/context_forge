from pathlib import Path

import pytest

from context_forge.evaluation.baseline import (
    BASELINE_SCHEMA_VERSION,
    BaselineStore,
    EvaluationBaseline,
)
from context_forge.evaluation.metrics import MetricResult
from context_forge.evaluation.models import (
    EvaluationRepository,
    EvaluationSet,
    EvaluationTask,
)
from context_forge.evaluation.regression import EvaluationCaseResult


def make_result(
    repository_id: str,
    task_id: str,
    *,
    expected: int = 10,
    actual: int = 10,
    matched: int = 10,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        repository_id=repository_id,
        task_id=task_id,
        metric=MetricResult(
            expected=expected,
            actual=actual,
            matched=matched,
        ),
    )


def make_evaluation_set() -> EvaluationSet:
    return EvaluationSet(
        repositories=(
            EvaluationRepository(
                id="repo-a",
                name="Repository A",
                root_path=Path("/tmp/repo-a"),
                tasks=(
                    EvaluationTask(
                        id="task-a",
                        description="Task A",
                    ),
                    EvaluationTask(
                        id="task-b",
                        description="Task B",
                    ),
                ),
            ),
            EvaluationRepository(
                id="repo-b",
                name="Repository B",
                root_path=Path("/tmp/repo-b"),
                tasks=(
                    EvaluationTask(
                        id="task-c",
                        description="Task C",
                    ),
                ),
            ),
        )
    )


def test_baseline_serializes_results():
    baseline = EvaluationBaseline(
        results=(
            make_result("repo-b", "task-c", expected=8, actual=7, matched=6),
            make_result("repo-a", "task-a"),
        )
    )

    data = baseline.to_dict()

    assert data == {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "results": [
            {
                "repository_id": "repo-a",
                "task_id": "task-a",
                "metric": {
                    "expected": 10,
                    "actual": 10,
                    "matched": 10,
                },
            },
            {
                "repository_id": "repo-b",
                "task_id": "task-c",
                "metric": {
                    "expected": 8,
                    "actual": 7,
                    "matched": 6,
                },
            },
        ],
    }


def test_baseline_json_is_deterministic():
    baseline = EvaluationBaseline(
        results=(
            make_result("repo-b", "task-b"),
            make_result("repo-a", "task-c"),
        )
    )

    assert baseline.to_json() == baseline.to_json()


def test_baseline_json_orders_results_deterministically():
    baseline = EvaluationBaseline(
        results=(
            make_result("repo-z", "task-a"),
            make_result("repo-a", "task-z"),
            make_result("repo-a", "task-a"),
        )
    )

    json_output = baseline.to_json()

    assert json_output.index('"repository_id": "repo-a"') < (
        json_output.index('"repository_id": "repo-z"')
    )
    assert json_output.index('"task_id": "task-a"') < (
        json_output.index('"task_id": "task-z"')
    )


def test_baseline_round_trip_preserves_results():
    baseline = EvaluationBaseline(
        results=(
            make_result("repo-a", "task-a", expected=5, actual=4, matched=3),
            make_result("repo-b", "task-b", expected=8, actual=9, matched=7),
        )
    )

    restored = EvaluationBaseline.from_json(baseline.to_json())

    assert restored == baseline
    assert restored.results == baseline.results
    assert restored.mean_f1 == baseline.mean_f1


def test_baseline_rejects_invalid_schema_version():
    with pytest.raises(ValueError, match="unsupported baseline schema version"):
        EvaluationBaseline.from_dict(
            {
                "schema_version": 999,
                "results": [],
            }
        )


def test_baseline_rejects_non_object_data():
    with pytest.raises(TypeError, match="baseline data must be an object"):
        EvaluationBaseline.from_dict([])


def test_baseline_rejects_non_list_results():
    with pytest.raises(TypeError, match="baseline results must be a list"):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": {},
            }
        )


def test_baseline_rejects_non_object_result():
    with pytest.raises(
        TypeError,
        match="each baseline result must be an object",
    ):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": [None],
            }
        )


def test_baseline_rejects_empty_repository_id():
    with pytest.raises(ValueError, match="repository_id must be a non-empty string"):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": [
                    {
                        "repository_id": "",
                        "task_id": "task-a",
                        "metric": {
                            "expected": 1,
                            "actual": 1,
                            "matched": 1,
                        },
                    }
                ],
            }
        )


def test_baseline_rejects_invalid_metric_object():
    with pytest.raises(TypeError, match="metric must be an object"):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": [
                    {
                        "repository_id": "repo-a",
                        "task_id": "task-a",
                        "metric": None,
                    }
                ],
            }
        )


def test_baseline_rejects_non_integer_metric_counts():
    with pytest.raises(ValueError, match="metric counts must be integers"):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": [
                    {
                        "repository_id": "repo-a",
                        "task_id": "task-a",
                        "metric": {
                            "expected": 1.5,
                            "actual": 1,
                            "matched": 1,
                        },
                    }
                ],
            }
        )


def test_baseline_rejects_negative_metric_counts():
    with pytest.raises(ValueError, match="metric counts must be non-negative"):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": [
                    {
                        "repository_id": "repo-a",
                        "task_id": "task-a",
                        "metric": {
                            "expected": -1,
                            "actual": 1,
                            "matched": 1,
                        },
                    }
                ],
            }
        )


def test_baseline_rejects_invalid_matched_count():
    with pytest.raises(
        ValueError,
        match="matched count cannot exceed expected or actual count",
    ):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": [
                    {
                        "repository_id": "repo-a",
                        "task_id": "task-a",
                        "metric": {
                            "expected": 1,
                            "actual": 1,
                            "matched": 2,
                        },
                    }
                ],
            }
        )


def test_baseline_rejects_duplicate_cases():
    result = make_result("repo-a", "task-a")

    with pytest.raises(ValueError, match="Evaluation case IDs must be unique"):
        EvaluationBaseline.from_dict(
            {
                "schema_version": BASELINE_SCHEMA_VERSION,
                "results": [
                    {
                        "repository_id": result.repository_id,
                        "task_id": result.task_id,
                        "metric": {
                            "expected": 10,
                            "actual": 10,
                            "matched": 10,
                        },
                    },
                    {
                        "repository_id": result.repository_id,
                        "task_id": result.task_id,
                        "metric": {
                            "expected": 8,
                            "actual": 8,
                            "matched": 8,
                        },
                    },
                ],
            }
        )


def test_baseline_coverage_is_complete():
    evaluation_set = make_evaluation_set()

    baseline = EvaluationBaseline(
        results=(
            make_result("repo-a", "task-a"),
            make_result("repo-a", "task-b"),
            make_result("repo-b", "task-c"),
        )
    )

    coverage = baseline.coverage(evaluation_set)

    assert coverage.expected_case_count == 3
    assert coverage.actual_case_count == 3
    assert coverage.missing_cases == ()
    assert coverage.unexpected_cases == ()
    assert coverage.is_complete


def test_baseline_coverage_reports_missing_cases():
    evaluation_set = make_evaluation_set()

    baseline = EvaluationBaseline(
        results=(
            make_result("repo-a", "task-a"),
            make_result("repo-b", "task-c"),
        )
    )

    coverage = baseline.coverage(evaluation_set)

    assert coverage.expected_case_count == 3
    assert coverage.actual_case_count == 2
    assert coverage.missing_cases == (("repo-a", "task-b"),)
    assert coverage.unexpected_cases == ()
    assert not coverage.is_complete


def test_baseline_coverage_reports_unexpected_cases():
    evaluation_set = make_evaluation_set()

    baseline = EvaluationBaseline(
        results=(
            make_result("repo-a", "task-a"),
            make_result("repo-a", "task-b"),
            make_result("repo-b", "task-c"),
            make_result("repo-x", "task-x"),
        )
    )

    coverage = baseline.coverage(evaluation_set)

    assert coverage.expected_case_count == 3
    assert coverage.actual_case_count == 4
    assert coverage.missing_cases == ()
    assert coverage.unexpected_cases == (("repo-x", "task-x"),)
    assert not coverage.is_complete


def test_empty_baseline_has_zero_cases_and_zero_mean_f1():
    baseline = EvaluationBaseline(results=())

    assert baseline.case_count == 0
    assert baseline.mean_f1 == 0.0
    assert baseline.summary.case_count == 0


def test_baseline_store_saves_and_loads(tmp_path):
    path = tmp_path / "evaluation" / "baseline.json"

    baseline = EvaluationBaseline(
        results=(make_result("repo-a", "task-a", expected=7, actual=6, matched=5),)
    )

    store = BaselineStore()
    store.save(baseline, path)

    assert path.exists()
    assert EvaluationBaseline.from_json(path.read_text(encoding="utf-8")) == baseline

    loaded = store.load(path)

    assert loaded == baseline


def test_baseline_store_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "evaluation" / "baseline.json"

    baseline = EvaluationBaseline(results=(make_result("repo-a", "task-a"),))

    BaselineStore().save(baseline, path)

    assert path.exists()


def test_baseline_store_rejects_missing_file(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(ValueError, match="unable to read baseline"):
        BaselineStore().load(path)


def test_baseline_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid baseline JSON"):
        EvaluationBaseline.from_json("{not-valid-json")
