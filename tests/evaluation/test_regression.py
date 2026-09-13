import pytest

from context_forge.evaluation.metrics import MetricResult
from context_forge.evaluation.regression import (
    EvaluationCaseResult,
    RegressionEvaluator,
)


def make_result(
    repository_id: str,
    task_id: str,
    f1: float,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        repository_id=repository_id,
        task_id=task_id,
        metric=MetricResult(
            expected=10,
            actual=10,
            matched=round(f1 * 10),
        ),
    )


def test_summary_aggregates_cases_and_repositories() -> None:
    evaluator = RegressionEvaluator()

    summary = evaluator.summarize(
        (
            make_result("repo-a", "task-1", 1.0),
            make_result("repo-a", "task-2", 0.8),
            make_result("repo-b", "task-1", 0.6),
        )
    )

    assert summary.case_count == 3
    assert summary.repository_count == 2
    assert summary.repository_ids == ("repo-a", "repo-b")
    assert summary.mean_f1 == pytest.approx(0.8)


def test_summary_rejects_duplicate_cases() -> None:
    evaluator = RegressionEvaluator()
    result = make_result("repo-a", "task-1", 1.0)

    with pytest.raises(ValueError, match="Evaluation case IDs must be unique"):
        evaluator.summarize((result, result))


def test_compare_detects_regression() -> None:
    evaluator = RegressionEvaluator()

    baseline = evaluator.summarize((make_result("repo-a", "task-1", 1.0),))
    current = evaluator.summarize((make_result("repo-a", "task-1", 0.6),))

    comparisons = evaluator.compare(current, baseline)

    assert len(comparisons) == 1
    assert comparisons[0].baseline_f1 == 1.0
    assert comparisons[0].current_f1 == 0.6
    assert comparisons[0].delta == pytest.approx(-0.4)
    assert comparisons[0].regressed is True


def test_compare_respects_tolerance() -> None:
    evaluator = RegressionEvaluator()

    baseline = evaluator.summarize((make_result("repo-a", "task-1", 1.0),))
    current = evaluator.summarize((make_result("repo-a", "task-1", 0.9),))

    comparisons = evaluator.compare(
        current,
        baseline,
        tolerance=0.1,
    )

    assert comparisons[0].regressed is False


def test_compare_ignores_new_cases() -> None:
    evaluator = RegressionEvaluator()

    baseline = evaluator.summarize((make_result("repo-a", "task-1", 1.0),))
    current = evaluator.summarize(
        (
            make_result("repo-a", "task-1", 1.0),
            make_result("repo-b", "task-1", 0.8),
        )
    )

    comparisons = evaluator.compare(current, baseline)

    assert len(comparisons) == 1
    assert comparisons[0].repository_id == "repo-a"


def test_negative_tolerance_is_rejected() -> None:
    evaluator = RegressionEvaluator()
    summary = evaluator.summarize(())

    with pytest.raises(ValueError, match="Regression tolerance"):
        evaluator.compare(summary, summary, tolerance=-0.1)


def test_empty_summary_is_supported() -> None:
    summary = RegressionEvaluator().summarize(())

    assert summary.case_count == 0
    assert summary.repository_count == 0
    assert summary.repository_ids == ()
    assert summary.mean_f1 == 0.0
