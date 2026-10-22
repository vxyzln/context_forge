from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

from context_forge.git import (
    EntityMappingStatus,
    GitRepository,
    GitStatusEntry,
    GitStatusResult,
    map_changed_paths,
    reconcile_git_path_to_project,
)
from context_forge.git.navigation import normalize_relative_path
from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.query.project import ProjectQuery
from context_forge.reporting.contract import OperationStatus


def run_git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def configure_git(path: Path) -> None:
    run_git(path, "init")
    run_git(path, "config", "user.name", "Context Forge Test")
    run_git(path, "config", "user.email", "test@example.com")


def _create_project_with_files(
    repo_dir: Path,
    file_rel_paths: list[str],
    dir_rel_paths: list[str] | None = None,
) -> Project:
    proj_id = uuid4()
    files: list[File] = []
    for rel in file_rel_paths:
        abs_p = repo_dir / rel
        abs_p.parent.mkdir(parents=True, exist_ok=True)
        if not abs_p.exists():
            abs_p.write_text(f"# content of {rel}\n", encoding="utf-8")
        files.append(
            File(
                project_id=proj_id,
                id=uuid4(),
                path=Path(rel),
                name=Path(rel).name,
                extension=Path(rel).suffix.lstrip("."),
                size=abs_p.stat().st_size,
            )
        )

    directories: list[Directory] = []
    if dir_rel_paths:
        for d in dir_rel_paths:
            abs_d = repo_dir / d
            abs_d.mkdir(parents=True, exist_ok=True)
            directories.append(
                Directory(
                    project_id=proj_id,
                    id=uuid4(),
                    path=Path(d),
                    name=Path(d).name,
                )
            )

    return Project(
        id=proj_id,
        name=repo_dir.name,
        root_path=repo_dir,
        files=files,
        directories=directories,
        analysis_status="analyzed",
    )


def test_map_exact_file_match(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["src/app.py"])

    entry = GitStatusEntry(
        path="src/app.py",
        index_status=" ",
        working_tree_status="M",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.is_git_repository is True
    assert nav.matched_count == 1
    assert nav.unmatched_count == 0
    assert len(nav.mappings) == 1

    mapping = nav.mappings[0]
    assert mapping.git_path == "src/app.py"
    assert mapping.project_path == "src/app.py"
    assert mapping.status == EntityMappingStatus.MATCHED
    assert mapping.matched_entity is not None
    assert mapping.matched_entity.entity_type == "file"
    assert mapping.matched_entity.name == "app.py"
    assert mapping.matched_entity.exists_in_source is True
    assert mapping.matched_entity.entity_id == project.files[0].id


def test_map_exact_directory_match(tmp_path: Path) -> None:
    project = _create_project_with_files(
        tmp_path,
        ["src/util.py"],
        dir_rel_paths=["src"],
    )

    entry = GitStatusEntry(
        path="src",
        index_status="?",
        working_tree_status="?",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.matched_count == 1
    mapping = nav.mappings[0]
    assert mapping.status == EntityMappingStatus.MATCHED
    assert mapping.matched_entity is not None
    assert mapping.matched_entity.entity_type == "directory"
    assert mapping.matched_entity.name == "src"
    assert mapping.matched_entity.exists_in_source is True


def test_map_untracked_absent_path(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["known.py"])

    entry = GitStatusEntry(
        path="untracked_new.py",
        index_status="?",
        working_tree_status="?",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.matched_count == 0
    assert nav.unmatched_count == 1
    mapping = nav.mappings[0]
    assert mapping.status == EntityMappingStatus.UNMATCHED
    assert mapping.matched_entity is None
    assert any("untracked" in lim.lower() for lim in mapping.limitations)


def test_map_deleted_path_matching_cached_entity(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["delete_me.py"])
    (tmp_path / "delete_me.py").unlink()

    entry = GitStatusEntry(
        path="delete_me.py",
        index_status=" ",
        working_tree_status="D",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.matched_count == 1
    mapping = nav.mappings[0]
    assert mapping.status == EntityMappingStatus.MATCHED
    assert mapping.matched_entity is not None
    assert mapping.matched_entity.exists_in_source is False
    assert any("deleted or absent" in lim.lower() for lim in mapping.limitations)


def test_map_deleted_path_absent_from_project(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["existing.py"])

    entry = GitStatusEntry(
        path="unknown_deleted.py",
        index_status=" ",
        working_tree_status="D",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.unmatched_count == 1
    mapping = nav.mappings[0]
    assert mapping.status == EntityMappingStatus.UNMATCHED


def test_map_rename_both_paths_matched(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["old_name.py", "new_name.py"])

    entry = GitStatusEntry(
        path="new_name.py",
        index_status="R",
        working_tree_status=" ",
        orig_path="old_name.py",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert len(nav.mappings) == 1
    mapping = nav.mappings[0]
    assert mapping.is_rename is True
    assert mapping.status == EntityMappingStatus.MATCHED
    assert mapping.matched_entity is not None
    assert mapping.matched_entity.name == "new_name.py"

    assert mapping.orig_git_path == "old_name.py"
    assert mapping.orig_status == EntityMappingStatus.MATCHED
    assert mapping.orig_matched_entity is not None
    assert mapping.orig_matched_entity.name == "old_name.py"


def test_map_rename_only_source_matched(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["old_name.py"])
    (tmp_path / "old_name.py").rename(tmp_path / "new_name.py")

    entry = GitStatusEntry(
        path="new_name.py",
        index_status="R",
        working_tree_status=" ",
        orig_path="old_name.py",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    mapping = nav.mappings[0]
    assert mapping.is_rename is True
    assert mapping.status == EntityMappingStatus.UNMATCHED
    assert mapping.matched_entity is None
    assert mapping.orig_status == EntityMappingStatus.MATCHED
    assert mapping.orig_matched_entity is not None
    assert mapping.orig_matched_entity.name == "old_name.py"


def test_map_rename_neither_matched(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["other.py"])

    entry = GitStatusEntry(
        path="unindexed_new.py",
        index_status="R",
        working_tree_status=" ",
        orig_path="unindexed_old.py",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    mapping = nav.mappings[0]
    assert mapping.is_rename is True
    assert mapping.status == EntityMappingStatus.UNMATCHED
    assert mapping.orig_status == EntityMappingStatus.UNMATCHED


def test_map_ambiguous_entity_match(tmp_path: Path) -> None:
    proj_id = uuid4()
    f1 = File(
        project_id=proj_id,
        id=uuid4(),
        path=Path("duplicate.py"),
        name="duplicate.py",
        extension="py",
    )
    f2 = File(
        project_id=proj_id,
        id=uuid4(),
        path=Path("duplicate.py"),
        name="duplicate.py",
        extension="py",
    )
    project = Project(
        id=proj_id,
        name="test",
        root_path=tmp_path,
        files=[f1, f2],
        analysis_status="analyzed",
    )

    entry = GitStatusEntry(
        path="duplicate.py",
        index_status=" ",
        working_tree_status="M",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.ambiguous_count == 1
    mapping = nav.mappings[0]
    assert mapping.status == EntityMappingStatus.AMBIGUOUS
    assert mapping.matched_entity is None
    assert len(mapping.candidate_entities) == 2
    assert any(d.code == "AMBIGUOUS_PATH_MATCH" for d in nav.diagnostics)


def test_reconcile_project_nested_under_git_root(tmp_path: Path) -> None:
    git_root = tmp_path
    project_root = tmp_path / "backend"
    project_root.mkdir()

    project = _create_project_with_files(project_root, ["api/handler.py"])

    entry_inside = GitStatusEntry(
        path="backend/api/handler.py",
        index_status=" ",
        working_tree_status="M",
    )
    entry_outside = GitStatusEntry(
        path="frontend/ui.js",
        index_status=" ",
        working_tree_status="M",
    )

    status_result = GitStatusResult(
        is_repository=True,
        root_path=git_root,
        branch="main",
        head_hash="abc",
        entries=(entry_inside, entry_outside),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.matched_count == 1
    assert nav.unmatched_count == 1

    mappings_by_git_path = {m.git_path: m for m in nav.mappings}

    m_inside = mappings_by_git_path["backend/api/handler.py"]
    assert m_inside.status == EntityMappingStatus.MATCHED
    assert m_inside.project_path == "api/handler.py"
    assert m_inside.matched_entity is not None
    assert m_inside.matched_entity.path == "api/handler.py"

    m_outside = mappings_by_git_path["frontend/ui.js"]
    assert m_outside.status == EntityMappingStatus.UNMATCHED
    assert m_outside.project_path is None
    assert any(
        "outside the project root" in lim.lower() for lim in m_outside.limitations
    )


def test_reconcile_incompatible_roots(tmp_path: Path) -> None:
    git_root = tmp_path / "repo1"
    git_root.mkdir()
    project_root = tmp_path / "repo2"
    project_root.mkdir()

    project = _create_project_with_files(project_root, ["file.py"])

    entry = GitStatusEntry(path="file.py", index_status=" ", working_tree_status="M")
    status_result = GitStatusResult(
        is_repository=True,
        root_path=git_root,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "ROOT_RECONCILIATION_FAILED" for d in nav.diagnostics)


def test_map_propagates_non_git_repository_outcome(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["file.py"])

    failed_status = GitRepository(tmp_path).get_status()

    nav = map_changed_paths(project, failed_status)

    assert nav.is_git_repository is False
    assert nav.outcome.status == OperationStatus.BLOCKED
    assert nav.mappings == ()


def test_project_query_navigate_git_clean(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "main.py").write_text("print('clean')\n")
    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "init")

    project = _create_project_with_files(tmp_path, ["main.py"])

    query = ProjectQuery(project)
    nav = query.navigate_git()

    assert nav.is_git_repository is True
    assert nav.is_clean is True
    assert nav.has_changes is False
    assert nav.mappings == ()
    assert nav.outcome.is_success is True


def test_project_query_navigate_git_with_changes(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "mod_a.py").write_text("a1\n")
    (tmp_path / "mod_b.py").write_text("b1\n")
    run_git(tmp_path, "add", "mod_a.py", "mod_b.py")
    run_git(tmp_path, "commit", "-m", "init")

    project = _create_project_with_files(tmp_path, ["mod_a.py", "mod_b.py"])

    (tmp_path / "mod_a.py").write_text("a2\n")
    (tmp_path / "new_untracked.py").write_text("new\n")

    query = ProjectQuery(project)
    nav = query.navigate_git()

    assert nav.is_clean is False
    assert nav.has_changes is True
    assert nav.matched_count == 1
    assert nav.unmatched_count == 1
    assert len(nav.mappings) == 2

    by_path = {m.git_path: m for m in nav.mappings}

    assert by_path["mod_a.py"].status == EntityMappingStatus.MATCHED
    assert by_path["mod_a.py"].matched_entity is not None
    assert by_path["mod_a.py"].matched_entity.name == "mod_a.py"

    assert by_path["new_untracked.py"].status == EntityMappingStatus.UNMATCHED
    assert by_path["new_untracked.py"].matched_entity is None


def test_project_query_navigate_git_missing_root_path() -> None:
    from unittest.mock import MagicMock

    mock_proj = MagicMock()
    mock_proj.root_path = None

    query = ProjectQuery(mock_proj)
    nav = query.navigate_git()

    assert nav.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "MISSING_ROOT_PATH" for d in nav.diagnostics)


def test_navigation_context_serialization_to_dict(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "x.py").write_text("x\n")
    project = _create_project_with_files(tmp_path, ["x.py"])

    query = ProjectQuery(project)
    nav = query.navigate_git()

    d = nav.to_dict()
    assert d["is_git_repository"] is True
    assert "counts" in d
    assert d["counts"]["total"] == len(nav.mappings)
    assert "mappings" in d
    assert "git_status" in d
    assert "outcome" in d


def test_normalize_relative_path_whitespace_preservation() -> None:
    assert normalize_relative_path(" leading_space.py") == " leading_space.py"
    assert normalize_relative_path("trailing_space.py ") == "trailing_space.py "
    assert normalize_relative_path(" dir/file.py") == " dir/file.py"
    assert normalize_relative_path("dir /file.py") == "dir /file.py"
    assert normalize_relative_path("./ leading_space.py") == " leading_space.py"
    assert normalize_relative_path(".\\trailing_space.py ") == "trailing_space.py "


def test_normalize_relative_path_dots_and_separators() -> None:
    assert normalize_relative_path("src\\pkg\\module.py") == "src/pkg/module.py"
    assert normalize_relative_path("./src/pkg/module.py") == "src/pkg/module.py"
    assert normalize_relative_path(".env") == ".env"
    assert normalize_relative_path(".gitignore") == ".gitignore"
    assert normalize_relative_path("./.env") == ".env"
    assert normalize_relative_path("..") == ".."
    assert normalize_relative_path("../outside.py") == "../outside.py"
    assert normalize_relative_path("src/pkg/") == "src/pkg"
    assert normalize_relative_path("/") == "/"


def test_normalize_relative_path_no_unjustified_collapse() -> None:
    p_plain = normalize_relative_path("file.py")
    p_lead = normalize_relative_path(" file.py")
    p_trail = normalize_relative_path("file.py ")

    assert p_plain == "file.py"
    assert p_lead == " file.py"
    assert p_trail == "file.py "
    assert p_plain != p_lead
    assert p_plain != p_trail
    assert p_lead != p_trail


def test_reconcile_git_path_to_project_absolute_and_escaping_paths(
    tmp_path: Path,
) -> None:
    git_root = tmp_path
    project_root = tmp_path

    p_abs, lim_abs = reconcile_git_path_to_project(
        "/etc/passwd", git_root, project_root
    )
    assert p_abs is None
    assert lim_abs is not None
    assert "absolute path or escapes" in lim_abs.lower()

    p_esc, lim_esc = reconcile_git_path_to_project(
        "../outside.py", git_root, project_root
    )
    assert p_esc is None
    assert lim_esc is not None
    assert "absolute path or escapes" in lim_esc.lower()

    p_parent, lim_parent = reconcile_git_path_to_project("..", git_root, project_root)
    assert p_parent is None
    assert lim_parent is not None


def test_reconcile_git_path_nested_traversal_rejection(tmp_path: Path) -> None:
    git_root = tmp_path
    project_root = tmp_path

    for bad_path in (
        "src/../../outside.py",
        "nested/dir/../../escape.py",
        "a/b/../c/../../d",
        "foo/..",
        "foo/bar/..",
        "src\\..\\..\\outside.py",
        "C:/Windows/System32",
    ):
        p, lim = reconcile_git_path_to_project(bad_path, git_root, project_root)
        assert p is None
        assert lim is not None
        assert "escapes" in lim.lower() or "absolute" in lim.lower()


def test_reconcile_git_path_legitimate_double_dot_filenames(tmp_path: Path) -> None:
    git_root = tmp_path
    project_root = tmp_path

    p1, lim1 = reconcile_git_path_to_project("..config.py", git_root, project_root)
    assert p1 == "..config.py"
    assert lim1 is None

    p2, lim2 = reconcile_git_path_to_project("src/..env", git_root, project_root)
    assert p2 == "src/..env"
    assert lim2 is None

    p3, lim3 = reconcile_git_path_to_project(
        "src/..data/file.txt", git_root, project_root
    )
    assert p3 == "src/..data/file.txt"
    assert lim3 is None


def test_map_git_deletion_with_file_existing_on_disk(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["staged_del.py"])
    assert (tmp_path / "staged_del.py").is_file()

    entry = GitStatusEntry(
        path="staged_del.py",
        index_status="D",
        working_tree_status=" ",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.matched_count == 1
    mapping = nav.mappings[0]
    assert mapping.status == EntityMappingStatus.MATCHED
    assert mapping.matched_entity is not None
    assert mapping.matched_entity.exists_in_source is True
    assert mapping.git_status_entry is not None
    assert mapping.git_status_entry.is_deleted is True
    assert mapping.git_status_entry.is_staged is True
    assert mapping.limitations == ()


def test_map_git_deletion_with_file_absent_on_disk(tmp_path: Path) -> None:
    project = _create_project_with_files(tmp_path, ["genuinely_gone.py"])
    (tmp_path / "genuinely_gone.py").unlink()
    assert not (tmp_path / "genuinely_gone.py").exists()

    entry = GitStatusEntry(
        path="genuinely_gone.py",
        index_status="D",
        working_tree_status=" ",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry,),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.matched_count == 1
    mapping = nav.mappings[0]
    assert mapping.status == EntityMappingStatus.MATCHED
    assert mapping.matched_entity is not None
    assert mapping.matched_entity.exists_in_source is False
    assert mapping.git_status_entry is not None
    assert mapping.git_status_entry.is_deleted is True
    assert any("deleted or absent" in lim.lower() for lim in mapping.limitations)


def test_map_changed_paths_with_filename_spaces(tmp_path: Path) -> None:
    project = _create_project_with_files(
        tmp_path,
        [" lead.py", "trail.py "],
    )

    entry_lead = GitStatusEntry(
        path=" lead.py",
        index_status=" ",
        working_tree_status="M",
    )
    entry_trail = GitStatusEntry(
        path="trail.py ",
        index_status=" ",
        working_tree_status="M",
    )
    status_result = GitStatusResult(
        is_repository=True,
        root_path=tmp_path,
        branch="main",
        head_hash="abc",
        entries=(entry_lead, entry_trail),
    )

    nav = map_changed_paths(project, status_result)

    assert nav.matched_count == 2
    assert nav.unmatched_count == 0

    by_path = {m.git_path: m for m in nav.mappings}
    assert by_path[" lead.py"].status == EntityMappingStatus.MATCHED
    assert by_path[" lead.py"].project_path == " lead.py"
    assert by_path["trail.py "].status == EntityMappingStatus.MATCHED
    assert by_path["trail.py "].project_path == "trail.py "
