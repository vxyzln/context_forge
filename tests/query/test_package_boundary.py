"""Tests for package-boundary analysis and policy evaluation."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.config.project import (
    PackageBoundaryPolicy,
    PackageDependencyRule,
)
from context_forge.config.validation import (
    ConfigurationValidationError,
    validate_project_config,
)
from context_forge.main import main
from context_forge.models.directory import Directory
from context_forge.models.enums import DirectoryType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.query.package_boundary import (
    PackageBoundaryReport,
    analyze_package_boundaries,
)
from context_forge.query.project import ProjectQuery
from context_forge.reporting.contract import OperationStatus


def create_multi_package_project(root: Path) -> Project:
    """Fixture project containing multiple conventional packages and non-package files:

    Packages:
      - src/pkg_a (with __init__.py, mod_a.py)
      - src/pkg_b (with __init__.py, mod_b.py)
      - src/pkg_c (with __init__.py, mod_c.py)

    Non-package:
      - scripts/standalone.py (no __init__.py in scripts)
    """
    project = Project(
        name="Multi-Package Test Project",
        root_path=root.resolve(),
        analysis_status="analyzed",
    )

    d_src = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
        directory_type=DirectoryType.SOURCE,
    )
    d_pkg_a = Directory(
        project_id=project.id, path=Path("src/pkg_a"), name="pkg_a", parent_id=d_src.id
    )
    d_pkg_b = Directory(
        project_id=project.id, path=Path("src/pkg_b"), name="pkg_b", parent_id=d_src.id
    )
    d_pkg_c = Directory(
        project_id=project.id, path=Path("src/pkg_c"), name="pkg_c", parent_id=d_src.id
    )
    d_scripts = Directory(project_id=project.id, path=Path("scripts"), name="scripts")

    for d in (d_src, d_pkg_a, d_pkg_b, d_pkg_c, d_scripts):
        project.add_directory(d)

    # Initializers defining conventional packages
    init_a = File(
        project_id=project.id,
        path=Path("src/pkg_a/__init__.py"),
        name="__init__.py",
        extension=".py",
        directory_id=d_pkg_a.id,
    )
    init_b = File(
        project_id=project.id,
        path=Path("src/pkg_b/__init__.py"),
        name="__init__.py",
        extension=".py",
        directory_id=d_pkg_b.id,
    )
    init_c = File(
        project_id=project.id,
        path=Path("src/pkg_c/__init__.py"),
        name="__init__.py",
        extension=".py",
        directory_id=d_pkg_c.id,
    )

    # Modules
    mod_a = File(
        project_id=project.id,
        path=Path("src/pkg_a/mod_a.py"),
        name="mod_a.py",
        extension=".py",
        directory_id=d_pkg_a.id,
    )
    mod_a2 = File(
        project_id=project.id,
        path=Path("src/pkg_a/mod_a2.py"),
        name="mod_a2.py",
        extension=".py",
        directory_id=d_pkg_a.id,
    )
    mod_b = File(
        project_id=project.id,
        path=Path("src/pkg_b/mod_b.py"),
        name="mod_b.py",
        extension=".py",
        directory_id=d_pkg_b.id,
    )
    mod_c = File(
        project_id=project.id,
        path=Path("src/pkg_c/mod_c.py"),
        name="mod_c.py",
        extension=".py",
        directory_id=d_pkg_c.id,
    )
    standalone = File(
        project_id=project.id,
        path=Path("scripts/standalone.py"),
        name="standalone.py",
        extension=".py",
        directory_id=d_scripts.id,
    )

    for f in (init_a, init_b, init_c, mod_a, mod_a2, mod_b, mod_c, standalone):
        project.add_file(f)

    # Symbols
    sym_a = Symbol(
        file_id=mod_a.id,
        name="func_a",
        qualified_name="pkg_a.mod_a.func_a",
        kind="function",
        start_line=10,
        end_line=15,
    )
    sym_b = Symbol(
        file_id=mod_b.id,
        name="func_b",
        qualified_name="pkg_b.mod_b.func_b",
        kind="function",
        start_line=20,
        end_line=25,
    )
    project.add_symbol(sym_a)
    project.add_symbol(sym_b)

    # 1. Internal dependency within pkg_a: mod_a2 -> mod_a
    project.add_relationship(
        Relationship(
            source_id=mod_a2.id,
            target_id=mod_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    # 2. Cross-package dependency: pkg_a (mod_a) -> pkg_b (mod_b)
    project.add_relationship(
        Relationship(
            source_id=mod_a.id,
            target_id=mod_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    # 3. Repeated cross-package dependency: pkg_a (sym_a) -> pkg_b (sym_b)
    project.add_relationship(
        Relationship(
            source_id=sym_a.id,
            target_id=sym_b.id,
            relationship_type=RelationshipType.CALLS,
        )
    )

    # 4. Reverse cross-package dependency: pkg_b (mod_b) -> pkg_c (mod_c)
    project.add_relationship(
        Relationship(
            source_id=mod_b.id,
            target_id=mod_c.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    # 5. Dependency involving standalone non-package file: standalone -> mod_a
    project.add_relationship(
        Relationship(
            source_id=standalone.id,
            target_id=mod_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    return project


def test_01_internal_package_dependency_not_cross_package(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    # mod_a2 -> mod_a is internal to src/pkg_a
    assert report.internal_dependencies_count >= 1
    internal_pairs = [
        (d.source_package, d.target_package)
        for d in report.cross_package_dependencies
        if d.source_package == d.target_package
    ]
    assert len(internal_pairs) == 0


def test_02_resolved_dependency_crosses_two_packages(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    cross_pairs = [
        (d.source_package, d.target_package) for d in report.cross_package_dependencies
    ]
    assert ("src/pkg_a", "src/pkg_b") in cross_pairs


def test_03_dependency_direction_is_importer_to_imported(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    dep = next(
        d
        for d in report.cross_package_dependencies
        if d.source_package == "src/pkg_a"
        and d.target_package == "src/pkg_b"
        and d.source_file_path == "src/pkg_a/mod_a.py"
    )
    assert dep.direction == "source_to_target"
    assert dep.source_file_path == "src/pkg_a/mod_a.py"
    assert dep.target_file_path == "src/pkg_b/mod_b.py"


def test_04_dependencies_in_opposite_directions(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    # Add reverse edge: pkg_b -> pkg_a
    mod_b = next(f for f in proj.files if f.name == "mod_b.py")
    mod_a = next(f for f in proj.files if f.name == "mod_a.py")
    proj.add_relationship(
        Relationship(
            source_id=mod_b.id,
            target_id=mod_a.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    report = analyze_package_boundaries(proj)
    cross_pairs = {
        (d.source_package, d.target_package) for d in report.cross_package_dependencies
    }
    assert ("src/pkg_a", "src/pkg_b") in cross_pairs
    assert ("src/pkg_b", "src/pkg_a") in cross_pairs


def test_05_source_and_target_package_identities(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    packages = set(report.packages)
    assert "src/pkg_a" in packages
    assert "src/pkg_b" in packages
    assert "src/pkg_c" in packages


def test_06_traceable_source_and_target_entities(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    call_dep = next(
        d for d in report.cross_package_dependencies if d.relationship_type == "calls"
    )
    assert call_dep.source_entity_name == "func_a"
    assert call_dep.target_entity_name == "func_b"
    assert call_dep.source_file_path == "src/pkg_a/mod_a.py"
    assert call_dep.target_file_path == "src/pkg_b/mod_b.py"


def test_07_relationship_evidence_string(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    dep = report.cross_package_dependencies[0]
    assert "Confirmed graph relationship" in dep.evidence
    assert dep.source_package in dep.evidence
    assert dep.target_package in dep.evidence


def test_08_repeated_cross_package_patterns_aggregation(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    patterns = report.repeated_patterns
    assert len(patterns) >= 1
    # Check that patterns are grouped by (source_package, target_package, relationship_type)
    for p in patterns:
        assert p.count == len(p.dependencies)
        assert p.count > 0


def test_09_repeated_patterns_correct_counts(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    mod_a2 = next(f for f in proj.files if f.name == "mod_a2.py")
    mod_b = next(f for f in proj.files if f.name == "mod_b.py")
    # Add a second imports relationship from pkg_a to pkg_b
    proj.add_relationship(
        Relationship(
            source_id=mod_a2.id,
            target_id=mod_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    report = analyze_package_boundaries(proj)
    pkg_a_to_b_imports = next(
        p
        for p in report.repeated_patterns
        if p.source_package == "src/pkg_a"
        and p.target_package == "src/pkg_b"
        and p.relationship_type == "imports"
    )
    assert pkg_a_to_b_imports.count == 2


def test_10_no_double_counting_of_same_relationship(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    mod_a = next(f for f in proj.files if f.name == "mod_a.py")
    mod_b = next(f for f in proj.files if f.name == "mod_b.py")
    # Add identical duplicate relationship
    proj.add_relationship(
        Relationship(
            source_id=mod_a.id,
            target_id=mod_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    report = analyze_package_boundaries(proj)
    # The duplicate must be deduplicated
    pkg_a_to_b_imports = [
        d
        for d in report.cross_package_dependencies
        if d.source_package == "src/pkg_a"
        and d.target_package == "src/pkg_b"
        and d.relationship_type == "imports"
    ]
    assert len(pkg_a_to_b_imports) == 1


def test_11_deterministic_aggregate_ordering(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report1 = analyze_package_boundaries(proj)

    # Reverse relationships order in project
    proj.relationships.reverse()
    report2 = analyze_package_boundaries(proj)

    assert [p.to_dict() for p in report1.repeated_patterns] == [
        p.to_dict() for p in report2.repeated_patterns
    ]
    assert [d.to_dict() for d in report1.cross_package_dependencies] == [
        d.to_dict() for d in report2.cross_package_dependencies
    ]


def test_12_cross_package_dependency_with_no_policy_is_unrestricted(
    tmp_path: Path,
) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj, policy=None)

    assert not report.policy_evaluated
    assert len(report.policy_violations) == 0
    for dep in report.cross_package_dependencies:
        assert dep.policy_status == "unrestricted"
        assert dep.violated_rule_id is None


def test_13_allowed_dependency_under_explicit_policy(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    policy = PackageBoundaryPolicy(
        rules=(
            PackageDependencyRule(
                source_package="src/pkg_a", target_package="src/pkg_b", policy="allow"
            ),
        ),
        default_policy="deny",
    )
    report = analyze_package_boundaries(proj, policy=policy)

    assert report.policy_evaluated
    dep = next(
        d
        for d in report.cross_package_dependencies
        if d.source_package == "src/pkg_a" and d.target_package == "src/pkg_b"
    )
    assert dep.policy_status == "allowed"


def test_14_prohibited_dependency_reported_as_violation(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    policy = PackageBoundaryPolicy(
        rules=(
            PackageDependencyRule(
                source_package="src/pkg_a",
                target_package="src/pkg_b",
                policy="deny",
                description="pkg_a must not import pkg_b",
            ),
        ),
        default_policy="allow",
    )
    report = analyze_package_boundaries(proj, policy=policy)

    assert report.policy_evaluated
    assert len(report.policy_violations) >= 1
    violation = report.policy_violations[0]
    assert violation.source_package == "src/pkg_a"
    assert violation.target_package == "src/pkg_b"
    assert "prohibited by rule" in violation.message


def test_15_violation_identifies_rule_and_relationship_evidence(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    rule = PackageDependencyRule(
        source_package="src/pkg_a",
        target_package="src/pkg_b",
        policy="deny",
        rule_id="RULE-001",
    )
    policy = PackageBoundaryPolicy(rules=(rule,))
    report = analyze_package_boundaries(proj, policy=policy)

    violation = next(v for v in report.policy_violations if v.rule_id == "RULE-001")
    assert violation.rule_id == "RULE-001"
    assert "Confirmed graph relationship" in violation.evidence


def test_16_invalid_policy_configuration_raises_error() -> None:
    # Test invalid config dictionary
    with pytest.raises(
        ConfigurationValidationError, match="missing or invalid 'source'"
    ):
        validate_project_config({"packages": {"rules": [{"target": "pkg_b"}]}})

    with pytest.raises(ConfigurationValidationError, match="invalid policy"):
        validate_project_config(
            {
                "packages": {
                    "rules": [
                        {
                            "source": "pkg_a",
                            "target": "pkg_b",
                            "policy": "invalid_policy",
                        }
                    ]
                }
            }
        )

    with pytest.raises(ConfigurationValidationError, match="format 'source -> target'"):
        validate_project_config(
            {"packages": {"deny": ["invalid_format_without_arrow"]}}
        )


def test_17_missing_source_package_reported_as_unclassified(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    # standalone.py -> mod_a: standalone.py is not in a package with __init__.py
    unclassified = [
        u
        for u in report.unclassified_dependencies
        if u.source_file_path == "scripts/standalone.py"
    ]
    assert len(unclassified) == 1
    assert (
        "Source 'scripts/standalone.py' does not belong to a package"
        in unclassified[0].reason
    )


def test_18_missing_target_package_reported_as_unclassified(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    mod_a = next(f for f in proj.files if f.name == "mod_a.py")
    standalone = next(f for f in proj.files if f.name == "standalone.py")
    # Add dependency pointing to standalone: mod_a -> standalone
    proj.add_relationship(
        Relationship(
            source_id=mod_a.id,
            target_id=standalone.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    report = analyze_package_boundaries(proj)
    unclassified = [
        u
        for u in report.unclassified_dependencies
        if u.target_file_path == "scripts/standalone.py"
    ]
    assert len(unclassified) == 1
    assert (
        "Target 'scripts/standalone.py' does not belong to a package"
        in unclassified[0].reason
    )


def test_19_namespace_package_limitation_disclosed(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj)

    assert any(
        "namespace packages without __init__.py are not inventoried" in lim
        for lim in report.limitations
    )


def test_20_unresolved_imports_excluded_from_confirmed_violations(
    tmp_path: Path,
) -> None:
    proj = create_multi_package_project(tmp_path)
    # Even under strict deny-all policy, unclassified or unresolved imports do not produce violations
    policy = PackageBoundaryPolicy(rules=(), default_policy="deny")
    report = analyze_package_boundaries(proj, policy=policy)

    # Violations must only be from resolved cross-package dependencies
    for v in report.policy_violations:
        assert v.source_package is not None
        assert v.target_package is not None


def test_21_incomplete_analysis_adds_limitation_and_diagnostic(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    proj.analysis_status = "partial"
    proj.errors = ["Syntax error in some_module.py"]

    policy = PackageBoundaryPolicy(
        rules=(
            PackageDependencyRule(
                source_package="src/pkg_a", target_package="src/pkg_b", policy="deny"
            ),
        )
    )
    report = analyze_package_boundaries(proj, policy=policy)

    assert report.outcome.status == OperationStatus.PARTIAL
    assert any(
        "Repository analysis status is 'partial'" in lim for lim in report.limitations
    )
    assert any(d.code == "INCOMPLETE_POLICY_EVALUATION" for d in report.diagnostics)


def test_22_failed_analysis_returns_failed_status(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    proj.analysis_status = "failed"
    report = analyze_package_boundaries(proj)

    assert report.outcome.status == OperationStatus.FAILED


def test_23_output_limits_and_truncation(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    report = analyze_package_boundaries(proj, limit=1)

    assert report.truncated
    assert report.total_cross_package_count > 1
    assert len(report.cross_package_dependencies) == 1
    assert any("display was truncated to 1" in lim for lim in report.limitations)


def test_24_json_serialization(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    policy = PackageBoundaryPolicy(
        rules=(
            PackageDependencyRule(
                source_package="src/pkg_a", target_package="src/pkg_b", policy="deny"
            ),
        )
    )
    report = analyze_package_boundaries(proj, policy=policy)

    data = report.to_dict()
    assert isinstance(data, dict)
    assert "cross_package_dependencies" in data
    assert "repeated_patterns" in data
    assert "unclassified_dependencies" in data
    assert "policy_violations" in data
    assert "total_cross_package_count" in data


def test_25_project_query_integration(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)
    query = ProjectQuery(proj)
    report = query.analyze_package_boundaries()

    assert isinstance(report, PackageBoundaryReport)
    assert report.total_cross_package_count >= 1


def test_26_cli_package_boundaries_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_multi_package_project(tmp_path)

    with patch("context_forge.main.load_fresh_project", return_value=(proj, None)):
        main(["package-boundaries", str(proj.root_path)])

    captured = capsys.readouterr()
    assert "Packages detected" in captured.out
    assert "src/pkg_a" in captured.out
    assert "Cross-package dependencies" in captured.out


def test_27_cli_package_boundaries_json_format(tmp_path: Path) -> None:
    proj = create_multi_package_project(tmp_path)

    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", new_callable=StringIO) as mock_stdout,
    ):
        main(["package-boundaries", str(proj.root_path), "--format", "json"])

    data = json.loads(mock_stdout.getvalue().strip())
    assert "cross_package_dependencies" in data
    assert "total_cross_package_count" in data


def test_28_conflicting_overlapping_wildcard_rules_reported_as_ambiguous(
    tmp_path: Path,
) -> None:
    proj = create_multi_package_project(tmp_path)
    # Rule 1 allows src/* -> src/pkg_b; Rule 2 denies src/pkg_a -> *
    rule_allow = PackageDependencyRule(
        source_package="src/*",
        target_package="src/pkg_b",
        policy="allow",
        rule_id="ALLOW_WILDCARD",
    )
    rule_deny = PackageDependencyRule(
        source_package="src/pkg_a",
        target_package="*",
        policy="deny",
        rule_id="DENY_WILDCARD",
    )
    policy = PackageBoundaryPolicy(rules=(rule_allow, rule_deny))

    # Evaluate directly
    status, matched_rule = policy.evaluate("src/pkg_a", "src/pkg_b")
    assert status == "ambiguous"
    assert matched_rule is None

    # Run boundary analysis
    report = analyze_package_boundaries(proj, policy=policy)
    ambiguous_deps = [
        d for d in report.cross_package_dependencies if d.policy_status == "ambiguous"
    ]
    assert len(ambiguous_deps) >= 1
    assert any(
        d.source_package == "src/pkg_a" and d.target_package == "src/pkg_b"
        for d in ambiguous_deps
    )
    assert any(d.code == "AMBIGUOUS_POLICY_EVALUATION" for d in report.diagnostics)
    assert any("Ambiguous package policy detected" in lim for lim in report.limitations)
    assert report.outcome.status == OperationStatus.PARTIAL


def test_29_reversing_conflicting_wildcard_rules_produces_identical_ambiguity(
    tmp_path: Path,
) -> None:
    proj = create_multi_package_project(tmp_path)
    rule_allow = PackageDependencyRule(
        source_package="src/*",
        target_package="src/pkg_b",
        policy="allow",
        rule_id="ALLOW_WILDCARD",
    )
    rule_deny = PackageDependencyRule(
        source_package="src/pkg_a",
        target_package="*",
        policy="deny",
        rule_id="DENY_WILDCARD",
    )

    # Order 1: allow first, deny second
    policy1 = PackageBoundaryPolicy(rules=(rule_allow, rule_deny))
    status1, _ = policy1.evaluate("src/pkg_a", "src/pkg_b")
    report1 = analyze_package_boundaries(proj, policy=policy1)

    # Order 2: deny first, allow second
    policy2 = PackageBoundaryPolicy(rules=(rule_deny, rule_allow))
    status2, _ = policy2.evaluate("src/pkg_a", "src/pkg_b")
    report2 = analyze_package_boundaries(proj, policy=policy2)

    # Reversing rule order must not change the outcome
    assert status1 == status2 == "ambiguous"
    assert [d.policy_status for d in report1.cross_package_dependencies] == [
        d.policy_status for d in report2.cross_package_dependencies
    ]
    assert report1.outcome.status == report2.outcome.status == OperationStatus.PARTIAL


def test_30_agreeing_overlapping_wildcard_rules_apply_decision() -> None:
    rule_deny1 = PackageDependencyRule(
        source_package="src/*",
        target_package="src/pkg_b",
        policy="deny",
        rule_id="DENY_1",
    )
    rule_deny2 = PackageDependencyRule(
        source_package="src/pkg_a",
        target_package="*",
        policy="deny",
        rule_id="DENY_2",
    )

    # Both wildcard rules agree on deny
    policy_deny = PackageBoundaryPolicy(rules=(rule_deny1, rule_deny2))
    status, matched_rule = policy_deny.evaluate("src/pkg_a", "src/pkg_b")
    assert status == "prohibited"
    assert matched_rule is not None

    # Both wildcard rules agree on allow
    rule_allow1 = PackageDependencyRule(
        source_package="src/*",
        target_package="src/pkg_b",
        policy="allow",
        rule_id="ALLOW_1",
    )
    rule_allow2 = PackageDependencyRule(
        source_package="src/pkg_a",
        target_package="*",
        policy="allow",
        rule_id="ALLOW_2",
    )
    policy_allow = PackageBoundaryPolicy(rules=(rule_allow1, rule_allow2))
    status, matched_rule = policy_allow.evaluate("src/pkg_a", "src/pkg_b")
    assert status == "allowed"
    assert matched_rule is not None


def test_31_exact_match_precedence_over_conflicting_wildcards() -> None:
    rule_allow = PackageDependencyRule(
        source_package="src/*",
        target_package="src/pkg_b",
        policy="allow",
        rule_id="ALLOW_WILDCARD",
    )
    rule_deny = PackageDependencyRule(
        source_package="src/pkg_a",
        target_package="*",
        policy="deny",
        rule_id="DENY_WILDCARD",
    )
    # Exact match rule takes precedence
    rule_exact = PackageDependencyRule(
        source_package="src/pkg_a",
        target_package="src/pkg_b",
        policy="deny",
        rule_id="EXACT_DENY",
    )

    policy = PackageBoundaryPolicy(rules=(rule_allow, rule_deny, rule_exact))
    status, matched_rule = policy.evaluate("src/pkg_a", "src/pkg_b")
    assert status == "prohibited"
    assert matched_rule is not None
    assert matched_rule.rule_id == "EXACT_DENY"
