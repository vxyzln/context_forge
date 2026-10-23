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
from context_forge.query.path import (
    find_relationship_path,
)
from context_forge.query.project import ProjectQuery
from context_forge.reporting.contract import OperationStatus


def create_path_test_project(tmp_path: Path) -> Project:
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)

    project = Project(
        name="Path Test Project",
        root_path=root,
        analysis_status="analyzed",
    )

    src_dir = Directory(project_id=project.id, path=Path("src"), name="src")
    project.add_directory(src_dir)

    files = {}
    for name in ("a.py", "b.py", "c.py", "d.py", "e.py", "isolated.py"):
        f = File(
            project_id=project.id,
            path=Path(f"src/{name}"),
            name=name,
            extension=".py",
            directory_id=src_dir.id,
        )
        project.add_file(f)
        files[name] = f
        (root / "src" / name).write_text(f"# {name}\n", encoding="utf-8")

    # Symbols
    sym_a = Symbol(
        file_id=files["a.py"].id,
        name="fn_a",
        kind="function",
        start_line=1,
        end_line=10,
    )
    sym_b = Symbol(
        file_id=files["b.py"].id,
        name="fn_b",
        kind="function",
        start_line=1,
        end_line=10,
    )
    project.add_symbol(sym_a)
    project.add_symbol(sym_b)

    # Base graph:
    # a.py -> imports -> b.py (line 10)
    # b.py -> calls -> c.py (line 25)
    # c.py -> references -> d.py (no line)
    # d.py -> depends_on -> e.py
    # Also a shortcut: a.py -> references -> c.py (length 2 vs length 3 path to d.py)
    project.add_relationship(
        Relationship(
            source_id=files["a.py"].id,
            target_id=files["b.py"].id,
            relationship_type=RelationshipType.IMPORTS,
            metadata={"line": "10"},
        )
    )
    project.add_relationship(
        Relationship(
            source_id=files["b.py"].id,
            target_id=files["c.py"].id,
            relationship_type=RelationshipType.CALLS,
            metadata={"line": "25"},
        )
    )
    project.add_relationship(
        Relationship(
            source_id=files["c.py"].id,
            target_id=files["d.py"].id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=files["d.py"].id,
            target_id=files["e.py"].id,
            relationship_type=RelationshipType.DEPENDS_ON,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=files["a.py"].id,
            target_id=files["c.py"].id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    return project


def test_01_direct_one_edge_path(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/a.py", "src/b.py")

    assert res.path_found is True
    assert res.is_exhaustive is True
    assert res.length == 1
    assert len(res.steps) == 1
    step = res.steps[0]
    assert step.from_name == "a.py"
    assert step.to_name == "b.py"
    assert step.relationship_type == "imports"
    assert step.traversal_direction == "outgoing"
    assert step.source_line == 10


def test_02_multi_edge_path(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/b.py", "src/e.py")

    assert res.path_found is True
    assert res.length == 3  # b -> c -> d -> e
    assert len(res.steps) == 3
    assert res.steps[0].to_name == "c.py"
    assert res.steps[1].to_name == "d.py"
    assert res.steps[2].to_name == "e.py"


def test_03_shortest_path_selected_when_multiple_exist(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # From a.py to d.py:
    # Path 1: a -> b -> c -> d (length 3)
    # Path 2: a -> c -> d (length 2)
    res = find_relationship_path(proj, "src/a.py", "src/d.py")

    assert res.path_found is True
    assert res.length == 2
    assert res.steps[0].to_name == "c.py"
    assert res.steps[1].to_name == "d.py"


def test_04_deterministic_tie_breaking_for_equal_length_paths(
    tmp_path: Path,
) -> None:
    proj = create_path_test_project(tmp_path)
    # Add parallel edge from a to b of different type
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))
    proj.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_b.id,
            relationship_type=RelationshipType.CALLS,
        )
    )

    res1 = find_relationship_path(proj, "src/a.py", "src/b.py")
    res2 = find_relationship_path(proj, "src/a.py", "src/b.py")

    assert res1.steps[0].relationship_id == res2.steps[0].relationship_id


def test_05_start_equal_to_end(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/a.py", "src/a.py")

    assert res.path_found is True
    assert res.is_exhaustive is True
    assert res.length == 0
    assert len(res.steps) == 0
    assert "zero-edge" in res.message


def test_06_missing_start_endpoint(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/missing_start.py", "src/b.py")

    assert res.path_found is False
    assert res.status == "endpoint_unresolved"
    assert any(d.code == "UNRESOLVED_START_ENDPOINT" for d in res.diagnostics)


def test_07_missing_end_endpoint(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/a.py", "src/missing_end.py")

    assert res.path_found is False
    assert res.status == "endpoint_unresolved"
    assert any(d.code == "UNRESOLVED_END_ENDPOINT" for d in res.diagnostics)


def test_08_ambiguous_start_endpoint(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))
    f_c = next(f for f in proj.files if f.path == Path("src/c.py"))
    proj.add_symbol(
        Symbol(
            file_id=f_b.id, name="dup_sym", kind="function", start_line=1, end_line=5
        )
    )
    proj.add_symbol(
        Symbol(
            file_id=f_c.id, name="dup_sym", kind="function", start_line=1, end_line=5
        )
    )

    res = find_relationship_path(proj, "dup_sym", "src/d.py")
    assert res.path_found is False
    assert res.status == "endpoint_unresolved"
    assert res.start_resolution is not None
    assert res.start_resolution.is_ambiguous is True


def test_09_ambiguous_end_endpoint(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))
    f_c = next(f for f in proj.files if f.path == Path("src/c.py"))
    proj.add_symbol(
        Symbol(
            file_id=f_b.id, name="dup_sym", kind="function", start_line=1, end_line=5
        )
    )
    proj.add_symbol(
        Symbol(
            file_id=f_c.id, name="dup_sym", kind="function", start_line=1, end_line=5
        )
    )

    res = find_relationship_path(proj, "src/a.py", "dup_sym")
    assert res.path_found is False
    assert res.status == "endpoint_unresolved"
    assert res.end_resolution is not None
    assert res.end_resolution.is_ambiguous is True


def test_10_invalid_endpoint_input(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    with pytest.raises(ValueError, match="cannot be empty"):
        find_relationship_path(proj, "   ", "src/b.py")


def test_11_disconnected_endpoints_exhaustive_search(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/a.py", "src/isolated.py")

    assert res.path_found is False
    assert res.is_exhaustive is True
    assert res.status == "no_path_found"
    assert res.outcome.is_success is True  # Definitive negative outcome


def test_12_depth_limited_search_inconclusive(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # Path from b.py to e.py is 3 hops: b -> c -> d -> e
    # If max_depth=1, it cannot reach e.py and frontier is truncated
    res = find_relationship_path(proj, "src/b.py", "src/e.py", max_depth=1)

    assert res.path_found is False
    assert res.is_exhaustive is False
    assert res.status == "depth_limited"
    assert res.outcome.status == OperationStatus.PARTIAL
    assert any(d.code == "DEPTH_LIMIT_REACHED" for d in res.diagnostics)


def test_13_depth_limit_reached_with_path_beyond(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/b.py", "src/e.py", max_depth=2)

    assert res.path_found is False
    assert res.is_exhaustive is False
    assert res.status == "depth_limited"


def test_14_path_found_within_permitted_depth(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/b.py", "src/e.py", max_depth=3)

    assert res.path_found is True
    assert res.length == 3


def test_15_expansion_limit_inconclusive(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # If max_expansions=1, expanding the start node exhausts limit before finding target
    res = find_relationship_path(
        proj, "src/a.py", "src/e.py", max_expansions=1, max_depth=10
    )

    assert res.path_found is False
    assert res.is_exhaustive is False
    assert res.status == "expansion_limited"
    assert any(d.code == "EXPANSION_LIMIT_REACHED" for d in res.diagnostics)


def test_16_cycle_handling(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))
    # Add cycle b -> a
    proj.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    res = find_relationship_path(proj, "src/a.py", "src/d.py")
    assert res.path_found is True
    assert res.length == 2


def test_17_self_loop_handling(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    proj.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    res = find_relationship_path(proj, "src/a.py", "src/b.py")
    assert res.path_found is True
    assert res.length == 1


def test_18_directional_traversal_outgoing(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # Stored edge: a.py -> b.py
    # Outgoing from a to b works:
    res = find_relationship_path(proj, "src/a.py", "src/b.py", direction="outgoing")
    assert res.path_found is True

    # Outgoing from b to a should find NO path:
    res_rev = find_relationship_path(proj, "src/b.py", "src/a.py", direction="outgoing")
    assert res_rev.path_found is False
    assert res_rev.is_exhaustive is True


def test_19_directional_traversal_incoming(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # Stored edge: a.py -> b.py
    # Incoming from b.py to a.py follows target -> source:
    res = find_relationship_path(proj, "src/b.py", "src/a.py", direction="incoming")
    assert res.path_found is True
    step = res.steps[0]
    assert step.traversal_direction == "incoming"
    assert step.stored_source_id == step.to_id
    assert step.stored_target_id == step.from_id


def test_20_both_direction_traversal(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # Stored: a -> b and a -> c. In both direction, path between b and c exists via a:
    res = find_relationship_path(proj, "src/b.py", "src/c.py", direction="both")
    assert res.path_found is True


def test_21_relationship_type_filtering(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # a.py -> b.py is IMPORTS
    res = find_relationship_path(
        proj, "src/a.py", "src/b.py", relationship_types={"imports"}
    )
    assert res.path_found is True


def test_22_excluded_relationship_types_not_traversed(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    # a.py -> b.py is IMPORTS; filter only CALLS
    res = find_relationship_path(
        proj, "src/a.py", "src/b.py", relationship_types={"calls"}
    )
    assert res.path_found is False
    assert res.is_exhaustive is True


def test_23_preservation_of_stored_relationship_direction(
    tmp_path: Path,
) -> None:
    proj = create_path_test_project(tmp_path)
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    f_b = next(f for f in proj.files if f.path == Path("src/b.py"))

    res = find_relationship_path(proj, "src/b.py", "src/a.py", direction="incoming")
    step = res.steps[0]
    # Stored source must remain f_a.id, stored target must remain f_b.id!
    assert step.stored_source_id == f_a.id
    assert step.stored_target_id == f_b.id
    assert step.traversal_direction == "incoming"


def test_24_accurate_traversal_direction_for_every_step(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/a.py", "src/d.py")
    for step in res.steps:
        assert step.traversal_direction in ("outgoing", "incoming")


def test_25_source_line_metadata_preserved_when_present(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/a.py", "src/b.py")
    assert res.steps[0].source_line == 10


def test_26_missing_source_line_metadata_handled_correctly(
    tmp_path: Path,
) -> None:
    proj = create_path_test_project(tmp_path)
    # a.py -> c.py has no line in metadata
    res = find_relationship_path(
        proj, "src/a.py", "src/c.py", relationship_types={"references"}
    )
    assert res.steps[0].source_line is None


def test_27_every_adjacent_step_joins_correctly(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/b.py", "src/e.py")
    assert res.length == 3
    for i in range(len(res.steps) - 1):
        assert res.steps[i].to_id == res.steps[i + 1].from_id


def test_28_complete_path_starts_and_ends_at_endpoints(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res = find_relationship_path(proj, "src/b.py", "src/e.py")
    assert res.steps[0].from_id == res.start_target.id
    assert res.steps[-1].to_id == res.end_target.id


def test_29_stable_result_ordering(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    res1 = find_relationship_path(proj, "src/a.py", "src/e.py")
    res2 = find_relationship_path(proj, "src/a.py", "src/e.py")

    assert [s.relationship_id for s in res1.steps] == [
        s.relationship_id for s in res2.steps
    ]


def test_30_empty_graph_complete_evidence(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    proj.relationships.clear()

    res = find_relationship_path(proj, "src/a.py", "src/b.py")
    assert res.path_found is False
    assert res.is_exhaustive is True
    assert res.status == "no_path_found"


def test_31_empty_or_incomplete_graph(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    proj.analysis_status = "failed"
    proj.errors = ["Some parser error"]

    res = find_relationship_path(proj, "src/a.py", "src/b.py")
    # Path is found in existing graph, but outcome should be incomplete/partial
    assert res.outcome.status == OperationStatus.INCOMPLETE


def test_32_cli_text_output_found_path(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    stdout = io.StringIO()
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", stdout),
    ):
        main(["path", "src/a.py", "src/b.py", "--path", str(proj.root_path)])

    output = stdout.getvalue()
    assert "Status: Path found" in output
    assert "Path steps:" in output
    assert "a.py" in output


def test_33_cli_text_output_no_path_found(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    stdout = io.StringIO()
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", stdout),
    ):
        main(["path", "src/a.py", "src/isolated.py", "--path", str(proj.root_path)])

    output = stdout.getvalue()
    assert "No path exists (exhaustive search)" in output


def test_34_cli_text_output_inconclusive(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    stdout = io.StringIO()
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", stdout),
    ):
        main(
            [
                "path",
                "src/b.py",
                "src/e.py",
                "--depth",
                "1",
                "--path",
                str(proj.root_path),
            ]
        )

    output = stdout.getvalue()
    assert "Inconclusive search" in output


def test_35_cli_json_output(tmp_path: Path) -> None:
    proj = create_path_test_project(tmp_path)
    stdout = io.StringIO()
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        patch("sys.stdout", stdout),
    ):
        main(
            [
                "path",
                "src/a.py",
                "src/b.py",
                "--path",
                str(proj.root_path),
                "--format",
                "json",
            ]
        )

    output = stdout.getvalue().strip()
    data = json.loads(output)
    assert data["path_found"] is True
    assert data["length"] == 1
    assert "steps" in data
    assert "start_target" in data
    assert "end_target" in data


def test_36_invalid_depth_and_expansion_arguments(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    proj = create_path_test_project(tmp_path)
    with (
        patch("context_forge.main.load_fresh_project", return_value=(proj, None)),
        pytest.raises(SystemExit) as exc_info,
    ):
        main(
            [
                "path",
                "src/a.py",
                "src/b.py",
                "--depth",
                "0",
                "--path",
                str(proj.root_path),
            ]
        )
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "positive integer" in captured.err


def test_37_project_query_method_and_traverse_regression(
    tmp_path: Path,
) -> None:
    proj = create_path_test_project(tmp_path)
    pq = ProjectQuery(proj)

    # find_relationship_path on ProjectQuery
    res = pq.find_relationship_path("src/a.py", "src/b.py")
    assert res.path_found is True

    # Regression: traverse on ProjectQuery still works
    f_a = next(f for f in proj.files if f.path == Path("src/a.py"))
    traversed = pq.traverse(f_a.id, max_depth=1)
    assert len(traversed) > 0
