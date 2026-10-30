from pathlib import Path
from unittest.mock import MagicMock

import pytest

from context_forge.comparison.models import ComparisonState
from context_forge.config.project import (
    PackageBoundaryPolicy,
    PackageDependencyRule,
    StructuralRule,
)
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.pipeline.freshness import (
    FreshnessState,
    WorkflowFreshness,
)
from context_forge.query.post_change import (
    CheckExecutionStatus,
    run_post_change_verification,
)
from context_forge.query.regression_rules import RuleKind
from context_forge.reporting.contract import OperationStatus


@pytest.fixture
def post_change_project(tmp_path: Path) -> Project:
    root = tmp_path.resolve()
    proj = Project(name="post_change_proj", root_path=root, analysis_status="completed")

    f_app = File(
        project_id=proj.id,
        path=Path("src/app.py"),
        name="app.py",
        extension=".py",
    )
    f_service = File(
        project_id=proj.id,
        path=Path("src/service.py"),
        name="service.py",
        extension=".py",
    )
    f_test = File(
        project_id=proj.id,
        path=Path("tests/test_app.py"),
        name="test_app.py",
        extension=".py",
    )
    proj.add_file(f_app)
    proj.add_file(f_service)
    proj.add_file(f_test)

    s_app = Symbol(
        file_id=f_app.id,
        name="App",
        qualified_name="app.App",
        kind="class",
        start_line=1,
        end_line=20,
    )
    s_srv = Symbol(
        file_id=f_service.id,
        name="Service",
        qualified_name="service.Service",
        kind="class",
        start_line=1,
        end_line=25,
    )
    s_test = Symbol(
        file_id=f_test.id,
        name="test_app_run",
        qualified_name="tests.test_app.test_app_run",
        kind="function",
        start_line=1,
        end_line=10,
    )
    proj.add_symbol(s_app)
    proj.add_symbol(s_srv)
    proj.add_symbol(s_test)

    proj.add_relationship(
        Relationship(
            source_id=s_app.id,
            target_id=s_srv.id,
            relationship_type=RelationshipType.CALLS,
        )
    )
    proj.add_relationship(
        Relationship(
            source_id=s_test.id,
            target_id=s_app.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    return proj


def test_post_change_verification_basic_success(post_change_project: Project) -> None:
    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
    )

    assert report.repository_path == post_change_project.root_path.as_posix()
    assert report.change_set == ("src/app.py",)
    assert report.changeset_impact is not None
    assert report.comparison_performed is False
    assert report.comparison_status == "not_performed"
    assert any("Before-state was not provided" in lim for lim in report.limitations)

    assert len(report.suggested_checks) > 0
    for chk in report.suggested_checks:
        assert chk.executed is False
        assert chk.status == CheckExecutionStatus.SUGGESTED.value

    assert report.summary is not None
    assert report.summary.changed_files_count == 1
    assert report.summary.suggested_checks_count == len(report.suggested_checks)


def test_missing_before_state_is_never_fabricated(
    post_change_project: Project,
) -> None:
    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        before_state=None,
        freshness=WorkflowFreshness(state=FreshnessState.CURRENT, reason="current"),
    )

    assert report.comparison_performed is False
    assert report.comparison_status == "not_performed"
    assert report.structural_comparison is None
    assert any(
        "Before-state was not provided; structural comparison between versions was not performed"
        in lim
        for lim in report.limitations
    )
    assert report.outcome.status == OperationStatus.SUCCESS


def test_with_valid_before_state(post_change_project: Project) -> None:
    before_proj = Project(
        name="post_change_proj",
        root_path=post_change_project.root_path,
        analysis_status="completed",
    )
    f_before_app = File(
        project_id=before_proj.id,
        path=Path("src/app.py"),
        name="app.py",
        extension=".py",
    )
    before_proj.add_file(f_before_app)

    before_state = ComparisonState(
        state_id="before_v1",
        project=before_proj,
        repository_path=post_change_project.root_path,
    )

    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        before_state=before_state,
        freshness=WorkflowFreshness(state=FreshnessState.CURRENT, reason="current"),
    )

    assert report.comparison_performed is True
    assert report.comparison_status == "completed"
    assert report.structural_comparison is not None
    assert report.structural_comparison.outcome.is_success
    assert len(report.structural_comparison.added_files) >= 1
    assert report.outcome.status in {OperationStatus.SUCCESS, OperationStatus.PARTIAL}


def test_stale_repository_refresh_truthful(post_change_project: Project) -> None:
    stale_freshness = WorkflowFreshness(
        state=FreshnessState.STALE,
        reason="modified files",
        refreshed=False,
    )
    report_no_refresh = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        allow_refresh=False,
        freshness=stale_freshness,
    )
    assert report_no_refresh.refreshed is False
    assert any(
        "Repository analysis is stale and refresh was not performed" in lim
        for lim in report_no_refresh.limitations
    )
    assert any(d.code == "STALE_REPOSITORY" for d in report_no_refresh.diagnostics)

    refreshed_proj = Project(
        name="post_change_proj",
        root_path=post_change_project.root_path,
        analysis_status="completed",
    )
    f_refreshed = File(
        project_id=refreshed_proj.id,
        path=Path("src/app.py"),
        name="app.py",
        extension=".py",
    )
    refreshed_proj.add_file(f_refreshed)

    mock_guard = MagicMock()
    mock_guard.guard.return_value = WorkflowFreshness(
        state=FreshnessState.CURRENT,
        reason="refreshed_clean",
        refreshed=True,
        project=refreshed_proj,
    )

    report_refresh = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        allow_refresh=True,
        guard=mock_guard,
    )
    assert report_refresh.refreshed is True
    assert report_refresh.freshness_state == "current"


def test_refresh_failure_reported_truthfully(post_change_project: Project) -> None:
    mock_guard = MagicMock()
    mock_guard.guard.return_value = WorkflowFreshness(
        state=FreshnessState.INCOMPLETE,
        reason="refresh_failed: analyzer syntax error",
        refreshed=True,
        refresh_error="analyzer syntax error",
        analysis_status="failed",
    )

    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        allow_refresh=True,
        guard=mock_guard,
    )

    assert report.refreshed is True
    assert any(
        "Repository refresh issue: analyzer syntax error" in lim
        for lim in report.limitations
    )
    assert report.outcome.status == OperationStatus.INCOMPLETE


def test_suggested_checks_remain_strictly_unexecuted(
    post_change_project: Project,
) -> None:
    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        freshness=WorkflowFreshness(state=FreshnessState.CURRENT, reason="current"),
    )

    assert len(report.suggested_checks) > 0
    for chk in report.suggested_checks:
        assert chk.executed is False
        assert chk.status == "suggested"


def test_comparison_failure_propagates_to_overall_status(
    post_change_project: Project,
) -> None:
    other_proj = Project(
        name="other_repo",
        root_path=Path("/tmp/different_repo"),
        analysis_status="completed",
    )
    blocked_state = ComparisonState(
        state_id="blocked_state",
        project=other_proj,
        repository_path=Path("/tmp/different_repo"),
    )

    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        before_state=blocked_state,
        freshness=WorkflowFreshness(state=FreshnessState.CURRENT, reason="current"),
    )

    assert report.comparison_status == "blocked"
    assert report.outcome.status == OperationStatus.BLOCKED


def test_comparison_failure_cannot_be_overridden_by_clean_rules(
    post_change_project: Project,
) -> None:
    other_proj = Project(
        name="other_repo",
        root_path=Path("/tmp/different_repo"),
        analysis_status="completed",
    )
    blocked_state = ComparisonState(
        state_id="blocked_state",
        project=other_proj,
        repository_path=Path("/tmp/different_repo"),
    )

    clean_rule = StructuralRule(
        rule_id="clean-rule",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="src/app.py",
        target="tests/test_app.py",
    )

    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        before_state=blocked_state,
        rules=[clean_rule],
        freshness=WorkflowFreshness(state=FreshnessState.CURRENT, reason="current"),
    )

    assert report.regression_rules is not None
    assert report.regression_rules.no_violations_count == 1
    assert report.comparison_status == "blocked"
    assert report.outcome.status == OperationStatus.BLOCKED


def test_package_boundary_and_rules_integration(
    post_change_project: Project,
) -> None:
    policy = PackageBoundaryPolicy(
        rules=(
            PackageDependencyRule(
                source_package="src",
                target_package="service",
                policy="deny",
            ),
        )
    )

    rule = StructuralRule(
        rule_id="no-app-calls-service",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="app.App",
        target="service.Service",
        description="App must not depend on Service",
    )

    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        package_policy=policy,
        rules=[rule],
        freshness=WorkflowFreshness(state=FreshnessState.CURRENT, reason="current"),
    )

    assert report.regression_rules is not None
    assert report.regression_rules.violations_count == 1
    assert report.summary.rule_violations_count == 1
    assert report.outcome.status == OperationStatus.PARTIAL
    assert "findings: 1 rule violation(s)" in report.outcome.message


def test_partial_failure_isolation(post_change_project: Project) -> None:
    invalid_rule = StructuralRule(
        rule_id="bad-rule",
        kind="unsupported_kind",
        source="nonexistent",
    )

    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
        rules=[invalid_rule],
        freshness=WorkflowFreshness(state=FreshnessState.CURRENT, reason="current"),
    )

    assert report.regression_rules is not None
    assert report.regression_rules.unevaluable_count == 1
    assert report.summary.rule_unevaluable_count == 1
    assert report.changeset_impact is not None
    assert report.change_risk is not None


def test_missing_persisted_analysis_blocks_workflow(
    post_change_project: Project,
) -> None:
    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
    )

    assert report.outcome.status == OperationStatus.BLOCKED
    assert any("MISSING_ANALYSIS" in (d.code or "") for d in report.diagnostics)


def test_post_change_report_serialization(post_change_project: Project) -> None:
    report = run_post_change_verification(
        post_change_project,
        paths=["src/app.py"],
    )

    payload = report.to_dict()
    assert payload["repository_path"] == post_change_project.root_path.as_posix()
    assert payload["change_set"] == ["src/app.py"]
    assert "summary" in payload
    assert payload["summary"]["changed_files_count"] == 1
    assert payload["comparison_status"] == "not_performed"
    assert "outcome" in payload
