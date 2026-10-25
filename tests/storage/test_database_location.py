import subprocess
from pathlib import Path

from context_forge.main import (
    analyze_project,
    load_fresh_project,
    load_guarded_project,
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
