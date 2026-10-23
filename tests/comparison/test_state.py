from __future__ import annotations

from pathlib import Path

import pytest

from context_forge.comparison.models import ComparisonState, is_terminal_complete_status
from context_forge.comparison.service import compare_states, validate_comparison_states
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.pipeline.freshness import FreshnessState, WorkflowFreshness
from context_forge.reporting.contract import DiagnosticSeverity, OperationStatus
from context_forge.storage.cache import RepositoryCacheMetadata


def make_sample_project(
    name: str = "test-repo",
    root: Path | None = None,
    analysis_status: str = "analyzed",
    errors: list[str] | None = None,
) -> Project:
    root_path = root or Path("/fake/repo").resolve()
    proj = Project(
        name=name,
        root_path=root_path,
        analysis_status=analysis_status,
        errors=errors or [],
    )
    f = File(
        project_id=proj.id,
        path=Path("src/main.py"),
        name="main.py",
        extension=".py",
        size=100,
    )
    proj.add_file(f)
    return proj


def test_two_valid_identifiable_states() -> None:
    p1 = make_sample_project("repo1", Path("/repo/a"))
    p2 = make_sample_project("repo1", Path("/repo/a"))

    s1 = ComparisonState.from_project(p1, state_id="v1.0")
    s2 = ComparisonState.from_project(p2, state_id="v1.1")

    res = validate_comparison_states(s1, s2)
    assert res.is_valid is True
    assert res.is_complete is True
    assert res.outcome.is_success is True
    assert res.reason == "valid"
    assert s1.is_usable is True
    assert s2.is_usable is True


def test_missing_before_state() -> None:
    p2 = make_sample_project("repo1", Path("/repo/a"))
    s2 = ComparisonState.from_project(p2, state_id="v1.1")

    res = validate_comparison_states(None, s2)
    assert res.is_valid is False
    assert res.is_complete is False
    assert res.outcome.is_blocked is True
    assert res.reason == "missing_before_state"
    assert any(d.code == "MISSING_BEFORE_STATE" for d in res.outcome.diagnostics)


def test_missing_after_state() -> None:
    p1 = make_sample_project("repo1", Path("/repo/a"))
    s1 = ComparisonState.from_project(p1, state_id="v1.0")

    res = validate_comparison_states(s1, None)
    assert res.is_valid is False
    assert res.is_complete is False
    assert res.outcome.is_blocked is True
    assert res.reason == "missing_after_state"
    assert any(d.code == "MISSING_AFTER_STATE" for d in res.outcome.diagnostics)


@pytest.mark.parametrize(
    ("status", "expected_complete"),
    [
        ("analyzed", True),
        ("completed", True),
        ("  ANALYZED  ", True),
        ("COMPLETED", True),
        ("not_analyzed", False),
        ("analyzing", False),
        ("failed", False),
        ("partial", False),
        ("incomplete", False),
        ("unknown_status", False),
        ("", False),
        (None, False),
    ],
)
def test_terminal_analysis_statuses_contract(
    status: str | None, expected_complete: bool
) -> None:
    assert is_terminal_complete_status(status) is expected_complete

    p = make_sample_project("repo1", Path("/repo/a"), analysis_status=status or "")
    if status is None:
        p.analysis_status = None  # type: ignore[assignment]
    state = ComparisonState.from_project(p, state_id="s1")
    assert state.is_complete is expected_complete


def test_incomplete_state_due_to_recorded_errors() -> None:
    p = make_sample_project(
        "repo1",
        Path("/repo/a"),
        analysis_status="analyzed",
        errors=["SyntaxError in src/bad.py"],
    )
    state = ComparisonState.from_project(p, state_id="s1")
    assert state.is_complete is False

    p2 = make_sample_project("repo1", Path("/repo/a"), analysis_status="analyzed")
    state2 = ComparisonState.from_project(p2, state_id="s2")

    res = validate_comparison_states(state, state2)
    assert res.is_valid is True
    assert res.is_complete is False
    assert res.outcome.status == OperationStatus.INCOMPLETE
    assert any(d.code == "INCOMPLETE_BEFORE_STATE" for d in res.outcome.diagnostics)


def test_incomplete_after_state_due_to_errors() -> None:
    p1 = make_sample_project("repo1", Path("/repo/a"), analysis_status="analyzed")
    p2 = make_sample_project(
        "repo1",
        Path("/repo/a"),
        analysis_status="analyzed",
        errors=["SyntaxError: invalid syntax in b.py"],
    )

    s1 = ComparisonState.from_project(p1, state_id="s1")
    s2 = ComparisonState.from_project(p2, state_id="s2")

    res = validate_comparison_states(s1, s2)
    assert res.is_valid is True
    assert res.is_complete is False
    assert res.outcome.status == OperationStatus.INCOMPLETE
    assert any(d.code == "INCOMPLETE_AFTER_STATE" for d in res.outcome.diagnostics)
    assert "After-state analysis is incomplete or has errors" in res.outcome.limitations


@pytest.mark.parametrize(
    "freshness",
    [
        FreshnessState.CURRENT,
        FreshnessState.STALE,
        FreshnessState.INCOMPLETE,
        FreshnessState.INDETERMINATE,
    ],
)
def test_all_freshness_states_explicitly(freshness: FreshnessState) -> None:
    p1 = make_sample_project("repo1", Path("/repo/a"))
    p2 = make_sample_project("repo1", Path("/repo/a"))

    s1 = ComparisonState.from_project(p1, state_id="s1", freshness=freshness)
    s2 = ComparisonState.from_project(
        p2, state_id="s2", freshness=FreshnessState.CURRENT
    )

    val_res = validate_comparison_states(s1, s2)
    cmp_res = compare_states(s1, s2)

    # Validation and comparison results must agree on completeness
    assert val_res.is_complete == cmp_res.is_complete

    if freshness == FreshnessState.CURRENT:
        assert s1.is_complete is True
        assert val_res.is_complete is True
        assert val_res.outcome.is_success is True
    elif freshness == FreshnessState.INCOMPLETE:
        assert s1.is_complete is False
        assert val_res.is_complete is False
        assert any(
            d.code == "INCOMPLETE_FRESHNESS" for d in val_res.outcome.diagnostics
        )
    elif freshness == FreshnessState.INDETERMINATE:
        assert s1.is_complete is False
        assert val_res.is_complete is False
        assert any(
            d.code == "INDETERMINATE_FRESHNESS" for d in val_res.outcome.diagnostics
        )
    elif freshness == FreshnessState.STALE:
        assert s1.is_complete is False
        assert val_res.is_complete is False
        assert any(d.code == "STALE_STATE" for d in val_res.outcome.diagnostics)


def test_workflow_freshness_wrapper_handling() -> None:
    p1 = make_sample_project("repo1", Path("/repo/a"))
    p2 = make_sample_project("repo1", Path("/repo/a"))

    wf_incomplete = WorkflowFreshness(
        state=FreshnessState.INCOMPLETE, reason="Partial scan"
    )
    wf_current = WorkflowFreshness(state=FreshnessState.CURRENT, reason="Up to date")

    s1 = ComparisonState.from_project(p1, state_id="s1", freshness=wf_incomplete)
    s2 = ComparisonState.from_project(p2, state_id="s2", freshness=wf_current)

    val_res = validate_comparison_states(s1, s2)
    cmp_res = compare_states(s1, s2)

    assert s1.is_complete is False
    assert s2.is_complete is True
    assert val_res.is_complete is False
    assert cmp_res.is_complete is False
    assert any(d.code == "INCOMPLETE_FRESHNESS" for d in val_res.outcome.diagnostics)


def test_repository_identity_mismatch() -> None:
    p1 = make_sample_project("repo1", Path("/repo/alpha"))
    p2 = make_sample_project("repo2", Path("/repo/beta"))

    s1 = ComparisonState.from_project(p1, state_id="s1")
    s2 = ComparisonState.from_project(p2, state_id="s2")

    res = validate_comparison_states(s1, s2)
    assert res.is_valid is False
    assert res.outcome.is_blocked is True
    assert res.reason == "repository_mismatch"
    assert any(d.code == "REPOSITORY_MISMATCH" for d in res.outcome.diagnostics)
    assert any(
        d.severity == DiagnosticSeverity.BLOCKER for d in res.outcome.diagnostics
    )


def test_historical_state_freshness_rules() -> None:
    p_hist = make_sample_project("repo1", Path("/repo/a"))
    p_curr = make_sample_project("repo1", Path("/repo/a"))

    # Historical state permits STALE freshness without making it incomplete or warning
    s_hist_stale = ComparisonState.from_project(
        p_hist,
        state_id="commit-abc1234",
        is_historical=True,
        freshness=FreshnessState.STALE,
    )
    s_curr = ComparisonState.from_project(
        p_curr,
        state_id="working-tree",
        is_historical=False,
        freshness=FreshnessState.CURRENT,
    )

    res = validate_comparison_states(s_hist_stale, s_curr)
    assert s_hist_stale.is_complete is True
    assert res.is_valid is True
    assert res.is_complete is True
    assert not any(
        d.code == "STALE_STATE" and "before" in d.message.lower()
        for d in res.outcome.diagnostics
    )

    # But historical state with INCOMPLETE freshness MUST still be incomplete and reported!
    s_hist_incomplete = ComparisonState.from_project(
        p_hist,
        state_id="commit-abc1234",
        is_historical=True,
        freshness=FreshnessState.INCOMPLETE,
    )
    res_incomplete = validate_comparison_states(s_hist_incomplete, s_curr)
    assert s_hist_incomplete.is_complete is False
    assert res_incomplete.is_complete is False
    assert any(
        d.code == "INCOMPLETE_FRESHNESS" for d in res_incomplete.outcome.diagnostics
    )


def test_state_metadata_and_serialization() -> None:
    proj = make_sample_project("repo1", Path("/repo/a"))
    meta = RepositoryCacheMetadata(
        repository_key="/repo/a",
        project_id=proj.id,
    )
    state = ComparisonState.from_project(
        proj,
        state_id="v1.0",
        metadata=meta,
        source_label="baseline",
    )
    data = state.to_dict()
    assert data["state_id"] == "v1.0"
    assert data["source_label"] == "baseline"
    assert data["is_supplied"] is True
    assert data["is_usable"] is True
    assert data["is_complete"] is True
    assert data["files_count"] == 1
    assert data["repository_key"] == "/repo/a"


def test_unsupplied_empty_state_contract() -> None:
    empty_state = ComparisonState(project=None, state_id=None)
    assert empty_state.is_supplied is False
    assert empty_state.is_usable is False
    assert empty_state.is_complete is False


def test_missing_metadata_does_not_fabricate_certainty() -> None:
    proj = make_sample_project("repo1", Path("/repo/a"))
    state = ComparisonState(project=proj, state_id="s1", metadata=None)
    assert state.is_supplied is True
    assert state.is_usable is True
    assert state.repository_key == str(Path("/repo/a").resolve())
