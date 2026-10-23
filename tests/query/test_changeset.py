from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.main import main
from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.query.changeset import analyze_changeset
from context_forge.query.impact import find_impact
from context_forge.query.project import ProjectQuery
from context_forge.reporting.contract import OperationStatus


def create_changeset_project(tmp_path: Path) -> Project:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)

    project = Project(
        name="ChangeSet Test Project",
        root_path=root,
        analysis_status="analyzed",
    )

    src_dir = Directory(project_id=project.id, path=Path("src"), name="src")
    tests_dir = Directory(project_id=project.id, path=Path("tests"), name="tests")
    project.add_directory(src_dir)
    project.add_directory(tests_dir)

    f_a = File(
        project_id=project.id,
        path=Path("src/a.py"),
        name="a.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_b = File(
        project_id=project.id,
        path=Path("src/b.py"),
        name="b.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_c = File(
        project_id=project.id,
        path=Path("src/c.py"),
        name="c.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_d = File(
        project_id=project.id,
        path=Path("src/d.py"),
        name="d.py",
        extension=".py",
        directory_id=src_dir.id,
    )
    f_test = File(
        project_id=project.id,
        path=Path("tests/test_a.py"),
        name="test_a.py",
        extension=".py",
        directory_id=tests_dir.id,
    )

    project.add_file(f_a)
    project.add_file(f_b)
    project.add_file(f_c)
    project.add_file(f_d)
    project.add_file(f_test)

    # Physical files on disk
    (root / "src" / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    (root / "src" / "b.py").write_text("import src.a\n", encoding="utf-8")
    (root / "src" / "c.py").write_text("import src.b\n", encoding="utf-8")
    (root / "src" / "d.py").write_text("def d(): pass\n", encoding="utf-8")
    (root / "tests" / "test_a.py").write_text("import src.a\n", encoding="utf-8")

    # Relationships:
    # b -> imports -> a (so changing a affects b; b is downstream of a in both/incoming)
    # c -> imports -> b (so changing b affects c; c is downstream of b)
    # test_a -> imports -> a
    project.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_c.id,
            target_id=f_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_test.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    return project


def test_01_single_valid_changed_file(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py"])

    assert res.status == "success"
    assert res.outcome.is_success is True
    assert len(res.supplied_paths) == 1
    assert len(res.resolved_inputs) == 1
    assert res.resolved_inputs[0].is_resolved is True
    # b.py is directly impacted, c.py is downstream
    affected_paths = [it.path for it in res.items]
    assert "src/b.py" in affected_paths
    assert "src/c.py" in affected_paths
    assert res.direct_count >= 1


def test_02_multiple_valid_changed_files(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # Both a.py and d.py changed
    res = analyze_changeset(proj, ["src/a.py", "src/d.py"])

    assert res.status == "success"
    assert len(res.resolved_inputs) == 2
    assert all(r.is_resolved for r in res.resolved_inputs)


def test_03_multiple_changed_files_affecting_same_downstream(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # Add an edge so d.py also affects c.py
    f_c = next(f for f in proj.files if f.path == Path("src/c.py"))
    f_d = next(f for f in proj.files if f.path == Path("src/d.py"))
    proj.add_relationship(
        Relationship(
            source_id=f_c.id,
            target_id=f_d.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    res = analyze_changeset(proj, ["src/a.py", "src/d.py"])
    # c.py is reached from BOTH src/a.py and src/d.py
    c_item = next(it for it in res.items if it.path == "src/c.py")
    assert "src/a.py" in c_item.roots
    assert "src/d.py" in c_item.roots
    assert len(c_item.provenance) == 2


def test_04_deduplication_by_stable_identity(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py", "src/b.py"])

    # Every item must have unique entity_id
    entity_ids = [it.entity_id for it in res.items]
    assert len(entity_ids) == len(set(entity_ids))


def test_05_distinct_entities_with_identical_names(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # Add two symbols with identical name 'helper' in different files
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))
    s1 = Symbol(
        file_id=f_a.id, name="helper", kind="function", start_line=1, end_line=5
    )
    s2 = Symbol(
        file_id=f_b.id, name="helper", kind="function", start_line=1, end_line=5
    )
    proj.add_symbol(s1)
    proj.add_symbol(s2)

    # Edge from a.py to s1, and edge from b.py to s2
    proj.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=s1.id,
            relationship_type=RelationshipType.CALLS,
        )
    )
    proj.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=s2.id,
            relationship_type=RelationshipType.CALLS,
        )
    )

    res = analyze_changeset(proj, ["src/a.py", "src/b.py"])
    helpers = [it for it in res.items if it.name == "helper"]
    # They should both be in items, with different entity_ids
    assert len(helpers) == 2
    assert helpers[0].entity_id != helpers[1].entity_id


def test_06_correct_direct_and_downstream_classification(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py"])

    b_item = next(it for it in res.items if it.path == "src/b.py")
    c_item = next(it for it in res.items if it.path == "src/c.py")

    assert b_item.classification == "direct"
    assert b_item.min_depth == 1
    assert c_item.classification == "downstream"
    assert c_item.min_depth == 2


def test_07_overlapping_roots(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # Both a.py and b.py are roots. b.py is also impacted by a.py!
    res = analyze_changeset(proj, ["src/a.py", "src/b.py"])

    # Consistent set-level classification: b.py is a root
    b_item = next(it for it in res.items if it.path == "src/b.py")
    assert b_item.classification == "root"
    # But b_item provenance records reachability from a.py
    assert any(p.root_path == "src/a.py" for p in b_item.provenance)


def test_08_multiple_paths_to_same_affected_entity(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # Add direct edge from a.py to c.py as well as transitive path through b.py
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    f_c = next(f for f in proj.files if f.path == Path("src/c.py"))
    proj.add_relationship(
        Relationship(
            source_id=f_c.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.CALLS,
        )
    )

    res = analyze_changeset(proj, ["src/a.py"])
    c_item = next(it for it in res.items if it.path == "src/c.py")
    # Shortest path is 1 hop (CALLS)
    assert c_item.min_depth == 1
    assert c_item.classification == "direct"


def test_09_cycles_and_self_loops(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))
    # Add cycle a -> b -> a
    proj.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_b.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )
    # Self-loop on a
    proj.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    # Must terminate without infinite loop
    res = analyze_changeset(proj, ["src/a.py"], max_depth=5)
    assert res.status == "success"


def test_10_duplicate_input_paths(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py", "src/a.py"])

    assert len(res.supplied_paths) == 2
    assert len(res.resolved_inputs) == 2
    # Affected items deduplicated
    entity_ids = [it.entity_id for it in res.items]
    assert len(entity_ids) == len(set(entity_ids))


def test_11_multiple_inputs_resolving_to_same_entity(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py", "./src/a.py"])

    assert len(res.resolved_inputs) == 2
    assert all(r.is_resolved for r in res.resolved_inputs)
    assert res.resolved_inputs[0].target.id == res.resolved_inputs[1].target.id


def test_12_missing_path(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/nonexistent.py"])

    assert res.status == "blocked"
    assert res.outcome.is_blocked is True
    assert res.resolved_inputs[0].status == "not_found"


def test_13_path_outside_permitted_root(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["../outside.py"])

    assert res.status == "blocked"
    assert res.resolved_inputs[0].status == "outside_root"
    assert any(d.code == "UNANALYZABLE_PATH" for d in res.diagnostics)


def test_14_ambiguous_path_mapping(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # Add duplicate file path in project inventory
    proj.add_file(
        File(
            project_id=proj.id,
            path=Path("src/a.py"),
            name="a.py",
            extension=".py",
        )
    )
    res = analyze_changeset(proj, ["src/a.py"])
    assert res.resolved_inputs[0].status == "ambiguous"


def test_15_unsupported_unindexed_file_type(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    (proj.root_path / "data.bin").write_bytes(b"\x00\x01\x02")
    res = analyze_changeset(proj, ["data.bin"])

    assert res.resolved_inputs[0].status == "unindexed"


def test_16_insufficient_analysis_evidence(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    proj.analysis_status = "failed"
    proj.errors = ["Parser crashed"]

    res = analyze_changeset(proj, ["src/a.py"])
    assert res.status == "incomplete"
    assert res.outcome.status == OperationStatus.INCOMPLETE


def test_17_mixed_valid_and_invalid_paths(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py", "src/missing.py"])

    # Partial success: a.py was analyzed, missing.py was reported
    assert res.status == "partial"
    assert res.outcome.status == OperationStatus.PARTIAL
    assert any(r.status == "resolved" for r in res.resolved_inputs)
    assert any(r.status == "not_found" for r in res.resolved_inputs)
    # Items from a.py are still found!
    assert len(res.items) > 0


def test_18_empty_change_set(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, [])

    assert res.status == "blocked"
    assert res.outcome.is_blocked is True
    assert any(d.code == "EMPTY_CHANGESET" for d in res.diagnostics)


def test_19_traversal_depth_limit(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # Depth 1 from a.py reaches b.py, but not c.py (which is depth 2)
    res = analyze_changeset(proj, ["src/a.py"], max_depth=1)

    affected_paths = [it.path for it in res.items]
    assert "src/b.py" in affected_paths
    assert "src/c.py" not in affected_paths
    assert any("Traversal depth was limited" in lim for lim in res.limitations)


def test_20_result_limit_and_explicit_truncation(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py"], limit=1)

    assert len(res.items) == 1
    assert res.truncated is True
    assert res.total > 1
    assert any("Display was limited to 1" in lim for lim in res.limitations)


def test_21_deterministic_output_ordering(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res1 = analyze_changeset(proj, ["src/a.py"])
    res2 = analyze_changeset(proj, ["src/a.py"])

    paths1 = [it.path for it in res1.items]
    paths2 = [it.path for it in res2.items]
    assert paths1 == paths2


def test_22_provenance_retained_for_multiple_roots(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))
    f_d = next(f for f in proj.files if f.path == Path("src/d.py"))
    proj.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=f_d.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    res = analyze_changeset(proj, ["src/a.py", "src/d.py"])
    b_item = next(it for it in res.items if it.path == "src/b.py")

    assert "src/a.py" in b_item.roots
    assert "src/d.py" in b_item.roots
    assert len(b_item.provenance) == 2


def test_23_evidence_based_relevant_tests(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # tests/test_a.py imports src/a.py in graph
    res = analyze_changeset(proj, ["src/a.py"])

    assert len(res.relevant_tests) >= 1
    test_paths = [t.test_file_path for t in res.relevant_tests]
    assert "tests/test_a.py" in test_paths


def test_24_no_unsupported_test_association_without_evidence(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    # src/d.py has no test relationships in graph
    res = analyze_changeset(proj, ["src/d.py"])

    assert len(res.relevant_tests) == 0
    assert any(
        "Test relevance could not be established" in lim for lim in res.limitations
    )


def test_25_partial_status_reporting(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    res = analyze_changeset(proj, ["src/a.py", "missing.py"])
    assert res.status == "partial"
    assert res.outcome.status == OperationStatus.PARTIAL


def test_26_cli_text_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = create_changeset_project(tmp_path)
    # Use ProjectQuery or mock load_fresh_project
    stdout = io.StringIO()
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", stdout),
    ):
        main(["changeset", "src/a.py", "--path", str(proj.root_path)])

    output = stdout.getvalue()
    assert "Change-set paths" in output
    assert "Overall impact" in output
    assert "Direct impact:" in output


def test_27_cli_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = create_changeset_project(tmp_path)
    stdout = io.StringIO()
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", stdout),
    ):
        main(
            [
                "changeset",
                "src/a.py",
                "--path",
                str(proj.root_path),
                "--format",
                "json",
            ]
        )

    output = stdout.getvalue().strip()
    data = json.loads(output)
    assert data["status"] == "success"
    assert "items" in data
    assert "resolved_inputs" in data
    assert "relevant_tests" in data


def test_28_invalid_cli_limit_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_changeset_project(tmp_path)
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(
            [
                "changeset",
                "src/a.py",
                "--limit",
                "0",
                "--path",
                str(proj.root_path),
            ]
        )
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "positive integer" in captured.err


def test_29_project_query_method_and_regression_coverage(tmp_path: Path) -> None:
    proj = create_changeset_project(tmp_path)
    pq = ProjectQuery(proj)

    # analyze_changeset on ProjectQuery
    res = pq.analyze_changeset(["src/a.py"])
    assert res.status == "success"

    # Regression: find_impact on ProjectQuery still works
    imp = pq.find_impact("src/a.py")
    assert imp.status == "resolved"
    assert imp.total > 0

    # Regression: direct find_impact function
    imp2 = find_impact(proj, "src/a.py")
    assert imp2.status == "resolved"
