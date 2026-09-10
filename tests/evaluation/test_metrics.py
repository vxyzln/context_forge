import pytest

from context_forge.evaluation.metrics import MetricResult


def test_metric_result_stores_counts() -> None:
    result = MetricResult(
        expected=10,
        actual=8,
        matched=6,
    )

    assert result.expected == 10
    assert result.actual == 8
    assert result.matched == 6


def test_metric_result_calculates_precision() -> None:
    result = MetricResult(
        expected=10,
        actual=8,
        matched=6,
    )

    assert result.precision == pytest.approx(0.75)


def test_metric_result_calculates_recall() -> None:
    result = MetricResult(
        expected=10,
        actual=8,
        matched=6,
    )

    assert result.recall == pytest.approx(0.6)


def test_metric_result_calculates_f1() -> None:
    result = MetricResult(
        expected=10,
        actual=8,
        matched=6,
    )

    assert result.f1 == pytest.approx(0.6666666667)


def test_metric_result_handles_empty_expected_and_actual() -> None:
    result = MetricResult(
        expected=0,
        actual=0,
        matched=0,
    )

    assert result.precision == 1.0
    assert result.recall == 1.0
    assert result.f1 == 1.0


def test_metric_result_handles_expected_without_actual() -> None:
    result = MetricResult(
        expected=5,
        actual=0,
        matched=0,
    )

    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0


def test_metric_result_handles_actual_without_expected() -> None:
    result = MetricResult(
        expected=0,
        actual=5,
        matched=0,
    )

    assert result.precision == 0.0
    assert result.recall == 1.0
    assert result.f1 == 0.0
