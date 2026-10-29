from pathlib import Path

import pytest

from context_forge.config import (
    DEFAULTS,
    ConfigurationValidationError,
    ProjectAnalysisConfiguration,
    ProjectConfiguration,
    ProjectStorageConfiguration,
    normalize_database_path,
    resolve_configuration,
    resolve_project_database_path,
)


def test_resolve_configuration_uses_defaults_when_layers_are_empty() -> None:
    result = resolve_configuration(
        global_config=ProjectConfiguration(),
        project_config=ProjectConfiguration(),
    )

    assert result == DEFAULTS
    assert result is not DEFAULTS


def test_resolve_configuration_global_overrides_defaults() -> None:
    global_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=50,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=ProjectConfiguration(),
    )

    assert result.database_path == "global.db"
    assert result.max_context_units == 50


def test_resolve_configuration_project_overrides_global() -> None:
    global_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=50,
        ),
    )
    project_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="project.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=10,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result.database_path == "project.db"
    assert result.max_context_units == 10


def test_resolve_configuration_merges_partial_project_overrides() -> None:
    global_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
        analysis=ProjectAnalysisConfiguration(
            max_context_units=50,
        ),
    )
    project_config = ProjectConfiguration(
        analysis=ProjectAnalysisConfiguration(
            max_context_units=15,
        ),
    )

    result = resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert result.database_path == "global.db"
    assert result.max_context_units == 15


def test_resolve_configuration_does_not_mutate_inputs() -> None:
    global_config = ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
    )
    project_config = ProjectConfiguration(
        analysis=ProjectAnalysisConfiguration(
            max_context_units=15,
        ),
    )

    resolve_configuration(
        global_config=global_config,
        project_config=project_config,
    )

    assert global_config == ProjectConfiguration(
        storage=ProjectStorageConfiguration(
            database_path="global.db",
        ),
    )
    assert project_config == ProjectConfiguration(
        analysis=ProjectAnalysisConfiguration(
            max_context_units=15,
        ),
    )


def test_normalize_database_path_relative_and_absolute(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    # 1. Relative database path with an absolute project root
    norm_rel = normalize_database_path("custom.db", tmp_path)
    assert norm_rel == tmp_path / "custom.db"
    assert norm_rel.is_absolute()

    # 2. Relative database path with project_root=None anchors to cwd and is absolute
    norm_none = normalize_database_path("custom.db", project_root=None)
    assert norm_none == tmp_path / "custom.db"
    assert norm_none.is_absolute()

    # 3. Relative project root such as Path(".")
    norm_dot = normalize_database_path("custom.db", project_root=Path("."))
    assert norm_dot == tmp_path / "custom.db"
    assert norm_dot.is_absolute()

    # 4. Project roots containing redundant '..' components
    sub = tmp_path / "x" / "y"
    sub.mkdir(parents=True)
    root_with_dots = sub / ".." / "y"
    norm_dots = normalize_database_path("custom.db", project_root=root_with_dots)
    assert norm_dots == sub / "custom.db"
    assert ".." not in norm_dots.parts
    assert norm_dots.is_absolute()

    # 5. Absolute database path remains independent of the project root
    abs_db = Path("/var/log/my.db")
    norm_abs = normalize_database_path(abs_db, project_root=tmp_path)
    assert norm_abs == abs_db
    assert norm_abs.is_absolute()

    # 6. Normalization does NOT create target file or missing parent directories
    nested_rel = "nonexistent_dir/nested/my.db"
    norm_nested = normalize_database_path(nested_rel, project_root=tmp_path)
    assert not norm_nested.exists()
    assert not (tmp_path / "nonexistent_dir").exists()


def test_resolve_project_database_path_relative_root_and_dots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    rel_root = Path(".")
    resolved = resolve_project_database_path(rel_root)
    assert resolved.is_absolute()
    assert resolved == tmp_path / ".context_forge.db"

    nested_dir = tmp_path / "a" / "b"
    nested_dir.mkdir(parents=True)
    root_with_dots = nested_dir / ".." / "b"
    resolved_dots = resolve_project_database_path(root_with_dots)
    assert resolved_dots.is_absolute()
    assert resolved_dots == nested_dir / ".context_forge.db"
    assert ".." not in resolved_dots.parts

    # Database file does not exist and is NOT created by resolution
    assert not resolved_dots.exists()


def test_resolve_project_database_path_precedence(tmp_path: Path) -> None:
    proj_cfg = ProjectConfiguration(
        storage=ProjectStorageConfiguration(database_path="proj.db")
    )
    glob_cfg = ProjectConfiguration(
        storage=ProjectStorageConfiguration(database_path="glob.db")
    )

    # 1. Project overrides global
    assert (
        resolve_project_database_path(
            tmp_path, project_config=proj_cfg, global_config=glob_cfg
        )
        == tmp_path / "proj.db"
    )

    # 2. Global applies when project omits
    empty_proj = ProjectConfiguration()
    assert (
        resolve_project_database_path(
            tmp_path, project_config=empty_proj, global_config=glob_cfg
        )
        == tmp_path / "glob.db"
    )

    # 3. Built-in default when neither sets it
    empty_glob = ProjectConfiguration()
    assert (
        resolve_project_database_path(
            tmp_path, project_config=empty_proj, global_config=empty_glob
        )
        == tmp_path / ".context_forge.db"
    )

    # 4. Explicit override takes absolute precedence
    override_path = tmp_path / "override.db"
    assert (
        resolve_project_database_path(
            tmp_path,
            database_path_override=override_path,
            project_config=proj_cfg,
            global_config=glob_cfg,
        )
        == override_path
    )


def test_resolve_project_database_path_relative_global_anchors_to_project_root(
    tmp_path: Path,
) -> None:
    # A relative database_path in global configuration must anchor to the project_root,
    # NOT to the current working directory of the process.
    glob_cfg = ProjectConfiguration(
        storage=ProjectStorageConfiguration(database_path="subfolder/global_rel.db")
    )
    empty_proj = ProjectConfiguration()

    resolved = resolve_project_database_path(
        tmp_path,
        project_config=empty_proj,
        global_config=glob_cfg,
    )
    assert resolved == tmp_path / "subfolder" / "global_rel.db"

    # An absolute database_path in global configuration remains absolute
    abs_global_path = Path("/var/shared/global.db")
    glob_abs_cfg = ProjectConfiguration(
        storage=ProjectStorageConfiguration(database_path=str(abs_global_path))
    )
    resolved_abs = resolve_project_database_path(
        tmp_path,
        project_config=empty_proj,
        global_config=glob_abs_cfg,
    )
    assert resolved_abs == abs_global_path


def test_resolve_project_database_path_rejects_directory(tmp_path: Path) -> None:
    dir_path = tmp_path / "somedir"
    dir_path.mkdir()

    cfg = ProjectConfiguration(
        storage=ProjectStorageConfiguration(database_path="somedir")
    )
    with pytest.raises(
        ConfigurationValidationError,
        match="Database path cannot be an existing directory",
    ):
        resolve_project_database_path(
            tmp_path,
            project_config=cfg,
            global_config=ProjectConfiguration(),
        )

    # Explicit override pointing to existing directory is also rejected
    with pytest.raises(
        ConfigurationValidationError,
        match="Database path cannot be an existing directory",
    ):
        resolve_project_database_path(
            tmp_path,
            database_path_override=dir_path,
        )
