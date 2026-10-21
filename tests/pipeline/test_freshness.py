"""Tests for Context Forge v0.12 Section 4: Workflow Freshness Guard.

Covers:
- Semantic freshness states: current, stale, incomplete, indeterminate
- Evidence-based detection: additions, modifications, deletions, status, errors
- Deterministic precedence rules
- Read-only guarantees
- Controlled refresh execution, failure handling, and duplicate refresh prevention
- Integration with ProjectQuery and main loader
- Structured reporting contracts and error representations
"""

from __future__ import annotations

from pathlib import Path
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
    """Helper to create a populated Project model."""
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
    """Helper to initialize and persist analysis for a repository."""
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


# ==============================================================================
# 1. Semantic Freshness States
# ==============================================================================


def test_freshness_state_enum_properties():
    """Verify FreshnessState properties."""
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
    """Verify WorkflowFreshness serialization and outcome contract."""
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
    """Verify clean, unmutated analyzed repository assesses as CURRENT."""
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


# ==============================================================================
# 2. Staleness Detection: Modified, Added, Deleted Files
# ==============================================================================


def test_assess_stale_when_file_modified(tmp_path: Path):
    """Verify modifying a file marks the repository as STALE."""
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    target_file = tmp_path / "app.py"

    # Modify file content and change mtime
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
    """Verify adding a new file marks the repository as STALE."""
    _setup_analyzed_repo(tmp_path, files=["app.py"])

    # Create new file on disk not in cached fingerprints
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
    """Verify deleting a file marks the repository as STALE."""
    _setup_analyzed_repo(tmp_path, files=["app.py", "remove_me.py"])

    # Delete one file from disk
    (tmp_path / "remove_me.py").unlink()

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.STALE
    assert "deleted" in freshness.reason
    assert freshness.changes is not None
    assert Path("remove_me.py") in freshness.changes.deleted
    assert freshness.outcome.status == OperationStatus.PARTIAL


def test_assess_stale_with_multiple_mixed_changes(tmp_path: Path):
    """Verify mixed add, modify, delete changes are accurately detected and reported."""
    _setup_analyzed_repo(tmp_path, files=["mod1.py", "mod2.py", "delete.py"])

    # Modify mod1
    (tmp_path / "mod1.py").write_text("# modified\n", encoding="utf-8")
    # Delete delete.py
    (tmp_path / "delete.py").unlink()
    # Add added.py
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


# ==============================================================================
# 3. Incompleteness Detection: Status and Errors
# ==============================================================================


@pytest.mark.parametrize("status", ["failed", "partial", "analyzing", "not_analyzed"])
def test_assess_incomplete_due_to_analysis_status(tmp_path: Path, status: str):
    """Verify non-successful analysis status marks repository as INCOMPLETE."""
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
    """Verify recorded analysis errors mark repository as INCOMPLETE."""
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


# ==============================================================================
# 4. Indeterminate Freshness Detection: Missing or Corrupt Evidence
# ==============================================================================


def test_assess_indeterminate_missing_database(tmp_path: Path):
    """Verify missing database returns INDETERMINATE with MISSING_ANALYSIS blocker."""
    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.is_indeterminate is True
    assert freshness.reason == "missing_analysis"
    assert freshness.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "MISSING_ANALYSIS" for d in freshness.diagnostics)


def test_assess_indeterminate_no_analysis_in_db(tmp_path: Path):
    """Verify empty database with no matching repository analysis returns INDETERMINATE."""
    db_path = tmp_path / ".context_forge.db"
    db = Database(db_path)
    db.initialize()

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_analysis"
    assert freshness.outcome.status == OperationStatus.BLOCKED


def test_assess_indeterminate_cache_schema_mismatch(tmp_path: Path):
    """Verify cache schema version mismatch returns INDETERMINATE with SCHEMA_VERSION_MISMATCH."""
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
    """Verify analyzer version mismatch returns INDETERMINATE with ANALYZER_VERSION_MISMATCH."""
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
    """Verify missing cached fingerprints returns INDETERMINATE with MISSING_FINGERPRINTS."""
    db, _repo, _proj, _metadata = _setup_analyzed_repo(tmp_path, files=["app.py"])

    # Clear cached fingerprints from database
    with db.connect() as conn:
        conn.execute("DELETE FROM repository_file_fingerprints")

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_fingerprints"
    assert freshness.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "MISSING_FINGERPRINTS" for d in freshness.diagnostics)


def test_assess_indeterminate_filesystem_error(tmp_path: Path):
    """Verify filesystem scan error returns INDETERMINATE with INDETERMINATE_FRESHNESS."""
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


# ==============================================================================
# 5. Deterministic Precedence Rules
# ==============================================================================


def test_precedence_stale_takes_precedence_over_incomplete(tmp_path: Path):
    """Verify file changes report as STALE even if analysis status is failed."""
    _setup_analyzed_repo(
        tmp_path,
        files=["app.py"],
        analysis_status="failed",
        errors=["Fatal parse error in app.py"],
    )

    # Modify app.py so file changes exist
    (tmp_path / "app.py").write_text("# changed\n", encoding="utf-8")

    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()

    assert freshness.state == FreshnessState.STALE
    assert freshness.is_stale is True
    # Analysis errors should still be tracked in diagnostics and fields
    assert freshness.analysis_status == "failed"
    assert len(freshness.analysis_errors) == 1
    assert any(d.code == "STALE_ANALYSIS" for d in freshness.diagnostics)
    assert any(d.code == "ANALYSIS_ERROR" for d in freshness.diagnostics)


def test_precedence_incomplete_takes_precedence_over_current(tmp_path: Path):
    """Verify unchanged files with failed analysis reports as INCOMPLETE, not CURRENT."""
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


# ==============================================================================
# 6. Read-Only Guarantees
# ==============================================================================


def test_readonly_guarantee_assess_freshness(tmp_path: Path):
    """Verify assess_freshness does not mutate repo files, DB, or execute analyze()."""
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
    """Verify guard(allow_refresh=False) strictly preserves read-only mode."""
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    with patch.object(ProjectAnalyzer, "analyze") as mock_analyze:
        guard = WorkflowFreshnessGuard(tmp_path)
        freshness = guard.guard(allow_refresh=False)

    assert freshness.is_stale is True
    mock_analyze.assert_not_called()


# ==============================================================================
# 7. Controlled Refresh Execution and Failure Handling
# ==============================================================================


def test_guard_no_refresh_when_already_current(tmp_path: Path):
    """Verify guard(allow_refresh=True) does not trigger analyzer when already CURRENT."""
    _setup_analyzed_repo(tmp_path, files=["app.py"])

    with patch.object(ProjectAnalyzer, "analyze") as mock_analyze:
        guard = WorkflowFreshnessGuard(tmp_path)
        freshness = guard.guard(allow_refresh=True)

    assert freshness.is_current is True
    assert freshness.refreshed is False
    mock_analyze.assert_not_called()


def test_guard_refreshes_when_stale_and_authorized(tmp_path: Path):
    """Verify guard(allow_refresh=True) executes analyzer and returns fresh analysis."""
    # Start with empty repo, analyze it with real ProjectAnalyzer
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, db_path)
    analyzer.analyze()

    # Modify mod.py to make it stale
    (tmp_path / "mod.py").write_text("x = 2\ny = 3\n", encoding="utf-8")

    guard = WorkflowFreshnessGuard(tmp_path)
    # First assess confirms stale
    initial = guard.assess_freshness()
    assert initial.is_stale is True

    # Now guard with allow_refresh=True
    post_freshness = guard.guard(allow_refresh=True)

    assert post_freshness.is_current is True
    assert post_freshness.refreshed is True
    assert post_freshness.refresh_error is None
    assert post_freshness.outcome.status == OperationStatus.SUCCESS


def test_guard_prevents_duplicate_refresh_in_same_guard_instance(tmp_path: Path):
    """Verify guard instance does not repeat refresh if already attempted."""
    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = _create_sample_project(
        tmp_path, files=["app.py"]
    )

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)

    # First call refreshes
    guard.guard(allow_refresh=True)
    assert mock_analyzer.analyze.call_count == 1

    # Second call must not call analyze again on the same guard instance
    guard.guard(allow_refresh=True)
    assert mock_analyzer.analyze.call_count == 1


def test_guard_reports_refresh_failure_honestly(tmp_path: Path):
    """Verify refresh exception is caught and reported honestly without crashing."""
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
    """Verify guard(allow_refresh=True) executes analyzer when analysis is incomplete."""
    _setup_analyzed_repo(tmp_path, files=["app.py"], analysis_status="failed")

    mock_analyzer = MagicMock()
    refreshed_proj = _create_sample_project(tmp_path, files=["app.py"])
    mock_analyzer.analyze.return_value = refreshed_proj

    guard = WorkflowFreshnessGuard(tmp_path, analyzer=mock_analyzer)
    initial = guard.assess_freshness()
    assert initial.is_incomplete is True

    # allow_refresh=True must refresh incomplete analysis
    post = guard.guard(allow_refresh=True)
    assert mock_analyzer.analyze.call_count == 1
    assert post.refreshed is True


@pytest.mark.parametrize(
    "setup_scenario",
    [
        "missing_analysis",
        "missing_fingerprints",
        "schema_version_mismatch",
        "analyzer_version_mismatch",
        "filesystem_error",
    ],
)
def test_guard_does_not_refresh_prohibited_indeterminate_states(
    tmp_path: Path, setup_scenario: str
):
    """Verify guard(allow_refresh=True) strictly refuses to invoke analyzer for indeterminate states."""
    if setup_scenario == "missing_analysis":
        # No DB, no analysis
        pass
    elif setup_scenario == "missing_fingerprints":
        db, _repo, _proj, _metadata = _setup_analyzed_repo(tmp_path, files=["app.py"])
        with db.connect() as conn:
            conn.execute("DELETE FROM repository_file_fingerprints")
    elif setup_scenario == "schema_version_mismatch":
        _setup_analyzed_repo(tmp_path, files=["app.py"], cache_schema_version=999)
    elif setup_scenario == "analyzer_version_mismatch":
        _setup_analyzed_repo(tmp_path, files=["app.py"], analyzer_version="obsolete")
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


# ==============================================================================
# 8. Query and Main Layer Integration
# ==============================================================================


def test_project_query_assess_freshness(tmp_path: Path):
    """Verify ProjectQuery.assess_freshness works seamlessly on an analyzed project."""
    _, _, proj, metadata = _setup_analyzed_repo(tmp_path, files=["app.py"])

    query = ProjectQuery(proj)
    freshness = query.assess_freshness(metadata=metadata)

    assert freshness.is_current is True
    assert freshness.state == FreshnessState.CURRENT
    assert freshness.outcome.is_success is True


def test_project_query_assess_freshness_without_metadata_preserves_supplied_project(
    tmp_path: Path,
):
    """Verify ProjectQuery.assess_freshness without metadata preserves supplied project instance."""
    _, _, proj, _ = _setup_analyzed_repo(tmp_path, files=["app.py"])

    query = ProjectQuery(proj)
    freshness = query.assess_freshness()  # metadata=None

    assert freshness.is_current is True
    assert freshness.state == FreshnessState.CURRENT
    assert freshness.project is proj  # Supplied project identity preserved!
    assert freshness.metadata is not None
    assert freshness.metadata.project_id == proj.id


def test_project_query_assess_freshness_unpersisted_project_preserves_supplied_project(
    tmp_path: Path,
):
    """Verify ProjectQuery.assess_freshness on unpersisted project returns INDETERMINATE preserving project."""
    proj = _create_sample_project(tmp_path, files=["app.py"])
    query = ProjectQuery(proj)

    freshness = query.assess_freshness()  # DB does not exist

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_analysis"
    assert freshness.project is proj  # Supplied project identity preserved!


def test_project_query_assess_freshness_missing_root_path():
    """Verify ProjectQuery.assess_freshness without root_path returns INDETERMINATE."""
    mock_proj = MagicMock()
    mock_proj.root_path = None
    query = ProjectQuery(mock_proj)
    freshness = query.assess_freshness()

    assert freshness.state == FreshnessState.INDETERMINATE
    assert freshness.reason == "missing_root_path"
    assert freshness.outcome.status == OperationStatus.BLOCKED


def test_load_guarded_project_returns_on_current(tmp_path: Path):
    """Verify load_guarded_project returns project, metadata, freshness on clean repository."""
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])

    proj, meta, freshness = load_guarded_project(tmp_path)
    assert proj is not None
    assert meta is not None
    assert freshness.is_current is True


def test_load_guarded_project_raises_stale_error(tmp_path: Path):
    """Verify load_guarded_project raises StaleAnalysisError when repo is stale."""
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"])
    (tmp_path / "app.py").write_text("# modified\n", encoding="utf-8")

    with pytest.raises(StaleAnalysisError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "stale" in str(exc_info.value).lower()
    assert exc_info.value.code == "STALE_ANALYSIS"


def test_load_guarded_project_raises_incomplete_error(tmp_path: Path):
    """Verify load_guarded_project raises IncompleteAnalysisError on incomplete analysis."""
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"], analysis_status="failed")

    with pytest.raises(IncompleteAnalysisError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "incomplete" in str(exc_info.value).lower()
    assert exc_info.value.code == "INCOMPLETE_ANALYSIS"


def test_load_guarded_project_raises_missing_error(tmp_path: Path):
    """Verify load_guarded_project raises MissingAnalysisError when database is absent."""
    from context_forge.main import load_guarded_project

    with pytest.raises(MissingAnalysisError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "no persisted analysis" in str(exc_info.value).lower()
    assert exc_info.value.code == "MISSING_ANALYSIS"


def test_load_guarded_project_raises_indeterminate_error(tmp_path: Path):
    """Verify load_guarded_project raises IndeterminateFreshnessError on version mismatch."""
    from context_forge.main import load_guarded_project

    _setup_analyzed_repo(tmp_path, files=["app.py"], cache_schema_version=99)

    with pytest.raises(IndeterminateFreshnessError) as exc_info:
        load_guarded_project(tmp_path, allow_refresh=False)

    assert "indeterminate" in str(exc_info.value).lower()
    assert exc_info.value.code == "INDETERMINATE_FRESHNESS"


def test_load_guarded_project_refreshes_when_allowed(tmp_path: Path):
    """Verify load_guarded_project refreshes stale project when allow_refresh=True."""
    from context_forge.main import load_guarded_project

    (tmp_path / "hello.py").write_text("print('hello')\n", encoding="utf-8")
    db_path = tmp_path / ".context_forge.db"
    ProjectAnalyzer(tmp_path, db_path).analyze()

    # Modify file
    (tmp_path / "hello.py").write_text("print('hello world')\n", encoding="utf-8")

    _proj, _meta, freshness = load_guarded_project(tmp_path, allow_refresh=True)
    assert freshness.is_current is True
    assert freshness.refreshed is True


# ==============================================================================
# 9. Structured Errors and Diagnostics Verification
# ==============================================================================


def test_error_classes_attributes_and_outcomes():
    """Verify error classes carry proper diagnostic and outcome properties."""
    err_inc = IncompleteAnalysisError("analysis incomplete")
    assert err_inc.code == "INCOMPLETE_ANALYSIS"
    assert err_inc.source == "analyzer"
    assert err_inc.outcome.status == OperationStatus.BLOCKED
    assert err_inc.outcome.diagnostics[0].severity == DiagnosticSeverity.BLOCKER

    err_ind = IndeterminateFreshnessError("freshness indeterminate")
    assert err_ind.code == "INDETERMINATE_FRESHNESS"
    assert err_ind.source == "storage"
    assert err_ind.outcome.status == OperationStatus.BLOCKED
