from pathlib import Path

import pytest

from context_forge.config.project import StructuralRule
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.query.regression_rules import (
    RuleKind,
    RuleOutcome,
    evaluate_structural_rules,
)
from context_forge.reporting.contract import OperationStatus


@pytest.fixture
def sample_project(tmp_path: Path) -> Project:
    root = tmp_path.resolve()
    proj = Project(name="test_proj", root_path=root, analysis_status="completed")

    f_ui = File(
        project_id=proj.id,
        path=Path("src/ui/view.py"),
        name="view.py",
        extension=".py",
    )
    f_service = File(
        project_id=proj.id,
        path=Path("src/service/core.py"),
        name="core.py",
        extension=".py",
    )
    f_db = File(
        project_id=proj.id,
        path=Path("src/storage/db.py"),
        name="db.py",
        extension=".py",
    )
    proj.add_file(f_ui)
    proj.add_file(f_service)
    proj.add_file(f_db)

    s_view = Symbol(
        file_id=f_ui.id,
        name="View",
        qualified_name="ui.view.View",
        kind="class",
        start_line=10,
        end_line=25,
    )
    s_core = Symbol(
        file_id=f_service.id,
        name="CoreService",
        qualified_name="service.core.CoreService",
        kind="class",
        start_line=5,
        end_line=30,
    )
    s_db = Symbol(
        file_id=f_db.id,
        name="Database",
        qualified_name="storage.db.Database",
        kind="class",
        start_line=1,
        end_line=50,
    )
    proj.add_symbol(s_view)
    proj.add_symbol(s_core)
    proj.add_symbol(s_db)

    proj.add_relationship(
        Relationship(
            source_id=s_view.id,
            target_id=s_core.id,
            relationship_type=RelationshipType.CALLS,
        )
    )
    proj.add_relationship(
        Relationship(
            source_id=s_core.id,
            target_id=s_db.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    return proj


def test_rule_no_violation_detected(sample_project: Project) -> None:
    rule = StructuralRule(
        rule_id="no-ui-to-db",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="src/ui/*",
        target="src/storage/*",
        description="UI must not directly depend on storage",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.violations_count == 0
    assert report.unevaluable_count == 0
    assert report.no_violations_count == 1
    assert report.outcome.status == OperationStatus.SUCCESS
    res = report.results[0]
    assert res.outcome == RuleOutcome.NO_VIOLATION_DETECTED.value
    assert "No violation detected" in res.message


def test_rule_violation_detected_with_traceability(sample_project: Project) -> None:
    rule = StructuralRule(
        rule_id="no-service-to-storage",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="src/service/*",
        target="src/storage/*",
        description="Service should not depend directly on storage",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.violations_count == 1
    assert report.no_violations_count == 0
    assert report.unevaluable_count == 0
    assert report.outcome.status == OperationStatus.PARTIAL

    item = report.results[0]
    assert item.outcome == RuleOutcome.VIOLATION_DETECTED.value
    assert item.source_path == "src/service/core.py"
    assert item.line == 5
    assert item.target_path == "src/storage/db.py"
    assert len(item.evidence) == 1
    assert (
        "service.core.CoreService (src/service/core.py:5) --[imports]--> storage.db.Database"
        in item.evidence[0]
    )
    assert "service.core.CoreService" in item.affected_entities
    assert "storage.db.Database" in item.affected_entities


def test_rule_invalid_syntax_unevaluable(sample_project: Project) -> None:
    rule = StructuralRule(
        rule_id="invalid-rule",
        kind="unsupported_kind",
        source="src/ui/*",
        target="src/storage/*",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.unevaluable_count == 1
    assert report.violations_count == 0
    item = report.results[0]
    assert item.outcome == RuleOutcome.UNEVALUABLE.value
    assert "Unsupported or missing rule kind" in item.message


def test_rule_unknown_referenced_entity_unevaluable(sample_project: Project) -> None:
    rule = StructuralRule(
        rule_id="unknown-entity-rule",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="src/nonexistent/module.py",
        target="src/storage/*",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.unevaluable_count == 1
    item = report.results[0]
    assert item.outcome == RuleOutcome.UNEVALUABLE.value
    assert "could not be resolved" in item.message


def test_rule_ambiguous_referenced_entity_unevaluable(sample_project: Project) -> None:
    f_other = File(
        project_id=sample_project.id,
        path=Path("src/other.py"),
        name="other.py",
        extension=".py",
    )
    sample_project.add_file(f_other)
    sym_dup = Symbol(
        file_id=f_other.id,
        name="View",
        qualified_name="other.View",
        kind="class",
        start_line=1,
        end_line=10,
    )
    sample_project.add_symbol(sym_dup)

    rule = StructuralRule(
        rule_id="ambiguous-rule",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="View",
        target="src/storage/*",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.unevaluable_count == 1
    item = report.results[0]
    assert item.outcome == RuleOutcome.UNEVALUABLE.value
    assert "Ambiguous symbol reference" in item.message


def test_rule_incomplete_analysis_reported_as_unevaluable(
    sample_project: Project,
) -> None:
    sample_project.analysis_status = "incomplete"
    sample_project.errors.append("Syntax error in src/parser/extra.py")

    rule = StructuralRule(
        rule_id="ui-check",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="src/ui/*",
        target="src/storage/*",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.unevaluable_count == 1
    assert report.no_violations_count == 0
    item = report.results[0]
    assert item.outcome == RuleOutcome.UNEVALUABLE.value
    assert "incomplete" in item.message
    assert any("INCOMPLETE_ANALYSIS" in str(d) for d in report.diagnostics)


def test_rule_prohibited_relationship_type(sample_project: Project) -> None:
    inherits_rule = StructuralRule(
        rule_id="no-view-inherits-core",
        kind=RuleKind.PROHIBITED_RELATIONSHIP.value,
        source="ui.view.View",
        target="service.core.CoreService",
        relationship_type="inherits",
    )
    calls_rule = StructuralRule(
        rule_id="no-view-calls-core",
        kind=RuleKind.PROHIBITED_RELATIONSHIP.value,
        source="ui.view.View",
        target="service.core.CoreService",
        relationship_type="calls",
    )
    report = evaluate_structural_rules(sample_project, [inherits_rule, calls_rule])

    assert report.violations_count == 1
    assert report.no_violations_count == 1
    assert report.results[0].rule_id == "no-view-calls-core"
    assert report.results[0].outcome == RuleOutcome.VIOLATION_DETECTED.value
    assert report.results[1].rule_id == "no-view-inherits-core"
    assert report.results[1].outcome == RuleOutcome.NO_VIOLATION_DETECTED.value


def test_rule_isolated_component(sample_project: Project) -> None:
    rule = StructuralRule(
        rule_id="isolate-db",
        kind=RuleKind.ISOLATED_COMPONENT.value,
        source="src/storage/*",
        description="Storage should be isolated",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.violations_count == 1
    item = report.results[0]
    assert item.outcome == RuleOutcome.VIOLATION_DETECTED.value
    assert "Isolated component violated" in item.evidence[0]


def test_unmatched_wildcard_source_unevaluable(sample_project: Project) -> None:
    rule = StructuralRule(
        rule_id="unmatched-wildcard-src",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="src/nonexistent/*",
        target="src/storage/*",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.unevaluable_count == 1
    assert report.no_violations_count == 0
    assert report.violations_count == 0
    item = report.results[0]
    assert item.outcome == RuleOutcome.UNEVALUABLE.value
    assert "Wildcard pattern 'src/nonexistent/*' matched no entities" in item.message
    assert any(d.code == "UNMATCHED_WILDCARD" for d in report.diagnostics)


def test_unmatched_wildcard_target_unevaluable(sample_project: Project) -> None:
    rule = StructuralRule(
        rule_id="unmatched-wildcard-tgt",
        kind=RuleKind.PROHIBITED_DEPENDENCY.value,
        source="src/ui/*",
        target="src/nonexistent_target/*",
    )
    report = evaluate_structural_rules(sample_project, [rule])

    assert report.unevaluable_count == 1
    assert report.no_violations_count == 0
    assert report.violations_count == 0
    item = report.results[0]
    assert item.outcome == RuleOutcome.UNEVALUABLE.value
    assert (
        "Wildcard pattern 'src/nonexistent_target/*' matched no entities"
        in item.message
    )
    assert any(d.code == "UNMATCHED_WILDCARD" for d in report.diagnostics)


def test_deterministic_ordering_and_serialization(sample_project: Project) -> None:
    rules = [
        StructuralRule(
            rule_id="z_rule",
            kind=RuleKind.PROHIBITED_DEPENDENCY.value,
            source="src/ui/*",
            target="src/storage/*",
        ),
        StructuralRule(
            rule_id="a_rule",
            kind=RuleKind.PROHIBITED_DEPENDENCY.value,
            source="src/ui/*",
            target="src/storage/*",
        ),
    ]
    report = evaluate_structural_rules(sample_project, rules)
    assert report.results[0].rule_id == "a_rule"
    assert report.results[1].rule_id == "z_rule"

    payload = report.to_dict()
    assert payload["violations_count"] == 0
    assert payload["no_violations_count"] == 2
    assert len(payload["results"]) == 2
