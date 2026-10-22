import subprocess
from datetime import UTC, datetime
from pathlib import Path

from context_forge.git.models import (
    GitCommit,
    GitFileChange,
    GitRepositoryInfo,
    GitStatusEntry,
    GitStatusResult,
)
from context_forge.reporting.contract import DiagnosticItem, OperationOutcome


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

        result = self._run_git(
            *arguments,
            check=False,
        )

        if result.returncode != 0:
            if "does not have any commits yet" in result.stderr:
                return []

            raise subprocess.CalledProcessError(
                result.returncode,
                result.args,
                output=result.stdout,
                stderr=result.stderr,
            )

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
            "-M",
            commit_hash,
        )

        numstat_result = self._run_git(
            "diff-tree",
            "--no-commit-id",
            "--root",
            "--numstat",
            "-r",
            "-M",
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

    def get_status(
        self,
        *,
        untracked_mode: str = "all",
        timeout_seconds: float = 15.0,
    ) -> GitStatusResult:
        root = self.get_root()
        if root is None or not self.is_repository():
            diag = DiagnosticItem.blocker(
                f"Directory is not a Git repository: {self.root_path}",
                code="NOT_A_GIT_REPOSITORY",
                source="git",
                path=str(self.root_path),
            )
            return GitStatusResult(
                is_repository=False,
                root_path=None,
                branch=None,
                head_hash=None,
                entries=(),
                limitations=(f"Directory is not a Git repository: {self.root_path}",),
                outcome=OperationOutcome.blocked(
                    "Not a Git repository",
                    diagnostics=(diag,),
                    limitations=(
                        f"Directory is not a Git repository: {self.root_path}",
                    ),
                ),
            )

        info = self.get_info()
        branch = info.current_branch if info else None
        head_hash = info.head_hash if info else None

        try:
            result = self._run_git(
                "status",
                "--porcelain=v1",
                "-z",
                f"--untracked-files={untracked_mode}",
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            diag = DiagnosticItem.error(
                f"Git status command timed out after {timeout_seconds}s",
                code="GIT_TIMEOUT",
                source="git",
                path=str(self.root_path),
            )
            return GitStatusResult(
                is_repository=True,
                root_path=root,
                branch=branch,
                head_hash=head_hash,
                entries=(),
                limitations=("Git status operation timed out.",),
                outcome=OperationOutcome.failed(
                    f"Git status timed out after {timeout_seconds}s",
                    diagnostics=(diag,),
                    limitations=("Git status operation timed out.",),
                ),
            )
        except (FileNotFoundError, PermissionError) as exc:
            diag = DiagnosticItem.error(
                f"Failed to invoke Git executable: {exc}",
                code="GIT_INVOCATION_FAILED",
                source="git",
                path=str(self.root_path),
            )
            return GitStatusResult(
                is_repository=True,
                root_path=root,
                branch=branch,
                head_hash=head_hash,
                entries=(),
                limitations=(f"Git executable cannot be invoked: {exc}",),
                outcome=OperationOutcome.failed(
                    f"Failed to invoke Git executable: {exc}",
                    diagnostics=(diag,),
                    limitations=(f"Git executable cannot be invoked: {exc}",),
                ),
            )

        if result.returncode != 0:
            stderr_msg = (
                result.stderr.strip()
                or f"Git status exited with code {result.returncode}"
            )
            diag = DiagnosticItem.error(
                stderr_msg,
                code="GIT_COMMAND_FAILED",
                source="git",
                path=str(self.root_path),
                details={
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                },
            )
            return GitStatusResult(
                is_repository=True,
                root_path=root,
                branch=branch,
                head_hash=head_hash,
                entries=(),
                limitations=(f"Git status command failed: {stderr_msg}",),
                outcome=OperationOutcome.failed(
                    stderr_msg,
                    diagnostics=(diag,),
                    limitations=(f"Git status command failed: {stderr_msg}",),
                ),
            )

        try:
            entries = self._parse_porcelain_z(result.stdout)
        except ValueError as exc:
            diag = DiagnosticItem.error(
                f"Failed to parse Git status output: {exc}",
                code="MALFORMED_GIT_STATUS",
                source="git",
                path=str(self.root_path),
            )
            return GitStatusResult(
                is_repository=True,
                root_path=root,
                branch=branch,
                head_hash=head_hash,
                entries=(),
                limitations=(f"Git status output could not be parsed: {exc}",),
                outcome=OperationOutcome.failed(
                    f"Failed to parse Git status output: {exc}",
                    diagnostics=(diag,),
                    limitations=(f"Git status output could not be parsed: {exc}",),
                ),
            )

        sorted_entries = tuple(
            sorted(
                entries,
                key=lambda e: (e.path, e.status_code, e.orig_path or ""),
            )
        )
        msg = (
            f"Discovered {len(sorted_entries)} changed path(s)"
            if sorted_entries
            else "Working tree is clean"
        )
        return GitStatusResult(
            is_repository=True,
            root_path=root,
            branch=branch,
            head_hash=head_hash,
            entries=sorted_entries,
            outcome=OperationOutcome.success(msg),
        )

    @staticmethod
    def _parse_porcelain_z(output: str) -> list[GitStatusEntry]:
        if not output:
            return []

        # Git porcelain -z uses NUL bytes as record delimiters.
        tokens = output.split("\0")
        entries: list[GitStatusEntry] = []
        i = 0
        total_tokens = len(tokens)

        while i < total_tokens:
            token = tokens[i]
            if not token and i == total_tokens - 1:
                break
            if not token:
                i += 1
                continue

            if len(token) <= 3 or token[2] != " ":
                raise ValueError(f"Malformed Git status record: {token!r}")

            index_status = token[0]
            working_tree_status = token[1]
            path = token[3:]
            orig_path: str | None = None

            if "R" in (index_status, working_tree_status) or "C" in (
                index_status,
                working_tree_status,
            ):
                i += 1
                if i < total_tokens and tokens[i]:
                    orig_path = tokens[i]
                else:
                    raise ValueError(
                        f"Missing original path for rename/copy record: {token!r}"
                    )

            entries.append(
                GitStatusEntry(
                    path=path,
                    index_status=index_status,
                    working_tree_status=working_tree_status,
                    orig_path=orig_path,
                )
            )
            i += 1

        return entries

    def _run_git(
        self,
        *arguments: str,
        check: bool = True,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.root_path,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
        )
