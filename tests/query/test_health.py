from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.parser.result import ImportReference
from context_forge.query.health import DEFAULT_HEALTH_LIMIT, build_health_report
from context_forge.query.project import ProjectQuery
from context_forge.storage.cache import (
    CacheFreshness,
    FileChangeSet,
    RepositoryCacheMetadata,
)


def _create_sample_project(tmp_path: Path) -> Project:
    project = Project(
        name="Health Test Project",
        root_path=tmp_path.resolve(),
        analysis_status="analyzed",
        project_type="python_project",
    )
    src_dir = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
    )
    pkg_dir = Directory(
        project_id=project.id,
        path=Path("src/pkg"),
        name="pkg",
        parent_id=src_dir.id,
    )
    project.add_directory(src_dir)
    project.add_directory(pkg_dir)

    init_file = File(
        project_id=project.id,
        path=Path("src/pkg/__init__.py"),
        name="__init__.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )
    mod_a = File(
        project_id=project.id,
        path=Path("src/pkg/a.py"),
        name="a.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )
    mod_b = File(
        project_id=project.id,
        path=Path("src/pkg/b.py"),
        name="b.py",
        extension=".py",
        directory_id=pkg_dir.id,
    )
    project.add_file(init_file)
    project.add_file(mod_a)
    project.add_file(mod_b)

    sym_a = Symbol(
        file_id=mod_a.id,
        name="func_a",
        kind="function",
        start_line=1,
        end_line=5,
    )
    sym_b = Symbol(
        file_id=mod_b.id,
        name="func_b",
        kind="function",
        start_line=1,
        end_line=5,
    )
    project.add_symbol(sym_a)
    project.add_symbol(sym_b)

    project.add_relationship(
        Relationship(
            source_id=mod_a.id,
            target_id=sym_a.id,
            relationship_type=RelationshipType.DEFINES,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=mod_b.id,
            target_id=sym_b.id,
            relationship_type=RelationshipType.DEFINES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=mod_a.id,
            target_id=mod_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    return project


def test_build_health_report_populated_project(tmp_path: Path) -> None:
    project = _create_sample_project(tmp_path)
    metadata = RepositoryCacheMetadata(
        repository_key=str(tmp_path.resolve()),
        project_id=project.id,
        cache_schema_version=2,
        analyzer_version="0.1.0",
    )
    freshness = CacheFreshness(is_fresh=True, reason="fresh")

    report = build_health_report(
        project=project,
        repository_path=tmp_path,
        metadata=metadata,
        freshness=freshness,
    )

    assert report["schema_version"] == 1
    assert report["repository"] == tmp_path.resolve().as_posix()
    assert report["project"] == {
        "name": "Health Test Project",
        "project_type": "python_project",
    }
    assert report["analysis"]["status"] == "analyzed"
    assert report["analysis"]["error_count"] == 0
    assert report["analysis"]["errors"] == []

    assert report["cache"]["status"] == "fresh"
    assert report["cache"]["reason"] == "fresh"
    assert "cache_schema_version" not in report["cache"]
    assert "analyzer_version" not in report["cache"]

    inv = report["inventory"]
    assert inv["directories"] == 2
    assert inv["files"] == 3
    assert inv["python_modules"] == 3
    assert inv["packages"] == 1
    assert inv["symbols"] == 2
    assert inv["relationships"] == 3
    assert inv["containment_edges"] == 6
    assert inv["dependencies"] == 1

    findings = report["findings"]
    assert findings["summary"]["unresolved_imports"] == 0
    assert findings["summary"]["dependency_cycles"] == 0
    assert findings["summary"]["structural_integrity"] == 0
    assert findings["summary"]["total_findings"] == 0

    assert len(report["limitations"]) >= 4


def test_build_health_report_empty_project(tmp_path: Path) -> None:
    project = Project(
        name="Empty Project",
        root_path=tmp_path.resolve(),
        analysis_status="analyzed",
    )
    metadata = RepositoryCacheMetadata(
        repository_key=str(tmp_path.resolve()),
        project_id=project.id,
    )
    freshness = CacheFreshness(is_fresh=True, reason="fresh")

    report = build_health_report(
        project=project,
        repository_path=tmp_path,
        metadata=metadata,
        freshness=freshness,
    )

    inv = report["inventory"]
    assert inv["directories"] == 0
    assert inv["files"] == 0
    assert inv["python_modules"] == 0
    assert inv["packages"] == 0
    assert inv["symbols"] == 0
    assert inv["relationships"] == 0
    assert inv["containment_edges"] == 0
    assert inv["dependencies"] == 0

    assert report["findings"]["summary"]["total_findings"] == 0


def test_build_health_report_unavailable_project(tmp_path: Path) -> None:
    report = build_health_report(
        project=None,
        repository_path=tmp_path,
    )

    assert report["project"] is None
    assert report["analysis"]["status"] == "not_analyzed"
    assert report["cache"]["status"] == "unavailable"
    assert report["cache"]["reason"] == "missing_analysis"

    inv = report["inventory"]
    for key, val in inv.items():
        assert val is None, f"Expected {key} to be None (unavailable), got {val}"

    summary = report["findings"]["summary"]
    for key, val in summary.items():
        assert val is None, f"Expected {key} to be None (unavailable), got {val}"

    assert any("No persisted analysis found" in lim for lim in report["limitations"])


def test_build_health_report_stale_cache(tmp_path: Path) -> None:
    project = _create_sample_project(tmp_path)
    metadata = RepositoryCacheMetadata(
        repository_key=str(tmp_path.resolve()),
        project_id=project.id,
    )
    changes = FileChangeSet(
        unchanged=frozenset(),
        modified=frozenset([Path("src/pkg/a.py")]),
        added=frozenset(),
        deleted=frozenset(),
    )
    freshness = CacheFreshness(
        is_fresh=False,
        reason="files_changed",
        changes=changes,
    )

    report = build_health_report(
        project=project,
        repository_path=tmp_path,
        metadata=metadata,
        freshness=freshness,
    )

    assert report["cache"]["status"] == "stale"
    assert report["cache"]["reason"] == "files_changed"
    assert any("Cached analysis is stale" in lim for lim in report["limitations"])
    assert any("files_changed" in lim for lim in report["limitations"])


def test_build_health_report_incomplete_and_failed_analysis(tmp_path: Path) -> None:
    project = _create_sample_project(tmp_path)
    project.analysis_status = "failed"
    project.errors = ["SyntaxError in src/pkg/a.py line 4"]

    report = build_health_report(
        project=project,
        repository_path=tmp_path,
    )

    assert report["analysis"]["status"] == "failed"
    assert report["analysis"]["error_count"] == 1
    assert report["analysis"]["errors"] == ["SyntaxError in src/pkg/a.py line 4"]

    assert any("Analysis status is 'failed'" in lim for lim in report["limitations"])
    assert any("contains errors" in lim for lim in report["limitations"])


def test_build_health_report_dependency_cycles(tmp_path: Path) -> None:
    project = Project(
        name="Cycle Project",
        root_path=tmp_path.resolve(),
        analysis_status="analyzed",
    )
    f_a = File(project_id=project.id, path=Path("a.py"), name="a.py", extension=".py")
    f_b = File(project_id=project.id, path=Path("b.py"), name="b.py", extension=".py")
    project.add_file(f_a)
    project.add_file(f_b)

    project.add_relationship(
        Relationship(
            source_id=f_a.id,
            target_id=f_b.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )
    project.add_relationship(
        Relationship(
            source_id=f_b.id,
            target_id=f_a.id,
            relationship_type=RelationshipType.IMPORTS,
        )
    )

    report = build_health_report(project=project, repository_path=tmp_path)

    assert report["findings"]["summary"]["dependency_cycles"] == 1
    cycles = report["findings"]["dependency_cycles"]["items"]
    assert len(cycles) == 1
    assert cycles[0]["module_count"] == 2
    assert cycles[0]["modules"] == ["a.py", "b.py"]
    assert cycles[0]["dependency_count"] == 2


def test_build_health_report_unresolved_imports(tmp_path: Path) -> None:
    project = Project(
        name="Unresolved Import Project",
        root_path=tmp_path.resolve(),
        analysis_status="analyzed",
    )
    f_a = File(project_id=project.id, path=Path("a.py"), name="a.py", extension=".py")
    project.add_file(f_a)

    project.add_import(
        ImportReference(
            file_id=f_a.id,
            module_name="external_pkg",
            imported_name="some_func",
            alias=None,
            level=0,
        )
    )

    report = build_health_report(project=project, repository_path=tmp_path)

    assert report["findings"]["summary"]["unresolved_imports"] == 1
    unresolved = report["findings"]["unresolved_imports"]["items"]
    assert len(unresolved) == 1
    assert unresolved[0]["module_name"] == "external_pkg"
    assert unresolved[0]["imported_name"] == "some_func"
    assert unresolved[0]["source_path"] == "a.py"


def test_build_health_report_structural_integrity(tmp_path: Path) -> None:
    project = Project(
        name="Integrity Project",
        root_path=tmp_path.resolve(),
        analysis_status="analyzed",
    )
    f_a = File(project_id=project.id, path=Path("a.py"), name="a.py", extension=".py")
    project.add_file(f_a)

    missing_id = uuid4()
    sym = Symbol(
        file_id=f_a.id,
        name="child_sym",
        kind="function",
        parent_symbol_id=missing_id,
        start_line=1,
        end_line=5,
    )
    project.add_symbol(sym)

    report = build_health_report(project=project, repository_path=tmp_path)

    assert report["findings"]["summary"]["structural_integrity"] >= 1
    findings = report["findings"]["structural_integrity"]["items"]
    assert any(
        f["type"] == "missing_parent_symbol" or "parent" in f["message"]
        for f in findings
    )


def test_build_health_report_bounded_limit(tmp_path: Path) -> None:
    project = Project(
        name="Limit Project",
        root_path=tmp_path.resolve(),
        analysis_status="analyzed",
    )
    f_a = File(project_id=project.id, path=Path("a.py"), name="a.py", extension=".py")
    project.add_file(f_a)

    project.add_import(ImportReference(file_id=f_a.id, module_name="ext1"))
    project.add_import(ImportReference(file_id=f_a.id, module_name="ext2"))

    report = build_health_report(
        project=project,
        repository_path=tmp_path,
        limit=1,
    )

    unresolved = report["findings"]["unresolved_imports"]
    assert DEFAULT_HEALTH_LIMIT == 50
    assert unresolved["total"] == 2
    assert len(unresolved["items"]) == 1
    assert unresolved["truncated"] is True
    assert any("limited to 1 items" in lim for lim in report["limitations"])

    with pytest.raises(ValueError, match="positive integer"):
        build_health_report(project=project, limit=0)
    with pytest.raises(ValueError, match="positive integer"):
        build_health_report(project=project, limit=-1)
    with pytest.raises(ValueError, match="positive integer"):
        build_health_report(project=project, limit=True)  # type: ignore[arg-type]


def test_build_health_report_determinism(tmp_path: Path) -> None:
    project = _create_sample_project(tmp_path)

    rep1 = build_health_report(project=project, repository_path=tmp_path)

    project.files.reverse()
    project.symbols.reverse()
    project.relationships.reverse()

    rep2 = build_health_report(project=project, repository_path=tmp_path)

    assert rep1 == rep2


def test_project_query_get_health_report(tmp_path: Path) -> None:
    project = _create_sample_project(tmp_path)
    query = ProjectQuery(project)

    report = query.get_health_report()
    assert report["schema_version"] == 1
    assert report["project"]["name"] == "Health Test Project"
    assert report["inventory"]["files"] == 3


def test_health_report_outcome_contract_states(tmp_path: Path) -> None:

    unavail_rep = build_health_report(project=None, repository_path=tmp_path)
    assert "outcome" in unavail_rep
    assert unavail_rep["outcome"]["status"] == "incomplete"
    assert unavail_rep["outcome"]["is_success"] is False
    assert unavail_rep["outcome"]["summary"]["blockers"] == 1
    assert unavail_rep["outcome"]["diagnostics"][0]["code"] == "MISSING_ANALYSIS"

    project = _create_sample_project(tmp_path)
    freshness = CacheFreshness(is_fresh=True, reason="clean")
    fresh_rep = build_health_report(
        project=project,
        repository_path=tmp_path,
        freshness=freshness,
    )
    assert fresh_rep["outcome"]["status"] == "success"
    assert fresh_rep["outcome"]["is_success"] is True
    assert fresh_rep["outcome"]["summary"]["errors"] == 0
    assert fresh_rep["outcome"]["summary"]["blockers"] == 0

    stale_freshness = CacheFreshness(is_fresh=False, reason="files_changed")
    stale_rep = build_health_report(
        project=project,
        repository_path=tmp_path,
        freshness=stale_freshness,
    )
    assert stale_rep["outcome"]["status"] == "partial"
    assert stale_rep["outcome"]["is_success"] is False
    assert any(
        d["code"] == "STALE_CACHE" and d["severity"] == "warning"
        for d in stale_rep["outcome"]["diagnostics"]
    )

    failed_project = _create_sample_project(tmp_path)
    failed_project.analysis_status = "failed"
    failed_project.errors = ["Syntax error in bad.py"]
    failed_rep = build_health_report(
        project=failed_project,
        repository_path=tmp_path,
    )
    assert failed_rep["outcome"]["status"] == "failed"
    assert failed_rep["outcome"]["is_success"] is False
    assert any(
        d["code"] == "ANALYSIS_ERROR" and d["severity"] == "error"
        for d in failed_rep["outcome"]["diagnostics"]
    )
