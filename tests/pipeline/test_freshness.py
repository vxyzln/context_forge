from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.pipeline.freshness import (
    FreshnessState,
    WorkflowFreshnessGuard,
)
from context_forge.query.project import ProjectQuery
from context_forge.reporting.contract import (
    DiagnosticSeverity,
    OperationStatus,
)
from context_forge.reporting.errors import (
    IncompleteAnalysisError,
    IndeterminateFreshnessError,
    MissingAnalysisError,
    RefreshFailedError,
    StaleAnalysisError,
)
from context_forge.storage.cache import (
    ANALYZER_VERSION,
    CACHE_SCHEMA_VERSION,
    RepositoryCacheMetadata,
    RepositoryIdentity,
    fingerprint_file,
)
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def _create_sample_project(
    repo_dir: Path,
    *,
    files: list[str] | None = None,
    analysis_status: str = "analyzed",
    errors: list[str] | None = None,
) -> Project:
    proj_id = uuid4()
    file_list: list[File] = []
    if files:
        for f in files:
            p = repo_dir / f
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text(f"# content of {f}\n", encoding="utf-8")
            file_list.append(
                File(
                    project_id=proj_id,
                    id=uuid4(),
                    path=Path(f),
                    name=Path(f).name,
                    extension=Path(f).suffix.lstrip("."),
                    size=p.stat().st_size,
                )
            )

    return Project(
        id=proj_id,
        name=repo_dir.name,
        root_path=repo_dir,
        files=file_list,
        analysis_status=analysis_status,
        errors=errors or [],
    )


def _setup_analyzed_repo(
    repo_dir: Path,
    *,
    files: list[str] | None = None,
    analysis_status: str = "analyzed",
    errors: list[str] | None = None,
    cache_schema_version: int = CACHE_SCHEMA_VERSION,
    analyzer_version: str = ANALYZER_VERSION,
) -> tuple[Database, ProjectRepository, Project, RepositoryCacheMetadata]:
    db_path = repo_dir / ".context_forge.db"
    db = Database(db_path)
    db.initialize()
    repo = ProjectRepository(db)

    file_names = files or ["mod_a.py", "mod_b.py"]
    proj = _create_sample_project(
        repo_dir,
        files=file_names,
        analysis_status=analysis_status,
        errors=errors,
    )

    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(repo_dir).key,
        project_id=proj.id,
        cache_schema_version=cache_schema_version,
        analyzer_version=analyzer_version,
    )

    fingerprints = {f.path: fingerprint_file(repo_dir, f.path) for f in proj.files}

    with db.connect() as conn:
        repo._save_project(conn, proj)
        repo._save_cache_metadata(conn, metadata)
        repo._save_file_fingerprints(
            conn, metadata.repository_key, list(fingerprints.values())
        )

    return db, repo, proj, metadata


def test_freshness_state_enum_properties():
    assert FreshnessState.CURRENT.is_current is True
    assert FreshnessState.CURRENT.is_stale is False
    assert FreshnessState.CURRENT.is_incomplete is False
    assert FreshnessState.CURRENT.is_indeterminate is False

    assert FreshnessState.STALE.is_stale is True
    assert FreshnessState.STALE.is_current is False

    assert FreshnessState.INCOMPLETE.is_incomplete is True
    assert FreshnessState.INCOMPLETE.is_current is False

    assert FreshnessState.INDETERMINATE.is_indeterminate is True
    assert FreshnessState.INDETERMINATE.is_current is False


def test_workflow_freshness_to_dict_and_contract(tmp_path: Path):
    _setup_analyzed_repo(tmp_path)
    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.is_current is True
    assert freshness.state == FreshnessState.CURRENT
    assert freshness.outcome.status == OperationStatus.SUCCESS
    assert freshness.outcome.is_success is True

    as_dict = freshness.to_dict()
    assert as_dict["state"] == "current"
    assert as_dict["is_current"] is True
    assert as_dict["reason"] == "fresh"
    assert as_dict["analysis_status"] == "analyzed"
    assert as_dict["analysis_errors"] == []
    assert as_dict["refreshed"] is False
    assert as_dict["refresh_error"] is None
    assert as_dict["outcome"]["status"] == "success"


def test_assess_current_repository(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py", "util.py"])
    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.CURRENT
    assert freshness.reason == "fresh"
    assert freshness.changes is not None
    assert freshness.changes.is_unchanged is True
    assert freshness.analysis_errors == ()
    assert freshness.diagnostics == ()
    assert freshness.limitations == ()
    assert freshness.project is not None
    assert freshness.metadata is not None


def test_assess_stale_when_file_modified(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    target_file = tmp_path / "app.py"

    # Ensure content changes alone trigger staleness.
    target_file.write_text("# modified content\nprint('new')\n", encoding="utf-8")

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.STALE
    assert freshness.is_stale is True
    assert "modified" in freshness.reason
    assert freshness.changes is not None
    assert Path("app.py") in freshness.changes.modified
    assert freshness.outcome.status == OperationStatus.PARTIAL
    assert len(freshness.diagnostics) >= 1
    assert freshness.diagnostics[0].code == "STALE_ANALYSIS"
    assert freshness.diagnostics[0].severity == DiagnosticSeverity.WARNING


def test_assess_stale_when_file_added(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])

    new_file = tmp_path / "new_module.py"
    new_file.write_text("# brand new\n", encoding="utf-8")

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.STALE
    assert "added" in freshness.reason
    assert freshness.changes is not None
    assert Path("new_module.py") in freshness.changes.added
    assert freshness.outcome.status == OperationStatus.PARTIAL


def test_assess_stale_when_file_deleted(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py", "remove_me.py"])

    (tmp_path / "remove_me.py").unlink()

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.STALE
    assert "deleted" in freshness.reason
    assert freshness.changes is not None
    assert Path("remove_me.py") in freshness.changes.deleted
    assert freshness.outcome.status == OperationStatus.PARTIAL


def test_assess_stale_with_multiple_mixed_changes(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["mod1.py", "mod2.py", "delete.py"])

    (tmp_path / "mod1.py").write_text("# modified\n", encoding="utf-8")

    (tmp_path / "delete.py").unlink()

    (tmp_path / "added.py").write_text("# added\n", encoding="utf-8")

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.STALE
    assert freshness.changes is not None
    assert Path("mod1.py") in freshness.changes.modified
    assert Path("delete.py") in freshness.changes.deleted
    assert Path("added.py") in freshness.changes.added
    assert "1 modified" in freshness.reason
    assert "1 added" in freshness.reason
    assert "1 deleted" in freshness.reason


@pytest.mark.parametrize("status", ["failed", "partial", "analyzing", "not_analyzed"])
def test_assess_incomplete_due_to_analysis_status(tmp_path: Path, status: str):
    _setup_analyzed_repo(tmp_path, files=["app.py"], analysis_status=status)

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INCOMPLETE
    assert freshness.is_incomplete is True
    assert freshness.analysis_status == status
    assert freshness.outcome.status == OperationStatus.INCOMPLETE
    assert len(freshness.diagnostics) >= 1
    assert freshness.diagnostics[0].code == "INCOMPLETE_ANALYSIS"


def test_assess_incomplete_due_to_recorded_errors(tmp_path: Path):
    _setup_analyzed_repo(
        tmp_path,
        files=["app.py"],
        analysis_status="analyzed",
        errors=["SyntaxError: invalid syntax in bad.py at line 10"],
    )

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INCOMPLETE
    assert freshness.is_incomplete is True
    assert len(freshness.analysis_errors) == 1
    assert "SyntaxError" in freshness.analysis_errors[0]
    assert freshness.outcome.status == OperationStatus.INCOMPLETE
    assert any(d.code == "ANALYSIS_ERROR" for d in freshness.diagnostics)


def test_assess_indeterminate_missing_database(tmp_path: Path):
    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.is_indeterminate is True
    assert freshness.reason == "missing_analysis"
    assert freshness.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "MISSING_ANALYSIS" for d in freshness.diagnostics)


def test_assess_indeterminate_no_analysis_in_db(tmp_path: Path):
    db_path = tmp_path / ".context_forge.db"
    db = Database(db_path)
    db.initialize()

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_analysis"
    assert freshness.outcome.status == OperationStatus.BLOCKED


def test_assess_indeterminate_cache_schema_mismatch(tmp_path: Path):
    _setup_analyzed_repo(
        tmp_path,
        files=["app.py"],
        cache_schema_version=999,
    )

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "schema_version_mismatch"
    assert freshness.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "SCHEMA_VERSION_MISMATCH" for d in freshness.diagnostics)


def test_assess_indeterminate_analyzer_version_mismatch(tmp_path: Path):
    _setup_analyzed_repo(
        tmp_path,
        files=["app.py"],
        analyzer_version="0.0.0-obsolete",
    )

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "analyzer_version_mismatch"
    assert freshness.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "ANALYZER_VERSION_MISMATCH" for d in freshness.diagnostics)


def test_assess_indeterminate_missing_fingerprints(tmp_path: Path):
    db, _repo, _proj, _metadata = _setup_analyzed_repo(tmp_path, files=["app.py"])

    with db.connect() as conn:
        conn.execute("DELETE FROM repository_file_fingerprints")

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_fingerprints"
    assert freshness.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "MISSING_FINGERPRINTS" for d in freshness.diagnostics)


def test_assess_indeterminate_filesystem_error(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])

    guard = WorkflowFreshnessGuard(tmp_path)
    with patch(
        "context_forge.pipeline.freshness._compute_current_fingerprints",
        side_effect=PermissionError("Access denied"),
    ):
        freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert "filesystem_error" in freshness.reason
    assert freshness.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "INDETERMINATE_FRESHNESS" for d in freshness.diagnostics)


def test_precedence_stale_takes_precedence_over_incomplete(tmp_path: Path):
    _setup_analyzed_repo(
        tmp_path,
        files=["app.py"],
        analysis_status="failed",
        errors=["Fatal parse error in app.py"],
    )

    (tmp_path / "app.py").write_text("# changed\n", encoding="utf-8")

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.STALE
    assert freshness.is_stale is True

    assert freshness.analysis_status == "failed"
    assert len(freshness.analysis_errors) == 1
    assert any(d.code == "STALE_ANALYSIS" for d in freshness.diagnostics)
    assert any(d.code == "ANALYSIS_ERROR" for d in freshness.diagnostics)


def test_precedence_incomplete_takes_precedence_over_current(tmp_path: Path):
    _setup_analyzed_repo(
        tmp_path,
        files=["app.py"],
        analysis_status="failed",
    )

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INCOMPLETE
    assert freshness.is_incomplete is True
    assert freshness.is_current is False


def test_readonly_guarantee_assess_freshness(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    mtime_before = (tmp_path / ".context_forge.db").stat().st_mtime

    with patch.object(ProjectAnalyzer, "analyze") as mock_analyze:
        guard = WorkflowFreshnessGuard(tmp_path)
        freshness = guard.assess_freshness()

    assert freshness.is_stale is True
    mock_analyze.assert_not_called()
    assert (tmp_path / ".context_forge.db").stat().st_mtime == mtime_before


def test_readonly_guarantee_guard_allow_refresh_false(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    with patch.object(ProjectAnalyzer, "analyze") as mock_analyze:
        guard = WorkflowFreshnessGuard(tmp_path)
        freshness = guard.guard(allow_refresh=False)

    assert freshness.is_stale is True
    mock_analyze.assert_not_called()


def test_guard_no_refresh_when_already_current(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])

    with patch.object(ProjectAnalyzer, "analyze") as mock_analyze:
        guard = WorkflowFreshnessGuard(tmp_path)
        freshness = guard.guard(allow_refresh=True)

    assert freshness.is_current is True
    assert freshness.refreshed is False
    mock_analyze.assert_not_called()


def test_guard_refreshes_when_stale_and_authorized(tmp_path: Path):

    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, db_path)
    analyzer.analyze()

    (tmp_path / "mod.py").write_text("x = 2\ny = 3\n", encoding="utf-8")

    guard = WorkflowFreshnessGuard(tmp_path)

    initial = guard.assess_freshness()
    assert initial.is_stale is True

    post_freshness = guard.guard(allow_refresh=True)

    assert post_freshness.is_current is True
    assert post_freshness.refreshed is True
    assert post_freshness.refresh_error is None
    assert post_freshness.outcome.status == OperationStatus.SUCCESS


def test_guard_prevents_duplicate_refresh_in_same_guard_instance(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _create_sample_project(
        tmp_path, files=["app.py"]
    )

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)

    guard.guard(allow_refresh=True)
    assert mock_analyzer.analyze.call_count == 1

    guard.guard(allow_refresh=True)
    assert mock_analyzer.analyze.call_count == 1


def test_guard_reports_refresh_failure_honestly(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    mock_analyzer = MagicMock()
    mock_analyzer.analyze.side_effect = RuntimeError("Disk full during analysis")

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)
    freshness = guard.guard(allow_refresh=True)

    assert freshness.refreshed is True
    assert freshness.refresh_error == "Disk full during analysis"
    assert freshness.outcome.status == OperationStatus.FAILED
    assert any(d.code == "REFRESH_FAILED" for d in freshness.diagnostics)
    assert any("Disk full" in err for err in freshness.analysis_errors)


def test_guard_refreshes_when_incomplete_and_authorized(tmp_path: Path):
    _setup_analyzed_repo(tmp_path, files=["app.py"], analysis_status="failed")

    mock_analyzer = MagicMock()
    refreshed_proj = _create_sample_project(tmp_path, files=["app.py"])
    mock_analyzer.analyze.return_value = refreshed_proj

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)
    initial = guard.assess_freshness()
    assert initial.is_incomplete is True

    post = guard.guard(allow_refresh=True)
    assert mock_analyzer.analyze.call_count == 1
    assert post.refreshed is True


@pytest.mark.parametrize(
    "setup_scenario",
    [
        "missing_fingerprints",
        "filesystem_error",
        "unreadable_cache",
    ],
)
def test_guard_does_not_refresh_prohibited_indeterminate_states(
    tmp_path: Path, setup_scenario: str
):
    if setup_scenario == "missing_fingerprints":
        db, _repo, _proj, _metadata = _setup_analyzed_repo(tmp_path, files=["app.py"])
        with db.connect() as conn:
            conn.execute("DELETE FROM repository_file_fingerprints")
    elif setup_scenario == "unreadable_cache":
        _setup_analyzed_repo(tmp_path, files=["app.py"])
        (tmp_path / ".context_forge.db").write_text(
            "CORRUPTED_NOT_SQLITE\n", encoding="utf-8"
        )
    elif setup_scenario == "filesystem_error":
        _setup_analyzed_repo(tmp_path, files=["app.py"])

    mock_analyzer = MagicMock()
    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)

    if setup_scenario == "filesystem_error":
        with patch(
            "context_forge.pipeline.freshness._compute_current_fingerprints",
            side_effect=PermissionError("Permission denied"),
        ):
            freshness = guard.guard(allow_refresh=True)
    else:
        freshness = guard.guard(allow_refresh=True)

    assert freshness.is_indeterminate is True
    assert freshness.refreshed is False
    mock_analyzer.analyze.assert_not_called()


@pytest.mark.parametrize(
    "setup_scenario",
    [
        "missing_analysis",
        "schema_version_mismatch",
        "analyzer_version_mismatch",
    ],
)
def test_guard_refreshes_recoverable_indeterminate_states_when_authorized(
    tmp_path: Path, setup_scenario: str
):
    if setup_scenario == "missing_analysis":
        pass
    elif setup_scenario == "schema_version_mismatch":
        _setup_analyzed_repo(tmp_path, files=["app.py"], cache_schema_version=999)
    elif setup_scenario == "analyzer_version_mismatch":
        _setup_analyzed_repo(tmp_path, files=["app.py"], analyzer_version="obsolete")

    mock_analyzer = MagicMock()
    refreshed_proj = _create_sample_project(tmp_path, files=["app.py"])
    mock_analyzer.analyze.return_value = refreshed_proj

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)

    # With allow_refresh=False, it does not refresh
    unrefreshed = guard.guard(allow_refresh=False)
    assert unrefreshed.is_indeterminate is True
    assert unrefreshed.refreshed is False
    mock_analyzer.analyze.assert_not_called()

    # With allow_refresh=True, it attempts recovery
    freshness = guard.guard(allow_refresh=True)
    assert mock_analyzer.analyze.call_count == 1
    assert freshness.refreshed is True


def test_project_query_assess_freshness(tmp_path: Path):
    _, _, proj, metadata = _setup_analyzed_repo(tmp_path, files=["app.py"])

    query = ProjectQuery(proj)
    freshness = query.assess_freshness(metadata=metadata)

    assert freshness.is_current is True
    assert freshness.state == FreshnessState.CURRENT
    assert freshness.outcome.is_success is True


def test_project_query_assess_freshness_without_metadata_preserves_supplied_project(
    tmp_path: Path,
):
    _, _, proj, _ = _setup_analyzed_repo(tmp_path, files=["app.py"])

    query = ProjectQuery(proj)
    freshness = query.assess_freshness()

    assert freshness.is_current is True
    assert freshness.state == FreshnessState.CURRENT
    assert freshness.project is proj
    assert freshness.metadata is not None
    assert freshness.metadata.project_id == proj.id


def test_project_query_assess_freshness_unpersisted_project_preserves_supplied_project(
    tmp_path: Path,
):
    proj = _create_sample_project(tmp_path, files=["app.py"])
    query = ProjectQuery(proj)

    freshness = query.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_analysis"
    assert freshness.project is proj


def test_project_query_assess_freshness_missing_root_path():
    mock_proj = MagicMock()
    mock_proj.root_path = None
    query = ProjectQuery(mock_proj)
    freshness = query.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_root_path"
    assert freshness.outcome.status == OperationStatus.BLOCKED


def test_load_guarded_project_returns_on_current(tmp_path: Path):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])

    proj, meta, freshness = load_guarded_project(tmp_path)
    assert proj is not None
    assert meta is not None
    assert freshness.is_current is True


def test_load_guarded_project_raises_stale_error(tmp_path: Path):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    with pytest.raises(StaleAnalysisError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "stale" in str(exc_info.value).lower()
    assert exc_info.value.code == "STALE_ANALYSIS"


def test_load_guarded_project_raises_incomplete_error(tmp_path: Path):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"], analysis_status="failed")

    with pytest.raises(IncompleteAnalysisError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "incomplete" in str(exc_info.value).lower()
    assert exc_info.value.code == "INCOMPLETE_ANALYSIS"


def test_load_guarded_project_raises_missing_error(tmp_path: Path):
    from context_forge.main import load_guarded_project

    with pytest.raises(MissingAnalysisError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "no persisted analysis" in str(exc_info.value).lower()
    assert exc_info.value.code == "MISSING_ANALYSIS"


def test_load_guarded_project_raises_indeterminate_error(tmp_path: Path):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"], cache_schema_version=99)

    with pytest.raises(IndeterminateFreshnessError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "indeterminate" in str(exc_info.value).lower()
    assert exc_info.value.code == "INDETERMINATE_FRESHNESS"


def test_load_guarded_project_refreshes_when_allowed(tmp_path: Path):
    from context_forge.main import load_guarded_project

    (tmp_path / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    (tmp_path / "hello.py").write_text("print('hello world')\n", encoding="utf-8")

    _proj, _meta, freshness = load_guarded_project(tmp_path, allow_refresh=True)
    assert freshness.is_current is True
    assert freshness.refreshed is True


def test_error_classes_attributes_and_outcomes():
    err_inc = IncompleteAnalysisError("analysis incomplete")
    assert err_inc.code == "INCOMPLETE_ANALYSIS"
    assert err_inc.source == "analyzer"
    assert err_inc.outcome.status == OperationStatus.BLOCKED
    assert err_inc.outcome.diagnostics[0].severity == DiagnosticSeverity.BLOCKER

    err_ind = IndeterminateFreshnessError("freshness indeterminate")
    assert err_ind.code == "INDETERMINATE_FRESHNESS"
    assert err_ind.source == "storage"
    assert err_ind.outcome.status == OperationStatus.BLOCKED

    err_ref = RefreshFailedError("refresh crashed")
    assert err_ref.code == "REFRESH_FAILED"
    assert err_ref.source == "analyzer"
    assert err_ref.outcome.status == OperationStatus.FAILED
    assert err_ref.outcome.diagnostics[0].severity == DiagnosticSeverity.ERROR


def test_load_guarded_project_raises_refresh_failed_error(tmp_path: Path):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# change\n", encoding="utf-8")

    with (
        patch.object(
            ProjectAnalyzer,
            "analyze",
            side_effect=RuntimeError("Disk full during reanalysis"),
        ),
        pytest.raises(RefreshFailedError) as exc_info,
    ):
        load_guarded_project(tmp_path, allow_refresh=True)

    assert exc_info.value.code == "REFRESH_FAILED"
    assert "Disk full during reanalysis" in str(exc_info.value)
    assert exc_info.value.outcome.status == OperationStatus.FAILED


def test_load_fresh_project_with_allow_refresh_success(tmp_path: Path):
    from context_forge.main import load_fresh_project

    (tmp_path / "x.py").write_text("x = 1\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    (tmp_path / "x.py").write_text("x = 2\n", encoding="utf-8")

    # With allow_refresh=False, it should raise StaleAnalysisError
    with pytest.raises(StaleAnalysisError):
        load_fresh_project(tmp_path, allow_refresh=False)

    # With allow_refresh=True, it should refresh and return project
    proj, meta = load_fresh_project(tmp_path, allow_refresh=True)
    assert proj is not None
    assert meta is not None


def test_load_fresh_project_raises_incomplete_error(tmp_path: Path):
    from context_forge.main import load_fresh_project

    _setup_analyzed_repo(tmp_path, files=["app.py"], analysis_status="failed")

    with pytest.raises(IncompleteAnalysisError) as exc_info:
        load_fresh_project(tmp_path, allow_refresh=False)

    assert "incomplete" in str(exc_info.value).lower()
    assert exc_info.value.code == "INCOMPLETE_ANALYSIS"


def test_load_fresh_project_raises_indeterminate_error(tmp_path: Path):
    from context_forge.main import load_fresh_project

    _setup_analyzed_repo(tmp_path, files=["app.py"], cache_schema_version=99)

    with pytest.raises(IndeterminateFreshnessError) as exc_info:
        load_fresh_project(tmp_path, allow_refresh=False)

    assert "indeterminate" in str(exc_info.value).lower()
    assert exc_info.value.code == "INDETERMINATE_FRESHNESS"


def test_load_fresh_project_raises_missing_error(tmp_path: Path):
    from context_forge.main import load_fresh_project

    with pytest.raises(MissingAnalysisError) as exc_info:
        load_fresh_project(tmp_path, allow_refresh=False)

    assert "no persisted analysis" in str(exc_info.value).lower()
    assert exc_info.value.code == "MISSING_ANALYSIS"


def test_guard_refresh_producing_incomplete_analysis_not_presented_as_current(
    tmp_path: Path,
):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"], analysis_status="failed")

    incomplete_proj = _create_sample_project(
        tmp_path,
        files=["app.py"],
        analysis_status="failed",
        errors=["Syntax error in app.py"],
    )
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = incomplete_proj

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)
    freshness = guard.guard(allow_refresh=True)

    assert freshness.refreshed is True
    assert freshness.is_current is False
    assert freshness.is_incomplete is True
    assert freshness.analysis_status == "failed"
    assert freshness.refresh_error is not None
    assert "Refresh completed but analysis remains" in freshness.refresh_error
    assert freshness.outcome.status == OperationStatus.FAILED

    # Without refresh allowed, load_guarded_project raises IncompleteAnalysisError
    with pytest.raises(IncompleteAnalysisError):
        load_guarded_project(tmp_path, allow_refresh=False)

    # With refresh allowed, when refresh leaves it incomplete, it raises RefreshFailedError
    with patch(
        "context_forge.pipeline.freshness.ProjectAnalyzer", return_value=mock_analyzer
    ):
        with pytest.raises(RefreshFailedError) as exc_info:
            load_guarded_project(tmp_path, allow_refresh=True)
        assert exc_info.value.code == "REFRESH_FAILED"
        assert exc_info.value.outcome.status == OperationStatus.FAILED


def test_guard_refresh_producing_stale_analysis_raises_refresh_failed(
    tmp_path: Path,
):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# disk change\n", encoding="utf-8")

    # Analyzer analyze() completes but does not update cached fingerprints on disk
    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _create_sample_project(
        tmp_path, files=["app.py"]
    )

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)
    freshness = guard.guard(allow_refresh=True)

    assert freshness.refreshed is True
    assert freshness.is_current is False
    assert freshness.is_stale is True
    assert freshness.refresh_error is not None
    assert freshness.outcome.status == OperationStatus.FAILED

    with patch(
        "context_forge.pipeline.freshness.ProjectAnalyzer", return_value=mock_analyzer
    ):
        with pytest.raises(RefreshFailedError) as exc_info:
            load_guarded_project(tmp_path, allow_refresh=True)
        assert exc_info.value.code == "REFRESH_FAILED"


def test_guard_refresh_exception_raises_refresh_failed(tmp_path: Path):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# disk change\n", encoding="utf-8")

    mock_analyzer = MagicMock()
    mock_analyzer.analyze.side_effect = RuntimeError("analysis crashed")

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)
    freshness = guard.guard(allow_refresh=True)

    assert freshness.refreshed is True
    assert freshness.refresh_error == "analysis crashed"
    assert freshness.outcome.status == OperationStatus.FAILED

    with patch(
        "context_forge.pipeline.freshness.ProjectAnalyzer", return_value=mock_analyzer
    ):
        with pytest.raises(RefreshFailedError) as exc_info:
            load_guarded_project(tmp_path, allow_refresh=True)
        assert "analysis crashed" in str(exc_info.value)
        assert exc_info.value.code == "REFRESH_FAILED"


def test_guard_refresh_success_restores_current(tmp_path: Path):
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("x = 42\n", encoding="utf-8")

    # Real analyzer refresh
    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.guard(allow_refresh=True)

    assert freshness.refreshed is True
    assert freshness.is_current is True
    assert freshness.refresh_error is None
    assert freshness.outcome.status == OperationStatus.SUCCESS

    proj, meta, guarded_freshness = load_guarded_project(tmp_path, allow_refresh=True)
    assert proj is not None
    assert meta is not None
    assert guarded_freshness.is_current is True


def test_refresh_failure_real_db_persistence_consistency(tmp_path: Path):
    from context_forge.main import load_guarded_project

    db_path = tmp_path / ".context_forge.db"
    (tmp_path / "app.py").write_text(
        "import helper\ndef run(): return helper.val\n", encoding="utf-8"
    )
    (tmp_path / "helper.py").write_text("val = 10\n", encoding="utf-8")

    # Initial analysis
    ProjectAnalyzer(tmp_path, db_path).analyze()

    db = Database(db_path)
    with db.connect() as conn:
        orig_projects = conn.execute("SELECT * FROM projects").fetchall()
        orig_cache = conn.execute("SELECT * FROM repository_cache").fetchall()
        orig_fingerprints = conn.execute(
            "SELECT * FROM repository_file_fingerprints"
        ).fetchall()
        orig_files = conn.execute("SELECT * FROM files").fetchall()
        orig_symbols = conn.execute("SELECT * FROM symbols").fetchall()

    assert len(orig_projects) == 1
    assert len(orig_cache) == 1
    assert len(orig_fingerprints) == 2
    assert len(orig_files) == 2
    assert len(orig_symbols) >= 1

    # Now modify app.py on disk
    (tmp_path / "app.py").write_text(
        "import helper\ndef run(): return helper.val * 2\n", encoding="utf-8"
    )

    # Invalidate & inject failure during RelationshipBuilder.build during refresh
    with patch(
        "context_forge.graph.builder.RelationshipBuilder.build",
        side_effect=RuntimeError("injected relationship builder crash"),
    ):
        guard = WorkflowFreshnessGuard(tmp_path)
        freshness = guard.guard(allow_refresh=True)

        assert freshness.refreshed is True
        assert freshness.is_current is False
        assert freshness.refresh_error == "injected relationship builder crash"
        assert freshness.outcome.status == OperationStatus.FAILED

    # Verify database consistency after failure:
    # 1. DB connection remains completely readable
    with db.connect() as conn:
        post_projects = conn.execute("SELECT * FROM projects").fetchall()
        post_cache = conn.execute("SELECT * FROM repository_cache").fetchall()
        post_fingerprints = conn.execute(
            "SELECT * FROM repository_file_fingerprints"
        ).fetchall()
        post_files = conn.execute("SELECT * FROM files").fetchall()

    assert len(post_projects) == 1
    assert len(post_cache) == 1
    assert len(post_files) >= 1
    # 2. In accordance with incremental invalidation: app.py was invalidated at the
    # start of refresh, so only helper.py remains in repository_file_fingerprints.
    # Because save_analysis failed, new fingerprints were not committed.
    assert len(post_fingerprints) == 1
    assert post_fingerprints[0]["path"] == "helper.py"

    # 3. Subsequent assessment detects app.py has no cache fingerprint vs disk -> STALE, NEVER CURRENT!
    post_guard = WorkflowFreshnessGuard(tmp_path)
    post_assessment = post_guard.assess_freshness()
    assert post_assessment.is_current is False
    assert post_assessment.state == FreshnessState.STALE
    assert "app.py" in str(post_assessment.changes)

    # 4. Without refresh, substantive loading is blocked with StaleAnalysisError
    with pytest.raises(StaleAnalysisError):
        load_guarded_project(tmp_path, allow_refresh=False)

    # 5. Subsequent refresh attempt without the injected error recovers cleanly
    recovered = post_guard.guard(allow_refresh=True)
    assert recovered.is_current is True
    assert recovered.refreshed is True
    assert recovered.refresh_error is None

    with db.connect() as conn:
        recovered_fingerprints = conn.execute(
            "SELECT * FROM repository_file_fingerprints"
        ).fetchall()
    assert len(recovered_fingerprints) == 2


def test_refresh_failure_during_persistence_consistency(tmp_path: Path):
    """Failure during save_analysis leaves database in a consistent stale state that recovers cleanly."""
    db_path = tmp_path / ".context_forge.db"
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "lib.py").write_text("y = 2\n", encoding="utf-8")

    # Initial analysis
    ProjectAnalyzer(tmp_path, db_path).analyze()
    db = Database(db_path)

    # Modify app.py
    (tmp_path / "app.py").write_text("x = 99\n", encoding="utf-8")

    # Inject failure during _save_file_fingerprints in save_analysis
    with patch(
        "context_forge.storage.repository.ProjectRepository._save_file_fingerprints",
        side_effect=sqlite3.OperationalError(
            "disk I/O error during fingerprint commit"
        ),
    ):
        guard = WorkflowFreshnessGuard(tmp_path)
        freshness = guard.guard(allow_refresh=True)

        assert freshness.refreshed is True
        assert freshness.is_current is False
        assert "disk I/O error" in str(freshness.refresh_error)

    # 1. Fresh database connection verifies tables are readable and intact
    with db.connect() as conn:
        post_projects = conn.execute("SELECT * FROM projects").fetchall()
        post_cache = conn.execute("SELECT * FROM repository_cache").fetchall()
        post_fingerprints = conn.execute(
            "SELECT * FROM repository_file_fingerprints"
        ).fetchall()

    assert len(post_projects) == 1
    assert len(post_cache) == 1
    # app.py fingerprint was invalidated; save_analysis transaction rolled back
    assert len(post_fingerprints) == 1
    assert post_fingerprints[0]["path"] == "lib.py"

    # 2. Fresh guard assessment detects repository is STALE, NEVER CURRENT
    fresh_guard = WorkflowFreshnessGuard(tmp_path)
    fresh_assessment = fresh_guard.assess_freshness()
    assert fresh_assessment.is_current is False
    assert fresh_assessment.is_stale is True

    # 3. Subsequent refresh without the error succeeds and achieves CURRENT status
    recovered = fresh_guard.guard(allow_refresh=True)
    assert recovered.is_current is True
    assert recovered.refreshed is True
    assert recovered.refresh_error is None

    with db.connect() as conn:
        final_fingerprints = conn.execute(
            "SELECT * FROM repository_file_fingerprints"
        ).fetchall()
    assert len(final_fingerprints) == 2


@pytest.mark.parametrize(
    ("mutate_fn", "expected_state", "expected_reason"),
    [
        (
            lambda p: (p / "new.py").write_text("y = 1\n"),
            FreshnessState.STALE,
            "files changed (1 added)",
        ),
        (
            lambda p: (p / "app.py").unlink(),
            FreshnessState.STALE,
            "files changed (1 deleted)",
        ),
        (
            lambda p: _set_db_field(p, "projects", "analysis_status", "not_analyzed"),
            FreshnessState.INCOMPLETE,
            "analysis_status_not_analyzed",
        ),
        (
            lambda p: _set_db_field(p, "projects", "analysis_status", "analyzing"),
            FreshnessState.INCOMPLETE,
            "analysis_status_analyzing",
        ),
        (
            lambda p: _set_db_field(p, "projects", "analysis_status", "partial"),
            FreshnessState.INCOMPLETE,
            "analysis_partial",
        ),
        (
            lambda p: _set_db_field(p, "projects", "analysis_status", "unknown_custom"),
            FreshnessState.INCOMPLETE,
            "analysis_status_unknown_custom",
        ),
        (
            lambda p: _set_db_field(p, "repository_cache", "cache_schema_version", 999),
            FreshnessState.INDETERMINATE,
            "schema_version_mismatch",
        ),
        (
            lambda p: _set_db_field(
                p, "repository_cache", "analyzer_version", "99.0.0"
            ),
            FreshnessState.INDETERMINATE,
            "analyzer_version_mismatch",
        ),
    ],
)
def test_freshness_state_precedence_and_transitions(
    tmp_path: Path,
    mutate_fn,
    expected_state: FreshnessState,
    expected_reason: str,
):
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    mutate_fn(tmp_path)

    guard = WorkflowFreshnessGuard(tmp_path)
    assessment = guard.assess_freshness()

    assert assessment.state == expected_state
    assert expected_reason in assessment.reason


def _set_db_field(root: Path, table: str, field: str, value: Any) -> None:
    db = Database(root / ".context_forge.db")
    with db.connect() as conn:
        conn.execute(f"UPDATE {table} SET {field} = ?", (value,))


# ==============================================================================
# 11. Section 3 Detailed Timing, Change Detection & Automatic Refresh Tests
# ==============================================================================


def test_current_project_does_not_reanalyze_unnecessarily(tmp_path: Path):
    """Running query against current project reuses analysis without calling analyzer."""
    from context_forge.main import load_fresh_project

    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    mock_analyzer = MagicMock()
    with patch(
        "context_forge.pipeline.freshness.ProjectAnalyzer", return_value=mock_analyzer
    ):
        proj, _ = load_fresh_project(tmp_path, allow_refresh=True)

    assert proj is not None
    assert mock_analyzer.analyze.call_count == 0


def test_timing_unchanged_project_after_30_and_60_seconds_does_not_reanalyze(
    tmp_path: Path,
):
    """Elapsed time alone (30s, 60s) must not trigger re-analysis when files are unchanged."""
    from context_forge.main import load_fresh_project

    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    # Simulate 30s elapsed by shifting timestamps
    stat = (tmp_path / "mod.py").stat()
    past_mtime = stat.st_mtime - 35
    import os

    os.utime(tmp_path / "mod.py", (past_mtime, past_mtime))

    mock_analyzer = MagicMock()
    with patch(
        "context_forge.pipeline.freshness.ProjectAnalyzer", return_value=mock_analyzer
    ):
        proj, _ = load_fresh_project(tmp_path, allow_refresh=True)

    assert proj is not None
    assert mock_analyzer.analyze.call_count == 0

    # Simulate 60s elapsed
    past_mtime_60 = stat.st_mtime - 70
    os.utime(tmp_path / "mod.py", (past_mtime_60, past_mtime_60))
    with patch(
        "context_forge.pipeline.freshness.ProjectAnalyzer", return_value=mock_analyzer
    ):
        proj2, _ = load_fresh_project(tmp_path, allow_refresh=True)

    assert proj2 is not None
    assert mock_analyzer.analyze.call_count == 0


def test_timing_changed_file_within_30_and_60_seconds_triggers_auto_refresh(
    tmp_path: Path,
):
    """Source file changed within 30s or 60s triggers automatic refresh."""
    from context_forge.main import load_fresh_project

    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    # 1. Modify file within 30s
    (tmp_path / "mod.py").write_text("x = 2\n", encoding="utf-8")
    proj, _ = load_fresh_project(tmp_path, allow_refresh=True)
    assert any(s.name == "x" for s in proj.symbols)

    # Verify updated in DB
    guard = WorkflowFreshnessGuard(tmp_path, database_path=db_path)
    assert guard.assess_freshness().is_current is True

    # 2. Modify file within 60s
    (tmp_path / "mod.py").write_text("y = 99\n", encoding="utf-8")
    proj2, _ = load_fresh_project(tmp_path, allow_refresh=True)
    assert any(s.name == "y" for s in proj2.symbols)
    assert guard.assess_freshness().is_current is True


def test_repeated_commands_after_refresh_reuse_updated_analysis(tmp_path: Path):
    """Repeated commands after a successful refresh reuse the updated analysis."""
    from context_forge.main import load_fresh_project

    (tmp_path / "mod.py").write_text("x = 10\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    # Modify
    (tmp_path / "mod.py").write_text("x = 20\n", encoding="utf-8")

    # Command 1: refreshes
    proj1, _ = load_fresh_project(tmp_path, allow_refresh=True)
    assert proj1 is not None

    # Command 2: reuses without re-analysis
    mock_analyzer = MagicMock()
    with patch(
        "context_forge.pipeline.freshness.ProjectAnalyzer", return_value=mock_analyzer
    ):
        proj2, _ = load_fresh_project(tmp_path, allow_refresh=True)

    assert proj2 is not None
    assert mock_analyzer.analyze.call_count == 0


def test_added_and_deleted_files_handled_by_automatic_refresh(tmp_path: Path):
    """Added and deleted files are detected and refreshed automatically."""
    from context_forge.main import load_fresh_project

    (tmp_path / "a.py").write_text("def fn_a(): pass\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    # 1. Add file
    (tmp_path / "b.py").write_text("def fn_b(): pass\n", encoding="utf-8")
    proj_add, _ = load_fresh_project(tmp_path, allow_refresh=True)
    assert any(s.name == "fn_b" for s in proj_add.symbols)

    # 2. Delete file
    (tmp_path / "a.py").unlink()
    proj_del, _ = load_fresh_project(tmp_path, allow_refresh=True)
    assert not any(s.name == "fn_a" for s in proj_del.symbols)
    assert any(s.name == "fn_b" for s in proj_del.symbols)


def test_changed_dependencies_updated_by_automatic_refresh(tmp_path: Path):
    """Changed dependencies update relationship graph on automatic refresh."""
    from context_forge.main import load_fresh_project
    from context_forge.query.project import ProjectQuery

    (tmp_path / "lib.py").write_text("VAL = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("import lib\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    # Change import in app.py
    (tmp_path / "app.py").write_text("import sys\n", encoding="utf-8")
    proj, _ = load_fresh_project(tmp_path, allow_refresh=True)

    app_file = next(f for f in proj.files if f.path == Path("app.py"))
    direct_deps = ProjectQuery(proj).get_direct_dependencies(app_file.id)
    # lib should no longer be a direct dependency
    assert not any(d.path == Path("lib.py") for d in direct_deps)


def test_load_fresh_project_initial_analysis_on_new_repo(tmp_path: Path):
    """Substantive queries auto-initialize analysis on an unanalyzed repo."""
    from context_forge.main import load_fresh_project

    (tmp_path / "hello.py").write_text("MSG = 'hello'\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    assert not db_path.exists()

    # 1. allow_refresh=False refuses to initialize
    with pytest.raises(MissingAnalysisError):
        load_fresh_project(tmp_path, allow_refresh=False)
    assert not db_path.exists()

    # 2. allow_refresh=True performs initial analysis
    proj, meta = load_fresh_project(tmp_path, allow_refresh=True)
    assert db_path.exists()
    assert proj is not None
    assert meta is not None
    assert any(s.name == "MSG" for s in proj.symbols)


def test_load_fresh_project_recovers_schema_version_mismatch(tmp_path: Path):
    """Schema mismatch is safely recovered via full reanalysis when allow_refresh=True."""
    from context_forge.main import load_fresh_project

    (tmp_path / "hello.py").write_text("MSG = 'hello'\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE repository_cache SET cache_schema_version = 0")
    conn.commit()
    conn.close()

    # Without refresh: raises IndeterminateFreshnessError
    with pytest.raises(IndeterminateFreshnessError):
        load_fresh_project(tmp_path, allow_refresh=False)

    # With refresh: recovers
    proj, meta = load_fresh_project(tmp_path, allow_refresh=True)
    assert proj is not None
    assert meta.cache_schema_version == CACHE_SCHEMA_VERSION


def test_load_fresh_project_recovers_analyzer_version_mismatch(tmp_path: Path):
    """Analyzer version mismatch is safely recovered when allow_refresh=True."""
    from context_forge.main import load_fresh_project

    (tmp_path / "hello.py").write_text("MSG = 'hello'\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE repository_cache SET analyzer_version = 'old_v0'")
    conn.commit()
    conn.close()

    # Without refresh: raises IndeterminateFreshnessError
    with pytest.raises(IndeterminateFreshnessError):
        load_fresh_project(tmp_path, allow_refresh=False)

    # With refresh: recovers
    proj, meta = load_fresh_project(tmp_path, allow_refresh=True)
    assert proj is not None
    assert meta.analyzer_version == ANALYZER_VERSION


def test_load_fresh_project_recovers_incomplete_analysis(tmp_path: Path):
    """Incomplete analysis is recovered when repo code is valid."""
    from context_forge.main import load_fresh_project

    (tmp_path / "hello.py").write_text("MSG = 'hello'\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE projects SET analysis_status = 'failed'")
    conn.commit()
    conn.close()

    # Without refresh: raises IncompleteAnalysisError
    with pytest.raises(IncompleteAnalysisError):
        load_fresh_project(tmp_path, allow_refresh=False)

    # With refresh: recovers
    proj, _ = load_fresh_project(tmp_path, allow_refresh=True)
    assert proj.analysis_status == "analyzed"


def test_load_fresh_project_recovery_fails_honestly_when_code_broken(tmp_path: Path):
    """Recovery analysis fails with RefreshFailedError if repo has syntax errors."""
    from context_forge.main import load_fresh_project

    (tmp_path / "hello.py").write_text("MSG = 'hello'\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    # Introduce broken code and set failed status
    (tmp_path / "hello.py").write_text("def broken(:\n", encoding="utf-8")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE projects SET analysis_status = 'failed'")
    conn.commit()
    conn.close()

    with pytest.raises(RefreshFailedError) as exc_info:
        load_fresh_project(tmp_path, allow_refresh=True)

    assert exc_info.value.code == "REFRESH_FAILED"
    assert exc_info.value.outcome.status == OperationStatus.FAILED


def test_load_fresh_project_corrupt_database_fails_safely(tmp_path: Path):
    """Corrupt SQLite database fails safely with IndeterminateFreshnessError and never recovers."""
    from context_forge.main import load_fresh_project

    (tmp_path / "hello.py").write_text("MSG = 'hello'\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    db_path.write_text("CORRUPTED_GARBAGE\n", encoding="utf-8")

    with pytest.raises(IndeterminateFreshnessError) as exc_info:
        load_fresh_project(tmp_path, allow_refresh=False)
    assert exc_info.value.code == "INDETERMINATE_FRESHNESS"

    with pytest.raises(IndeterminateFreshnessError) as exc_info2:
        load_fresh_project(tmp_path, allow_refresh=True)
    assert exc_info2.value.code == "INDETERMINATE_FRESHNESS"
