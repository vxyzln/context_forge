from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from context_forge.reporting.contract import OperationOutcome


@dataclass(frozen=True)
class GitStatusEntry:
    path: str
    index_status: str
    working_tree_status: str
    orig_path: str | None = None

    @property
    def status_code(self) -> str:
        return f"{self.index_status}{self.working_tree_status}"

    @property
    def is_staged(self) -> bool:
        return self.index_status not in (" ", "?", "!")

    @property
    def is_unstaged(self) -> bool:
        return self.working_tree_status not in (" ", "?", "!")

    @property
    def is_untracked(self) -> bool:
        return self.index_status == "?" and self.working_tree_status == "?"

    @property
    def is_modified(self) -> bool:
        return "M" in (self.index_status, self.working_tree_status)

    @property
    def is_added(self) -> bool:
        return "A" in (self.index_status, self.working_tree_status)

    @property
    def is_deleted(self) -> bool:
        return "D" in (self.index_status, self.working_tree_status)

    @property
    def is_renamed(self) -> bool:
        return "R" in (self.index_status, self.working_tree_status)

    @property
    def is_copied(self) -> bool:
        return "C" in (self.index_status, self.working_tree_status)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": self.path,
            "status_code": self.status_code,
            "index_status": self.index_status,
            "working_tree_status": self.working_tree_status,
            "is_staged": self.is_staged,
            "is_unstaged": self.is_unstaged,
            "is_untracked": self.is_untracked,
            "is_modified": self.is_modified,
            "is_added": self.is_added,
            "is_deleted": self.is_deleted,
            "is_renamed": self.is_renamed,
            "is_copied": self.is_copied,
        }
        if self.orig_path is not None:
            result["orig_path"] = self.orig_path
        return result


@dataclass(frozen=True)
class GitStatusResult:
    is_repository: bool
    root_path: Path | None
    branch: str | None
    head_hash: str | None
    entries: tuple[GitStatusEntry, ...] = ()
    outcome: OperationOutcome = field(
        default_factory=lambda: OperationOutcome.success()
    )
    limitations: tuple[str, ...] = ()

    @property
    def has_changes(self) -> bool:
        return len(self.entries) > 0

    @property
    def is_clean(self) -> bool:
        return self.outcome.is_success and len(self.entries) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_repository": self.is_repository,
            "root_path": self.root_path.as_posix() if self.root_path else None,
            "branch": self.branch,
            "head_hash": self.head_hash,
            "has_changes": self.has_changes,
            "is_clean": self.is_clean,
            "entries": [e.to_dict() for e in self.entries],
            "limitations": list(self.limitations),
            "outcome": self.outcome.to_dict(),
        }


@dataclass(frozen=True)
class GitFileChange:
    path: str
    status: str
    additions: int
    deletions: int


@dataclass(frozen=True)
class GitCommit:
    hash: str
    message: str
    author: str
    timestamp: datetime
    parent_hashes: tuple[str, ...]
    changes: tuple[GitFileChange, ...] = ()


@dataclass(frozen=True)
class GitRepositoryInfo:
    root_path: str
    current_branch: str | None
    head_hash: str


@dataclass(frozen=True)
class GitActivitySummary:
    total_commits: int
    total_authors: int
    files_changed: int
    total_additions: int
    total_deletions: int
