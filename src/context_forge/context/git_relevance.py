from collections import Counter
from pathlib import Path

from context_forge.git.models import GitCommit
from context_forge.models.file import File


class GitRelevance:
    """Calculate deterministic Git-history relevance for project files."""

    def __init__(self, commits: list[GitCommit]) -> None:
        self._change_counts = self._build_change_counts(commits)

    @staticmethod
    def _build_change_counts(
        commits: list[GitCommit],
    ) -> dict[str, int]:
        counts: Counter[str] = Counter()

        for commit in commits:
            for change in commit.changes:
                path = Path(change.path).as_posix()
                counts[path] += 1

        return dict(counts)

    def score(self, file: File) -> float:
        count = self._change_counts.get(file.path.as_posix(), 0)

        if count == 0:
            return 0.0

        return min(1.0, count / 10.0)
