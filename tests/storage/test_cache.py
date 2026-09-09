from pathlib import Path
from uuid import UUID

from context_forge.storage.cache import (
    ANALYZER_VERSION,
    CACHE_SCHEMA_VERSION,
    CacheFreshness,
    CacheInvalidation,
    FileChangeSet,
    FileFingerprint,
    RepositoryCacheMetadata,
    detect_file_changes,
    determine_cache_invalidation,
    fingerprint_file,
    validate_cache_freshness,
)


def make_fingerprint(
    path: str,
    content_hash: str,
    size: int = 10,
) -> FileFingerprint:
    return FileFingerprint(
        path=Path(path),
        size=size,
        modified_at_ns=1,
        content_hash=content_hash,
    )


def test_fingerprint_file_uses_repository_relative_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "main.py"
    source.parent.mkdir()
    source.write_text("print('hello')", encoding="utf-8")

    fingerprint = fingerprint_file(tmp_path, source)

    assert fingerprint.path == Path("src/main.py")
    assert fingerprint.size == source.stat().st_size
    assert fingerprint.modified_at_ns == source.stat().st_mtime_ns
    assert len(fingerprint.content_hash) == 64


def test_fingerprint_changes_when_content_changes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text("hello", encoding="utf-8")

    first = fingerprint_file(tmp_path, source)

    source.write_text("world", encoding="utf-8")

    second = fingerprint_file(tmp_path, source)

    assert first.content_hash != second.content_hash


def test_fingerprint_is_deterministic_for_unchanged_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text("print('hello')", encoding="utf-8")

    first = fingerprint_file(tmp_path, source)
    second = fingerprint_file(tmp_path, source)

    assert first == second


def test_change_detection_identifies_unchanged_files() -> None:
    cached = {
        Path("main.py"): make_fingerprint(
            "main.py",
            "same",
        )
    }
    current = {
        Path("main.py"): make_fingerprint(
            "main.py",
            "same",
        )
    }

    changes = detect_file_changes(cached, current)

    assert changes.unchanged == frozenset({Path("main.py")})
    assert changes.modified == frozenset()
    assert changes.added == frozenset()
    assert changes.deleted == frozenset()
    assert changes.is_unchanged


def test_change_detection_identifies_modified_files() -> None:
    cached = {
        Path("main.py"): make_fingerprint(
            "main.py",
            "old",
        )
    }
    current = {
        Path("main.py"): make_fingerprint(
            "main.py",
            "new",
        )
    }

    changes = detect_file_changes(cached, current)

    assert changes.unchanged == frozenset()
    assert changes.modified == frozenset({Path("main.py")})
    assert changes.added == frozenset()
    assert changes.deleted == frozenset()
    assert changes.changed == frozenset({Path("main.py")})


def test_change_detection_identifies_added_files() -> None:
    cached = {}
    current = {
        Path("main.py"): make_fingerprint(
            "main.py",
            "new",
        )
    }

    changes = detect_file_changes(cached, current)

    assert changes.unchanged == frozenset()
    assert changes.modified == frozenset()
    assert changes.added == frozenset({Path("main.py")})
    assert changes.deleted == frozenset()


def test_change_detection_identifies_deleted_files() -> None:
    cached = {
        Path("main.py"): make_fingerprint(
            "main.py",
            "old",
        )
    }
    current = {}

    changes = detect_file_changes(cached, current)

    assert changes.unchanged == frozenset()
    assert changes.modified == frozenset()
    assert changes.added == frozenset()
    assert changes.deleted == frozenset({Path("main.py")})


def test_change_detection_identifies_all_change_types() -> None:
    cached = {
        Path("unchanged.py"): make_fingerprint(
            "unchanged.py",
            "same",
        ),
        Path("modified.py"): make_fingerprint(
            "modified.py",
            "old",
        ),
        Path("deleted.py"): make_fingerprint(
            "deleted.py",
            "deleted",
        ),
    }

    current = {
        Path("unchanged.py"): make_fingerprint(
            "unchanged.py",
            "same",
        ),
        Path("modified.py"): make_fingerprint(
            "modified.py",
            "new",
        ),
        Path("added.py"): make_fingerprint(
            "added.py",
            "added",
        ),
    }

    changes = detect_file_changes(cached, current)

    assert changes.unchanged == frozenset({Path("unchanged.py")})
    assert changes.modified == frozenset({Path("modified.py")})
    assert changes.added == frozenset({Path("added.py")})
    assert changes.deleted == frozenset({Path("deleted.py")})


def test_validate_cache_freshness_accepts_matching_cache() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    fingerprints = {
        Path("main.py"): make_fingerprint(
            "main.py",
            "same",
        ),
    }

    result = validate_cache_freshness(
        metadata=metadata,
        current_schema_version=CACHE_SCHEMA_VERSION,
        current_analyzer_version=ANALYZER_VERSION,
        cached_fingerprints=fingerprints,
        current_fingerprints=fingerprints,
    )

    assert result.is_fresh
    assert result.reason == "fresh"
    assert result.changes is not None
    assert result.changes.is_unchanged


def test_validate_cache_freshness_rejects_modified_files() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    cached = {
        Path("main.py"): make_fingerprint("main.py", "old"),
    }
    current = {
        Path("main.py"): make_fingerprint("main.py", "new"),
    }

    result = validate_cache_freshness(
        metadata,
        CACHE_SCHEMA_VERSION,
        ANALYZER_VERSION,
        cached,
        current,
    )

    assert not result.is_fresh
    assert result.reason == "files_changed"
    assert result.changes is not None
    assert result.changes.modified == frozenset({Path("main.py")})


def test_validate_cache_freshness_rejects_added_files() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    cached = {}
    current = {
        Path("main.py"): make_fingerprint("main.py", "new"),
    }

    result = validate_cache_freshness(
        metadata,
        CACHE_SCHEMA_VERSION,
        ANALYZER_VERSION,
        cached,
        current,
    )

    assert not result.is_fresh
    assert result.reason == "files_changed"
    assert result.changes is not None
    assert result.changes.added == frozenset({Path("main.py")})


def test_validate_cache_freshness_rejects_deleted_files() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    cached = {
        Path("main.py"): make_fingerprint("main.py", "old"),
    }
    current = {}

    result = validate_cache_freshness(
        metadata,
        CACHE_SCHEMA_VERSION,
        ANALYZER_VERSION,
        cached,
        current,
    )

    assert not result.is_fresh
    assert result.reason == "files_changed"
    assert result.changes is not None
    assert result.changes.deleted == frozenset({Path("main.py")})


def test_validate_cache_freshness_rejects_schema_mismatch() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        cache_schema_version=CACHE_SCHEMA_VERSION - 1,
    )

    result = validate_cache_freshness(
        metadata,
        CACHE_SCHEMA_VERSION,
        ANALYZER_VERSION,
        {},
        {},
    )

    assert not result.is_fresh
    assert result.reason == "schema_version_mismatch"


def test_validate_cache_freshness_rejects_analyzer_version_mismatch() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        analyzer_version="different",
    )

    result = validate_cache_freshness(
        metadata,
        CACHE_SCHEMA_VERSION,
        ANALYZER_VERSION,
        {},
        {},
    )

    assert not result.is_fresh
    assert result.reason == "analyzer_version_mismatch"


def test_validate_cache_freshness_rejects_missing_metadata() -> None:
    result = validate_cache_freshness(
        metadata=None,
        current_schema_version=CACHE_SCHEMA_VERSION,
        current_analyzer_version=ANALYZER_VERSION,
        cached_fingerprints=None,
        current_fingerprints={},
    )

    assert not result.is_fresh
    assert result.reason == "missing_metadata"


def test_determine_cache_invalidation_returns_no_invalidation_for_fresh_cache() -> None:
    freshness = validate_cache_freshness(
        metadata=RepositoryCacheMetadata(
            repository_key="/repo",
            project_id=UUID("00000000-0000-0000-0000-000000000001"),
        ),
        current_schema_version=CACHE_SCHEMA_VERSION,
        current_analyzer_version=ANALYZER_VERSION,
        cached_fingerprints={},
        current_fingerprints={},
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=False,
        paths=frozenset(),
        reason="fresh",
    )


def test_determine_cache_invalidation_selects_changed_files() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    cached = {
        Path("unchanged.py"): make_fingerprint(
            "unchanged.py",
            "same",
        ),
        Path("modified.py"): make_fingerprint(
            "modified.py",
            "old",
        ),
        Path("deleted.py"): make_fingerprint(
            "deleted.py",
            "deleted",
        ),
    }

    current = {
        Path("unchanged.py"): make_fingerprint(
            "unchanged.py",
            "same",
        ),
        Path("modified.py"): make_fingerprint(
            "modified.py",
            "new",
        ),
        Path("added.py"): make_fingerprint(
            "added.py",
            "added",
        ),
    }

    freshness = validate_cache_freshness(
        metadata=metadata,
        current_schema_version=CACHE_SCHEMA_VERSION,
        current_analyzer_version=ANALYZER_VERSION,
        cached_fingerprints=cached,
        current_fingerprints=current,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert not invalidation.full
    assert invalidation.reason == "files_changed"
    assert invalidation.paths == frozenset(
        {
            Path("modified.py"),
            Path("added.py"),
            Path("deleted.py"),
        }
    )


def test_determine_cache_invalidation_fully_invalidates_missing_metadata() -> None:
    freshness = validate_cache_freshness(
        metadata=None,
        current_schema_version=CACHE_SCHEMA_VERSION,
        current_analyzer_version=ANALYZER_VERSION,
        cached_fingerprints=None,
        current_fingerprints={},
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="missing_metadata",
    )


def test_determine_cache_invalidation_fully_invalidates_schema_mismatch() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        cache_schema_version=CACHE_SCHEMA_VERSION - 1,
    )

    freshness = validate_cache_freshness(
        metadata=metadata,
        current_schema_version=CACHE_SCHEMA_VERSION,
        current_analyzer_version=ANALYZER_VERSION,
        cached_fingerprints={},
        current_fingerprints={},
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="schema_version_mismatch",
    )


def test_determine_cache_invalidation_fully_invalidates_analyzer_mismatch() -> None:
    metadata = RepositoryCacheMetadata(
        repository_key="/repo",
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        analyzer_version="different",
    )

    freshness = validate_cache_freshness(
        metadata=metadata,
        current_schema_version=CACHE_SCHEMA_VERSION,
        current_analyzer_version=ANALYZER_VERSION,
        cached_fingerprints={},
        current_fingerprints={},
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="analyzer_version_mismatch",
    )


def test_determine_cache_invalidation_for_fresh_cache() -> None:
    freshness = CacheFreshness(
        is_fresh=True,
        reason="fresh",
        changes=None,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=False,
        paths=frozenset(),
        reason="fresh",
    )


def test_determine_cache_invalidation_for_changed_files() -> None:
    changes = FileChangeSet(
        unchanged=frozenset({Path("unchanged.py")}),
        modified=frozenset({Path("modified.py")}),
        added=frozenset({Path("added.py")}),
        deleted=frozenset({Path("deleted.py")}),
    )
    freshness = CacheFreshness(
        is_fresh=False,
        reason="files_changed",
        changes=changes,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=False,
        paths=frozenset(
            {
                Path("modified.py"),
                Path("added.py"),
                Path("deleted.py"),
            }
        ),
        reason="files_changed",
    )


def test_determine_cache_invalidation_for_missing_metadata() -> None:
    freshness = CacheFreshness(
        is_fresh=False,
        reason="missing_metadata",
        changes=None,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="missing_metadata",
    )


def test_determine_cache_invalidation_for_schema_mismatch() -> None:
    freshness = CacheFreshness(
        is_fresh=False,
        reason="schema_version_mismatch",
        changes=None,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="schema_version_mismatch",
    )


def test_determine_cache_invalidation_for_analyzer_mismatch() -> None:
    freshness = CacheFreshness(
        is_fresh=False,
        reason="analyzer_version_mismatch",
        changes=None,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="analyzer_version_mismatch",
    )


def test_determine_cache_invalidation_for_missing_fingerprints() -> None:
    freshness = CacheFreshness(
        is_fresh=False,
        reason="missing_fingerprints",
        changes=None,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="missing_fingerprints",
    )


def test_determine_cache_invalidation_for_missing_current_fingerprints() -> None:
    freshness = CacheFreshness(
        is_fresh=False,
        reason="missing_current_fingerprints",
        changes=None,
    )

    invalidation = determine_cache_invalidation(freshness)

    assert invalidation == CacheInvalidation(
        full=True,
        paths=frozenset(),
        reason="missing_current_fingerprints",
    )
