from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from context_forge.main import main
from context_forge.models.directory import Directory
from context_forge.models.enums import DirectoryType, FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.pipeline.freshness import FreshnessState, WorkflowFreshness
from context_forge.query.changeset import (
    ChangeSetImpactItem,
    ChangeSetImpactResult,
    analyze_changeset,
)
from context_forge.query.project import ProjectQuery
from context_forge.query.verification import (
    DYNAMIC_COVERAGE_DISCLAIMER,
    TestAssociationClassification,
    TestAssociationItem,
    VerificationChecklist,
    generate_verification_checklist,
    identify_test_associations,
)
from context_forge.reporting.contract import DiagnosticItem


def create_verification_fixture_project(root: Path) -> Project:
    """Create a multi-file project with structural, heuristic, and unassociated tests."""
    project = Project(
        name="Verification Test Project",
        root_path=root.resolve(),
        analysis_status="analyzed",
    )

    src_dir = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
        directory_type=DirectoryType.SOURCE,
    )
    tests_dir = Directory(
        project_id=project.id,
        path=Path("tests"),
        name="tests",
        directory_type=DirectoryType.TESTS,
    )
    project.add_directory(src_dir)
    project.add_directory(tests_dir)

    # Production files:
    # 1. src/service.py - Has direct structural link from tests/test_service.py
    # 2. src/helper.py - Also imported by tests/test_service.py (shared test)
    # 3. src/calculator.py - Has NO structural link, but matches tests/test_calculator.py by naming convention
    # 4. src/utils.py - Has symbol 'hash_token', matched by symbol in tests/test_misc.py
    # 5. src/orphan.py - Has no test links or matching names whatsoever
    f_service = File(
        project_id=project.id,
        path=Path("src/service.py"),
        name="service.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_helper = File(
        project_id=project.id,
        path=Path("src/helper.py"),
        name="helper.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_calc = File(
        project_id=project.id,
        path=Path("src/calculator.py"),
        name="calculator.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_utils = File(
        project_id=project.id,
        path=Path("src/utils.py"),
        name="utils.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_orphan = File(
        project_id=project.id,
        path=Path("src/orphan.py"),
        name="orphan.py",
        extension=".py",
        directory_id=src_dir.id,
    )

    # Test files:
    f_test_service = File(
        project_id=project.id,
        path=Path("tests/test_service.py"),
        name="test_service.py",
        extension=".py",
        file_type=FileType.TEST,
        directory_id=tests_dir.id,
    )
    f_test_calc = File(
        project_id=project.id,
        path=Path("tests/test_calculator.py"),
        name="test_calculator.py",
        extension=".py",
        file_type=FileType.TEST,
        directory_id=tests_dir.id,
    )
    f_test_misc = File(
        project_id=project.id,
        path=Path("tests/test_misc.py"),
        name="test_misc.py",
        extension=".py",
        file_type=FileType.TEST,
        directory_id=tests_dir.id,
    )

    for f in (
        f_service,
        f_helper,
        f_calc,
        f_utils,
        f_orphan,
        f_test_service,
        f_test_calc,
        f_test_misc,
    ):
        project.add_file(f)

    # Physical files on disk
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)

    (root / "src" / "service.py").write_text(
        "def run_service(): pass\n", encoding="utf-8"
    )
    (root / "src" / "helper.py").write_text("def assist(): pass\n", encoding="utf-8")
    (root / "src" / "calculator.py").write_text(
        "def add(x, y): return x + y\n", encoding="utf-8"
    )
    (root / "src" / "utils.py").write_text(
        "def hash_token(t): pass\n", encoding="utf-8"
    )
    (root / "src" / "orphan.py").write_text("def lonely(): pass\n", encoding="utf-8")

    (root / "tests" / "test_service.py").write_text(
        "import src.service\nimport src.helper\n", encoding="utf-8"
    )
    (root / "tests" / "test_calculator.py").write_text(
        "# Heuristic naming only; no static import\n", encoding="utf-8"
    )
    (root / "tests" / "test_misc.py").write_text(
        "def test_hash_token(): pass\n", encoding="utf-8"
    )

    # Add symbols
    sym_utils = Symbol(
        file_id=f_utils.id,
        name="hash_token",
        kind="function",
        start_line=1,
        end_line=1,
    )
    project.add_symbol(sym_utils)

    sym_test_misc = Symbol(
        file_id=f_test_misc.id,
        name="test_hash_token",
        kind="function",
        start_line=1,
        end_line=1,
    )
    project.add_symbol(sym_test_misc)

    # Relationships:
    # 1. tests/test_service.py -> imports -> src/service.py
    # 2. tests/test_service.py -> imports -> src/helper.py
    project.add_relationship(
        Relationship(
            source_id=f_test_service.id,
            target_id=f_service.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_test_service.id,
            target_id=f_helper.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    return project


# ==============================================================================
# Part 1: Test-to-Code Evidence Model Tests
# ==============================================================================


def test_01_direct_structural_association_evidence(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    service_file = next(f for f in proj.files if f.name == "service.py")

    direct, heuristic, unknown = identify_test_associations(
        proj,
        [(service_file.id, "service.py", "src/service.py", "root")],
    )

    assert len(direct) == 1
    assert direct[0].classification == TestAssociationClassification.DIRECT.value
    assert direct[0].test_file_path == "tests/test_service.py"
    assert direct[0].relationship_type == "imports"
    assert direct[0].rule == "structural_imports"
    assert direct[0].confidence == "high"
    assert "Confirmed graph relationship" in direct[0].evidence
    assert direct[0].target_entity_name == "service.py"

    assert len(heuristic) == 0
    assert len(unknown) == 0


def test_02_direct_precedence_over_heuristic(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    service_file = next(f for f in proj.files if f.name == "service.py")

    # test_service.py matches both naming_convention AND has a direct imports relationship
    direct, heuristic, _unknown = identify_test_associations(
        proj,
        [(service_file.id, "service.py", "src/service.py", "root")],
    )

    # Direct must take precedence; heuristic should NOT contain test_service.py
    assert len(direct) == 1
    assert direct[0].test_file_path == "tests/test_service.py"
    assert direct[0].classification == "direct"
    assert len(heuristic) == 0


def test_03_heuristic_naming_convention_evidence(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    calc_file = next(f for f in proj.files if f.name == "calculator.py")

    direct, heuristic, _unknown = identify_test_associations(
        proj,
        [(calc_file.id, "calculator.py", "src/calculator.py", "root")],
    )

    assert len(direct) == 0
    assert len(heuristic) == 1
    assert heuristic[0].classification == TestAssociationClassification.HEURISTIC.value
    assert heuristic[0].rule == "naming_convention"
    assert heuristic[0].confidence == "medium"
    assert heuristic[0].test_file_path == "tests/test_calculator.py"
    assert "matches naming convention" in heuristic[0].evidence


def test_04_heuristic_symbol_name_match_evidence(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    utils_file = next(f for f in proj.files if f.name == "utils.py")

    direct, heuristic, _unknown = identify_test_associations(
        proj,
        [(utils_file.id, "utils.py", "src/utils.py", "root")],
    )

    assert len(direct) == 0
    assert len(heuristic) == 1
    assert heuristic[0].classification == TestAssociationClassification.HEURISTIC.value
    assert heuristic[0].rule == "symbol_name_match"
    assert heuristic[0].confidence == "medium"
    assert heuristic[0].test_file_path == "tests/test_misc.py"
    assert "matches target symbol 'hash_token'" in heuristic[0].evidence


def test_05_unknown_association_when_unassociated(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    orphan_file = next(f for f in proj.files if f.name == "orphan.py")

    direct, heuristic, unknown = identify_test_associations(
        proj,
        [(orphan_file.id, "orphan.py", "src/orphan.py", "root")],
    )

    assert len(direct) == 0
    assert len(heuristic) == 0
    assert len(unknown) == 1
    assert unknown[0].classification == TestAssociationClassification.UNKNOWN.value
    assert unknown[0].rule == "unassociated"
    assert unknown[0].confidence == "none"
    assert (
        "Available structural and heuristic evidence did not identify test associations"
        in unknown[0].evidence
    )


def test_06_dynamic_coverage_disclaimer_present() -> None:
    assert "do not establish runtime execution" in DYNAMIC_COVERAGE_DISCLAIMER
    assert "behavioral coverage" in DYNAMIC_COVERAGE_DISCLAIMER


def test_07_test_association_item_serialization() -> None:
    item_id = uuid4()
    item = TestAssociationItem(
        test_file_path="tests/test_foo.py",
        target_entity_name="foo.py",
        classification="direct",
        rule="structural_imports",
        evidence="Graph relationship imports",
        target_entity_id=item_id,
        target_entity_path="src/foo.py",
        target_kind="root",
        relationship_type="imports",
        direction="outgoing_from_test",
        confidence="high",
    )
    d = item.to_dict()
    assert d["test_file_path"] == "tests/test_foo.py"
    assert d["classification"] == "direct"
    assert d["target_entity_id"] == str(item_id)
    assert d["confidence"] == "high"


# ==============================================================================
# Part 2: Verification Checklist Generation Tests
# ==============================================================================


def test_08_checklist_category_partitioning(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    chk = generate_verification_checklist(
        proj,
        ["src/service.py", "src/calculator.py", "src/orphan.py"],
    )

    # Category A: structural test (test_service.py)
    assert len(chk.detected_structural_tests) >= 1
    assert any(
        it.test_file_path == "tests/test_service.py"
        for it in chk.detected_structural_tests
    )

    # Category B: heuristic test (test_calculator.py)
    assert len(chk.heuristic_tests) >= 1
    assert any(
        it.test_file_path == "tests/test_calculator.py" for it in chk.heuristic_tests
    )

    # Category C: additional verification (orphan.py needs coverage)
    assert len(chk.additional_verifications) >= 1
    assert any("orphan.py" in it.action for it in chk.additional_verifications)

    # Category D: unverified area noting orphan.py
    assert len(chk.unverified_areas) >= 1
    assert any("orphan.py" in it.rationale for it in chk.unverified_areas)


def test_09_multi_file_changes_shared_test_deduplication(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    # Both service.py and helper.py are imported by tests/test_service.py
    chk = generate_verification_checklist(
        proj,
        ["src/service.py", "src/helper.py"],
    )

    # Category A should have exactly ONE deduplicated item for tests/test_service.py
    service_items = [
        it
        for it in chk.detected_structural_tests
        if it.test_file_path == "tests/test_service.py"
    ]
    assert len(service_items) == 1
    item = service_items[0]

    # Target entities must include both files
    assert "service.py" in item.target_entities
    assert "helper.py" in item.target_entities
    assert len(item.supporting_evidence) == 2


def test_10_unexecuted_status_guarantee(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    chk = generate_verification_checklist(
        proj,
        ["src/service.py", "src/calculator.py", "src/orphan.py"],
    )

    assert len(chk.items) > 0
    for item in chk.items:
        assert item.executed is False
        assert item.execution_status == "unexecuted"


def test_11_suggested_commands_collection(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    chk = generate_verification_checklist(
        proj,
        ["src/service.py", "src/calculator.py"],
    )

    cmds = chk.suggested_commands
    assert "pytest tests/test_service.py" in cmds
    assert "pytest tests/test_calculator.py" in cmds


def test_12_consolidated_test_run_suggestion(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    chk = generate_verification_checklist(
        proj,
        ["src/service.py", "src/calculator.py"],
    )

    # With 2 distinct test files, a consolidated command is in Category C
    consolidated = [
        it
        for it in chk.additional_verifications
        if it.item_id == "consolidated_test_run"
    ]
    assert len(consolidated) == 1
    assert (
        "pytest tests/test_calculator.py tests/test_service.py"
        in consolidated[0].suggested_command
    )


def test_13_unresolved_inputs_reported_in_category_d(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    chk = generate_verification_checklist(
        proj,
        ["src/service.py", "nonexistent/missing.py"],
    )

    unresolved_items = [
        it for it in chk.unverified_areas if it.item_id.startswith("unresolved_path:")
    ]
    assert len(unresolved_items) == 1
    assert "nonexistent/missing.py" in unresolved_items[0].target_entities


def test_14_incomplete_project_status_reported_in_category_d(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    proj.analysis_status = "failed"
    proj.errors.append("Parser encountered syntax error in module X")

    chk = generate_verification_checklist(proj, ["src/service.py"])

    assert chk.analysis_status == "incomplete"
    incomplete_items = [
        it for it in chk.unverified_areas if it.item_id == "incomplete_analysis"
    ]
    assert len(incomplete_items) == 1
    assert "syntax error" in incomplete_items[0].supporting_evidence[0]


def test_15_stale_freshness_reported_in_category_d(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)

    # Mock WorkflowFreshnessGuard to return STALE
    mock_wf = WorkflowFreshness(
        state=FreshnessState.STALE,
        reason="modified_files",
        diagnostics=(
            DiagnosticItem.warning(
                "Files have changed", code="STALE_ANALYSIS", source="freshness"
            ),
        ),
        limitations=("Working tree has modifications",),
    )

    with patch(
        "context_forge.query.verification.WorkflowFreshnessGuard.assess_freshness",
        return_value=mock_wf,
    ):
        chk = generate_verification_checklist(proj, ["src/service.py"])

    assert chk.freshness_state == "stale"
    stale_items = [it for it in chk.unverified_areas if it.item_id == "stale_freshness"]
    assert len(stale_items) == 1
    assert "Refresh repository analysis" in stale_items[0].action
    assert any(d.code == "STALE_ANALYSIS" for d in chk.diagnostics)


def test_16_deterministic_checklist_ordering(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    paths = ["src/service.py", "src/calculator.py", "src/orphan.py", "missing.py"]

    chk1 = generate_verification_checklist(proj, paths)
    chk2 = generate_verification_checklist(proj, paths)

    assert [it.item_id for it in chk1.items] == [it.item_id for it in chk2.items]
    assert chk1.suggested_commands == chk2.suggested_commands


def test_17_full_json_serialization(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    chk = generate_verification_checklist(proj, ["src/service.py", "src/calculator.py"])

    data = chk.to_dict()
    assert isinstance(data, dict)
    assert "change_inputs" in data
    assert "items" in data
    assert "detected_structural_tests" in data
    assert "heuristic_tests" in data
    assert "additional_verifications" in data
    assert "unverified_areas" in data
    assert "suggested_commands" in data
    assert "disclaimer" in data
    assert "analysis_status" in data
    assert "freshness_state" in data

    # Confirm JSON dumps cleanly
    json_str = json.dumps(data)
    assert len(json_str) > 0


def test_18_project_query_integration(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    pq = ProjectQuery(proj)

    chk = pq.generate_verification_checklist(["src/service.py"])
    assert isinstance(chk, VerificationChecklist)
    assert len(chk.detected_structural_tests) == 1


# ==============================================================================
# Defect A: Freshness State Handling Regression Tests
# ==============================================================================


def test_23_freshness_current_state(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    mock_wf = WorkflowFreshness(
        state=FreshnessState.CURRENT,
        reason="fresh",
    )
    with patch(
        "context_forge.query.verification.WorkflowFreshnessGuard.assess_freshness",
        return_value=mock_wf,
    ):
        chk = generate_verification_checklist(proj, ["src/service.py"])

    assert chk.freshness_state == "current"
    # No freshness warning in Category D for CURRENT
    assert not any(
        it.item_id
        in {"stale_freshness", "incomplete_freshness", "indeterminate_freshness"}
        for it in chk.unverified_areas
    )


def test_24_freshness_incomplete_state(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    mock_wf = WorkflowFreshness(
        state=FreshnessState.INCOMPLETE,
        reason="analysis_incomplete",
        limitations=("Some symbols missing",),
    )
    with patch(
        "context_forge.query.verification.WorkflowFreshnessGuard.assess_freshness",
        return_value=mock_wf,
    ):
        chk = generate_verification_checklist(proj, ["src/service.py"])

    assert chk.freshness_state == "incomplete"
    inc_items = [
        it for it in chk.unverified_areas if it.item_id == "incomplete_freshness"
    ]
    assert len(inc_items) == 1
    assert "Re-analyze repository" in inc_items[0].action
    assert any("Some symbols missing" in lim for lim in chk.limitations)


def test_25_freshness_indeterminate_state(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    mock_wf = WorkflowFreshness(
        state=FreshnessState.INDETERMINATE,
        reason="missing_analysis",
        limitations=("No database found",),
    )
    with patch(
        "context_forge.query.verification.WorkflowFreshnessGuard.assess_freshness",
        return_value=mock_wf,
    ):
        chk = generate_verification_checklist(proj, ["src/service.py"])

    assert chk.freshness_state == "indeterminate"
    ind_items = [
        it for it in chk.unverified_areas if it.item_id == "indeterminate_freshness"
    ]
    assert len(ind_items) == 1
    assert "Verify repository analysis state" in ind_items[0].action


def test_26_freshness_exception_during_assessment(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    with patch(
        "context_forge.query.verification.WorkflowFreshnessGuard.assess_freshness",
        side_effect=OSError("Database disk I/O error"),
    ):
        chk = generate_verification_checklist(proj, ["src/service.py"])

    assert chk.freshness_state == "indeterminate"
    assert any(d.code == "FRESHNESS_CHECK_FAILED" for d in chk.diagnostics)
    assert any("Database disk I/O error" in lim for lim in chk.limitations)
    ind_items = [
        it for it in chk.unverified_areas if it.item_id == "indeterminate_freshness"
    ]
    assert len(ind_items) == 1


def test_27_freshness_missing_root_path() -> None:
    # Project with nonexistent root path
    proj = Project(
        name="No Root Project",
        root_path=Path("/tmp/nonexistent_cf_path_12345"),
        analysis_status="analyzed",
    )
    chk = generate_verification_checklist(proj, ["src/foo.py"])
    assert chk.freshness_state == "indeterminate"
    ind_items = [
        it for it in chk.unverified_areas if it.item_id == "indeterminate_freshness"
    ]
    assert len(ind_items) == 1


# ==============================================================================
# Defect B: Analysis Status Vocabulary Consistency Tests
# ==============================================================================


def test_28_canonical_status_analyzed(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    proj.analysis_status = "analyzed"
    chk = generate_verification_checklist(proj, ["src/service.py"])
    assert chk.analysis_status == "analyzed"
    assert not any(it.item_id == "incomplete_analysis" for it in chk.unverified_areas)


def test_29_canonical_status_completed(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    proj.analysis_status = "completed"
    chk = generate_verification_checklist(proj, ["src/service.py"])
    assert chk.analysis_status == "completed"
    assert not any(it.item_id == "incomplete_analysis" for it in chk.unverified_areas)


def test_30_non_canonical_status_complete_is_incomplete(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    # "complete" is NOT canonical ("analyzed" and "completed" are)
    proj.analysis_status = "complete"
    chk = generate_verification_checklist(proj, ["src/service.py"])
    assert chk.analysis_status == "incomplete"
    assert any(it.item_id == "incomplete_analysis" for it in chk.unverified_areas)


def test_31_status_with_analysis_errors_is_incomplete(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    proj.analysis_status = "analyzed"
    proj.errors.append("Syntax error in module b")
    chk = generate_verification_checklist(proj, ["src/service.py"])
    assert chk.analysis_status == "incomplete"
    assert any(it.item_id == "incomplete_analysis" for it in chk.unverified_areas)


def test_32_status_not_analyzed_or_analyzing_or_failed(tmp_path: Path) -> None:
    for st in ("not_analyzed", "analyzing", "failed", "partial", "unknown_xyz"):
        proj = create_verification_fixture_project(tmp_path)
        proj.analysis_status = st
        chk = generate_verification_checklist(proj, ["src/service.py"])
        assert chk.analysis_status == "incomplete"
        assert any(it.item_id == "incomplete_analysis" for it in chk.unverified_areas)


# ==============================================================================
# Defect C: Truncation and Impact Scope Tests
# ==============================================================================


def test_33_truncation_preserves_omitted_downstream_test_associations(
    tmp_path: Path,
) -> None:
    """When changeset display limit truncates items, checklist still reasons about full affected set."""
    proj = create_verification_fixture_project(tmp_path)

    # helper.py is downstream of service.py in the graph
    # Add a chain: service -> helper -> child
    src_dir = next(d for d in proj.directories if d.name == "src")
    f_child = File(
        project_id=proj.id,
        path=Path("src/child.py"),
        name="child.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    proj.add_file(f_child)
    (tmp_path / "src" / "child.py").write_text(
        "def child_fn(): pass\n", encoding="utf-8"
    )

    # Add test for child.py: tests/test_child.py
    tests_dir = next(d for d in proj.directories if d.name == "tests")
    f_test_child = File(
        project_id=proj.id,
        path=Path("tests/test_child.py"),
        name="test_child.py",
        extension=".py",
        file_type=FileType.TEST,
        directory_id=tests_dir.id,
    )
    proj.add_file(f_test_child)
    (tmp_path / "tests" / "test_child.py").write_text(
        "import src.child\n", encoding="utf-8"
    )

    f_service = next(f for f in proj.files if f.name == "service.py")
    f_helper = next(f for f in proj.files if f.name == "helper.py")

    proj.add_relationship(
        Relationship(
            source_id=f_helper.id,
            target_id=f_service.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    proj.add_relationship(
        Relationship(
            source_id=f_child.id,
            target_id=f_helper.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    proj.add_relationship(
        Relationship(
            source_id=f_test_child.id,
            target_id=f_child.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    # Analyze changeset with limit=1 to force truncation in displayed items
    res = analyze_changeset(
        proj,
        ["src/service.py"],
        limit=1,
        include_checklist=True,
    )

    assert res.truncated is True
    assert len(res.items) == 1
    assert res.total > 1

    # Checklist must include tests for downstream child even though child was truncated from display
    chk = res.verification_checklist
    assert chk is not None
    test_files = [it.test_file_path for it in chk.detected_structural_tests]
    assert "tests/test_child.py" in test_files
    assert any("accounts for all" in lim for lim in chk.limitations)


def test_34_truncation_without_all_items_reports_partial_coverage(
    tmp_path: Path,
) -> None:
    """When an external truncated result lacks _all_items, checklist honestly reports partial coverage."""
    proj = create_verification_fixture_project(tmp_path)

    # Mock an impact result that was truncated and has NO _all_items
    mock_impact = ChangeSetImpactResult(
        status="success",
        supplied_paths=("src/service.py",),
        resolved_inputs=(),
        items=(
            ChangeSetImpactItem(
                entity_id=uuid4(),
                entity_type="file",
                name="service.py",
                path="src/service.py",
                kind="file",
                qualified_name="service",
                classification="direct",
                min_depth=1,
                roots=("src/service.py",),
                provenance=(),
                shortest_path=(),
            ),
        ),
        total=10,
        direct_count=1,
        downstream_count=9,
        truncated=True,
        limit=1,
        max_depth=3,
        depth_reached=1,
        direction="both",
        relationship_types=("imports",),
        _all_items=None,  # Not available!
    )

    chk = generate_verification_checklist(
        proj, ["src/service.py"], impact_result=mock_impact
    )
    assert any("Checklist coverage is partial" in lim for lim in chk.limitations)
    assert any(it.item_id == "truncated_impact_coverage" for it in chk.unverified_areas)


# ==============================================================================
# Defect D: Compatibility & Default Changeset Behavior Tests
# ==============================================================================


def test_35_changeset_default_does_not_generate_checklist(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    res = analyze_changeset(proj, ["src/service.py"])

    # Default call must NOT attach a checklist
    assert res.verification_checklist is None

    # to_dict must NOT contain verification_checklist
    data = res.to_dict()
    assert "verification_checklist" not in data


def test_36_changeset_opt_in_attaches_checklist(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    res = analyze_changeset(proj, ["src/service.py"], include_checklist=True)

    assert res.verification_checklist is not None
    assert isinstance(res.verification_checklist, VerificationChecklist)

    data = res.to_dict()
    assert "verification_checklist" in data
    assert data["verification_checklist"]["analysis_status"] == "analyzed"


def test_37_no_freshness_guard_called_when_checklist_not_requested(
    tmp_path: Path,
) -> None:
    proj = create_verification_fixture_project(tmp_path)

    with patch(
        "context_forge.pipeline.freshness.WorkflowFreshnessGuard.assess_freshness"
    ) as mock_assess:
        res = analyze_changeset(proj, ["src/service.py"])
        assert res.verification_checklist is None
        # Must not perform freshness guard checks on ordinary changeset query
        mock_assess.assert_not_called()


# ==============================================================================
# Defect E: Direct Association Deduplication Tests
# ==============================================================================


def test_38_exact_duplicate_relationships_deduplicated(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    service_file = next(f for f in proj.files if f.name == "service.py")
    test_service_file = next(f for f in proj.files if f.name == "test_service.py")

    # Add an identical duplicate relationship
    proj.add_relationship(
        Relationship(
            source_id=test_service_file.id,
            target_id=service_file.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    direct, _heuristic, _unknown = identify_test_associations(
        proj,
        [(service_file.id, "service.py", "src/service.py", "root")],
    )

    # Must produce exactly ONE direct association item, NOT two
    assert len(direct) == 1
    assert direct[0].test_file_path == "tests/test_service.py"
    assert direct[0].target_entity_name == "service.py"


def test_39_multiple_distinct_relationships_merged_deterministically(
    tmp_path: Path,
) -> None:
    proj = create_verification_fixture_project(tmp_path)
    service_file = next(f for f in proj.files if f.name == "service.py")
    test_service_file = next(f for f in proj.files if f.name == "test_service.py")

    # Add CALLS relationship in addition to IMPORTS
    proj.add_relationship(
        Relationship(
            source_id=test_service_file.id,
            target_id=service_file.id,
            relationship_type=RelationshipType.CALLS,
        )
    )

    direct, _heuristic, _unknown = identify_test_associations(
        proj,
        [(service_file.id, "service.py", "src/service.py", "root")],
    )

    # Must produce exactly ONE merged direct item, with both types and combined evidence
    assert len(direct) == 1
    item = direct[0]
    assert "calls" in item.relationship_type
    assert "imports" in item.relationship_type
    assert "Confirmed graph relationship 'calls'" in item.evidence
    assert "Confirmed graph relationship 'imports'" in item.evidence
    assert item.rule == "structural_calls_imports"


def test_40_distinct_targets_with_same_name_remain_distinct(tmp_path: Path) -> None:
    proj = create_verification_fixture_project(tmp_path)
    test_service_file = next(f for f in proj.files if f.name == "test_service.py")

    # Two different targets with identical name "mod.py" in different directories
    f1 = File(
        project_id=proj.id,
        path=Path("src/pkg1/mod.py"),
        name="mod.py",
        extension=".py",
    )
    f2 = File(
        project_id=proj.id,
        path=Path("src/pkg2/mod.py"),
        name="mod.py",
        extension=".py",
    )
    proj.add_file(f1)
    proj.add_file(f2)

    proj.add_relationship(
        Relationship(
            source_id=test_service_file.id,
            target_id=f1.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    proj.add_relationship(
        Relationship(
            source_id=test_service_file.id,
            target_id=f2.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    direct, _, _ = identify_test_associations(
        proj,
        [
            (f1.id, "mod.py", "src/pkg1/mod.py", "root"),
            (f2.id, "mod.py", "src/pkg2/mod.py", "root"),
        ],
    )

    # Must produce 2 distinct items for the 2 distinct targets
    assert len(direct) == 2
    target_ids = {a.target_entity_id for a in direct}
    assert f1.id in target_ids
    assert f2.id in target_ids


def test_41_multiple_test_files_for_same_target_remain_distinct(
    tmp_path: Path,
) -> None:
    proj = create_verification_fixture_project(tmp_path)
    service_file = next(f for f in proj.files if f.name == "service.py")
    test_calc = next(f for f in proj.files if f.name == "test_calculator.py")

    # test_calculator also imports service.py
    proj.add_relationship(
        Relationship(
            source_id=test_calc.id,
            target_id=service_file.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    direct, _, _ = identify_test_associations(
        proj,
        [(service_file.id, "service.py", "src/service.py", "root")],
    )

    # 2 distinct test files -> 2 distinct items
    assert len(direct) == 2
    paths = {a.test_file_path for a in direct}
    assert "tests/test_service.py" in paths
    assert "tests/test_calculator.py" in paths


def test_42_reversing_relationship_order_produces_identical_output(
    tmp_path: Path,
) -> None:
    proj = create_verification_fixture_project(tmp_path)
    service_file = next(f for f in proj.files if f.name == "service.py")

    direct1, _, _ = identify_test_associations(
        proj,
        [(service_file.id, "service.py", "src/service.py", "root")],
    )

    # Reverse relationships list
    proj.relationships.reverse()

    direct2, _, _ = identify_test_associations(
        proj,
        [(service_file.id, "service.py", "src/service.py", "root")],
    )

    assert [d.to_dict() for d in direct1] == [d.to_dict() for d in direct2]


# ==============================================================================
# CLI Verification Checklist Tests
# ==============================================================================


def test_20_cli_changeset_with_checklist_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_verification_fixture_project(tmp_path)

    with patch("context_forge.main.load_fresh_project", return_value=(proj, None)):
        main(
            [
                "changeset",
                "src/service.py",
                "src/calculator.py",
                "--checklist",
                "--path",
                str(proj.root_path),
            ]
        )

    captured = capsys.readouterr()
    assert "Verification checklist:" in captured.out
    assert "Category A: Detected structural tests (1):" in captured.out
    assert "tests/test_service.py" in captured.out
    assert "Category B: Heuristic recommendations (1):" in captured.out
    assert "tests/test_calculator.py" in captured.out
    assert "[unexecuted]" in captured.out
    assert "Category C: Additional verification" in captured.out
    assert "Category D: Unverified areas" in captured.out


def test_21_cli_changeset_json_contains_checklist_when_flag_passed(
    tmp_path: Path,
) -> None:
    proj = create_verification_fixture_project(tmp_path)

    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", new_callable=StringIO) as mock_stdout,
    ):
        main(
            [
                "changeset",
                "src/service.py",
                "--checklist",
                "--format",
                "json",
                "--path",
                str(proj.root_path),
            ]
        )

    output = mock_stdout.getvalue().strip()
    data = json.loads(output)
    assert "verification_checklist" in data
    chk_data = data["verification_checklist"]
    assert "detected_structural_tests" in chk_data
    assert len(chk_data["detected_structural_tests"]) == 1
    assert (
        chk_data["detected_structural_tests"][0]["test_file_path"]
        == "tests/test_service.py"
    )


def test_22_cli_changeset_without_checklist_flag_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_verification_fixture_project(tmp_path)

    with patch("context_forge.main.load_fresh_project", return_value=(proj, None)):
        main(
            [
                "changeset",
                "src/service.py",
                "--path",
                str(proj.root_path),
            ]
        )

    captured = capsys.readouterr()
    # Without --checklist, "Verification checklist:" header should NOT be present
    assert "Verification checklist:" not in captured.out
    # Standard changeset headers should be present
    assert "Change-set paths" in captured.out
    assert "Direct impact:" in captured.out


def test_43_cli_changeset_alias_change_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_verification_fixture_project(tmp_path)

    with patch("context_forge.main.load_fresh_project", return_value=(proj, None)):
        main(
            [
                "change-set",
                "src/service.py",
                "--checklist",
                "--path",
                str(proj.root_path),
            ]
        )

    captured = capsys.readouterr()
    assert "Verification checklist:" in captured.out
    assert "tests/test_service.py" in captured.out
