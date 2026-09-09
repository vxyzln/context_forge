from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import UUID

CACHE_SCHEMA_VERSION = 1
ANALYZER_VERSION = "0.1.0"


@dataclass(frozen=True)
class RepositoryIdentity:
    root_path: Path

    @property
    def key(self) -> str:
        return str(self.root_path.resolve())


@dataclass(frozen=True)
class RepositoryCacheMetadata:
    repository_key: str
    project_id: UUID
    cache_schema_version: int = CACHE_SCHEMA_VERSION
    analyzer_version: str = ANALYZER_VERSION


@dataclass(frozen=True)
class FileFingerprint:
    path: Path
    size: int
    modified_at_ns: int
    content_hash: str


@dataclass(frozen=True)
class FileChangeSet:
    unchanged: frozenset[Path]
    modified: frozenset[Path]
    added: frozenset[Path]
    deleted: frozenset[Path]

    @property
    def changed(self) -> frozenset[Path]:
        return self.modified | self.added | self.deleted

    @property
    def is_unchanged(self) -> bool:
        return not self.changed


@dataclass(frozen=True)
class CacheFreshness:
    is_fresh: bool
    reason: str
    changes: FileChangeSet | None = None


def validate_cache_freshness(
    metadata: RepositoryCacheMetadata | None,
    current_schema_version: int,
    current_analyzer_version: str,
    cached_fingerprints: dict[Path, FileFingerprint] | None,
    current_fingerprints: dict[Path, FileFingerprint] | None,
) -> CacheFreshness:
    if metadata is None:
        return CacheFreshness(
            is_fresh=False,
            reason="missing_metadata",
        )

    if metadata.cache_schema_version != current_schema_version:
        return CacheFreshness(
            is_fresh=False,
            reason="schema_version_mismatch",
        )

    if metadata.analyzer_version != current_analyzer_version:
        return CacheFreshness(
            is_fresh=False,
            reason="analyzer_version_mismatch",
        )

    if cached_fingerprints is None:
        return CacheFreshness(
            is_fresh=False,
            reason="missing_fingerprints",
        )

    if current_fingerprints is None:
        return CacheFreshness(
            is_fresh=False,
            reason="missing_current_fingerprints",
        )

    changes = detect_file_changes(
        cached_fingerprints,
        current_fingerprints,
    )

    if not changes.is_unchanged:
        return CacheFreshness(
            is_fresh=False,
            reason="files_changed",
            changes=changes,
        )

    return CacheFreshness(
        is_fresh=True,
        reason="fresh",
        changes=changes,
    )


def fingerprint_file(root_path: Path, file_path: Path) -> FileFingerprint:
    root_path = root_path.resolve()
    absolute_path = (
        file_path if file_path.is_absolute() else root_path / file_path
    ).resolve()

    relative_path = absolute_path.relative_to(root_path)
    stat = absolute_path.stat()

    digest = sha256()

    with absolute_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return FileFingerprint(
        path=relative_path,
        size=stat.st_size,
        modified_at_ns=stat.st_mtime_ns,
        content_hash=digest.hexdigest(),
    )


def detect_file_changes(
    cached: dict[Path, FileFingerprint],
    current: dict[Path, FileFingerprint],
) -> FileChangeSet:
    cached_paths = set(cached)
    current_paths = set(current)

    unchanged: set[Path] = set()
    modified: set[Path] = set()

    for path in cached_paths & current_paths:
        cached_fingerprint = cached[path]
        current_fingerprint = current[path]

        if cached_fingerprint.content_hash == current_fingerprint.content_hash:
            unchanged.add(path)
        else:
            modified.add(path)

    return FileChangeSet(
        unchanged=frozenset(unchanged),
        modified=frozenset(modified),
        added=frozenset(current_paths - cached_paths),
        deleted=frozenset(cached_paths - current_paths),
    )
