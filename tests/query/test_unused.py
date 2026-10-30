from pathlib import Path

import pytest

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.parser.result import SymbolReference
from context_forge.query.project import ProjectQuery
from context_forge.query.unused import (
    UnusedClassification,
    UnusedEntitiesReport,
    _normalize_kind_filter,
    find_unused_candidates,
)
from context_forge.reporting.contract import OperationStatus


def _create_test_project(tmp_path: Path) -> Project:
    root = tmp_path.resolve()
    return Project(
        name="test_proj",
        root_path=root,
        analysis_status="analyzed",
    )


def test_unused_function_candidate(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    unused_fn = Symbol(
        file_id=file_a.id,
        name="unused_func",
        kind="function",
        start_line=10,
        end_line=15,
        qualified_name="a.unused_func",
    )
    proj.symbols.append(unused_fn)

    report = find_unused_candidates(proj)
    assert isinstance(report, UnusedEntitiesReport)
    assert report.outcome.status == OperationStatus.SUCCESS
    assert report.summary.candidates_count >= 1

    candidate_names = [c.name for c in report.candidates]
    assert "unused_func" in candidate_names
    item = next(c for c in report.candidates if c.name == "unused_func")
    assert item.kind == "function"
    assert item.classification == UnusedClassification.APPARENT_UNUSED_CANDIDATE.value
    assert item.start_line == 10
    assert item.end_line == 15
    assert "No external incoming references" in item.reason


def test_used_function_is_not_candidate(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/b.py"), name="b.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    used_fn = Symbol(
        file_id=file_a.id,
        name="used_func",
        kind="function",
        start_line=10,
        end_line=15,
        qualified_name="a.used_func",
    )
    proj.symbols.append(used_fn)

    proj.relationships.append(
        Relationship(
            source_id=file_b.id,
            target_id=used_fn.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"line": "5"},
        )
    )

    report = find_unused_candidates(proj, kind="function")
    candidate_names = [c.name for c in report.candidates]
    assert "used_func" not in candidate_names


def test_self_referencing_recursive_function(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    recurse_fn = Symbol(
        file_id=file_a.id,
        name="recurse_me",
        kind="function",
        start_line=20,
        end_line=25,
        qualified_name="a.recurse_me",
    )
    proj.symbols.append(recurse_fn)

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=recurse_fn.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"line": "22"},
        )
    )

    report = find_unused_candidates(proj, kind="function")
    candidate_names = [c.name for c in report.candidates]
    assert "recurse_me" in candidate_names
    item = next(c for c in report.candidates if c.name == "recurse_me")
    assert any("self-referential" in ev for ev in item.evidence)


def test_same_file_call_from_another_function_is_not_self_reference(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    target_fn = Symbol(
        file_id=file_a.id,
        name="target_func",
        kind="function",
        start_line=10,
        end_line=15,
        qualified_name="a.target_func",
    )
    caller_fn = Symbol(
        file_id=file_a.id,
        name="caller_func",
        kind="function",
        start_line=30,
        end_line=40,
        qualified_name="a.caller_func",
    )
    proj.symbols.extend([target_fn, caller_fn])

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=target_fn.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"line": "35"},
        )
    )

    report = find_unused_candidates(proj, kind="function")
    candidate_names = [c.name for c in report.candidates]
    assert "target_func" not in candidate_names
    assert "caller_func" in candidate_names


def test_missing_or_malformed_reference_line_metadata_treated_conservatively(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    fn = Symbol(
        file_id=file_a.id,
        name="some_func",
        kind="function",
        start_line=10,
        end_line=15,
        qualified_name="a.some_func",
    )
    proj.symbols.append(fn)

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=fn.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={},
        )
    )

    report = find_unused_candidates(proj, kind="function")
    candidate_names = [c.name for c in report.candidates]
    assert "some_func" not in candidate_names


def test_recursion_with_coexisting_external_call_in_same_file(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    target_fn = Symbol(
        file_id=file_a.id,
        name="recursive_but_called",
        kind="function",
        start_line=10,
        end_line=20,
        qualified_name="a.recursive_but_called",
    )
    proj.symbols.append(target_fn)

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=target_fn.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"line": "12"},
        )
    )
    proj.references.extend(
        [
            SymbolReference(file_id=file_a.id, name="recursive_but_called", line=12),
            SymbolReference(file_id=file_a.id, name="recursive_but_called", line=45),
        ]
    )

    report = find_unused_candidates(proj, kind="function")
    candidate_names = [c.name for c in report.candidates]
    assert "recursive_but_called" not in candidate_names


def test_inherited_class_is_not_candidate(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    base_class = Symbol(
        file_id=file_a.id,
        name="BaseService",
        kind="class",
        start_line=5,
        end_line=15,
        qualified_name="a.BaseService",
    )
    sub_class = Symbol(
        file_id=file_a.id,
        name="ChildService",
        kind="class",
        start_line=20,
        end_line=30,
        qualified_name="a.ChildService",
    )
    proj.symbols.extend([base_class, sub_class])

    proj.relationships.append(
        Relationship(
            source_id=sub_class.id,
            target_id=base_class.id,
            relationship_type=RelationshipType.INHERITS,
        )
    )

    report = find_unused_candidates(proj, kind="class")
    candidate_names = [c.name for c in report.candidates]
    assert "BaseService" not in candidate_names
    assert "ChildService" in candidate_names


def test_standard_dunder_methods_excluded_but_arbitrary_dunder_names_reported(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    init_method = Symbol(
        file_id=file_a.id,
        name="__init__",
        kind="method",
        start_line=5,
        end_line=8,
    )
    custom_dunder_method = Symbol(
        file_id=file_a.id,
        name="__custom_internal_op__",
        kind="method",
        start_line=10,
        end_line=14,
    )
    custom_dunder_fn = Symbol(
        file_id=file_a.id,
        name="__custom_helper__",
        kind="function",
        start_line=16,
        end_line=20,
    )
    proj.symbols.extend([init_method, custom_dunder_method, custom_dunder_fn])

    report = find_unused_candidates(proj)
    candidate_names = [c.name for c in report.candidates]
    assert "__init__" not in candidate_names
    assert "__custom_internal_op__" in candidate_names
    assert "__custom_helper__" in candidate_names


def test_main_function_entry_point_distinction(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    main_file = File(
        project_id=proj.id, path=Path("src/main.py"), name="main.py", extension=".py"
    )
    util_file = File(
        project_id=proj.id,
        path=Path("src/utils/calc.py"),
        name="calc.py",
        extension=".py",
    )
    proj.add_file(main_file)
    proj.add_file(util_file)

    entry_main = Symbol(
        file_id=main_file.id,
        name="main",
        kind="function",
        start_line=10,
        end_line=20,
    )
    arbitrary_main = Symbol(
        file_id=util_file.id,
        name="main",
        kind="function",
        start_line=5,
        end_line=15,
    )
    proj.symbols.extend([entry_main, arbitrary_main])

    report = find_unused_candidates(proj, kind="function")
    assert not any(
        c.name == "main" and c.path == "src/main.py" for c in report.candidates
    )
    assert any(
        c.name == "main" and c.path == "src/utils/calc.py" for c in report.candidates
    )


def test_test_file_discovery_conventions(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    test_file = File(
        project_id=proj.id,
        path=Path("tests/test_something.py"),
        name="test_something.py",
        extension=".py",
    )
    proj.add_file(test_file)

    test_fn = Symbol(
        file_id=test_file.id,
        name="test_feature_works",
        kind="function",
        start_line=10,
        end_line=15,
    )
    test_cls = Symbol(
        file_id=test_file.id,
        name="TestFeatureSuite",
        kind="class",
        start_line=18,
        end_line=28,
    )
    helper_fn = Symbol(
        file_id=test_file.id,
        name="fixture_app_state",
        kind="function",
        start_line=2,
        end_line=8,
    )
    proj.symbols.extend([test_fn, test_cls, helper_fn])

    report = find_unused_candidates(proj)
    candidate_names = [c.name for c in report.candidates]
    assert "test_something.py" not in candidate_names
    assert "test_feature_works" not in candidate_names
    assert "TestFeatureSuite" not in candidate_names
    assert "fixture_app_state" in candidate_names


def test_unused_file_candidate(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    orphan_file = File(
        project_id=proj.id,
        path=Path("src/orphaned.py"),
        name="orphaned.py",
        extension=".py",
    )
    proj.add_file(orphan_file)

    report = find_unused_candidates(proj, kind="file")
    candidate_names = [c.name for c in report.candidates]
    assert "orphaned.py" in candidate_names

    item = next(c for c in report.candidates if c.name == "orphaned.py")
    assert item.kind == "file"
    assert item.classification == UnusedClassification.APPARENT_UNUSED_CANDIDATE.value


def test_used_file_is_not_candidate(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/b.py"), name="b.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=file_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    report = find_unused_candidates(proj, kind="file")
    candidate_names = [c.name for c in report.candidates]
    assert "b.py" not in candidate_names


def test_analysis_error_attribution_with_shared_basename(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id,
        path=Path("src/a/config.py"),
        name="config.py",
        extension=".py",
    )
    file_b = File(
        project_id=proj.id,
        path=Path("tests/b/config.py"),
        name="config.py",
        extension=".py",
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    sym_a = Symbol(
        file_id=file_a.id,
        name="fn_in_a",
        kind="function",
        start_line=1,
        end_line=5,
    )
    sym_b = Symbol(
        file_id=file_b.id,
        name="fn_in_b",
        kind="function",
        start_line=1,
        end_line=5,
    )
    proj.symbols.extend([sym_a, sym_b])

    proj.errors.append("SyntaxError in src/a/config.py: unexpected EOF")

    report = find_unused_candidates(proj)
    unassessable_paths = [u.path for u in report.unassessable]

    assert "src/a/config.py" in unassessable_paths
    assert "tests/b/config.py" not in unassessable_paths

    candidate_names = [c.name for c in report.candidates]
    assert "fn_in_b" in candidate_names
    assert "fn_in_a" not in candidate_names


def test_deterministic_sorting_and_truncation(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/z.py"), name="z.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    sym_z = Symbol(
        file_id=file_a.id, name="z_func", kind="function", start_line=10, end_line=15
    )
    sym_a2 = Symbol(
        file_id=file_b.id, name="a2_func", kind="function", start_line=20, end_line=25
    )
    sym_a1 = Symbol(
        file_id=file_b.id, name="a1_func", kind="function", start_line=5, end_line=10
    )
    proj.symbols.extend([sym_z, sym_a2, sym_a1])

    report = find_unused_candidates(proj, kind="function", limit=2)
    assert report.truncated is True
    assert len(report.candidates) == 2
    assert report.summary.candidates_count == 3
    assert report.candidates[0].name == "a1_func"
    assert report.candidates[1].name == "a2_func"


def test_serialization_to_dict(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)
    sym = Symbol(
        file_id=file_a.id, name="my_fn", kind="function", start_line=1, end_line=3
    )
    proj.symbols.append(sym)

    report = find_unused_candidates(proj)
    d = report.to_dict()

    assert "repository_path" in d
    assert "analysis_status" in d
    assert "summary" in d
    assert "candidates" in d
    assert "unassessable" in d
    assert "limitations" in d
    assert "outcome" in d
    assert d["summary"]["total_entities_analyzed"] >= 1
    assert d["summary"]["candidates_count"] >= 1
    assert len(d["limitations"]) > 0


def test_project_query_method_integration(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)
    sym = Symbol(
        file_id=file_a.id, name="query_fn", kind="function", start_line=1, end_line=5
    )
    proj.symbols.append(sym)

    query = ProjectQuery(proj)
    report = query.find_unused_candidates(kind="function")
    assert report.summary.candidates_count == 1
    assert report.candidates[0].name == "query_fn"


def test_multiple_references_and_relationship_types(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/b.py"), name="b.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    service_cls = Symbol(
        file_id=file_a.id,
        name="UserService",
        kind="class",
        start_line=1,
        end_line=20,
    )
    unused_cls = Symbol(
        file_id=file_a.id,
        name="UnusedService",
        kind="class",
        start_line=22,
        end_line=30,
    )
    proj.symbols.extend([service_cls, unused_cls])

    proj.relationships.append(
        Relationship(
            source_id=file_b.id,
            target_id=service_cls.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )
    proj.relationships.append(
        Relationship(
            source_id=file_b.id,
            target_id=service_cls.id,
            relationship_type=RelationshipType.CALLS,
        )
    )

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=unused_cls.id,
            relationship_type=RelationshipType.CONTAINS,
        )
    )

    report = find_unused_candidates(proj, kind="class")
    candidate_names = [c.name for c in report.candidates]
    assert "UserService" not in candidate_names
    assert "UnusedService" in candidate_names


def test_unresolved_imports_do_not_fabricate_dependencies(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/b.py"), name="b.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    sym = Symbol(
        file_id=file_a.id,
        name="calculate_tax",
        kind="function",
        start_line=10,
        end_line=15,
    )
    unresolved_import = Symbol(
        file_id=file_b.id,
        name="tax_lib",
        kind="import",
        start_line=1,
        end_line=1,
    )
    proj.symbols.extend([sym, unresolved_import])

    report = find_unused_candidates(proj, kind="function")
    candidate_names = [c.name for c in report.candidates]
    assert "calculate_tax" in candidate_names


def test_analysis_error_attribution_overlapping_path_fragments(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_short = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_long = File(
        project_id=proj.id,
        path=Path("sub/src/a.py"),
        name="a.py",
        extension=".py",
    )
    file_bak = File(
        project_id=proj.id, path=Path("src/a.py.bak"), name="a.py.bak", extension=".bak"
    )
    proj.add_file(file_short)
    proj.add_file(file_long)
    proj.add_file(file_bak)

    sym_short = Symbol(
        file_id=file_short.id,
        name="short_fn",
        kind="function",
        start_line=1,
        end_line=5,
    )
    sym_long = Symbol(
        file_id=file_long.id,
        name="long_fn",
        kind="function",
        start_line=1,
        end_line=5,
    )
    proj.symbols.extend([sym_short, sym_long])

    proj.errors.append("SyntaxError in sub/src/a.py: unexpected EOF")

    report = find_unused_candidates(proj)
    unassessable_paths = [u.path for u in report.unassessable]

    assert "sub/src/a.py" in unassessable_paths
    assert "src/a.py" not in unassessable_paths
    assert "src/a.py.bak" not in unassessable_paths

    candidate_names = [c.name for c in report.candidates]
    assert "short_fn" in candidate_names
    assert "long_fn" not in candidate_names


def test_analysis_error_attribution_shared_basename_ambiguity(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id,
        path=Path("src/a/config.py"),
        name="config.py",
        extension=".py",
    )
    file_b = File(
        project_id=proj.id,
        path=Path("tests/b/config.py"),
        name="config.py",
        extension=".py",
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    sym_a = Symbol(
        file_id=file_a.id, name="fn_a", kind="function", start_line=1, end_line=5
    )
    sym_b = Symbol(
        file_id=file_b.id, name="fn_b", kind="function", start_line=1, end_line=5
    )
    proj.symbols.extend([sym_a, sym_b])

    proj.errors.append("SyntaxError in config.py: invalid syntax")

    report = find_unused_candidates(proj)
    unassessable_err_paths = [
        u.path for u in report.unassessable if "encountered analysis error" in u.reason
    ]

    assert "src/a/config.py" not in unassessable_err_paths
    assert "tests/b/config.py" not in unassessable_err_paths

    assert report.outcome.status == OperationStatus.PARTIAL
    assert any(
        "could not be unambiguously attributed" in d.message for d in report.diagnostics
    )


def test_analysis_error_attribution_absolute_path(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id,
        path=Path("src/service.py"),
        name="service.py",
        extension=".py",
    )
    proj.add_file(file_a)
    sym = Symbol(
        file_id=file_a.id, name="serv_fn", kind="function", start_line=1, end_line=5
    )
    proj.symbols.append(sym)

    abs_path = (proj.root_path / "src/service.py").resolve().as_posix()
    proj.errors.append(f"{abs_path}:10:5: SyntaxError: unexpected indent")

    report = find_unused_candidates(proj)
    unassessable_paths = [u.path for u in report.unassessable]
    assert "src/service.py" in unassessable_paths


def test_analysis_error_attribution_unidentifiable_path(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id,
        path=Path("src/a.py"),
        name="a.py",
        extension=".py",
    )
    proj.add_file(file_a)
    sym = Symbol(
        file_id=file_a.id, name="fn_a", kind="function", start_line=1, end_line=5
    )
    proj.symbols.append(sym)

    proj.errors.append("General database timeout during indexing")

    report = find_unused_candidates(proj)
    unassessable_err_paths = [
        u.path for u in report.unassessable if "encountered analysis error" in u.reason
    ]
    assert "src/a.py" not in unassessable_err_paths
    assert report.outcome.status == OperationStatus.PARTIAL


def test_same_file_same_named_functions_reference_ambiguity(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    fn1 = Symbol(
        file_id=file_a.id,
        name="compute",
        kind="function",
        start_line=10,
        end_line=20,
        qualified_name="a.compute_v1",
    )
    fn2 = Symbol(
        file_id=file_a.id,
        name="compute",
        kind="function",
        start_line=30,
        end_line=40,
        qualified_name="a.compute_v2",
    )
    proj.symbols.extend([fn1, fn2])

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=fn1.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"line": "12"},
        )
    )
    proj.references.append(SymbolReference(file_id=file_a.id, name="compute", line=50))

    report = find_unused_candidates(proj, kind="function")
    unassessable_names = [u.name for u in report.unassessable]
    assert "compute" in unassessable_names
    item = next(u for u in report.unassessable if u.entity_id == str(fn1.id))
    assert "Multiple same-named symbols" in item.reason


def test_same_file_same_named_functions_with_qualified_name_disambiguation(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    method1 = Symbol(
        file_id=file_a.id,
        name="helper",
        kind="method",
        start_line=10,
        end_line=20,
        qualified_name="ClassA.helper",
    )
    method2 = Symbol(
        file_id=file_a.id,
        name="helper",
        kind="method",
        start_line=30,
        end_line=40,
        qualified_name="ClassB.helper",
    )
    proj.symbols.extend([method1, method2])

    proj.references.append(
        SymbolReference(
            file_id=file_a.id,
            name="helper",
            line=60,
            qualified_name="ClassB.helper",
        )
    )

    report = find_unused_candidates(proj, kind="method")
    assert any(c.qualified_name == "ClassA.helper" for c in report.candidates)
    assert not any(c.qualified_name == "ClassB.helper" for c in report.candidates)


def test_graph_builder_realistic_relationship_types_and_ids(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/b.py"), name="b.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    func_target = Symbol(
        file_id=file_a.id,
        name="target_op",
        kind="function",
        start_line=10,
        end_line=20,
    )
    proj.symbols.append(func_target)

    proj.relationships.append(
        Relationship(
            source_id=file_b.id,
            target_id=func_target.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"source": "ast", "name": "target_op", "line": "15"},
        )
    )

    report = find_unused_candidates(proj, kind="function")
    candidate_names = [c.name for c in report.candidates]
    assert "target_op" not in candidate_names


def test_file_level_internal_references_only_remains_unused(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id,
        path=Path("src/isolated.py"),
        name="isolated.py",
        extension=".py",
    )
    proj.add_file(file_a)

    fn1 = Symbol(
        file_id=file_a.id, name="f1", kind="function", start_line=1, end_line=5
    )
    fn2 = Symbol(
        file_id=file_a.id, name="f2", kind="function", start_line=10, end_line=15
    )
    proj.symbols.extend([fn1, fn2])

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=fn2.id,
            relationship_type=RelationshipType.REFERENCES,
            metadata={"line": "3"},
        )
    )

    report = find_unused_candidates(proj, kind="file")
    candidate_names = [c.name for c in report.candidates]
    assert "isolated.py" in candidate_names


def test_file_level_structural_relationships_do_not_count_as_usage(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/mod.py"), name="mod.py", extension=".py"
    )
    proj.add_file(file_a)

    fn = Symbol(
        file_id=file_a.id, name="my_fn", kind="function", start_line=1, end_line=5
    )
    proj.symbols.append(fn)

    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=fn.id,
            relationship_type=RelationshipType.DEFINES,
        )
    )
    proj.relationships.append(
        Relationship(
            source_id=file_a.id,
            target_id=fn.id,
            relationship_type=RelationshipType.CONTAINS,
        )
    )

    report = find_unused_candidates(proj, kind="file")
    candidate_names = [c.name for c in report.candidates]
    assert "mod.py" in candidate_names


def test_limit_validation_rejects_non_positive_and_invalid(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    import pytest

    for invalid_limit in [0, -1, -50, True, False, "50"]:
        with pytest.raises(ValueError, match="Report limit must be a positive integer"):
            find_unused_candidates(proj, limit=invalid_limit)


def test_limit_none_returns_unlimited(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)

    for i in range(10):
        proj.symbols.append(
            Symbol(
                file_id=file_a.id,
                name=f"fn_{i}",
                kind="function",
                start_line=i * 5 + 1,
                end_line=i * 5 + 4,
            )
        )

    report = find_unused_candidates(proj, kind="function", limit=None)
    assert report.truncated is False
    assert report.limit is None
    assert len(report.candidates) == 10
    assert report.summary.candidates_count == 10


def test_outcome_status_for_different_project_states(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.symbols.append(
        Symbol(file_id=file_a.id, name="fn", kind="function", start_line=1, end_line=5)
    )

    report_clean = find_unused_candidates(proj)
    assert report_clean.outcome.status == OperationStatus.SUCCESS

    proj.analysis_status = "not_analyzed"
    report_not_analyzed = find_unused_candidates(proj)
    assert report_not_analyzed.outcome.status == OperationStatus.INCOMPLETE

    proj.analysis_status = "failed"
    report_failed = find_unused_candidates(proj)
    assert report_failed.outcome.status == OperationStatus.PARTIAL


def test_normalize_kind_filter_validation(tmp_path: Path) -> None:
    for invalid in ["invalid_kind", "foo", "module", "packages", "attr"]:
        with pytest.raises(ValueError, match="Unsupported kind filter"):
            _normalize_kind_filter(invalid)

    proj = _create_test_project(tmp_path)
    with pytest.raises(ValueError, match="Unsupported kind filter"):
        find_unused_candidates(proj, kind="bogus_kind")

    assert _normalize_kind_filter("  function  ") == {"function"}
    assert _normalize_kind_filter("FUNCTION") == {"function"}
    assert _normalize_kind_filter("\tMETHOD\n") == {"method"}

    assert _normalize_kind_filter("function") == {"function"}
    assert _normalize_kind_filter("functions") == {"function"}
    assert _normalize_kind_filter("method") == {"method"}
    assert _normalize_kind_filter("methods") == {"method"}
    assert _normalize_kind_filter("class") == {"class"}
    assert _normalize_kind_filter("classes") == {"class"}
    assert _normalize_kind_filter("variable") == {"variable"}
    assert _normalize_kind_filter("variables") == {"variable"}
    assert _normalize_kind_filter("file") == {"file"}
    assert _normalize_kind_filter("files") == {"file"}
    assert _normalize_kind_filter("symbol") == {"symbol"}
    assert _normalize_kind_filter("symbols") == {"symbol"}

    assert _normalize_kind_filter("all") == {"all"}
    assert _normalize_kind_filter("*") == {"all"}
    assert _normalize_kind_filter("") == {"all"}
    assert _normalize_kind_filter("   ") == {"all"}
    assert _normalize_kind_filter(None) == {"all"}


def test_analysis_error_attribution_multiple_files_identifiable_location(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/b.py"), name="b.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    sym_a = Symbol(
        file_id=file_a.id, name="fn_a", kind="function", start_line=1, end_line=5
    )
    sym_b = Symbol(
        file_id=file_b.id, name="fn_b", kind="function", start_line=1, end_line=5
    )
    proj.symbols.extend([sym_a, sym_b])

    proj.errors.append("src/a.py:10: cannot import name 'helper' from src/b.py")

    report = find_unused_candidates(proj, kind="function")
    unassessable_paths = [u.path for u in report.unassessable]
    candidate_names = [c.name for c in report.candidates]

    assert "src/a.py" in unassessable_paths
    assert "src/b.py" not in unassessable_paths
    assert "fn_b" in candidate_names
    assert "fn_a" not in candidate_names


def test_analysis_error_attribution_multiple_files_ambiguous_location(
    tmp_path: Path,
) -> None:
    proj = _create_test_project(tmp_path)
    file_a = File(
        project_id=proj.id, path=Path("src/a.py"), name="a.py", extension=".py"
    )
    file_b = File(
        project_id=proj.id, path=Path("src/b.py"), name="b.py", extension=".py"
    )
    proj.add_file(file_a)
    proj.add_file(file_b)

    sym_a = Symbol(
        file_id=file_a.id, name="fn_a", kind="function", start_line=1, end_line=5
    )
    sym_b = Symbol(
        file_id=file_b.id, name="fn_b", kind="function", start_line=1, end_line=5
    )
    proj.symbols.extend([sym_a, sym_b])

    proj.errors.append("Circular import conflict between src/a.py and src/b.py")

    report = find_unused_candidates(proj, kind="function")
    unassessable_paths = [u.path for u in report.unassessable]
    candidate_names = [c.name for c in report.candidates]

    assert "src/a.py" not in unassessable_paths
    assert "src/b.py" not in unassessable_paths
    assert report.outcome.status == OperationStatus.PARTIAL
    assert any(
        "could not be unambiguously attributed" in d.message for d in report.diagnostics
    )
    assert "fn_a" in candidate_names
    assert "fn_b" in candidate_names


def test_analysis_error_attribution_path_variants(tmp_path: Path) -> None:
    proj1 = _create_test_project(tmp_path / "p1")
    f1 = File(project_id=proj1.id, path=Path("src/a.py"), name="a.py", extension=".py")
    proj1.add_file(f1)
    proj1.symbols.append(
        Symbol(file_id=f1.id, name="fn", kind="function", start_line=1, end_line=5)
    )
    proj1.errors.append("./src/a.py:12: SyntaxError: unexpected EOF")

    r1 = find_unused_candidates(proj1)
    assert any(u.path == "src/a.py" for u in r1.unassessable)

    proj2 = _create_test_project(tmp_path / "p2")
    f2 = File(project_id=proj2.id, path=Path("src/a.py"), name="a.py", extension=".py")
    proj2.add_file(f2)
    proj2.symbols.append(
        Symbol(file_id=f2.id, name="fn", kind="function", start_line=1, end_line=5)
    )
    proj2.errors.append("src\\a.py:15: SyntaxError: invalid syntax")

    r2 = find_unused_candidates(proj2)
    assert any(u.path == "src/a.py" for u in r2.unassessable)

    proj3 = _create_test_project(tmp_path / "p3")
    f3 = File(project_id=proj3.id, path=Path("src/a.py"), name="a.py", extension=".py")
    proj3.add_file(f3)
    proj3.symbols.append(
        Symbol(file_id=f3.id, name="fn", kind="function", start_line=1, end_line=5)
    )
    proj3.errors.append(".\\src\\a.py:20: SyntaxError: invalid syntax")

    r3 = find_unused_candidates(proj3)
    assert any(u.path == "src/a.py" for u in r3.unassessable)

    proj4 = _create_test_project(tmp_path / "p4")
    f4 = File(project_id=proj4.id, path=Path("src/a.py"), name="a.py", extension=".py")
    proj4.add_file(f4)
    proj4.symbols.append(
        Symbol(file_id=f4.id, name="fn", kind="function", start_line=1, end_line=5)
    )
    abs_str = (proj4.root_path / "src/a.py").as_posix()
    proj4.errors.append(f"{abs_str}:25: SyntaxError: bad token")

    r4 = find_unused_candidates(proj4)
    assert any(u.path == "src/a.py" for u in r4.unassessable)


def test_report_limit_contract_sections(tmp_path: Path) -> None:
    proj = _create_test_project(tmp_path)
    file_good = File(
        project_id=proj.id, path=Path("src/good.py"), name="good.py", extension=".py"
    )
    file_bad = File(
        project_id=proj.id, path=Path("src/bad.py"), name="bad.py", extension=".py"
    )
    proj.add_file(file_good)
    proj.add_file(file_bad)

    for i in range(5):
        proj.symbols.append(
            Symbol(
                file_id=file_good.id,
                name=f"cand_{i}",
                kind="function",
                start_line=i * 5 + 1,
                end_line=i * 5 + 4,
            )
        )
    for i in range(5):
        proj.symbols.append(
            Symbol(
                file_id=file_bad.id,
                name=f"unassess_{i}",
                kind="function",
                start_line=i * 5 + 1,
                end_line=i * 5 + 4,
            )
        )
    proj.errors.append("src/bad.py:1: syntax error")

    rep_both = find_unused_candidates(proj, kind="function", limit=3)
    assert rep_both.truncated is True
    assert rep_both.limit == 3
    assert len(rep_both.candidates) == 3
    assert len(rep_both.unassessable) == 3
    assert rep_both.summary.candidates_count == 5
    assert rep_both.summary.unassessable_count == 5

    proj.symbols = [
        s for s in proj.symbols if s.name not in ("unassess_3", "unassess_4")
    ]
    rep_cand_only = find_unused_candidates(proj, kind="function", limit=4)
    assert rep_cand_only.truncated is True
    assert rep_cand_only.limit == 4
    assert len(rep_cand_only.candidates) == 4
    assert len(rep_cand_only.unassessable) == 3
    assert rep_cand_only.summary.candidates_count == 5
    assert rep_cand_only.summary.unassessable_count == 3

    proj.symbols = [
        s for s in proj.symbols if s.name not in ("cand_2", "cand_3", "cand_4")
    ]
    proj.symbols.extend(
        [
            Symbol(
                file_id=file_bad.id,
                name="unassess_3",
                kind="function",
                start_line=16,
                end_line=19,
            ),
            Symbol(
                file_id=file_bad.id,
                name="unassess_4",
                kind="function",
                start_line=21,
                end_line=24,
            ),
        ]
    )
    rep_unassess_only = find_unused_candidates(proj, kind="function", limit=4)
    assert rep_unassess_only.truncated is True
    assert rep_unassess_only.limit == 4
    assert len(rep_unassess_only.candidates) == 2
    assert len(rep_unassess_only.unassessable) == 4
    assert rep_unassess_only.summary.candidates_count == 2
    assert rep_unassess_only.summary.unassessable_count == 5

    rep_neither = find_unused_candidates(proj, kind="function", limit=10)
    assert rep_neither.truncated is False
    assert rep_neither.limit == 10
    assert len(rep_neither.candidates) == 2
    assert len(rep_neither.unassessable) == 5
    assert rep_neither.summary.candidates_count == 2
    assert rep_neither.summary.unassessable_count == 5

    rep_unlimited = find_unused_candidates(proj, kind="function", limit=None)
    assert rep_unlimited.truncated is False
    assert rep_unlimited.limit is None
    assert len(rep_unlimited.candidates) == 2
    assert len(rep_unlimited.unassessable) == 5
    assert rep_unlimited.summary.candidates_count == 2
    assert rep_unlimited.summary.unassessable_count == 5
