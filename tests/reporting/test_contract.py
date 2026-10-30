from __future__ import annotations

import pytest

from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)
from context_forge.reporting.formatter import (
    format_diagnostic_line,
    render_outcome_text,
)


def test_operation_status_semantics() -> None:
    assert OperationStatus.SUCCESS.value == "success"
    assert OperationStatus.PARTIAL.value == "partial"
    assert OperationStatus.INCOMPLETE.value == "incomplete"
    assert OperationStatus.BLOCKED.value == "blocked"
    assert OperationStatus.FAILED.value == "failed"

    assert OperationStatus.SUCCESS.is_successful
    assert not OperationStatus.PARTIAL.is_successful
    assert not OperationStatus.INCOMPLETE.is_successful
    assert not OperationStatus.BLOCKED.is_successful
    assert not OperationStatus.FAILED.is_successful

    assert OperationStatus.FAILED.is_failure
    assert not OperationStatus.SUCCESS.is_failure

    assert OperationStatus.BLOCKED.is_blocked
    assert not OperationStatus.SUCCESS.is_blocked

    assert OperationStatus.PARTIAL.is_partial
    assert not OperationStatus.SUCCESS.is_partial

    assert OperationStatus.INCOMPLETE.is_incomplete
    assert not OperationStatus.SUCCESS.is_incomplete


def test_diagnostic_severity_semantics() -> None:
    assert DiagnosticSeverity.INFO.value == "info"
    assert DiagnosticSeverity.WARNING.value == "warning"
    assert DiagnosticSeverity.BLOCKER.value == "blocker"
    assert DiagnosticSeverity.ERROR.value == "error"

    assert not DiagnosticSeverity.INFO.is_blocking
    assert not DiagnosticSeverity.WARNING.is_blocking
    assert DiagnosticSeverity.BLOCKER.is_blocking
    assert DiagnosticSeverity.ERROR.is_blocking

    assert not DiagnosticSeverity.INFO.is_actionable
    assert DiagnosticSeverity.WARNING.is_actionable
    assert DiagnosticSeverity.BLOCKER.is_actionable
    assert DiagnosticSeverity.ERROR.is_actionable


def test_diagnostic_item_factories_and_serialization() -> None:
    info = DiagnosticItem.info("Repository scanned", code="INFO_SCAN")
    assert info.severity == DiagnosticSeverity.INFO
    assert info.message == "Repository scanned"
    assert info.code == "INFO_SCAN"

    warning = DiagnosticItem.warning(
        "Cache is stale",
        code="STALE_CACHE",
        path="src/main.py",
        line=10,
        column=2,
        source="cache",
        details={"age_seconds": 3600},
    )
    assert warning.severity == DiagnosticSeverity.WARNING
    assert warning.line == 10
    assert warning.column == 2
    assert warning.source == "cache"

    blocker = DiagnosticItem.blocker(
        "No persisted analysis found",
        code="MISSING_ANALYSIS",
    )
    assert blocker.severity == DiagnosticSeverity.BLOCKER

    error = DiagnosticItem.error(
        "Syntax error encountered",
        code="PARSE_ERROR",
        path="broken.py",
        line=15,
    )
    assert error.severity == DiagnosticSeverity.ERROR

    d_dict = warning.to_dict()
    assert d_dict == {
        "severity": "warning",
        "message": "Cache is stale",
        "code": "STALE_CACHE",
        "path": "src/main.py",
        "line": 10,
        "column": 2,
        "source": "cache",
        "details": {"age_seconds": 3600},
    }


def test_diagnostic_item_validation() -> None:
    with pytest.raises(ValueError, match="Diagnostic message cannot be empty"):
        DiagnosticItem(severity=DiagnosticSeverity.INFO, message="   ")

    item = DiagnosticItem(severity="warning", message="Something odd")
    assert item.severity == DiagnosticSeverity.WARNING


def test_operation_outcome_factories_and_properties() -> None:

    succ = OperationOutcome.success("Analysis complete")
    assert succ.is_success
    assert not succ.is_partial
    assert not succ.is_incomplete
    assert not succ.is_blocked
    assert not succ.is_failed
    assert not succ.has_warnings
    assert not succ.has_blockers
    assert not succ.has_errors
    assert succ.status == OperationStatus.SUCCESS

    warn_item = DiagnosticItem.warning("1 cycle detected")
    part = OperationOutcome.partial(
        "Analysis has warnings",
        diagnostics=[warn_item],
        limitations=["Package detection heuristic"],
    )
    assert part.is_partial
    assert not part.is_success
    assert part.has_warnings
    assert len(part.warnings) == 1
    assert part.warnings[0] == warn_item
    assert not part.has_blockers
    assert not part.has_errors

    inc = OperationOutcome.incomplete(
        "Project not analyzed",
        limitations=["Run analyze first"],
    )
    assert inc.is_incomplete
    assert not inc.is_success
    assert not inc.is_failed

    blk_item = DiagnosticItem.blocker("Analysis stale, refresh needed")
    blocked = OperationOutcome.blocked(
        "Operation blocked",
        diagnostics=[blk_item],
    )
    assert blocked.is_blocked
    assert not blocked.is_success
    assert blocked.has_blockers
    assert len(blocked.blockers) == 1

    err_item = DiagnosticItem.error("Parse syntax error", path="bad.py")
    failed = OperationOutcome.failed(
        "Analysis failed",
        diagnostics=[err_item],
    )
    assert failed.is_failed
    assert not failed.is_success
    assert failed.has_errors
    assert len(failed.errors) == 1


def test_operation_outcome_from_diagnostics_resolution() -> None:
    err = DiagnosticItem.error("Crash")
    blk = DiagnosticItem.blocker("Prerequisite missing")
    warn = DiagnosticItem.warning("Stale timestamp")
    info = DiagnosticItem.info("Processed 10 files")

    outcome_err = OperationOutcome.from_diagnostics([warn, err, blk])
    assert outcome_err.status == OperationStatus.FAILED
    assert outcome_err.has_errors
    assert outcome_err.has_blockers
    assert outcome_err.has_warnings

    outcome_blk = OperationOutcome.from_diagnostics([warn, blk, info])
    assert outcome_blk.status == OperationStatus.BLOCKED
    assert outcome_blk.has_blockers
    assert not outcome_blk.has_errors

    outcome_warn = OperationOutcome.from_diagnostics([info, warn])
    assert outcome_warn.status == OperationStatus.SUCCESS
    assert outcome_warn.is_success
    assert outcome_warn.has_warnings

    outcome_partial = OperationOutcome.from_diagnostics([info, warn], is_partial=True)
    assert outcome_partial.status == OperationStatus.PARTIAL
    assert not outcome_partial.is_success

    outcome_inc = OperationOutcome.from_diagnostics([info], is_incomplete=True)
    assert outcome_inc.status == OperationStatus.INCOMPLETE
    assert not outcome_inc.is_success

    outcome_clean = OperationOutcome.from_diagnostics([info])
    assert outcome_clean.status == OperationStatus.SUCCESS
    assert outcome_clean.is_success
    assert not outcome_clean.has_warnings


def test_operation_outcome_distinguishes_five_states() -> None:

    clean = OperationOutcome.from_diagnostics(
        [DiagnosticItem.info("Processed clean repository")]
    )
    assert clean.status == OperationStatus.SUCCESS
    assert clean.is_success
    assert not clean.has_warnings
    assert not clean.has_blockers
    assert not clean.has_errors

    with_warn = OperationOutcome.from_diagnostics(
        [
            DiagnosticItem.info("All 10 modules analyzed"),
            DiagnosticItem.warning(
                "Dependency cycle detected between a and b", code="CYCLE"
            ),
        ],
        is_partial=False,
    )
    assert with_warn.status == OperationStatus.SUCCESS
    assert with_warn.is_success
    assert with_warn.has_warnings
    assert not with_warn.has_blockers
    assert not with_warn.has_errors

    part = OperationOutcome.from_diagnostics(
        [DiagnosticItem.warning("Results truncated to limit 50", code="TRUNCATED")],
        is_partial=True,
    )
    assert part.status == OperationStatus.PARTIAL
    assert not part.is_success
    assert part.is_partial
    assert part.has_warnings

    blocked = OperationOutcome.from_diagnostics(
        [
            DiagnosticItem.blocker(
                "Ambiguous target: multiple matches", code="TARGET_AMBIGUOUS"
            )
        ]
    )
    assert blocked.status == OperationStatus.BLOCKED
    assert not blocked.is_success
    assert blocked.is_blocked
    assert blocked.has_blockers

    failed = OperationOutcome.from_diagnostics(
        [DiagnosticItem.error("Crash during AST parsing", code="PARSE_ERROR")]
    )
    assert failed.status == OperationStatus.FAILED
    assert not failed.is_success
    assert failed.is_failed
    assert failed.has_errors


def test_operation_outcome_to_dict_structure() -> None:
    warn = DiagnosticItem.warning(
        "Cycle found",
        code="CYCLE",
        path="pkg/a.py",
        line=5,
    )
    outcome = OperationOutcome.partial(
        "Completed with warnings",
        diagnostics=[warn],
        limitations=["Max 50 items displayed"],
        metadata={"run_id": "123"},
    )
    data = outcome.to_dict()

    assert data["status"] == "partial"
    assert data["is_success"] is False
    assert data["message"] == "Completed with warnings"
    assert data["summary"] == {
        "errors": 0,
        "blockers": 0,
        "warnings": 1,
        "info": 0,
        "limitations": 1,
        "total_diagnostics": 1,
    }
    assert len(data["diagnostics"]) == 1
    assert data["diagnostics"][0]["code"] == "CYCLE"
    assert data["limitations"] == ["Max 50 items displayed"]
    assert data["metadata"] == {"run_id": "123"}


def test_outcome_formatting_helpers() -> None:
    diag_full = DiagnosticItem.error(
        "Syntax error",
        code="SYNTAX",
        path="foo.py",
        line=12,
        column=4,
    )
    assert format_diagnostic_line(diag_full) == "[ERROR] foo.py:12:4: Syntax error"

    diag_code_only = DiagnosticItem.blocker(
        "Prerequisite missing",
        code="NO_INDEX",
    )
    assert (
        format_diagnostic_line(diag_code_only)
        == "[BLOCKER] (NO_INDEX) Prerequisite missing"
    )

    outcome = OperationOutcome.partial(
        "Some issues",
        diagnostics=[
            DiagnosticItem.blocker("Missing index", code="NO_INDEX"),
            DiagnosticItem.warning("Deprecated syntax", path="mod.py", line=1),
            DiagnosticItem.info("Analysis took 2s"),
        ],
        limitations=["Only Python 3 supported"],
    )
    lines = render_outcome_text(outcome)
    text = "\n".join(lines)

    assert "Outcome: PARTIAL - Some issues" in text
    assert "Blockers:" in text
    assert "[BLOCKER] (NO_INDEX) Missing index" in text
    assert "Warnings:" in text
    assert "[WARNING] mod.py:1: Deprecated syntax" in text
    assert "Information:" in text
    assert "[INFO] Analysis took 2s" in text
    assert "Limitations:" in text
    assert "- Only Python 3 supported" in text
