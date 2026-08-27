import subprocess
from pathlib import Path

import pytest

from context_forge.git import GitRepository


def run_git(path: Path, *arguments: str) -> None:

    subprocess.run(
        ["git", *arguments],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_repository_detects_git_work_tree(tmp_path: Path) -> None:
    run_git(tmp_path, "init")

    repository = GitRepository(tmp_path)

    assert repository.is_repository()


def test_repository_returns_none_for_non_git_directory(
    tmp_path: Path,
) -> None:
    repository = GitRepository(tmp_path)

    assert not repository.is_repository()
    assert repository.get_root() is None
    assert repository.get_info() is None


def test_repository_gets_root(tmp_path: Path) -> None:
    run_git(tmp_path, "init")

    repository = GitRepository(tmp_path)

    root = repository.get_root()

    assert root == tmp_path.resolve()


def test_repository_gets_current_branch_and_head(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    (tmp_path / "example.py").write_text("print('hello')\n")

    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "initial commit")

    repository = GitRepository(tmp_path)

    info = repository.get_info()

    assert info is not None
    assert info.root_path == str(tmp_path.resolve())
    assert info.current_branch in {"main", "master"}
    assert len(info.head_hash) == 40


def test_repository_reads_commit_metadata(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    (tmp_path / "example.py").write_text("print('hello')\n")

    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "initial commit")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    assert len(commits) == 1
    assert len(commits[0].hash) == 40
    assert commits[0].author == "Context Forge Test"
    assert commits[0].message == "initial commit"
    assert commits[0].parent_hashes == ()


def test_repository_reads_multiple_commits_in_order(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    file = tmp_path / "example.py"

    file.write_text("one\n")
    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "first commit")

    file.write_text("two\n")
    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "second commit")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    assert [commit.message for commit in commits] == [
        "second commit",
        "first commit",
    ]

    assert len(commits[0].parent_hashes) == 1


def test_repository_respects_commit_limit(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    file = tmp_path / "example.py"

    for index in range(3):
        file.write_text(f"{index}\n")
        run_git(tmp_path, "add", "example.py")
        run_git(tmp_path, "commit", "-m", f"commit {index}")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits(limit=2)

    assert len(commits) == 2
    assert [commit.message for commit in commits] == [
        "commit 2",
        "commit 1",
    ]


def test_repository_rejects_invalid_commit_limit(
    tmp_path: Path,
) -> None:
    repository = GitRepository(tmp_path)

    with pytest.raises(ValueError, match="greater than zero"):
        repository.get_commits(limit=0)


def test_repository_requires_absolute_path() -> None:
    with pytest.raises(
        ValueError,
        match="must be absolute",
    ):
        GitRepository(Path("relative/path"))
