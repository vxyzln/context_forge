from dataclasses import dataclass
from datetime import datetime


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
