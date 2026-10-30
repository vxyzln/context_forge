from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from context_forge.comparison.models import ComparisonState
from context_forge.comparison.service import compare_states
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.pipeline.freshness import FreshnessState
from context_forge.reporting.contract import OperationStatus
from context_forge.storage.cache import FileFingerprint


def make_project(
    name: str = "demo-repo",
    root: Path | None = None,
    analysis_status: str = "analyzed",
    errors: list[str] | None = None,
) -> Project:
    root_path = root or Path("/fake/repo").resolve()
    return Project(
        name=name,
        root_path=root_path,
        analysis_status=analysis_status,
        errors=errors or [],
    )


def add_file(project: Project, path_str: str, size: int = 100) -> File:
    f = File(
        project_id=project.id,
        path=Path(path_str),
        name=Path(path_str).name,
        extension=Path(path_str).suffix,
        size=size,
    )
    project.add_file(f)
    return f


def add_symbol(
    project: Project,
    file_id: any,
    name: str,
    kind: str = "function",
    start_line: int = 10,
    end_line: int = 20,
    qualified_name: str | None = None,
    signature: str | None = None,
) -> Symbol:
    s = Symbol(
        file_id=file_id,
        name=name,
        kind=kind,
        start_line=start_line,
        end_line=end_line,
        qualified_name=qualified_name or name,
        signature=signature or f"def {name}()",
    )
    project.add_symbol(s)
    return s


def test_01_two_valid_states_no_structural_changes() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/util.py", size=100)
    add_symbol(p1, f1.id, "compute", signature="def compute(x)")

    p2 = make_project()
    f2 = add_file(p2, "src/util.py", size=100)
    add_symbol(p2, f2.id, "compute", signature="def compute(x)")

    res = compare_states(p1, p2)
    assert res.outcome.is_success is True
    assert res.is_complete is True
    assert res.has_structural_changes is False
    assert res.total_changes_count == 0


def test_02_added_files() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py")

    p2 = make_project()
    add_file(p2, "src/a.py")
    add_file(p2, "src/b.py")

    res = compare_states(p1, p2)
    assert res.has_structural_changes is True
    assert len(res.added_files) == 1
    assert res.added_files[0].path == "src/b.py"
    assert res.added_files[0].change_type == "added"
    assert len(res.removed_files) == 0


def test_03_removed_files() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py")
    add_file(p1, "src/b.py")

    p2 = make_project()
    add_file(p2, "src/a.py")

    res = compare_states(p1, p2)
    assert len(res.removed_files) == 1
    assert res.removed_files[0].path == "src/b.py"
    assert res.removed_files[0].change_type == "removed"
    assert len(res.added_files) == 0


def test_04_added_symbols() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "init")

    p2 = make_project()
    f2 = add_file(p2, "src/a.py")
    add_symbol(p2, f2.id, "init")
    add_symbol(p2, f2.id, "helper")

    res = compare_states(p1, p2)
    assert len(res.added_symbols) == 1
    assert res.added_symbols[0].name == "helper"
    assert res.added_symbols[0].change_type == "added"
    assert len(res.removed_symbols) == 0


def test_05_removed_symbols() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "init")
    add_symbol(p1, f1.id, "deprecated")

    p2 = make_project()
    f2 = add_file(p2, "src/a.py")
    add_symbol(p2, f2.id, "init")

    res = compare_states(p1, p2)
    assert len(res.removed_symbols) == 1
    assert res.removed_symbols[0].name == "deprecated"
    assert res.removed_symbols[0].change_type == "removed"
    assert len(res.added_symbols) == 0


def test_06_modified_entities_with_fingerprints() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py")
    fps1 = {Path("src/a.py"): FileFingerprint(Path("src/a.py"), 100, 1000, "hash_aaa")}

    p2 = make_project()
    add_file(p2, "src/a.py")
    fps2 = {Path("src/a.py"): FileFingerprint(Path("src/a.py"), 120, 2000, "hash_bbb")}

    s1 = ComparisonState.from_project(p1, state_id="s1", fingerprints=fps1)
    s2 = ComparisonState.from_project(p2, state_id="s2", fingerprints=fps2)

    res = compare_states(s1, s2)
    assert len(res.modified_files) == 1
    assert res.modified_files[0].path == "src/a.py"
    assert res.modified_files[0].before_fingerprint == "hash_aaa"
    assert res.modified_files[0].after_fingerprint == "hash_bbb"


def test_07_moved_file_with_reliable_evidence() -> None:
    p1 = make_project()
    add_file(p1, "src/old_path.py")
    fps1 = {
        Path("src/old_path.py"): FileFingerprint(
            Path("src/old_path.py"), 100, 1000, "unique_hash_123"
        )
    }

    p2 = make_project()
    add_file(p2, "src/new_path.py")
    fps2 = {
        Path("src/new_path.py"): FileFingerprint(
            Path("src/new_path.py"), 100, 2000, "unique_hash_123"
        )
    }

    s1 = ComparisonState.from_project(p1, state_id="s1", fingerprints=fps1)
    s2 = ComparisonState.from_project(p2, state_id="s2", fingerprints=fps2)

    res = compare_states(s1, s2)
    assert len(res.moved_files) == 1
    assert res.moved_files[0].before_path == "src/old_path.py"
    assert res.moved_files[0].after_path == "src/new_path.py"
    assert len(res.added_files) == 0
    assert len(res.removed_files) == 0


def test_08_moved_symbol_across_files() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "parse_input", signature="def parse_input(data: str)")

    p2 = make_project()
    f2 = add_file(p2, "src/b.py")
    add_symbol(p2, f2.id, "parse_input", signature="def parse_input(data: str)")

    res = compare_states(p1, p2)
    assert len(res.moved_symbols) == 1
    assert res.moved_symbols[0].name == "parse_input"
    assert res.moved_symbols[0].before_file_path == "src/a.py"
    assert res.moved_symbols[0].after_file_path == "src/b.py"
    assert len(res.added_symbols) == 0
    assert len(res.removed_symbols) == 0


def test_09_location_shift_is_not_semantic_modification() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "foo", start_line=10, end_line=20, signature="def foo()")

    p2 = make_project()
    f2 = add_file(p2, "src/a.py")
    add_symbol(p2, f2.id, "foo", start_line=30, end_line=40, signature="def foo()")

    res = compare_states(p1, p2)
    assert len(res.modified_symbols) == 0
    assert len(res.added_symbols) == 0
    assert len(res.removed_symbols) == 0


def test_10_insufficient_evidence_prevents_file_modification_claim() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py", size=100)

    p2 = make_project()
    add_file(p2, "src/a.py", size=100)

    s1 = ComparisonState.from_project(p1, state_id="s1", fingerprints=None)
    s2 = ComparisonState.from_project(p2, state_id="s2", fingerprints=None)

    res = compare_states(s1, s2)
    assert len(res.modified_files) == 0
    assert res.has_structural_changes is False


def test_11_added_relationships() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py")
    add_file(p1, "src/b.py")

    p2 = make_project()
    f1_new = add_file(p2, "src/a.py")
    f2_new = add_file(p2, "src/b.py")
    p2.add_relationship(
        Relationship(
            source_id=f1_new.id,
            target_id=f2_new.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    res = compare_states(p1, p2)
    assert len(res.added_relationships) == 1
    assert res.added_relationships[0].relationship_type == "imports"
    assert res.added_relationships[0].source_key == "file:src/a.py"
    assert res.added_relationships[0].target_key == "file:src/b.py"


def test_12_removed_relationships() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    f2 = add_file(p1, "src/b.py")
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    p2 = make_project()
    add_file(p2, "src/a.py")
    add_file(p2, "src/b.py")

    res = compare_states(p1, p2)
    assert len(res.removed_relationships) == 1
    assert res.removed_relationships[0].relationship_type == "imports"
    assert res.removed_relationships[0].source_key == "file:src/a.py"
    assert res.removed_relationships[0].target_key == "file:src/b.py"


def test_13_modified_relationship_confidence_and_metadata() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    f2 = add_file(p1, "src/b.py")
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.REFERENCES,
            confidence=0.5,
            metadata={"source": "heuristic"},
        )
    )

    p2 = make_project()
    f1_new = add_file(p2, "src/a.py")
    f2_new = add_file(p2, "src/b.py")
    p2.add_relationship(
        Relationship(
            source_id=f1_new.id,
            target_id=f2_new.id,
            relationship_type=RelationshipType.REFERENCES,
            confidence=1.0,
            metadata={"source": "ast"},
        )
    )

    res = compare_states(p1, p2)
    assert len(res.modified_relationships) == 1
    rel = res.modified_relationships[0]
    assert rel.before_confidence == 0.5
    assert rel.after_confidence == 1.0
    assert rel.metadata_changes["before"] == {"source": "heuristic"}
    assert rel.metadata_changes["after"] == {"source": "ast"}


def test_14_relationship_matching_uses_stable_endpoints_not_uuid() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    f2 = add_file(p1, "src/b.py")
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    p2 = make_project()
    f1_new = add_file(p2, "src/a.py")
    f2_new = add_file(p2, "src/b.py")
    p2.add_relationship(
        Relationship(
            source_id=f1_new.id,
            target_id=f2_new.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    res = compare_states(p1, p2)
    assert len(res.added_relationships) == 0
    assert len(res.removed_relationships) == 0
    assert len(res.modified_relationships) == 0


def test_15_relationship_with_unresolved_endpoint() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    ghost_id = uuid4()
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=ghost_id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    p2 = make_project()
    add_file(p2, "src/a.py")

    res = compare_states(p1, p2)
    assert any(d.code == "UNRESOLVED_RELATIONSHIP_ENDPOINT" for d in res.diagnostics)
    assert any("unresolved endpoint" in lim for lim in res.limitations)


def test_16_unresolved_imports_do_not_become_fabricated_graph_edges() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py")

    p2 = make_project()
    add_file(p2, "src/a.py")

    res = compare_states(p1, p2)
    assert len(res.added_relationships) == 0


def test_17_affected_components_grounded_in_relationships() -> None:
    p1 = make_project()
    add_file(p1, "src/lib.py")
    add_file(p1, "src/app.py")
    fps1 = {Path("src/lib.py"): FileFingerprint(Path("src/lib.py"), 100, 1000, "h1")}

    p2 = make_project()
    f_lib2 = add_file(p2, "src/lib.py")
    f_app2 = add_file(p2, "src/app.py")
    fps2 = {Path("src/lib.py"): FileFingerprint(Path("src/lib.py"), 110, 2000, "h2")}
    p2.add_relationship(
        Relationship(
            source_id=f_app2.id,
            target_id=f_lib2.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    s1 = ComparisonState.from_project(p1, state_id="s1", fingerprints=fps1)
    s2 = ComparisonState.from_project(p2, state_id="s2", fingerprints=fps2)

    res = compare_states(s1, s2)
    assert len(res.modified_files) == 1
    assert any(
        a.path == "src/app.py" and "src/lib.py" in a.reason
        for a in res.affected_components
    )


def test_18_ambiguous_symbol_matching() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/old.py")
    add_symbol(p1, f1.id, "parse", signature="def parse()")

    p2 = make_project()
    f2a = add_file(p2, "src/new1.py")
    f2b = add_file(p2, "src/new2.py")
    add_symbol(p2, f2a.id, "parse", signature="def parse()")
    add_symbol(p2, f2b.id, "parse", signature="def parse()")

    res = compare_states(p1, p2)
    assert len(res.ambiguous_matches) == 1
    amb = res.ambiguous_matches[0]
    assert amb.category == "symbol"
    assert len(amb.after_candidates) == 2


def test_19_ambiguous_moved_file_candidates() -> None:
    p1 = make_project()
    add_file(p1, "src/old.py")
    fps1 = {Path("src/old.py"): FileFingerprint(Path("src/old.py"), 100, 1000, "dup_h")}

    p2 = make_project()
    add_file(p2, "src/new_a.py")
    add_file(p2, "src/new_b.py")
    fps2 = {
        Path("src/new_a.py"): FileFingerprint(Path("src/new_a.py"), 100, 2000, "dup_h"),
        Path("src/new_b.py"): FileFingerprint(Path("src/new_b.py"), 100, 2000, "dup_h"),
    }

    s1 = ComparisonState.from_project(p1, state_id="s1", fingerprints=fps1)
    s2 = ComparisonState.from_project(p2, state_id="s2", fingerprints=fps2)

    res = compare_states(s1, s2)
    assert len(res.ambiguous_matches) == 1
    assert res.ambiguous_matches[0].category == "file"
    assert len(res.ambiguous_matches[0].after_candidates) == 2


def test_20_deterministic_ordering_of_ambiguous_candidates() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/old.py")
    add_symbol(p1, f1.id, "helper")

    p2 = make_project()
    f_z = add_file(p2, "src/z.py")
    f_a = add_file(p2, "src/a.py")
    add_symbol(p2, f_z.id, "helper")
    add_symbol(p2, f_a.id, "helper")

    res = compare_states(p1, p2)
    assert len(res.ambiguous_matches) == 1
    cands = res.ambiguous_matches[0].after_candidates
    assert cands == tuple(sorted(cands))


def test_21_incomplete_before_state() -> None:
    p1 = make_project(analysis_status="analyzing")
    add_file(p1, "src/a.py")

    p2 = make_project(analysis_status="analyzed")
    add_file(p2, "src/a.py")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert res.outcome.status == OperationStatus.INCOMPLETE
    assert any(d.code == "INCOMPLETE_BEFORE_STATE" for d in res.diagnostics)


def test_22_incomplete_after_state() -> None:
    p1 = make_project(analysis_status="analyzed")
    add_file(p1, "src/a.py")

    p2 = make_project(errors=["Failed to parse some file"])
    add_file(p2, "src/a.py")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert res.outcome.status == OperationStatus.INCOMPLETE
    assert any(d.code == "INCOMPLETE_AFTER_STATE" for d in res.diagnostics)


def test_23_missing_before_state() -> None:
    p2 = make_project()
    res = compare_states(None, p2)
    assert res.outcome.is_blocked is True
    assert res.is_complete is False


def test_24_missing_after_state() -> None:
    p1 = make_project()
    res = compare_states(p1, None)
    assert res.outcome.is_blocked is True
    assert res.is_complete is False


def test_25_parsing_failures_affecting_comparison() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py")

    p2 = make_project(errors=["SyntaxError in src/b.py"])
    add_file(p2, "src/a.py")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert any("INCOMPLETE_AFTER_STATE" in (d.code or "") for d in res.diagnostics)


def test_26_stale_or_indeterminate_states() -> None:
    p1 = make_project()
    p2 = make_project()

    s1 = ComparisonState.from_project(p1, state_id="s1", freshness=FreshnessState.STALE)
    s2 = ComparisonState.from_project(
        p2, state_id="s2", freshness=FreshnessState.INDETERMINATE
    )

    res = compare_states(s1, s2)
    assert any(d.code == "STALE_STATE" for d in res.diagnostics)
    assert any(d.code == "INDETERMINATE_FRESHNESS" for d in res.diagnostics)


def test_27_missing_fingerprints_no_unsupported_modification_claim() -> None:
    p1 = make_project()
    add_file(p1, "src/a.py", size=100)

    p2 = make_project()
    add_file(p2, "src/a.py", size=100)

    res = compare_states(p1, p2)
    assert len(res.modified_files) == 0


def test_28_deterministic_ordering_independent_of_input_order() -> None:
    p1 = make_project()
    add_file(p1, "src/c.py")
    add_file(p1, "src/a.py")
    add_file(p1, "src/b.py")

    p2 = make_project()
    add_file(p2, "src/b.py")
    add_file(p2, "src/a.py")
    add_file(p2, "src/c.py")
    add_file(p2, "src/z.py")
    add_file(p2, "src/m.py")

    res1 = compare_states(p1, p2)
    assert [f.path for f in res1.added_files] == ["src/m.py", "src/z.py"]


def test_29_serialized_output_deterministic() -> None:
    p1 = make_project()
    add_file(p1, "src/b.py")
    add_file(p1, "src/a.py")

    p2 = make_project()
    add_file(p2, "src/a.py")
    add_file(p2, "src/c.py")

    res = compare_states(p1, p2)
    dict1 = res.to_dict()
    json1 = json.dumps(dict1, sort_keys=True)
    dict2 = res.to_dict()
    json2 = json.dumps(dict2, sort_keys=True)

    assert json1 == json2
    assert "added_files" in dict1
    assert "removed_files" in dict1


def test_30_symbol_signature_modification() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "run", signature="def run()")

    p2 = make_project()
    f2 = add_file(p2, "src/a.py")
    add_symbol(p2, f2.id, "run", signature="def run(verbose: bool = False)")

    res = compare_states(p1, p2)
    assert len(res.modified_symbols) == 1
    sym = res.modified_symbols[0]
    assert sym.name == "run"
    assert sym.before_signature == "def run()"
    assert sym.after_signature == "def run(verbose: bool = False)"


def test_31_state_identity_and_outcome_information_exposed() -> None:
    p1 = make_project()
    p2 = make_project()
    s1 = ComparisonState.from_project(p1, state_id="v0.12-base")
    s2 = ComparisonState.from_project(p2, state_id="v0.13-head")

    res = compare_states(s1, s2)
    assert res.before_state_id == "v0.12-base"
    assert res.after_state_id == "v0.13-head"
    assert res.repository_key == str(p1.root_path.resolve())
    assert res.outcome.is_success is True


def test_32_no_silent_fallback_to_current_cache() -> None:
    res = compare_states(None, make_project())
    assert res.outcome.is_blocked is True
    assert res.before_state_id is None


def test_regression_01_incomplete_before_state_with_file_additions() -> None:
    p1 = make_project(analysis_status="failed")
    add_file(p1, "src/a.py")

    p2 = make_project(analysis_status="analyzed")
    add_file(p2, "src/a.py")
    add_file(p2, "src/new_file.py")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert len(res.added_files) == 1
    assert res.added_files[0].path == "src/new_file.py"
    assert (
        res.added_files[0].details.get("qualification")
        == "unconfirmed_addition_due_to_incomplete_analysis"
    )


def test_regression_02_incomplete_before_state_with_symbol_additions() -> None:
    p1 = make_project(analysis_status="not_analyzed")
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "existing")

    p2 = make_project(analysis_status="analyzed")
    f2 = add_file(p2, "src/a.py")
    add_symbol(p2, f2.id, "existing")
    add_symbol(p2, f2.id, "new_fn")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert len(res.added_symbols) == 1
    assert res.added_symbols[0].name == "new_fn"
    assert (
        res.added_symbols[0].details.get("qualification")
        == "unconfirmed_addition_due_to_incomplete_analysis"
    )


def test_regression_03_incomplete_before_state_with_relationship_additions() -> None:
    p1 = make_project(errors=["analyzer timeout on module b"])
    add_file(p1, "src/a.py")
    add_file(p1, "src/b.py")

    p2 = make_project(analysis_status="analyzed")
    f1 = add_file(p2, "src/a.py")
    f2 = add_file(p2, "src/b.py")
    p2.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert len(res.added_relationships) == 1
    assert (
        res.added_relationships[0].details.get("qualification")
        == "unconfirmed_addition_due_to_incomplete_analysis"
    )


def test_regression_04_incomplete_after_state_with_file_removals() -> None:
    p1 = make_project(analysis_status="analyzed")
    add_file(p1, "src/a.py")
    add_file(p1, "src/b.py")

    p2 = make_project(analysis_status="partial")
    add_file(p2, "src/a.py")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert len(res.removed_files) == 1
    assert res.removed_files[0].path == "src/b.py"
    assert (
        res.removed_files[0].details.get("qualification")
        == "unconfirmed_removal_due_to_incomplete_analysis"
    )


def test_regression_05_incomplete_after_state_with_symbol_removals() -> None:
    p1 = make_project(analysis_status="analyzed")
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "stay")
    add_symbol(p1, f1.id, "remove_me")

    p2 = make_project(errors=["Parse error in a.py"])
    f2 = add_file(p2, "src/a.py")
    add_symbol(p2, f2.id, "stay")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert len(res.removed_symbols) == 1
    assert res.removed_symbols[0].name == "remove_me"
    assert (
        res.removed_symbols[0].details.get("qualification")
        == "unconfirmed_removal_due_to_incomplete_analysis"
    )


def test_regression_06_incomplete_after_state_with_relationship_removals() -> None:
    p1 = make_project(analysis_status="analyzed")
    f1 = add_file(p1, "src/a.py")
    f2 = add_file(p1, "src/b.py")
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    p2 = make_project(analysis_status="failed")
    add_file(p2, "src/a.py")
    add_file(p2, "src/b.py")

    res = compare_states(p1, p2)
    assert res.is_complete is False
    assert len(res.removed_relationships) == 1
    assert (
        res.removed_relationships[0].details.get("qualification")
        == "unconfirmed_removal_due_to_incomplete_analysis"
    )


def test_regression_07_fully_complete_pair_reports_unqualified_differences() -> None:
    p1 = make_project(analysis_status="analyzed")
    f1 = add_file(p1, "src/stay.py")
    f_rem = add_file(p1, "src/removed.py")
    add_symbol(p1, f1.id, "sym_stay")
    add_symbol(p1, f1.id, "sym_remove")
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f_rem.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    p2 = make_project(analysis_status="analyzed")
    f1_new = add_file(p2, "src/stay.py")
    f_add = add_file(p2, "src/added.py")
    add_symbol(p2, f1_new.id, "sym_stay")
    add_symbol(p2, f1_new.id, "sym_add")
    p2.add_relationship(
        Relationship(
            source_id=f1_new.id,
            target_id=f_add.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    res = compare_states(p1, p2)
    assert res.is_complete is True
    assert res.outcome.is_success is True

    assert len(res.added_files) == 1
    assert res.added_files[0].path == "src/added.py"
    assert "qualification" not in res.added_files[0].details
    assert len(res.removed_files) == 1
    assert res.removed_files[0].path == "src/removed.py"
    assert "qualification" not in res.removed_files[0].details

    assert len(res.added_symbols) == 1
    assert res.added_symbols[0].name == "sym_add"
    assert "qualification" not in res.added_symbols[0].details
    assert len(res.removed_symbols) == 1
    assert res.removed_symbols[0].name == "sym_remove"
    assert "qualification" not in res.removed_symbols[0].details

    assert len(res.added_relationships) == 1
    assert "qualification" not in res.added_relationships[0].details
    assert len(res.removed_relationships) == 1
    assert "qualification" not in res.removed_relationships[0].details


def test_symmetrical_modifications_qualification_under_incomplete_state() -> None:
    p1 = make_project(analysis_status="analyzed")
    f1 = add_file(p1, "src/a.py")
    f2 = add_file(p1, "src/b.py")
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.REFERENCES,
            confidence=0.5,
        )
    )

    p2 = make_project(analysis_status="failed")
    f1_new = add_file(p2, "src/a.py")
    f2_new = add_file(p2, "src/b.py")
    p2.add_relationship(
        Relationship(
            source_id=f1_new.id,
            target_id=f2_new.id,
            relationship_type=RelationshipType.REFERENCES,
            confidence=0.9,
        )
    )

    res = compare_states(p1, p2)
    assert len(res.modified_relationships) == 1
    rel_diff = res.modified_relationships[0]
    assert (
        rel_diff.details.get("qualification")
        == "unconfirmed_modification_due_to_incomplete_analysis"
    )


def test_symbol_collision_detection_and_ambiguity() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    add_symbol(p1, f1.id, "overloaded", start_line=10, end_line=15)
    add_symbol(p1, f1.id, "overloaded", start_line=20, end_line=25)

    p2 = make_project()
    f2 = add_file(p2, "src/a.py")
    add_symbol(p2, f2.id, "overloaded", start_line=10, end_line=15)

    res = compare_states(p1, p2)
    assert any(d.code == "SYMBOL_COLLISION" for d in res.diagnostics)
    assert any("Symbol key collision detected" in lim for lim in res.limitations)
    assert any(
        amb.category == "symbol" and "Symbol collision" in amb.reason
        for amb in res.ambiguous_matches
    )


def test_relationship_collision_detection_and_ambiguity() -> None:
    p1 = make_project()
    f1 = add_file(p1, "src/a.py")
    f2 = add_file(p1, "src/b.py")
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"call_line": 10},
        )
    )
    p1.add_relationship(
        Relationship(
            source_id=f1.id,
            target_id=f2.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"call_line": 42},
        )
    )

    p2 = make_project()
    f1_new = add_file(p2, "src/a.py")
    f2_new = add_file(p2, "src/b.py")
    p2.add_relationship(
        Relationship(
            source_id=f1_new.id,
            target_id=f2_new.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"call_line": 10},
        )
    )

    res = compare_states(p1, p2)
    assert any(d.code == "RELATIONSHIP_COLLISION" for d in res.diagnostics)
    assert any("Relationship collision detected" in lim for lim in res.limitations)
    assert any(
        amb.category == "relationship" and "Relationship collision" in amb.reason
        for amb in res.ambiguous_matches
    )
