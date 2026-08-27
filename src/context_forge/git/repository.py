import subprocess
from datetime import UTC, datetime
from pathlib import Path

from context_forge.git.models import GitCommit, GitFileChange, GitRepositoryInfo


class GitRepository:
    def __init__(self, root_path: Path) -> None:
        if not root_path.is_absolute():
            raise ValueError("Git repository root path must be absolute")

        self.root_path = root_path

    def is_repository(self) -> bool:
        result = self._run_git(
            "rev-parse",
            "--is-inside-work-tree",
            check=False,
        )

        return result.returncode == 0 and result.stdout.strip() == "true"

    def get_root(self) -> Path | None:
        result = self._run_git(
            "rev-parse",
            "--show-toplevel",
            check=False,
        )

        if result.returncode != 0:
            return None

        root = result.stdout.strip()

        if not root:
            return None

        return Path(root).resolve()

    def get_info(self) -> GitRepositoryInfo | None:
        root = self.get_root()

        if root is None:
            return None

        head_result = self._run_git(
            "rev-parse",
            "HEAD",
            check=False,
        )

        if head_result.returncode != 0:
            return None

        head_hash = head_result.stdout.strip()

        if not head_hash:
            return None

        branch_result = self._run_git(
            "branch",
            "--show-current",
            check=False,
        )

        branch = branch_result.stdout.strip()
        current_branch = branch if branch else None

        return GitRepositoryInfo(
            root_path=str(root),
            current_branch=current_branch,
            head_hash=head_hash,
        )

    def get_commits(self, limit: int | None = None) -> list[GitCommit]:
        if limit is not None and limit < 1:
            raise ValueError("Commit limit must be greater than zero")

        format_string = "%H%x1f%an%x1f%aI%x1f%P%x1f%s%x1e"

        arguments = [
            "log",
            f"--format={format_string}",
        ]

        if limit is not None:
            arguments.append(f"-n{limit}")

        result = self._run_git(*arguments)

        commits: list[GitCommit] = []

        for record in result.stdout.split("\x1e"):
            record = record.strip()

            if not record:
                continue

            fields = record.split("\x1f")

            if len(fields) != 5:
                raise RuntimeError("Unexpected Git commit format")

            commit_hash, author, timestamp, parents, message = fields

            changes = self.get_commit_changes(commit_hash)

            commits.append(
                GitCommit(
                    hash=commit_hash,
                    message=message,
                    author=author,
                    timestamp=datetime.fromisoformat(timestamp).astimezone(UTC),
                    parent_hashes=tuple(parent for parent in parents.split() if parent),
                    changes=tuple(changes),
                )
            )

        return commits

    def get_commit_changes(self, commit_hash: str) -> list[GitFileChange]:
        status_result = self._run_git(
            "diff-tree",
            "--no-commit-id",
            "--root",
            "--name-status",
            "-r",
            commit_hash,
        )

        numstat_result = self._run_git(
            "diff-tree",
            "--no-commit-id",
            "--root",
            "--numstat",
            "-r",
            commit_hash,
        )

        statuses = self._parse_name_status(status_result.stdout)
        statistics = self._parse_numstat(numstat_result.stdout)

        changes: list[GitFileChange] = []

        for path, status in statuses:
            additions, deletions = statistics.get(path, (0, 0))

            changes.append(
                GitFileChange(
                    path=path,
                    status=status,
                    additions=additions,
                    deletions=deletions,
                )
            )

        return changes

    @staticmethod
    def _parse_name_status(output: str) -> list[tuple[str, str]]:
        changes: list[tuple[str, str]] = []

        for line in output.splitlines():
            if not line.strip():
                continue

            parts = line.split("\t")

            if len(parts) < 2:
                continue

            status = parts[0][0]
            path = parts[-1]

            changes.append((path, status))

        return changes

    @staticmethod
    def _parse_numstat(output: str) -> dict[str, tuple[int, int]]:
        statistics: dict[str, tuple[int, int]] = {}

        for line in output.splitlines():
            if not line.strip():
                continue

            parts = line.split("\t")

            if len(parts) < 3:
                continue

            additions = GitRepository._parse_line_count(parts[0])
            deletions = GitRepository._parse_line_count(parts[1])
            path = parts[-1]

            statistics[path] = (additions, deletions)

        return statistics

    @staticmethod
    def _parse_line_count(value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0

    def _run_git(
        self,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root_path,
            capture_output=True,
            text=True,
            check=check,
        )
