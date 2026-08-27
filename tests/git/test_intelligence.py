import subprocess
from datetime import UTC, datetime
from pathlib import Path

from context_forge.git import GitActivitySummary, summarize_commits
from context_forge.git.models import GitCommit, GitFileChange

TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def run_git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def make_commit(
    author: str,
    changes: tuple[GitFileChange, ...] = (),
) -> GitCommit:
    return GitCommit(
        hash="a" * 40,
        message="test commit",
        author=author,
        timestamp=TIMESTAMP,
        parent_hashes=(),
        changes=changes,
    )


def test_summarize_empty_history() -> None:
    summary = summarize_commits([])

    assert summary == GitActivitySummary(
        total_commits=0,
        total_authors=0,
        files_changed=0,
        total_additions=0,
        total_deletions=0,
    )


def test_summarize_single_commit() -> None:
    commits = [
        make_commit(
            "Alice",
            (
                GitFileChange(
                    path="src/main.py",
                    status="M",
                    additions=10,
                    deletions=2,
                ),
            ),
        ),
    ]

    summary = summarize_commits(commits)

    assert summary.total_commits == 1
    assert summary.total_authors == 1
    assert summary.files_changed == 1
    assert summary.total_additions == 10
    assert summary.total_deletions == 2


def test_summarize_counts_repeated_file_once() -> None:
    commits = [
        make_commit(
            "Alice",
            (
                GitFileChange(
                    path="src/main.py",
                    status="M",
                    additions=10,
                    deletions=2,
                ),
            ),
        ),
        make_commit(
            "Alice",
            (
                GitFileChange(
                    path="src/main.py",
                    status="M",
                    additions=3,
                    deletions=1,
                ),
            ),
        ),
    ]

    summary = summarize_commits(commits)

    assert summary.files_changed == 1
    assert summary.total_additions == 13
    assert summary.total_deletions == 3


def test_summarize_counts_unique_authors() -> None:
    commits = [
        make_commit("Alice"),
        make_commit("Bob"),
        make_commit("Alice"),
    ]

    summary = summarize_commits(commits)

    assert summary.total_commits == 3
    assert summary.total_authors == 2


def test_summarize_counts_multiple_files() -> None:
    commits = [
        make_commit(
            "Alice",
            (
                GitFileChange(
                    path="src/a.py",
                    status="A",
                    additions=5,
                    deletions=0,
                ),
                GitFileChange(
                    path="src/b.py",
                    status="A",
                    additions=8,
                    deletions=0,
                ),
                GitFileChange(
                    path="README.md",
                    status="A",
                    additions=3,
                    deletions=0,
                ),
            ),
        ),
    ]

    summary = summarize_commits(commits)

    assert summary.files_changed == 3


def test_summarize_totals_additions_and_deletions() -> None:
    commits = [
        make_commit(
            "Alice",
            (
                GitFileChange(
                    path="src/a.py",
                    status="M",
                    additions=10,
                    deletions=4,
                ),
                GitFileChange(
                    path="src/b.py",
                    status="M",
                    additions=6,
                    deletions=2,
                ),
            ),
        ),
        make_commit(
            "Bob",
            (
                GitFileChange(
                    path="src/c.py",
                    status="A",
                    additions=9,
                    deletions=0,
                ),
            ),
        ),
    ]

    summary = summarize_commits(commits)

    assert summary.total_additions == 25
    assert summary.total_deletions == 6


def test_summarize_result_is_deterministic() -> None:
    commits = [
        make_commit(
            "Alice",
            (
                GitFileChange(
                    path="src/main.py",
                    status="M",
                    additions=10,
                    deletions=2,
                ),
            ),
        ),
        make_commit(
            "Bob",
            (
                GitFileChange(
                    path="README.md",
                    status="M",
                    additions=2,
                    deletions=1,
                ),
            ),
        ),
    ]

    first = summarize_commits(commits)
    second = summarize_commits(commits)

    assert first == second


def test_summarize_empty_history_is_safe() -> None:
    summary = summarize_commits(())

    assert summary.total_commits == 0
    assert summary.total_authors == 0
    assert summary.files_changed == 0
    assert summary.total_additions == 0
    assert summary.total_deletions == 0
