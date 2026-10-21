from __future__ import annotations

from context_forge.reporting.contract import (
    DiagnosticSeverity,
    OperationStatus,
)
from context_forge.reporting.errors import (
    BlockedOperationError,
    ContextForgeError,
    MissingAnalysisError,
    OperationalError,
    StaleAnalysisError,
)


def test_context_forge_error_subclasses_runtime_error() -> None:
    err = ContextForgeError("Something broke", code="ERR_CODE")
    assert isinstance(err, ValueError)
    assert str(err) == "Something broke"
    assert err.code == "ERR_CODE"
    assert err.severity == DiagnosticSeverity.ERROR
    assert err.outcome.status == OperationStatus.FAILED
    assert err.outcome.is_failed
    assert len(err.outcome.diagnostics) == 1
    assert err.diagnostic.code == "ERR_CODE"
    assert err.diagnostic.severity == DiagnosticSeverity.ERROR


def test_blocked_operation_error_outcome() -> None:
    blocked = BlockedOperationError(
        "Cannot inspect: target ambiguous",
        code="TARGET_AMBIGUOUS",
        details={"matches": 2},
    )
    assert isinstance(blocked, ContextForgeError)
    assert isinstance(blocked, ValueError)
    assert blocked.severity == DiagnosticSeverity.BLOCKER
    assert blocked.outcome.status == OperationStatus.BLOCKED
    assert blocked.outcome.is_blocked
    assert blocked.details == {"matches": 2}
    assert blocked.diagnostic.details == {"matches": 2}


def test_missing_analysis_error() -> None:
    err = MissingAnalysisError()
    assert isinstance(err, BlockedOperationError)
    assert isinstance(err, OperationalError)
    assert isinstance(err, ValueError)
    assert str(err) == "No persisted analysis found; run 'context-forge analyze' first"
    assert err.code == "MISSING_ANALYSIS"
    assert err.severity == DiagnosticSeverity.BLOCKER
    assert err.outcome.status == OperationStatus.BLOCKED


def test_stale_analysis_error() -> None:
    err = StaleAnalysisError()
    assert isinstance(err, BlockedOperationError)
    assert isinstance(err, OperationalError)
    assert isinstance(err, ValueError)
    assert (
        str(err)
        == "Repository analysis is stale; run 'context-forge analyze' to refresh"
    )
    assert err.code == "STALE_ANALYSIS"
    assert err.severity == DiagnosticSeverity.BLOCKER
    assert err.outcome.status == OperationStatus.BLOCKED


def test_error_to_dict_matches_outcome() -> None:
    err = OperationalError("Disk full", code="IO_DISK_FULL", path="/tmp/db")
    payload = err.to_dict()
    assert payload["status"] == "failed"
    assert payload["is_success"] is False
    assert payload["message"] == "Disk full"
    assert payload["diagnostics"][0]["code"] == "IO_DISK_FULL"
    assert payload["diagnostics"][0]["path"] == "/tmp/db"
