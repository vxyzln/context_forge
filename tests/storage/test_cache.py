from pathlib import Path

from context_forge.storage.cache import (
    FileFingerprint,
    detect_file_changes,
    fingerprint_file,
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
