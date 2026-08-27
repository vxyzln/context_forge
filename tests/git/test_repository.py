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


def test_repository_preserves_commit_parent_chain(
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

    file.write_text("three\n")
    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "third commit")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    assert len(commits) == 3

    assert commits[0].message == "third commit"
    assert commits[1].message == "second commit"
    assert commits[2].message == "first commit"

    assert commits[0].parent_hashes == (commits[1].hash,)
    assert commits[1].parent_hashes == (commits[2].hash,)
    assert commits[2].parent_hashes == ()


def test_repository_preserves_merge_commit_parents(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init", "-b", "main")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    file = tmp_path / "example.py"
    file.write_text("initial\n")
    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "initial commit")

    run_git(tmp_path, "checkout", "-b", "feature")

    feature_file = tmp_path / "feature.py"
    feature_file.write_text("feature\n")
    run_git(tmp_path, "add", "feature.py")
    run_git(tmp_path, "commit", "-m", "feature commit")

    run_git(tmp_path, "checkout", "main")

    main_file = tmp_path / "main.py"
    main_file.write_text("main\n")
    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "main commit")

    run_git(
        tmp_path,
        "merge",
        "--no-ff",
        "feature",
        "-m",
        "merge feature",
    )

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    merge_commit = commits[0]

    assert merge_commit.message == "merge feature"
    assert len(merge_commit.parent_hashes) == 2

    assert merge_commit.parent_hashes[0] == commits[1].hash
    assert merge_commit.parent_hashes[1] == commits[2].hash


def test_repository_history_is_deterministic(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    file = tmp_path / "example.py"

    for index in range(4):
        file.write_text(f"{index}\n")
        run_git(tmp_path, "add", "example.py")
        run_git(tmp_path, "commit", "-m", f"commit {index}")

    repository = GitRepository(tmp_path)

    first = repository.get_commits()
    second = repository.get_commits()

    assert first == second


def test_repository_reads_commit_file_changes(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    file = tmp_path / "example.py"

    file.write_text("one\n")
    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "initial commit")

    file.write_text("one\ntwo\nthree\n")
    run_git(tmp_path, "add", "example.py")
    run_git(tmp_path, "commit", "-m", "modify example")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    change = commits[0].changes[0]

    assert change.path == "example.py"
    assert change.status == "M"
    assert change.additions == 2
    assert change.deletions == 0


def test_repository_reads_added_and_deleted_files(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    added = tmp_path / "added.py"
    added.write_text("print('hello')\n")

    run_git(tmp_path, "add", "added.py")
    run_git(tmp_path, "commit", "-m", "add file")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    added_change = commits[0].changes[0]

    assert added_change.path == "added.py"
    assert added_change.status == "A"
    assert added_change.additions == 1
    assert added_change.deletions == 0

    run_git(tmp_path, "rm", "added.py")
    run_git(tmp_path, "commit", "-m", "delete file")

    commits = repository.get_commits()

    deleted_change = commits[0].changes[0]

    assert deleted_change.path == "added.py"
    assert deleted_change.status == "D"
    assert deleted_change.additions == 0
    assert deleted_change.deletions == 1


def test_repository_reads_multiple_file_changes(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    first = tmp_path / "first.py"
    second = tmp_path / "second.py"

    first.write_text("first\n")
    second.write_text("second\n")

    run_git(tmp_path, "add", "first.py", "second.py")
    run_git(tmp_path, "commit", "-m", "add multiple files")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    changes = commits[0].changes

    assert len(changes) == 2
    assert [change.path for change in changes] == [
        "first.py",
        "second.py",
    ]


def test_repository_handles_empty_history(tmp_path: Path) -> None:
    run_git(tmp_path, "init")

    repository = GitRepository(tmp_path)

    assert repository.is_repository()
    assert repository.get_commits() == []


def test_repository_info_is_none_before_first_commit(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")

    repository = GitRepository(tmp_path)

    assert repository.get_info() is None


def configure_git_identity(path: Path) -> None:
    run_git(path, "config", "user.name", "Context Forge Test")
    run_git(path, "config", "user.email", "test@example.com")


def test_repository_handles_shallow_history(tmp_path: Path) -> None:
    source = tmp_path / "source"
    shallow = tmp_path / "shallow"

    source.mkdir()
    run_git(source, "init")
    configure_git_identity(source)

    file = source / "example.py"

    for index in range(3):
        file.write_text(f"{index}\n")
        run_git(source, "add", "example.py")
        run_git(source, "commit", "-m", f"commit {index}")

    run_git(
        tmp_path,
        "clone",
        "--depth",
        "1",
        f"file://{source}",
        str(shallow),
    )

    repository = GitRepository(shallow)

    commits = repository.get_commits()

    assert len(commits) == 1
    assert commits[0].message == "commit 2"
    assert commits[0].parent_hashes == ()


def test_repository_reads_renamed_files(tmp_path: Path) -> None:
    run_git(tmp_path, "init")
    configure_git_identity(tmp_path)

    original = tmp_path / "old.py"
    original.write_text("print('hello')\n")

    run_git(tmp_path, "add", "old.py")
    run_git(tmp_path, "commit", "-m", "add old file")

    run_git(tmp_path, "mv", "old.py", "new.py")
    run_git(tmp_path, "commit", "-m", "rename file")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    change = commits[0].changes[0]

    assert change.status == "R"
    assert change.path == "new.py"


def test_repository_handles_binary_file_changes(tmp_path: Path) -> None:
    run_git(tmp_path, "init")
    configure_git_identity(tmp_path)

    binary_file = tmp_path / "image.bin"
    binary_file.write_bytes(b"\x00\x01\x02\x03")

    run_git(tmp_path, "add", "image.bin")
    run_git(tmp_path, "commit", "-m", "add binary file")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    change = commits[0].changes[0]

    assert change.path == "image.bin"
    assert change.status == "A"
    assert change.additions == 0
    assert change.deletions == 0


def test_repository_handles_binary_file_modification(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    configure_git_identity(tmp_path)

    binary_file = tmp_path / "image.bin"
    binary_file.write_bytes(b"\x00\x01\x02")

    run_git(tmp_path, "add", "image.bin")
    run_git(tmp_path, "commit", "-m", "add binary file")

    binary_file.write_bytes(b"\x00\x01\x02\x03\x04")

    run_git(tmp_path, "add", "image.bin")
    run_git(tmp_path, "commit", "-m", "modify binary file")

    repository = GitRepository(tmp_path)

    commits = repository.get_commits()

    change = commits[0].changes[0]

    assert change.path == "image.bin"
    assert change.status == "M"
    assert change.additions == 0
    assert change.deletions == 0


def test_repository_rejects_malformed_commit_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = GitRepository(tmp_path)

    malformed = subprocess.CompletedProcess(
        args=["git", "log"],
        returncode=0,
        stdout="malformed\x1fcommit\x1e",
        stderr="",
    )

    monkeypatch.setattr(
        repository,
        "_run_git",
        lambda *args, **kwargs: malformed,
    )

    with pytest.raises(RuntimeError, match="Unexpected Git commit format"):
        repository.get_commits()


def test_repository_handles_git_command_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = GitRepository(tmp_path)

    failure = subprocess.CompletedProcess(
        args=["git", "rev-parse"],
        returncode=128,
        stdout="",
        stderr="fatal: not a git repository",
    )

    monkeypatch.setattr(
        repository,
        "_run_git",
        lambda *args, **kwargs: failure,
    )

    assert not repository.is_repository()
    assert repository.get_root() is None
    assert repository.get_info() is None


def test_parse_numstat_handles_malformed_counts() -> None:
    output = "not-a-number\talso-not-a-number\tbroken.py\n5\t2\tvalid.py\n"

    statistics = GitRepository._parse_numstat(output)

    assert statistics == {
        "broken.py": (0, 0),
        "valid.py": (5, 2),
    }


def test_parse_name_status_ignores_malformed_lines() -> None:
    output = "\nM\tvalid.py\nmalformed\nA\tanother.py\n"

    changes = GitRepository._parse_name_status(output)

    assert changes == [
        ("valid.py", "M"),
        ("another.py", "A"),
    ]


def test_repository_propagates_unexpected_git_failure(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")

    repository = GitRepository(tmp_path)

    with pytest.raises(subprocess.CalledProcessError):
        repository._run_git(
            "command-that-does-not-exist",
        )


def test_repository_info_is_none_without_commits(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")

    repository = GitRepository(tmp_path)

    assert repository.get_info() is None
