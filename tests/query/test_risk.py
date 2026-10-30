from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.comparison.models import (
    AmbiguousMatch,
    FileDiff,
    StructuralComparisonResult,
)
from context_forge.config.project import (
    PackageBoundaryPolicy,
    PackageDependencyRule,
)
from context_forge.main import main
from context_forge.models.directory import Directory
from context_forge.models.enums import DirectoryType, FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.pipeline.freshness import FreshnessState, WorkflowFreshness
from context_forge.query.project import ProjectQuery
from context_forge.query.risk import (
    RISK_REPORT_DISCLAIMER,
    ChangeRiskReport,
    InferredConcern,
    ObservedFact,
    RiskConcernCategory,
    RiskFactCategory,
    generate_change_risk_report,
)
from context_forge.reporting.contract import (
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)


def create_risk_fixture_project(root: Path) -> Project:
    project = Project(
        name="Risk Fixture Project",
        root_path=root.resolve(),
        analysis_status="analyzed",
    )

    d_src = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
        directory_type=DirectoryType.SOURCE,
    )
    d_core = Directory(
        project_id=project.id, path=Path("src/core"), name="core", parent_id=d_src.id
    )
    d_api = Directory(
        project_id=project.id, path=Path("src/api"), name="api", parent_id=d_src.id
    )
    d_tests = Directory(
        project_id=project.id,
        path=Path("tests"),
        name="tests",
        directory_type=DirectoryType.TESTS,
    )

    for d in (d_src, d_core, d_api, d_tests):
        project.add_directory(d)

    init_core = File(
        project_id=project.id,
        path=Path("src/core/__init__.py"),
        name="__init__.py",
        extension=".py",
        directory_id=d_core.id,
    )
    init_api = File(
        project_id=project.id,
        path=Path("src/api/__init__.py"),
        name="__init__.py",
        extension=".py",
        directory_id=d_api.id,
    )

    f_service = File(
        project_id=project.id,
        path=Path("src/core/service.py"),
        name="service.py",
        extension=".py",
        directory_id=d_core.id,
    )
    f_calc = File(
        project_id=project.id,
        path=Path("src/core/calculator.py"),
        name="calculator.py",
        extension=".py",
        directory_id=d_core.id,
    )
    f_util = File(
        project_id=project.id,
        path=Path("src/core/util.py"),
        name="util.py",
        extension=".py",
        directory_id=d_core.id,
    )
    f_routes = File(
        project_id=project.id,
        path=Path("src/api/routes.py"),
        name="routes.py",
        extension=".py",
        directory_id=d_api.id,
    )
    f_client = File(
        project_id=project.id,
        path=Path("src/api/client.py"),
        name="client.py",
        extension=".py",
        directory_id=d_api.id,
    )

    f_test_service = File(
        project_id=project.id,
        path=Path("tests/test_service.py"),
        name="test_service.py",
        extension=".py",
        file_type=FileType.TEST,
        directory_id=d_tests.id,
    )
    f_test_calc = File(
        project_id=project.id,
        path=Path("tests/test_calculator.py"),
        name="test_calculator.py",
        extension=".py",
        file_type=FileType.TEST,
        directory_id=d_tests.id,
    )

    for f in (
        init_core,
        init_api,
        f_service,
        f_calc,
        f_util,
        f_routes,
        f_client,
        f_test_service,
        f_test_calc,
    ):
        project.add_file(f)

    s_srv = Symbol(
        file_id=f_service.id,
        name="do_work",
        kind="function",
        start_line=10,
        end_line=15,
    )
    s_route = Symbol(
        file_id=f_routes.id,
        name="handle_request",
        kind="function",
        start_line=5,
        end_line=12,
    )
    project.add_symbol(s_srv)
    project.add_symbol(s_route)

    project.add_relationship(
        Relationship(
            source_id=f_test_service.id,
            target_id=f_service.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=f_routes.id,
            target_id=f_service.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=f_client.id,
            target_id=f_routes.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=f_service.id,
            target_id=f_util.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    return project


def test_01_complete_analysis_with_structural_changes(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    assert isinstance(report, ChangeRiskReport)
    assert report.directly_affected_count >= 1
    assert report.downstream_affected_count >= 1
    assert report.outcome.status == OperationStatus.SUCCESS


def test_02_change_affecting_multiple_components(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(
        proj, ["src/core/service.py", "src/core/calculator.py"]
    )

    assert report.directly_affected_count >= 2
    root_facts = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.CHANGED_ENTITY.value
    ]
    assert len(root_facts) == 2


def test_03_direct_vs_downstream_impact_classification(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    direct_facts = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.CHANGED_ENTITY.value
    ]
    downstream_facts = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.AFFECTED_COMPONENT.value
    ]

    assert any("service.py" in f.statement for f in direct_facts)
    assert any(
        "routes.py" in f.statement or "util.py" in f.statement for f in downstream_facts
    )


def test_04_overlapping_paths_to_same_affected_entity_deduplicated(
    tmp_path: Path,
) -> None:
    proj = create_risk_fixture_project(tmp_path)
    f_calc = next(f for f in proj.files if f.name == "calculator.py")
    f_routes = next(f for f in proj.files if f.name == "routes.py")

    proj.add_relationship(
        Relationship(
            source_id=f_routes.id,
            target_id=f_calc.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    report = generate_change_risk_report(
        proj, ["src/core/service.py", "src/core/calculator.py"]
    )

    downstream_routes = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.AFFECTED_COMPONENT.value
        and "routes.py" in (f.path or "")
    ]
    assert len(downstream_routes) == 1


def test_05_reuse_of_comparison_results(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)

    comparison = StructuralComparisonResult(
        before_state_id="state_1",
        after_state_id="state_2",
        repository_key=str(proj.root_path),
        outcome=OperationOutcome.success(),
        modified_files=(FileDiff(path="src/core/service.py", change_type="modified"),),
        added_files=(FileDiff(path="src/core/new_feature.py", change_type="added"),),
        limitations=("Historical state compared against commit HEAD",),
    )

    report = generate_change_risk_report(proj, [], comparison=comparison)

    assert "src/core/service.py" in report.change_inputs
    assert "src/core/new_feature.py" in report.change_inputs
    assert any("Historical state compared" in lim for lim in report.limitations)


def test_06_reuse_of_relationship_path_evidence(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    path_facts = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.DEPENDENCY_PATH.value
    ]
    assert len(path_facts) >= 1
    assert "Impact path" in path_facts[0].statement


def test_07_direct_test_associations_observed(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    test_facts = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.TEST_ASSOCIATION.value
        and "test_service.py" in (f.path or "")
    ]
    assert len(test_facts) == 1
    assert "Confirmed structural test suite" in test_facts[0].statement


def test_08_heuristic_test_associations_observed(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/calculator.py"])

    heuristic_facts = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.TEST_ASSOCIATION.value
        and "test_calculator.py" in (f.path or "")
    ]
    assert len(heuristic_facts) == 1
    assert "Heuristic test suite" in heuristic_facts[0].statement


def test_09_missing_or_unknown_test_associations(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/util.py"])

    unassociated_facts = [
        f
        for f in report.observed_facts
        if f.category == RiskFactCategory.TEST_ASSOCIATION.value
        and "util.py" in (f.entity_name or "")
    ]
    assert len(unassociated_facts) == 1
    assert report.unassociated_targets_count >= 1

    assert any(
        c.category == RiskConcernCategory.UNVERIFIED_AREA.value
        for c in report.inferred_concerns
    )


def test_10_suggested_verification_versus_observed_execution(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    for c in report.inferred_concerns:
        assert "executed" not in c.summary.lower()
    assert report.disclaimer == RISK_REPORT_DISCLAIMER


def test_11_stale_analysis_generates_concern_and_missing_evidence(
    tmp_path: Path,
) -> None:
    proj = create_risk_fixture_project(tmp_path)

    stale_wf = WorkflowFreshness(
        state=FreshnessState.STALE, reason="2 modified files detected"
    )
    with patch(
        "context_forge.pipeline.freshness.WorkflowFreshnessGuard.assess_freshness",
        return_value=stale_wf,
    ):
        report = generate_change_risk_report(proj, ["src/core/service.py"])

    assert report.freshness_state == "stale"
    assert any(
        c.category == RiskConcernCategory.STALE_ANALYSIS.value
        for c in report.inferred_concerns
    )
    assert any(m.category == "repository_freshness" for m in report.missing_evidence)


def test_12_incomplete_analysis_generates_concern_and_partial_status(
    tmp_path: Path,
) -> None:
    proj = create_risk_fixture_project(tmp_path)
    proj.analysis_status = "incomplete"
    proj.errors = ["Missing type stub"]

    report = generate_change_risk_report(proj, ["src/core/service.py"])

    assert report.outcome.status == OperationStatus.PARTIAL
    assert any(
        c.category == RiskConcernCategory.INCOMPLETE_ANALYSIS.value
        for c in report.inferred_concerns
    )
    assert any(m.category == "structural_graph" for m in report.missing_evidence)


def test_13_failed_upstream_evidence_sets_failed_status(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    proj.analysis_status = "failed"
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    assert report.outcome.status == OperationStatus.FAILED


def test_14_ambiguous_comparison_evidence(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    comparison = StructuralComparisonResult(
        before_state_id="state_1",
        after_state_id="state_2",
        repository_key=str(proj.root_path),
        outcome=OperationOutcome.success(),
        ambiguous_matches=(
            AmbiguousMatch(
                category="symbols",
                before_candidates=("pkg.old_func",),
                after_candidates=("pkg.new_func1", "pkg.new_func2"),
                reason="Multiple candidates with identical signature",
            ),
        ),
        limitations=("Ambiguous symbol match could not be resolved cleanly",),
    )

    report = generate_change_risk_report(
        proj, ["src/core/service.py"], comparison=comparison
    )
    assert any("Ambiguous symbol match" in lim for lim in report.limitations)


def test_15_observed_facts_clearly_distinguishable_from_inferred_concerns(
    tmp_path: Path,
) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    assert len(report.observed_facts) > 0
    assert len(report.inferred_concerns) > 0

    for f in report.observed_facts:
        assert isinstance(f, ObservedFact)
        assert f.statement
    for c in report.inferred_concerns:
        assert isinstance(c, InferredConcern)
        assert c.rationale
        assert len(c.supporting_fact_ids) > 0 or len(c.supporting_evidence) > 0


def test_16_every_inference_has_supporting_evidence(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    for c in report.inferred_concerns:
        assert len(c.supporting_fact_ids) > 0 or len(c.supporting_evidence) > 0


def test_17_missing_evidence_reported_honestly(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/util.py"])

    assert any(m.category == "test_associations" for m in report.missing_evidence)


def test_18_no_unsupported_risk_probability_or_defect_score(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    d = report.to_dict()
    assert "risk_score" not in d
    assert "defect_probability" not in d
    assert "failure_rate" not in d
    assert "percentage" not in d


def test_19_no_contradictory_duplicate_findings(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    fact_ids = [f.fact_id for f in report.observed_facts]
    assert len(fact_ids) == len(set(fact_ids))


def test_20_deterministic_ordering(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report1 = generate_change_risk_report(
        proj, ["src/core/service.py", "src/core/calculator.py"]
    )

    proj.relationships.reverse()
    report2 = generate_change_risk_report(
        proj, ["src/core/calculator.py", "src/core/service.py"]
    )

    assert [f.fact_id for f in report1.observed_facts] == [
        f.fact_id for f in report2.observed_facts
    ]
    assert [c.concern_id for c in report1.inferred_concerns] == [
        c.concern_id for c in report2.inferred_concerns
    ]


def test_21_cross_package_impact_detected(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    assert report.cross_package_impact_count >= 1
    assert any(
        c.category == RiskConcernCategory.CROSS_PACKAGE_IMPACT.value
        for c in report.inferred_concerns
    )


def test_22_package_policy_violation_in_risk_report(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    policy = PackageBoundaryPolicy(
        rules=(
            PackageDependencyRule(
                source_package="src/api",
                target_package="src/core",
                policy="deny",
                rule_id="NO_API_TO_CORE",
            ),
        )
    )
    report = generate_change_risk_report(proj, ["src/core/service.py"], policy=policy)

    violation_concerns = [
        c
        for c in report.inferred_concerns
        if c.category == RiskConcernCategory.POLICY_VIOLATION.value
    ]
    assert len(violation_concerns) >= 1
    assert violation_concerns[0].severity == DiagnosticSeverity.ERROR
    assert len(violation_concerns[0].supporting_fact_ids) >= 1
    fact_ids = {f.fact_id for f in report.observed_facts}
    assert all(fid in fact_ids for fid in violation_concerns[0].supporting_fact_ids)


def test_23_json_serialization(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/core/service.py"])

    data = report.to_dict()
    assert isinstance(data, dict)
    assert "observed_facts" in data
    assert "inferred_concerns" in data
    assert "missing_evidence" in data
    assert "directly_affected_count" in data
    assert "downstream_affected_count" in data
    assert "disclaimer" in data


def test_24_invalid_inputs_handling(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, [])

    assert report.outcome.status == OperationStatus.FAILED
    assert any(m.category == "inputs" for m in report.missing_evidence)


def test_25_unresolved_input_paths(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    report = generate_change_risk_report(proj, ["src/nonexistent/file.py"])

    assert any(
        c.category == RiskConcernCategory.UNRESOLVED_INPUT.value
        for c in report.inferred_concerns
    )
    assert any(m.category == "input_resolution" for m in report.missing_evidence)


def test_26_project_query_integration(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    query = ProjectQuery(proj)
    report = query.generate_change_risk_report(["src/core/service.py"])

    assert isinstance(report, ChangeRiskReport)
    assert report.directly_affected_count >= 1


def test_27_cli_risk_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_risk_fixture_project(tmp_path)

    with patch("context_forge.main.load_fresh_project", return_value=(proj, None)):
        main(["risk", "src/core/service.py", "--path", str(proj.root_path)])

    captured = capsys.readouterr()
    assert "Change inputs" in captured.out
    assert "Summary:" in captured.out
    assert "Inferred concerns:" in captured.out
    assert "Observed facts:" in captured.out
    assert "Disclaimer:" in captured.out


def test_28_cli_changeset_with_risk_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_risk_fixture_project(tmp_path)

    with patch("context_forge.main.load_fresh_project", return_value=(proj, None)):
        main(
            [
                "changeset",
                "src/core/service.py",
                "--risk",
                "--path",
                str(proj.root_path),
            ]
        )

    captured = capsys.readouterr()
    assert "Change-set paths" in captured.out
    assert "Change-risk report:" in captured.out
    assert "Inferred concerns" in captured.out


def test_29_cli_changeset_json_with_risk_flag(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)

    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", new_callable=StringIO) as mock_stdout,
    ):
        main(
            [
                "changeset",
                "src/core/service.py",
                "--risk",
                "--format",
                "json",
                "--path",
                str(proj.root_path),
            ]
        )

    data = json.loads(mock_stdout.getvalue().strip())
    assert "change_risk" in data
    assert "inferred_concerns" in data["change_risk"]
    assert "observed_facts" in data["change_risk"]


def test_30_ambiguous_package_policy_concern(tmp_path: Path) -> None:
    proj = create_risk_fixture_project(tmp_path)
    rule_allow = PackageDependencyRule(
        source_package="src/*",
        target_package="src/core",
        policy="allow",
        rule_id="ALLOW_WILDCARD",
    )
    rule_deny = PackageDependencyRule(
        source_package="src/api",
        target_package="*",
        policy="deny",
        rule_id="DENY_WILDCARD",
    )
    policy = PackageBoundaryPolicy(rules=(rule_allow, rule_deny))
    report = generate_change_risk_report(proj, ["src/core/service.py"], policy=policy)

    ambiguous_concerns = [
        c
        for c in report.inferred_concerns
        if c.concern_id == "ambiguous_package_policy"
    ]
    assert len(ambiguous_concerns) == 1
    assert ambiguous_concerns[0].severity == DiagnosticSeverity.WARNING
    assert "ambiguous policy definitions" in ambiguous_concerns[0].summary
    assert len(ambiguous_concerns[0].supporting_fact_ids) >= 1
