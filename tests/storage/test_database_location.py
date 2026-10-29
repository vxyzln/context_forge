import subprocess
from pathlib import Path

from context_forge.main import (
    _record_execution_start,
    analyze_project,
    load_fresh_project,
    load_guarded_project,
    run_history,
)
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.pipeline.freshness import WorkflowFreshnessGuard
from context_forge.preflight.readiness import build_preflight_report
from context_forge.storage.database import DATABASE_FILENAME, project_database_path


def test_fixed_database_path_helper(tmp_path: Path) -> None:
    expected = tmp_path / DATABASE_FILENAME
    assert project_database_path(tmp_path) == expected
    assert DATABASE_FILENAME == ".context_forge.db"


def test_automatic_creation_on_first_analysis(tmp_path: Path) -> None:
    (tmp_path / "module_a.py").write_text(
        "def hello(): return 'world'\n", encoding="utf-8"
    )
    db_file = tmp_path / DATABASE_FILENAME

    # Before analysis, DB must not exist
    assert not db_file.exists()

    # First analysis creates the database automatically
    project = analyze_project(tmp_path)
    assert db_file.is_file()
    assert len(project.files) >= 1

    # Persistence verification: subsequent read loads the stored model
    loaded_project, metadata = load_fresh_project(tmp_path, allow_refresh=False)
    assert loaded_project.name == project.name
    assert len(loaded_project.files) == len(project.files)
    assert metadata is not None


def test_lazy_creation_preflight_and_read_only(tmp_path: Path) -> None:
    (tmp_path / "module_b.py").write_text("x = 42\n", encoding="utf-8")
    db_file = tmp_path / DATABASE_FILENAME

    # Preflight check must be non-mutating
    report = build_preflight_report(tmp_path)
    assert report["readiness"] != "blocked"
    assert report["analysis_readiness"]["has_persisted_analysis"] is False
    assert not db_file.exists()


def test_lazy_creation_cli_help(tmp_path: Path) -> None:
    db_file = tmp_path / DATABASE_FILENAME

    # Running help via CLI in the project directory must not create .context_forge.db
    cmd = ["uv", "run", "cf", "--help"]
    result = subprocess.run(
        cmd, check=False, cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert not db_file.exists()

    # Subcommand help also must not create .context_forge.db
    cmd_sub = ["uv", "run", "cf", "analyze", "--help"]
    result_sub = subprocess.run(
        cmd_sub, check=False, cwd=tmp_path, capture_output=True, text=True
    )
    assert result_sub.returncode == 0
    assert not db_file.exists()


def test_project_isolation_two_independent_projects(tmp_path: Path) -> None:
    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    project_a.mkdir()
    project_b.mkdir()

    (project_a / "alpha.py").write_text("class AlphaService: pass\n", encoding="utf-8")
    (project_b / "beta.py").write_text("class BetaWorker: pass\n", encoding="utf-8")

    db_a = project_a / DATABASE_FILENAME
    db_b = project_b / DATABASE_FILENAME

    assert not db_a.exists()
    assert not db_b.exists()

    # Analyze project A
    analyze_project(project_a)
    assert db_a.is_file()
    assert not db_b.exists()

    # Analyze project B
    analyze_project(project_b)
    assert db_b.is_file()

    # Verify Project A and B do not see each other's symbols/files
    loaded_a, _ = load_fresh_project(project_a, allow_refresh=False)
    loaded_b, _ = load_fresh_project(project_b, allow_refresh=False)

    files_a = {f.name for f in loaded_a.files}
    files_b = {f.name for f in loaded_b.files}

    assert "alpha.py" in files_a
    assert "beta.py" not in files_a

    assert "beta.py" in files_b
    assert "alpha.py" not in files_b


def test_invoking_from_different_working_directory(tmp_path: Path) -> None:
    external_dir = tmp_path / "external_cwd"
    target_project = tmp_path / "target_project"
    external_dir.mkdir()
    target_project.mkdir()

    (target_project / "service.py").write_text("def run(): pass\n", encoding="utf-8")
    db_target = target_project / DATABASE_FILENAME
    db_external = external_dir / DATABASE_FILENAME

    # Run analyze from external_dir pointing to target_project
    cmd = ["uv", "run", "cf", "analyze", str(target_project)]
    result = subprocess.run(
        cmd, check=False, cwd=external_dir, capture_output=True, text=True
    )
    assert result.returncode == 0

    # The database must be in target_project, NEVER in external_dir
    assert db_target.is_file()
    assert not db_external.exists()


def test_explicit_database_path_override_honored(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("x = 10\n", encoding="utf-8")
    custom_db = tmp_path.parent / "custom_location" / "custom.db"
    default_db = project_database_path(tmp_path)

    custom_db.parent.mkdir(parents=True, exist_ok=True)

    # 1. ProjectAnalyzer honors explicit database_path
    analyzer = ProjectAnalyzer(root_path=tmp_path, database_path=custom_db)
    analyzer.analyze()

    assert custom_db.is_file()
    assert not default_db.exists(), (
        "Default DB must not be created when override is used"
    )

    # 2. WorkflowFreshnessGuard honors explicit database_path override
    guard = WorkflowFreshnessGuard(tmp_path, database_path=custom_db)
    freshness = guard.assess_freshness()
    assert freshness.is_current
    assert freshness.project is not None
    assert not default_db.exists()

    # 3. load_guarded_project honors explicit database_path override
    proj, meta, fresh = load_guarded_project(
        tmp_path, allow_refresh=False, database_path=custom_db
    )
    assert proj.name == tmp_path.name
    assert meta is not None
    assert fresh.is_current
    assert not default_db.exists()

    # 4. load_fresh_project honors explicit database_path override
    proj_fresh, meta_fresh = load_fresh_project(
        tmp_path, allow_refresh=False, database_path=custom_db
    )
    assert proj_fresh.name == tmp_path.name
    assert meta_fresh is not None
    assert not default_db.exists()


def test_configured_project_database_path_honored_and_parent_created(
    tmp_path: Path,
) -> None:
    (tmp_path / "hello.py").write_text("def hello(): pass\n", encoding="utf-8")
    (tmp_path / ".contextforge.toml").write_text(
        """
[storage]
database_path = "nested/storage/custom.db"
""",
        encoding="utf-8",
    )
    custom_db = tmp_path / "nested" / "storage" / "custom.db"
    default_db = tmp_path / DATABASE_FILENAME

    assert not custom_db.exists()
    assert not (tmp_path / "nested").exists()

    # 1. First analysis creates nested parent and custom DB
    project = analyze_project(tmp_path)
    assert custom_db.is_file()
    assert not default_db.exists()
    file_names = {f.name for f in project.files}
    assert "hello.py" in file_names
    assert "custom.db" not in file_names

    # 2. Subsequent load uses custom DB
    loaded_project, metadata = load_fresh_project(tmp_path, allow_refresh=False)
    assert loaded_project.name == project.name
    loaded_file_names = {f.name for f in loaded_project.files}
    assert "hello.py" in loaded_file_names
    assert "custom.db" not in loaded_file_names
    assert metadata is not None
    assert not default_db.exists()

    # 3. Freshness check uses custom DB and reports current
    guard = WorkflowFreshnessGuard(tmp_path)
    freshness = guard.assess_freshness()
    assert freshness.is_current
    assert not default_db.exists()


def test_scanner_excludes_custom_database_file(tmp_path: Path) -> None:
    from context_forge.scanner.repository import RepositoryScanner

    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    custom_db_dir = tmp_path / "build" / "data"
    custom_db_dir.mkdir(parents=True, exist_ok=True)
    custom_db = custom_db_dir / "my_custom.db"
    custom_db.write_text("sqlite placeholder", encoding="utf-8")

    # Scanner with ignored_files pointing to custom_db (both raw and with ..)
    scanner = RepositoryScanner(
        tmp_path,
        ignored_files={
            custom_db,
            tmp_path / "build" / ".." / "build" / "data" / "my_custom.db",
        },
    )
    scanned = scanner.scan()

    scanned_filenames = {f.name for f in scanned.files}
    assert "app.py" in scanned_filenames
    assert "my_custom.db" not in scanned_filenames


def test_execution_history_uses_configured_database(tmp_path: Path) -> None:
    (tmp_path / ".contextforge.toml").write_text(
        """
[storage]
database_path = "history.db"
""",
        encoding="utf-8",
    )
    custom_db = tmp_path / "history.db"
    default_db = tmp_path / DATABASE_FILENAME

    repo, exec_id = _record_execution_start(tmp_path, "context-forge analyze")
    assert repo is not None
    assert exec_id is not None
    assert custom_db.is_file()
    assert not default_db.exists()


def test_malformed_project_config_fails_fast_without_silent_fallback(
    tmp_path: Path,
) -> None:
    from context_forge.config.loader import ConfigurationLoadError

    (tmp_path / ".contextforge.toml").write_text(
        "INVALID TOML [[[",
        encoding="utf-8",
    )
    default_db = tmp_path / DATABASE_FILENAME

    # Analysis must fail fast with ConfigurationLoadError, not silently fall back
    import pytest

    with pytest.raises(ConfigurationLoadError):
        analyze_project(tmp_path)

    assert not default_db.exists()

    # Execution tracking handles config failure gracefully without creating default DB
    repo, exec_id = _record_execution_start(tmp_path, "context-forge analyze")
    assert repo is None
    assert exec_id is None
    assert not default_db.exists()


def test_configured_database_across_all_runtime_consumers(
    tmp_path: Path,
    capsys,
) -> None:
    source_file = tmp_path / "app.py"
    source_file.write_text("def run(): pass\n", encoding="utf-8")
    (tmp_path / ".contextforge.toml").write_text(
        """
[storage]
database_path = "store/app.db"
""",
        encoding="utf-8",
    )
    custom_db = tmp_path / "store" / "app.db"
    default_db = tmp_path / DATABASE_FILENAME

    # 1. Preflight before analysis sees the custom db path and reports unpersisted
    pre_report = build_preflight_report(tmp_path)
    assert pre_report["analysis_readiness"]["database_path"] == "store/app.db"
    assert pre_report["analysis_readiness"]["has_persisted_analysis"] is False
    assert not custom_db.exists()
    assert not default_db.exists()

    # 2. Execution start records into custom db (creates directory and db)
    repo, exec_id = _record_execution_start(tmp_path, "context-forge analyze")
    assert repo is not None
    assert exec_id is not None
    assert custom_db.is_file()
    assert not default_db.exists()

    # 3. Analyze populates the custom db
    project = analyze_project(tmp_path)
    assert custom_db.is_file()
    assert not default_db.exists()
    assert project.name == tmp_path.name

    # 4. Preflight after analysis reports persisted
    post_report = build_preflight_report(tmp_path)
    assert post_report["analysis_readiness"]["has_persisted_analysis"] is True
    assert not default_db.exists()

    # 5. Guarded load loads from custom db
    proj, meta, fresh = load_guarded_project(tmp_path, allow_refresh=False)
    assert proj.name == tmp_path.name
    assert meta is not None
    assert fresh.is_current
    assert not default_db.exists()

    # 6. Freshness guard refresh when source changes
    source_file.write_text("def run(): return 42\n", encoding="utf-8")
    guard = WorkflowFreshnessGuard(tmp_path)
    refreshed = guard.guard(allow_refresh=True)
    assert refreshed.is_current
    assert not default_db.exists()

    # 7. History retrieval reads from custom db
    run_history(tmp_path, output_format="text")
    out = capsys.readouterr().out
    assert "context-forge analyze" in out
    assert not default_db.exists()


def test_global_database_path_used_across_runtime_when_project_omits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home_dir = tmp_path / "home"
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "worker.py").write_text("def work(): pass\n", encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: home_dir)
    global_db_file = tmp_path / "global_shared.db"
    default_db = project_dir / DATABASE_FILENAME

    global_cfg_file = home_dir / ".config" / "context-forge" / "config.toml"
    global_cfg_file.parent.mkdir(parents=True, exist_ok=True)
    global_cfg_file.write_text(
        f"""
[storage]
database_path = "{global_db_file.as_posix()}"
""",
        encoding="utf-8",
    )

    # 1. Analyze uses global DB
    proj = analyze_project(project_dir)
    assert global_db_file.is_file()
    assert not default_db.exists()
    assert proj.name == project_dir.name

    # 2. Guarded load uses global DB
    loaded_proj, meta, fresh = load_guarded_project(project_dir, allow_refresh=False)
    assert loaded_proj.name == project_dir.name
    assert meta is not None
    assert fresh.is_current
    assert not default_db.exists()
