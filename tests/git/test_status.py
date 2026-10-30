from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from context_forge.git import GitRepository
from context_forge.reporting.contract import DiagnosticSeverity, OperationStatus


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


def test_status_clean_repository_with_commits(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "hello.py").write_text("print('hello')\n")
    run_git(tmp_path, "add", "hello.py")
    run_git(tmp_path, "commit", "-m", "init")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert status.is_repository is True
    assert status.is_clean is True
    assert status.has_changes is False
    assert status.entries == ()
    assert status.outcome.status == OperationStatus.SUCCESS
    assert status.outcome.is_success is True


def test_status_clean_repository_no_commits(tmp_path: Path) -> None:
    configure_git(tmp_path)

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert status.is_repository is True
    assert status.is_clean is True
    assert status.has_changes is False
    assert status.entries == ()


def test_status_unstaged_modification(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "app.py").write_text("v1\n")
    run_git(tmp_path, "add", "app.py")
    run_git(tmp_path, "commit", "-m", "init")

    (tmp_path / "app.py").write_text("v2\n")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert status.is_clean is False
    assert status.has_changes is True
    assert len(status.entries) == 1

    entry = status.entries[0]
    assert entry.path == "app.py"
    assert entry.status_code == " M"
    assert entry.is_staged is False
    assert entry.is_unstaged is True
    assert entry.is_modified is True
    assert entry.is_deleted is False


def test_status_staged_modification(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "app.py").write_text("v1\n")
    run_git(tmp_path, "add", "app.py")
    run_git(tmp_path, "commit", "-m", "init")

    (tmp_path / "app.py").write_text("v2\n")
    run_git(tmp_path, "add", "app.py")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    entry = status.entries[0]
    assert entry.path == "app.py"
    assert entry.status_code == "M "
    assert entry.is_staged is True
    assert entry.is_unstaged is False
    assert entry.is_modified is True


def test_status_staged_addition(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "init.py").write_text("init\n")
    run_git(tmp_path, "add", "init.py")
    run_git(tmp_path, "commit", "-m", "init")

    (tmp_path / "new_file.py").write_text("new\n")
    run_git(tmp_path, "add", "new_file.py")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    entry = status.entries[0]
    assert entry.path == "new_file.py"
    assert entry.status_code == "A "
    assert entry.is_staged is True
    assert entry.is_added is True


def test_status_untracked_file(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "untracked.py").write_text("untracked\n")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    entry = status.entries[0]
    assert entry.path == "untracked.py"
    assert entry.status_code == "??"
    assert entry.is_untracked is True
    assert entry.is_staged is False
    assert entry.is_unstaged is False


def test_status_unstaged_deletion(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "del.py").write_text("delete me\n")
    run_git(tmp_path, "add", "del.py")
    run_git(tmp_path, "commit", "-m", "init")

    (tmp_path / "del.py").unlink()

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    entry = status.entries[0]
    assert entry.path == "del.py"
    assert entry.status_code == " D"
    assert entry.is_deleted is True
    assert entry.is_unstaged is True


def test_status_staged_deletion(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "del.py").write_text("delete me\n")
    run_git(tmp_path, "add", "del.py")
    run_git(tmp_path, "commit", "-m", "init")

    run_git(tmp_path, "rm", "del.py")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    entry = status.entries[0]
    assert entry.path == "del.py"
    assert entry.status_code == "D "
    assert entry.is_deleted is True
    assert entry.is_staged is True


def test_status_renamed_file_staged(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "old_name.py").write_text("content\n")
    run_git(tmp_path, "add", "old_name.py")
    run_git(tmp_path, "commit", "-m", "init")

    run_git(tmp_path, "mv", "old_name.py", "new_name.py")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    entry = status.entries[0]
    assert entry.path == "new_name.py"
    assert entry.orig_path == "old_name.py"
    assert entry.is_renamed is True
    assert entry.is_staged is True


def test_status_combined_changes(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "f_modified.py").write_text("one\n")
    (tmp_path / "f_deleted.py").write_text("del\n")
    run_git(tmp_path, "add", "f_modified.py", "f_deleted.py")
    run_git(tmp_path, "commit", "-m", "init")

    (tmp_path / "f_modified.py").write_text("two\n")
    (tmp_path / "f_deleted.py").unlink()
    (tmp_path / "f_added.py").write_text("added\n")
    run_git(tmp_path, "add", "f_added.py")
    (tmp_path / "untracked.py").write_text("untracked\n")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    paths = {e.path: e for e in status.entries}
    assert "f_modified.py" in paths
    assert paths["f_modified.py"].status_code == " M"

    assert "f_deleted.py" in paths
    assert paths["f_deleted.py"].status_code == " D"

    assert "f_added.py" in paths
    assert paths["f_added.py"].status_code == "A "

    assert "untracked.py" in paths
    assert paths["untracked.py"].status_code == "??"


def test_status_path_with_spaces(tmp_path: Path) -> None:
    configure_git(tmp_path)
    file_with_spaces = tmp_path / "my module with spaces.py"
    file_with_spaces.write_text("print('spaces')\n")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    assert status.entries[0].path == "my module with spaces.py"


def test_status_path_with_unicode(tmp_path: Path) -> None:
    configure_git(tmp_path)
    unicode_file = tmp_path / "документ_модель.py"
    unicode_file.write_text("print('unicode')\n", encoding="utf-8")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    assert status.entries[0].path == "документ_модель.py"


def test_status_nested_directory_paths(tmp_path: Path) -> None:
    configure_git(tmp_path)
    nested = tmp_path / "src" / "pkg" / "sub"
    nested.mkdir(parents=True)
    (nested / "module.py").write_text("x = 1\n")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    assert status.entries[0].path == "src/pkg/sub/module.py"


def test_status_rename_with_spaces(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "old file name.txt").write_text("content\n")
    run_git(tmp_path, "add", "old file name.txt")
    run_git(tmp_path, "commit", "-m", "init")

    run_git(tmp_path, "mv", "old file name.txt", "new file name.txt")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert len(status.entries) == 1
    entry = status.entries[0]
    assert entry.path == "new file name.txt"
    assert entry.orig_path == "old file name.txt"
    assert entry.is_renamed is True


def test_status_non_git_directory(tmp_path: Path) -> None:
    repo = GitRepository(tmp_path)
    status = repo.get_status()

    assert status.is_repository is False
    assert status.root_path is None
    assert status.entries == ()
    assert status.outcome.status == OperationStatus.BLOCKED
    assert any(d.code == "NOT_A_GIT_REPOSITORY" for d in status.outcome.diagnostics)


def test_status_git_command_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_git(tmp_path)
    repo = GitRepository(tmp_path)

    orig_run = repo._run_git
    failed_proc = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=128,
        stdout="",
        stderr="fatal: corrupted repository",
    )

    def mock_run(*args, **kwargs):
        if args and args[0] == "status":
            return failed_proc
        return orig_run(*args, **kwargs)

    monkeypatch.setattr(repo, "_run_git", mock_run)

    status = repo.get_status()

    assert status.outcome.status == OperationStatus.FAILED
    assert any(d.code == "GIT_COMMAND_FAILED" for d in status.outcome.diagnostics)
    assert any(
        d.severity == DiagnosticSeverity.ERROR for d in status.outcome.diagnostics
    )


def test_status_timeout_handling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_git(tmp_path)
    repo = GitRepository(tmp_path)

    orig_run = repo._run_git

    def mock_run(*args, **kwargs):
        if args and args[0] == "status":
            raise subprocess.TimeoutExpired(cmd=["git", "status"], timeout=1.0)
        return orig_run(*args, **kwargs)

    monkeypatch.setattr(repo, "_run_git", mock_run)

    status = repo.get_status(timeout_seconds=1.0)

    assert status.outcome.status == OperationStatus.FAILED
    assert any(d.code == "GIT_TIMEOUT" for d in status.outcome.diagnostics)


def test_status_malformed_porcelain_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_git(tmp_path)
    repo = GitRepository(tmp_path)

    orig_run = repo._run_git
    malformed_proc = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout="X\0",
        stderr="",
    )

    def mock_run(*args, **kwargs):
        if args and args[0] == "status":
            return malformed_proc
        return orig_run(*args, **kwargs)

    monkeypatch.setattr(repo, "_run_git", mock_run)

    status = repo.get_status()

    assert status.outcome.status == OperationStatus.FAILED
    assert any(d.code == "MALFORMED_GIT_STATUS" for d in status.outcome.diagnostics)


def test_status_deterministic_ordering(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "z_file.py").write_text("z\n")
    (tmp_path / "a_file.py").write_text("a\n")
    (tmp_path / "m_file.py").write_text("m\n")

    repo = GitRepository(tmp_path)
    status_1 = repo.get_status()
    status_2 = repo.get_status()

    paths_1 = [e.path for e in status_1.entries]
    paths_2 = [e.path for e in status_2.entries]

    assert paths_1 == ["a_file.py", "m_file.py", "z_file.py"]
    assert paths_1 == paths_2


def test_status_serialization_to_dict(tmp_path: Path) -> None:
    configure_git(tmp_path)
    (tmp_path / "app.py").write_text("code\n")

    repo = GitRepository(tmp_path)
    status = repo.get_status()

    data = status.to_dict()
    assert data["is_repository"] is True
    assert data["has_changes"] is True
    assert data["is_clean"] is False
    assert len(data["entries"]) == 1
    assert data["entries"][0]["path"] == "app.py"
    assert data["entries"][0]["status_code"] == "??"
    assert data["outcome"]["status"] == "success"


def test_parse_porcelain_rename_missing_original_path() -> None:
    with pytest.raises(ValueError, match="Missing original path"):
        GitRepository._parse_porcelain_z("R  new.py")


def test_parse_porcelain_rename_empty_original_path() -> None:
    with pytest.raises(ValueError, match="Missing original path"):
        GitRepository._parse_porcelain_z("R  new.py\0")

    with pytest.raises(ValueError, match="Missing original path"):
        GitRepository._parse_porcelain_z("R  new.py\0\0")


def test_parse_porcelain_copy_missing_and_empty_original_path() -> None:
    with pytest.raises(ValueError, match="Missing original path"):
        GitRepository._parse_porcelain_z("C  copied.py")

    with pytest.raises(ValueError, match="Missing original path"):
        GitRepository._parse_porcelain_z("C  copied.py\0")

    with pytest.raises(ValueError, match="Missing original path"):
        GitRepository._parse_porcelain_z("C  copied.py\0\0")


def test_parse_porcelain_valid_rename_and_copy() -> None:
    entries = GitRepository._parse_porcelain_z("R  new.py\0old.py\0")
    assert len(entries) == 1
    assert entries[0].path == "new.py"
    assert entries[0].orig_path == "old.py"
    assert entries[0].is_renamed is True

    copy_entries = GitRepository._parse_porcelain_z("C  dest.py\0src.py\0")
    assert len(copy_entries) == 1
    assert copy_entries[0].path == "dest.py"
    assert copy_entries[0].orig_path == "src.py"
    assert copy_entries[0].is_copied is True


def test_parse_porcelain_rename_with_spaces() -> None:
    entries = GitRepository._parse_porcelain_z("R  new file.py\0old file.py\0")
    assert len(entries) == 1
    assert entries[0].path == "new file.py"
    assert entries[0].orig_path == "old file.py"
    assert entries[0].is_renamed is True


def test_status_rename_empty_orig_path_produces_malformed_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_git(tmp_path)
    repo = GitRepository(tmp_path)

    orig_run = repo._run_git
    malformed_proc = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout="R  new.py\0",
        stderr="",
    )

    def mock_run(*args, **kwargs):
        if args and args[0] == "status":
            return malformed_proc
        return orig_run(*args, **kwargs)

    monkeypatch.setattr(repo, "_run_git", mock_run)

    status = repo.get_status()
    assert status.outcome.status == OperationStatus.FAILED
    assert any(d.code == "MALFORMED_GIT_STATUS" for d in status.outcome.diagnostics)
