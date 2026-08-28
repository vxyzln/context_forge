from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from context_forge.context.git_relevance import GitRelevance
from context_forge.git.models import GitCommit, GitFileChange
from context_forge.models.file import File


def make_file(path: str) -> File:
    return File(
        project_id=uuid4(),
        path=Path(path),
        name=Path(path).name,
        extension=Path(path).suffix,
    )


def make_commit(path: str) -> GitCommit:
    return GitCommit(
        hash=uuid4().hex,
        message="change file",
        author="Context Forge Test",
        timestamp=datetime.now(UTC),
        parent_hashes=(),
        changes=(
            GitFileChange(
                path=path,
                status="M",
                additions=1,
                deletions=0,
            ),
        ),
    )


def test_git_relevance_is_zero_for_unmodified_file() -> None:
    relevance = GitRelevance([make_commit("src/main.py")])

    file = make_file("src/other.py")

    assert relevance.score(file) == 0.0


def test_git_relevance_increases_with_change_frequency() -> None:
    commits = [
        make_commit("src/main.py"),
        make_commit("src/main.py"),
        make_commit("src/main.py"),
    ]

    relevance = GitRelevance(commits)

    file = make_file("src/main.py")

    assert relevance.score(file) == 0.3


def test_git_relevance_is_capped_at_one() -> None:
    commits = [make_commit("src/main.py") for _ in range(20)]

    relevance = GitRelevance(commits)

    file = make_file("src/main.py")

    assert relevance.score(file) == 1.0


def test_git_relevance_is_deterministic() -> None:
    commits = [
        make_commit("src/main.py"),
        make_commit("src/main.py"),
    ]

    first = GitRelevance(commits).score(
        make_file("src/main.py"),
    )
    second = GitRelevance(commits).score(
        make_file("src/main.py"),
    )

    assert first == second
