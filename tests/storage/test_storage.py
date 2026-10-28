import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.git import GitActivitySummary
from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.parser.python import PythonParser
from context_forge.parser.result import ImportReference
from context_forge.scanner.repository import RepositoryScanner
from context_forge.storage.cache import (
    ANALYZER_VERSION,
    CACHE_SCHEMA_VERSION,
    CacheInvalidation,
    FileFingerprint,
    RepositoryCacheMetadata,
    RepositoryIdentity,
    fingerprint_file,
)
from context_forge.storage.database import Database
from context_forge.storage.repository import (
    ProjectRepository,
    _is_missing_imports_table_error,
)


def parse_project(project: Project) -> None:
    parser = PythonParser()

    for file in project.files:
        if file.extension != ".py":
            continue

        source = (project.root_path / file.path).read_text(encoding="utf-8")
        result = parser.parse(source, file)

        for symbol in result.symbols:
            project.add_symbol(symbol)


def test_database_initializes(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")

    database.initialize()

    assert database.path.exists()


def test_project_can_be_saved_and_loaded(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert loaded.id == project.id
    assert loaded.name == "Test Project"
    assert loaded.root_path == tmp_path


def test_missing_project_returns_none(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    loaded = repository.load(uuid4())

    assert loaded is None


def test_analyzed_project_persists_analysis_records(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    with database.connect() as connection:
        project_row = connection.execute(
            "SELECT COUNT(*) AS count FROM projects WHERE id = ?",
            (str(project.id),),
        ).fetchone()

        directory_row = connection.execute(
            "SELECT COUNT(*) AS count FROM directories WHERE project_id = ?",
            (str(project.id),),
        ).fetchone()

        file_row = connection.execute(
            "SELECT COUNT(*) AS count FROM files WHERE project_id = ?",
            (str(project.id),),
        ).fetchone()

        symbol_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM symbols
            WHERE file_id IN (
                SELECT id FROM files WHERE project_id = ?
            )
            """,
            (str(project.id),),
        ).fetchone()

        relationship_row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM relationships
            WHERE source_id IN (
                SELECT id FROM files WHERE project_id = ?
            )
            """,
            (str(project.id),),
        ).fetchone()

    assert project_row["count"] == 1
    assert directory_row["count"] == len(project.directories)
    assert file_row["count"] == len(project.files)
    assert symbol_row["count"] == len(project.symbols)
    assert relationship_row["count"] == len(project.relationships)


def test_analysis_errors_are_persisted(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
        errors=["main.py:1:1: Invalid syntax"],
    )

    repository.save(project)

    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT message
            FROM analysis_errors
            WHERE project_id = ?
            """,
            (str(project.id),),
        ).fetchone()

    assert row is not None
    assert row["message"] == "main.py:1:1: Invalid syntax"


def test_project_load_rehydrates_analysis_records(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    project.errors.append("example.py:1:1: Invalid syntax")

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None

    assert loaded.id == project.id
    assert loaded.name == project.name
    assert loaded.root_path == project.root_path

    assert len(loaded.directories) == len(project.directories)
    assert len(loaded.files) == len(project.files)
    assert len(loaded.symbols) == len(project.symbols)
    assert len(loaded.relationships) == len(project.relationships)
    assert loaded.errors == project.errors

    assert loaded.files[0].id == project.files[0].id
    assert loaded.files[0].path == project.files[0].path

    assert loaded.symbols[0].id == project.symbols[0].id
    assert loaded.symbols[0].name == project.symbols[0].name

    assert loaded.relationships[0].id == project.relationships[0].id
    assert (
        loaded.relationships[0].relationship_type
        == project.relationships[0].relationship_type
    )


def test_symbol_schema_matches_symbol_model(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    with database.connect() as connection:
        columns = connection.execute("PRAGMA table_info(symbols)").fetchall()

    column_names = {column["name"] for column in columns}

    assert column_names == {
        "id",
        "file_id",
        "name",
        "kind",
        "qualified_name",
        "start_line",
        "end_line",
        "parent_symbol_id",
        "signature",
    }


def test_symbol_fields_survive_repository_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert len(loaded.symbols) == len(project.symbols)

    original = project.symbols
    restored = loaded.symbols

    for expected, actual in zip(original, restored):
        assert actual.id == expected.id
        assert actual.file_id == expected.file_id
        assert actual.name == expected.name
        assert actual.kind == expected.kind
        assert actual.qualified_name == expected.qualified_name
        assert actual.start_line == expected.start_line
        assert actual.end_line == expected.end_line
        assert actual.parent_symbol_id == expected.parent_symbol_id
        assert actual.signature == expected.signature


def test_project_save_removes_stale_symbols(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def first():
    return 1

def second():
    return 2
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    original_symbol_count = len(project.symbols)
    assert original_symbol_count == 2

    project.symbols = project.symbols[:1]
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert len(loaded.symbols) == 1
    assert loaded.symbols[0].name == "first"


def test_project_save_removes_stale_relationships(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
import os

def hello():
    return os.getcwd()
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save(project)

    original_relationship_count = len(project.relationships)

    project.relationships = []
    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert original_relationship_count > 0
    assert loaded.relationships == []


def test_git_activity_fields_survive_repository_round_trip(
    tmp_path: Path,
) -> None:
    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    project.git_activity = GitActivitySummary(
        total_commits=12,
        total_authors=3,
        files_changed=8,
        total_additions=145,
        total_deletions=37,
    )

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert loaded.git_activity == project.git_activity


def test_missing_git_activity_survives_repository_round_trip(
    tmp_path: Path,
) -> None:
    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    assert project.git_activity is None

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert loaded.git_activity is None


def test_repository_identity_is_deterministic(tmp_path: Path) -> None:
    identity = RepositoryIdentity(tmp_path)

    assert identity.key == str(tmp_path.resolve())


def test_repository_cache_metadata_survives_round_trip(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    repository.save(project)

    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
    )

    repository.save_cache_metadata(metadata)

    loaded = repository.load_cache_metadata(metadata.repository_key)

    assert loaded is not None
    assert loaded == metadata


def test_repository_cache_metadata_uses_current_versions(
    tmp_path: Path,
) -> None:
    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
    )

    assert metadata.cache_schema_version == CACHE_SCHEMA_VERSION
    assert metadata.analyzer_version == ANALYZER_VERSION


def test_missing_repository_cache_metadata_returns_none(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    loaded = repository.load_cache_metadata(
        RepositoryIdentity(tmp_path).key,
    )

    assert loaded is None


def test_repository_cache_metadata_can_be_replaced(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    first_project = Project(
        name="First Project",
        root_path=tmp_path,
    )
    second_project = Project(
        name="Second Project",
        root_path=tmp_path,
    )

    repository.save(first_project)
    repository.save(second_project)

    repository_key = RepositoryIdentity(tmp_path).key

    repository.save_cache_metadata(
        RepositoryCacheMetadata(
            repository_key=repository_key,
            project_id=first_project.id,
        )
    )

    repository.save_cache_metadata(
        RepositoryCacheMetadata(
            repository_key=repository_key,
            project_id=second_project.id,
        )
    )

    loaded = repository.load_cache_metadata(repository_key)

    assert loaded is not None
    assert loaded.project_id == second_project.id


def test_save_analysis_persists_project_and_cache_metadata(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )
    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
    )

    repository.save_analysis(project, metadata)

    loaded_project = repository.load(project.id)
    loaded_metadata = repository.load_cache_metadata(metadata.repository_key)

    assert loaded_project is not None
    assert loaded_project.id == project.id
    assert loaded_project.name == project.name
    assert loaded_metadata == metadata


def test_load_analysis_returns_project_and_metadata(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )
    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
    )

    repository.save_analysis(project, metadata)

    loaded = repository.load_analysis(metadata.repository_key)

    assert loaded is not None

    loaded_project, loaded_metadata = loaded

    assert loaded_project.id == project.id
    assert loaded_project.name == project.name
    assert loaded_metadata == metadata


def test_load_analysis_returns_none_for_missing_cache(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    loaded = repository.load_analysis(
        RepositoryIdentity(tmp_path).key,
    )

    assert loaded is None


def test_load_analysis_returns_none_when_cached_project_is_missing(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )
    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
    )

    repository.save_cache_metadata(metadata)

    loaded = repository.load_analysis(metadata.repository_key)

    assert loaded is None


def test_load_analysis_preserves_repository_identity(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )
    repository_key = RepositoryIdentity(tmp_path).key
    metadata = RepositoryCacheMetadata(
        repository_key=repository_key,
        project_id=project.id,
    )

    repository.save_analysis(project, metadata)

    loaded = repository.load_analysis(repository_key)

    assert loaded is not None

    loaded_project, loaded_metadata = loaded

    assert loaded_project.root_path == tmp_path.resolve()
    assert loaded_metadata.repository_key == repository_key


def test_file_fingerprint_round_trip(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    repository_key = RepositoryIdentity(tmp_path).key

    fingerprint = FileFingerprint(
        path=Path("main.py"),
        size=10,
        modified_at_ns=123456789,
        content_hash="abc123",
    )

    repository.save_file_fingerprints(
        repository_key,
        [fingerprint],
    )

    loaded = repository.load_file_fingerprints(repository_key)

    assert loaded == {Path("main.py"): fingerprint}


def test_file_fingerprint_storage_replaces_previous_state(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    repository_key = RepositoryIdentity(tmp_path).key

    first = FileFingerprint(
        path=Path("main.py"),
        size=10,
        modified_at_ns=1,
        content_hash="first",
    )

    second = FileFingerprint(
        path=Path("other.py"),
        size=20,
        modified_at_ns=2,
        content_hash="second",
    )

    repository.save_file_fingerprints(
        repository_key,
        [first],
    )
    repository.save_file_fingerprints(
        repository_key,
        [second],
    )

    loaded = repository.load_file_fingerprints(repository_key)

    assert loaded == {Path("other.py"): second}


def test_missing_file_fingerprints_return_empty_mapping(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    repository_key = RepositoryIdentity(tmp_path).key

    assert repository.load_file_fingerprints(repository_key) == {}


def test_check_cache_freshness_returns_fresh_for_matching_cache(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="example",
        root_path=tmp_path,
    )
    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
    )

    repository.save(project)
    repository.save_cache_metadata(metadata)

    fingerprint = FileFingerprint(
        path=Path("main.py"),
        size=10,
        modified_at_ns=1,
        content_hash="same",
    )
    repository.save_file_fingerprints(
        metadata.repository_key,
        [fingerprint],
    )

    result = repository.check_cache_freshness(
        metadata.repository_key,
        {Path("main.py"): fingerprint},
    )

    assert result.is_fresh
    assert result.reason == "fresh"
    assert result.changes is not None
    assert result.changes.is_unchanged


def test_check_cache_freshness_detects_modified_file(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="example",
        root_path=tmp_path,
    )
    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
    )

    repository.save(project)
    repository.save_cache_metadata(metadata)

    cached = FileFingerprint(
        path=Path("main.py"),
        size=10,
        modified_at_ns=1,
        content_hash="old",
    )
    current = FileFingerprint(
        path=Path("main.py"),
        size=11,
        modified_at_ns=2,
        content_hash="new",
    )

    repository.save_file_fingerprints(
        metadata.repository_key,
        [cached],
    )

    result = repository.check_cache_freshness(
        metadata.repository_key,
        {Path("main.py"): current},
    )

    assert not result.is_fresh
    assert result.reason == "files_changed"
    assert result.changes is not None
    assert result.changes.modified == frozenset({Path("main.py")})


def test_check_cache_freshness_detects_missing_metadata(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    repository_key = RepositoryIdentity(tmp_path).key

    result = repository.check_cache_freshness(
        repository_key,
        {},
    )

    assert not result.is_fresh
    assert result.reason == "missing_metadata"


def test_check_cache_freshness_detects_schema_version_mismatch(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="example",
        root_path=tmp_path,
    )
    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
        cache_schema_version=CACHE_SCHEMA_VERSION - 1,
    )

    repository.save(project)
    repository.save_cache_metadata(metadata)

    result = repository.check_cache_freshness(
        metadata.repository_key,
        {},
    )

    assert not result.is_fresh
    assert result.reason == "schema_version_mismatch"


def test_check_cache_freshness_detects_analyzer_version_mismatch(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="example",
        root_path=tmp_path,
    )
    metadata = RepositoryCacheMetadata(
        repository_key=RepositoryIdentity(tmp_path).key,
        project_id=project.id,
        analyzer_version="different",
    )

    repository.save(project)
    repository.save_cache_metadata(metadata)

    result = repository.check_cache_freshness(
        metadata.repository_key,
        {},
    )

    assert not result.is_fresh
    assert result.reason == "analyzer_version_mismatch"


def test_invalidate_cache_with_fresh_state_preserves_analysis(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text("value = 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
    )

    repository_key = RepositoryIdentity(tmp_path).key
    invalidation = CacheInvalidation(
        full=False,
        paths=frozenset(),
        reason="fresh",
    )

    repository.invalidate_cache(repository_key, invalidation)

    assert repository.load_analysis(repository_key) is not None


def test_invalidate_cache_selectively_removes_affected_file(
    tmp_path: Path,
) -> None:
    changed = tmp_path / "changed.py"
    unchanged = tmp_path / "unchanged.py"
    changed.write_text("changed = 1\n")
    unchanged.write_text("unchanged = 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
    )

    repository.invalidate_cache(
        RepositoryIdentity(tmp_path).key,
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("changed.py")}),
            reason="files_changed",
        ),
    )

    loaded = repository.load_analysis(RepositoryIdentity(tmp_path).key)
    assert loaded is not None
    loaded_project, _ = loaded
    assert Path("changed.py") not in {file.path for file in loaded_project.files}
    assert Path("unchanged.py") in {file.path for file in loaded_project.files}


def test_invalidate_cache_selectively_removes_affected_symbols(
    tmp_path: Path,
) -> None:
    changed = tmp_path / "changed.py"
    unchanged = tmp_path / "unchanged.py"
    changed.write_text("def changed():\n    return 1\n")
    unchanged.write_text("def unchanged():\n    return 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
    )

    changed_file = next(
        file for file in project.files if file.path == Path("changed.py")
    )
    changed_symbol_ids = {
        symbol.id for symbol in project.symbols if symbol.file_id == changed_file.id
    }

    repository.invalidate_cache(
        RepositoryIdentity(tmp_path).key,
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("changed.py")}),
            reason="files_changed",
        ),
    )

    loaded = repository.load_analysis(RepositoryIdentity(tmp_path).key)
    assert loaded is not None

    loaded_project, _ = loaded
    assert changed_symbol_ids.isdisjoint(
        {symbol.id for symbol in loaded_project.symbols}
    )


def test_invalidate_cache_selectively_removes_affected_relationships(
    tmp_path: Path,
) -> None:
    changed = tmp_path / "changed.py"
    unchanged = tmp_path / "unchanged.py"
    changed.write_text("def changed():\n    return 1\n")
    unchanged.write_text("def unchanged():\n    return 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
    )

    changed_file = next(
        file for file in project.files if file.path == Path("changed.py")
    )
    changed_symbol_ids = {
        symbol.id for symbol in project.symbols if symbol.file_id == changed_file.id
    }
    affected_ids = changed_symbol_ids | {changed_file.id}

    affected_relationship_ids = {
        relationship.id
        for relationship in project.relationships
        if (
            relationship.source_id in affected_ids
            or relationship.target_id in affected_ids
        )
    }

    repository.invalidate_cache(
        RepositoryIdentity(tmp_path).key,
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("changed.py")}),
            reason="files_changed",
        ),
    )

    loaded = repository.load_analysis(RepositoryIdentity(tmp_path).key)
    assert loaded is not None
    loaded_project, _ = loaded

    assert affected_relationship_ids.isdisjoint(
        {relationship.id for relationship in loaded_project.relationships}
    )


def test_invalidate_cache_selectively_removes_affected_fingerprint(
    tmp_path: Path,
) -> None:
    (tmp_path / "changed.py").write_text("changed = 1\n")
    (tmp_path / "unchanged.py").write_text("unchanged = 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
        [fingerprint_file(tmp_path, file.path) for file in project.files],
    )

    repository.invalidate_cache(
        RepositoryIdentity(tmp_path).key,
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("changed.py")}),
            reason="files_changed",
        ),
    )

    fingerprints = repository.load_file_fingerprints(
        RepositoryIdentity(tmp_path).key,
    )

    assert Path("changed.py") not in fingerprints
    assert Path("unchanged.py") in fingerprints


def test_invalidate_cache_preserves_unaffected_fingerprints(
    tmp_path: Path,
) -> None:
    (tmp_path / "changed.py").write_text("changed = 1\n")
    (tmp_path / "unchanged.py").write_text("unchanged = 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
        [fingerprint_file(tmp_path, file.path) for file in project.files],
    )

    repository_key = RepositoryIdentity(tmp_path).key
    before = repository.load_file_fingerprints(repository_key)

    repository.invalidate_cache(
        repository_key,
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("changed.py")}),
            reason="files_changed",
        ),
    )

    after = repository.load_file_fingerprints(repository_key)

    assert after[Path("unchanged.py")] == before[Path("unchanged.py")]


def test_invalidate_cache_fully_removes_analysis(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.py").write_text("value = 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
        [fingerprint_file(tmp_path, file.path) for file in project.files],
    )

    repository_key = RepositoryIdentity(tmp_path).key

    repository.invalidate_cache(
        repository_key,
        CacheInvalidation(
            full=True,
            paths=frozenset(),
            reason="schema_version_mismatch",
        ),
    )

    assert repository.load_analysis(repository_key) is None
    assert repository.load_cache_metadata(repository_key) is None
    assert repository.load_file_fingerprints(repository_key) == {}


def test_invalidate_cache_fully_removes_graph_data(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.py").write_text("def main():\n    return 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
    )

    repository.invalidate_cache(
        RepositoryIdentity(tmp_path).key,
        CacheInvalidation(
            full=True,
            paths=frozenset(),
            reason="analyzer_version_mismatch",
        ),
    )

    assert repository.load_analysis(RepositoryIdentity(tmp_path).key) is None


def test_invalidate_cache_with_missing_repository_is_safe(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    repository.invalidate_cache(
        RepositoryIdentity(tmp_path).key,
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("missing.py")}),
            reason="files_changed",
        ),
    )

    assert repository.load_analysis(RepositoryIdentity(tmp_path).key) is None


def test_invalidate_cache_ignores_paths_without_persisted_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "main.py").write_text("value = 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)
    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=RepositoryIdentity(tmp_path).key,
            project_id=project.id,
        ),
    )

    repository.invalidate_cache(
        RepositoryIdentity(tmp_path).key,
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("new.py")}),
            reason="files_changed",
        ),
    )

    assert repository.load_analysis(RepositoryIdentity(tmp_path).key) is not None


def test_refresh_cache_state_returns_fresh_invalidation(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    repository_key = RepositoryIdentity(tmp_path).key

    metadata = RepositoryCacheMetadata(
        repository_key=repository_key,
        project_id=project.id,
    )

    fingerprint = FileFingerprint(
        path=Path("main.py"),
        size=10,
        modified_at_ns=1,
        content_hash="same",
    )

    repository.save_analysis(
        project,
        metadata,
        [fingerprint],
    )

    invalidation = repository.refresh_cache_state(
        repository_key,
        {Path("main.py"): fingerprint},
    )

    assert not invalidation.full
    assert invalidation.paths == frozenset()
    assert invalidation.reason == "fresh"

    assert repository.load_analysis(repository_key) is not None


def test_refresh_cache_state_selectively_invalidates_changed_files(
    tmp_path: Path,
) -> None:
    changed = tmp_path / "changed.py"
    unchanged = tmp_path / "unchanged.py"

    changed.write_text("changed = 1\n")
    unchanged.write_text("unchanged = 1\n")

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, [])

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    repository_key = RepositoryIdentity(tmp_path).key

    metadata = RepositoryCacheMetadata(
        repository_key=repository_key,
        project_id=project.id,
    )

    cached_fingerprints = [
        fingerprint_file(tmp_path, file.path) for file in project.files
    ]

    repository.save_analysis(
        project,
        metadata,
        cached_fingerprints,
    )

    changed.write_text("changed = 2\n")

    current_fingerprints = {
        file.path: fingerprint_file(tmp_path, file.path) for file in project.files
    }

    invalidation = repository.refresh_cache_state(
        repository_key,
        current_fingerprints,
    )

    assert not invalidation.full
    assert invalidation.paths == frozenset({Path("changed.py")})
    assert invalidation.reason == "files_changed"

    loaded = repository.load_analysis(repository_key)

    assert loaded is not None

    loaded_project, _ = loaded

    assert Path("changed.py") not in {file.path for file in loaded_project.files}

    assert Path("unchanged.py") in {file.path for file in loaded_project.files}


def test_refresh_cache_state_fully_invalidates_incompatible_cache(
    tmp_path: Path,
) -> None:
    project = Project(
        name="Test Project",
        root_path=tmp_path,
    )

    database = Database(tmp_path / "context_forge.db")
    database.initialize()

    repository = ProjectRepository(database)

    repository_key = RepositoryIdentity(tmp_path).key

    repository.save_analysis(
        project,
        RepositoryCacheMetadata(
            repository_key=repository_key,
            project_id=project.id,
            analyzer_version="old-version",
        ),
    )

    current_fingerprints: dict[Path, FileFingerprint] = {}

    invalidation = repository.refresh_cache_state(
        repository_key,
        current_fingerprints,
    )

    assert invalidation.full
    assert invalidation.paths == frozenset()
    assert invalidation.reason == "analyzer_version_mismatch"

    assert repository.load_analysis(repository_key) is None
    assert repository.load_cache_metadata(repository_key) is None
    assert repository.load_file_fingerprints(repository_key) == {}


def test_project_save_removes_stale_symbol_relationships(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
class Parent:
    def method(self):
        return 1
""",
        encoding="utf-8",
    )

    project = RepositoryScanner(tmp_path).scan()
    parse_project(project)
    RelationshipBuilder().build(project, project.imports)

    symbol_ids = {str(symbol.id) for symbol in project.symbols}
    symbol_relationships = [
        relationship
        for relationship in project.relationships
        if str(relationship.source_id) in symbol_ids
        and str(relationship.target_id) in symbol_ids
    ]

    assert symbol_relationships, "Test setup must produce symbol-to-symbol edges"

    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    repository.save(project)

    project.relationships = []
    repository.save(project)

    with database.connect() as connection:
        remaining = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM relationships
            WHERE source_id IN (SELECT id FROM symbols)
               OR target_id IN (SELECT id FROM symbols)
            """
        ).fetchone()["count"]

    assert remaining == 0, (
        f"Expected stale symbol relationships to be removed; found {remaining}"
    )


def test_save_analysis_rolls_back_all_writes_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = RepositoryScanner(tmp_path).scan()

    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    metadata = RepositoryCacheMetadata(
        repository_key="atomic-save-test",
        project_id=project.id,
        cache_schema_version=1,
        analyzer_version="original",
    )

    repository.save_analysis(project, metadata)

    original_project_name = project.name

    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO repository_file_fingerprints (
                repository_key,
                path,
                size,
                modified_at_ns,
                content_hash
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                metadata.repository_key,
                "main.py",
                100,
                123456789,
                "original-hash",
            ),
        )

    original_save_fingerprints = repository._save_file_fingerprints

    def fail_after_fingerprint_write(
        connection: sqlite3.Connection,
        repository_key: str,
        fingerprints: list[FileFingerprint],
    ) -> None:
        original_save_fingerprints(
            connection,
            repository_key,
            fingerprints,
        )
        raise RuntimeError("injected fingerprint persistence failure")

    monkeypatch.setattr(
        repository,
        "_save_file_fingerprints",
        fail_after_fingerprint_write,
    )

    project.name = "updated-project"

    updated_metadata = RepositoryCacheMetadata(
        repository_key=metadata.repository_key,
        project_id=project.id,
        cache_schema_version=1,
        analyzer_version="updated",
    )

    with pytest.raises(
        RuntimeError,
        match="injected fingerprint persistence failure",
    ):
        repository.save_analysis(
            project,
            updated_metadata,
            fingerprints=[],
        )

    saved_project = repository.load(project.id)
    assert saved_project is not None
    assert saved_project.name == original_project_name

    saved_metadata = repository.load_cache_metadata(
        metadata.repository_key,
    )
    assert saved_metadata is not None
    assert saved_metadata.analyzer_version == "original"

    with database.connect() as connection:
        fingerprint = connection.execute(
            """
            SELECT path, size, modified_at_ns, content_hash
            FROM repository_file_fingerprints
            WHERE repository_key = ?
            """,
            (metadata.repository_key,),
        ).fetchone()

    assert fingerprint is not None
    assert fingerprint["path"] == "main.py"
    assert fingerprint["size"] == 100
    assert fingerprint["modified_at_ns"] == 123456789
    assert fingerprint["content_hash"] == "original-hash"


def test_project_languages_and_frameworks_survive_repository_round_trip(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="Classification Test",
        root_path=tmp_path,
        languages=["Python", "TypeScript"],
        frameworks=["Django", "FastAPI"],
    )

    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert loaded.languages == ["Python", "TypeScript"]
    assert loaded.frameworks == ["Django", "FastAPI"]


def test_project_empty_languages_and_frameworks_survive_round_trip(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(
        name="Unclassified Project",
        root_path=tmp_path,
    )

    repository.save(project)

    loaded = repository.load(project.id)

    assert loaded is not None
    assert loaded.languages == []
    assert loaded.frameworks == []


def test_database_migration_adds_project_classification_columns(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "context_forge.db"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                repository_url TEXT,
                default_branch TEXT,
                project_type TEXT,
                package_manager TEXT,
                analysis_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                git_total_commits INTEGER,
                git_total_authors INTEGER,
                git_files_changed INTEGER,
                git_total_additions INTEGER,
                git_total_deletions INTEGER
            )
            """
        )

        project_id = uuid4()
        root_path = str(tmp_path)
        timestamp = "2026-01-01T00:00:00+00:00"

        connection.execute(
            """
            INSERT INTO projects (
                id,
                name,
                root_path,
                analysis_status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(project_id),
                "Legacy Project",
                root_path,
                "analyzed",
                timestamp,
                timestamp,
            ),
        )

    database = Database(database_path)
    database.initialize()

    with database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(projects)").fetchall()
        }

        row = connection.execute(
            "SELECT * FROM projects WHERE id = ?",
            (str(project_id),),
        ).fetchone()

    assert "languages" in columns
    assert "frameworks" in columns

    assert row is not None
    assert row["name"] == "Legacy Project"
    assert row["root_path"] == root_path
    assert row["analysis_status"] == "analyzed"

    assert row["languages"] == "[]"
    assert row["frameworks"] == "[]"

    repository = ProjectRepository(database)
    loaded = repository.load(project_id)

    assert loaded is not None
    assert loaded.name == "Legacy Project"
    assert loaded.languages == []
    assert loaded.frameworks == []


def test_load_analysis_keeps_separate_repositories_isolated(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    first_root = tmp_path / "project_a"
    second_root = tmp_path / "project_b"
    first_root.mkdir()
    second_root.mkdir()

    first_project = Project(
        name="Project A",
        root_path=first_root,
    )
    second_project = Project(
        name="Project B",
        root_path=second_root,
    )

    first_key = RepositoryIdentity(first_root).key
    second_key = RepositoryIdentity(second_root).key

    first_metadata = RepositoryCacheMetadata(
        repository_key=first_key,
        project_id=first_project.id,
    )
    second_metadata = RepositoryCacheMetadata(
        repository_key=second_key,
        project_id=second_project.id,
    )

    repository.save_analysis(first_project, first_metadata)
    repository.save_analysis(second_project, second_metadata)

    first_loaded = repository.load_analysis(first_key)
    second_loaded = repository.load_analysis(second_key)

    assert first_loaded is not None
    assert second_loaded is not None

    first_loaded_project, first_loaded_metadata = first_loaded
    second_loaded_project, second_loaded_metadata = second_loaded

    assert first_loaded_project.id == first_project.id
    assert first_loaded_project.name == "Project A"
    assert first_loaded_metadata == first_metadata

    assert second_loaded_project.id == second_project.id
    assert second_loaded_project.name == "Project B"
    assert second_loaded_metadata == second_metadata

    assert first_loaded_metadata.repository_key != (
        second_loaded_metadata.repository_key
    )


def test_import_reference_round_trip_preserves_all_fields(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(name="Import Test Project", root_path=tmp_path)
    file_a = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    project.add_file(file_a)

    import_ref = ImportReference(
        file_id=file_a.id,
        module_name="os.path",
        imported_name="join",
        alias="pjoin",
        level=0,
    )
    relative_ref = ImportReference(
        file_id=file_a.id,
        module_name="..sibling",
        imported_name="Helper",
        alias=None,
        level=2,
    )
    project.add_import(import_ref)
    project.add_import(relative_ref)

    repository.save(project)
    loaded = repository.load(project.id)

    assert loaded is not None
    assert len(loaded.imports) == 2
    first, second = loaded.imports
    assert first.file_id == file_a.id
    assert first.module_name == "os.path"
    assert first.imported_name == "join"
    assert first.alias == "pjoin"
    assert first.level == 0

    assert second.file_id == file_a.id
    assert second.module_name == "..sibling"
    assert second.imported_name == "Helper"
    assert second.alias is None
    assert second.level == 2


def test_import_reference_repeated_save_does_not_duplicate_records(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(name="Repeat Save Project", root_path=tmp_path)
    file_a = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    project.add_file(file_a)
    project.add_import(
        ImportReference(
            file_id=file_a.id,
            module_name="math",
            imported_name="sqrt",
        )
    )

    repository.save(project)
    repository.save(project)

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM imports WHERE project_id = ?",
            (str(project.id),),
        ).fetchone()["count"]

    assert count == 1

    loaded = repository.load(project.id)
    assert loaded is not None
    assert len(loaded.imports) == 1


def test_import_reference_repository_isolation(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project_1 = Project(name="Project 1", root_path=tmp_path / "p1")
    file_1 = File(
        project_id=project_1.id,
        path=Path("p1.py"),
        name="p1.py",
        extension=".py",
    )
    project_1.add_file(file_1)
    project_1.add_import(ImportReference(file_id=file_1.id, module_name="pkg1"))

    project_2 = Project(name="Project 2", root_path=tmp_path / "p2")
    file_2 = File(
        project_id=project_2.id,
        path=Path("p2.py"),
        name="p2.py",
        extension=".py",
    )
    project_2.add_file(file_2)
    project_2.add_import(ImportReference(file_id=file_2.id, module_name="pkg2"))

    repository.save(project_1)
    repository.save(project_2)

    loaded_1 = repository.load(project_1.id)
    loaded_2 = repository.load(project_2.id)

    assert loaded_1 is not None and loaded_2 is not None
    assert [imp.module_name for imp in loaded_1.imports] == ["pkg1"]
    assert [imp.module_name for imp in loaded_2.imports] == ["pkg2"]


def test_import_reference_deleted_file_invalidation(tmp_path: Path) -> None:
    database = Database(tmp_path / "context_forge.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(name="Invalidation Test", root_path=tmp_path)
    file_a = File(
        project_id=project.id,
        path=Path("a.py"),
        name="a.py",
        extension=".py",
    )
    file_b = File(
        project_id=project.id,
        path=Path("b.py"),
        name="b.py",
        extension=".py",
    )
    project.add_file(file_a)
    project.add_file(file_b)
    project.add_import(ImportReference(file_id=file_a.id, module_name="mod_a"))
    project.add_import(ImportReference(file_id=file_b.id, module_name="mod_b"))

    metadata = RepositoryCacheMetadata(
        repository_key=str(tmp_path),
        project_id=project.id,
    )
    repository.save_analysis(project, metadata)

    invalidation = CacheInvalidation(
        full=False,
        paths=frozenset({Path("a.py")}),
        reason="files_changed",
    )
    repository.invalidate_cache(str(tmp_path), invalidation)

    with database.connect() as connection:
        remaining = connection.execute(
            "SELECT module_name FROM imports WHERE project_id = ?",
            (str(project.id),),
        ).fetchall()

    assert [row["module_name"] for row in remaining] == ["mod_b"]


def test_project_repository_loads_older_database_without_imports_table(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "legacy.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(name="Legacy Project", root_path=tmp_path)
    file_a = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    project.add_file(file_a)
    project.add_import(ImportReference(file_id=file_a.id, module_name="sys"))
    repository.save(project)

    with database.connect() as connection:
        connection.execute("DROP TABLE imports")

    loaded = repository.load(project.id)
    assert loaded is not None
    assert loaded.id == project.id
    assert len(loaded.files) == 1
    assert loaded.imports == []

    repository.invalidate_cache(
        str(tmp_path),
        CacheInvalidation(
            full=False,
            paths=frozenset({Path("main.py")}),
            reason="files_changed",
        ),
    )


def test_project_repository_propagates_unrelated_sqlite_operational_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(name="Test Project", root_path=tmp_path)
    file_a = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    project.add_file(file_a)
    repository.save(project)

    real_connect = database.connect

    class FailingConnectionProxy:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def execute(self, sql: str, *args, **kwargs):
            if "FROM imports" in sql or "DELETE FROM imports" in sql:
                raise sqlite3.OperationalError("database is locked")
            return self._conn.execute(sql, *args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._conn.__exit__(exc_type, exc_val, exc_tb)

        def __getattr__(self, name: str):
            return getattr(self._conn, name)

    monkeypatch.setattr(
        database, "connect", lambda: FailingConnectionProxy(real_connect())
    )

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        repository.load(project.id)


def test_project_repository_propagates_missing_differently_named_table_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    repository = ProjectRepository(database)

    project = Project(name="Test Project", root_path=tmp_path)
    file_a = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )
    project.add_file(file_a)
    repository.save(project)

    real_connect = database.connect

    class FailingConnectionProxy:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def execute(self, sql: str, *args, **kwargs):
            if "FROM imports" in sql or "DELETE FROM imports" in sql:
                raise sqlite3.OperationalError("no such table: user_imports")
            return self._conn.execute(sql, *args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._conn.__exit__(exc_type, exc_val, exc_tb)

        def __getattr__(self, name: str):
            return getattr(self._conn, name)

    monkeypatch.setattr(
        database, "connect", lambda: FailingConnectionProxy(real_connect())
    )

    with pytest.raises(sqlite3.OperationalError, match="no such table: user_imports"):
        repository.load(project.id)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("no such table: imports", True),
        ("no such table: main.imports", True),
        ("NO SUCH TABLE: IMPORTS", True),
        ("no such table: user_imports", False),
        ("no such table: imports_v2", False),
        ("no such table: other_imports", False),
        ("no such table: files", False),
        ("database is locked", False),
        ("disk I/O error", False),
    ],
)
def test_is_missing_imports_table_error_matches_exact_table_only(
    message: str, expected: bool
) -> None:
    exc = sqlite3.OperationalError(message)
    assert _is_missing_imports_table_error(exc) is expected


def test_database_initializes_execution_history_table(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    db.initialize()

    with db.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "execution_history" in tables


def test_existing_database_remains_compatible_with_execution_history(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "legacy.db"
    # Create a database with only the projects table
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                root_path TEXT NOT NULL,
                analysis_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO projects VALUES ('p1', 'proj', '/tmp', 'analyzed', '2026-01-01', '2026-01-01')"
        )

    # Initialize should upgrade schema non-destructively
    db = Database(db_file)
    db.initialize()

    with db.connect() as conn:
        row = conn.execute("SELECT name FROM projects WHERE id='p1'").fetchone()
        assert row[0] == "proj"
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "execution_history" in tables


def test_execution_history_records_independent_runs_and_outcomes(
    tmp_path: Path,
) -> None:
    db = Database(tmp_path / "test.db")
    repo = ProjectRepository(db)

    # Run 1: success
    id1 = repo.record_execution_start("analyze", tmp_path)
    repo.record_execution_finish(
        execution_id=id1,
        outcome="success",
        duration_seconds=1.234,
        finished_at="2026-10-28T10:00:02+00:00",
    )

    # Run 2: failed
    id2 = repo.record_execution_start("refresh", tmp_path)
    repo.record_execution_finish(
        execution_id=id2,
        outcome="failed",
        duration_seconds=0.456,
        finished_at="2026-10-28T10:00:05+00:00",
        error_type="RuntimeError",
        error_message="corrupt AST",
    )

    # Run 3: incomplete (process terminated before finish)
    id3 = repo.record_execution_start("analyze", tmp_path)

    history = repo.get_execution_history(repository_path=tmp_path, limit=10)
    assert len(history) == 3

    # All three executions are retained independently
    ids = {rec.id for rec in history}
    assert ids == {id1, id2, id3}

    rec1 = next(r for r in history if r.id == id1)
    assert rec1.command == "analyze"
    assert rec1.outcome == "success"
    assert rec1.duration_seconds == 1.234
    assert rec1.finished_at == "2026-10-28T10:00:02+00:00"

    rec2 = next(r for r in history if r.id == id2)
    assert rec2.command == "refresh"
    assert rec2.outcome == "failed"
    assert rec2.error_type == "RuntimeError"
    assert rec2.error_message == "corrupt AST"

    rec3 = next(r for r in history if r.id == id3)
    assert rec3.command == "analyze"
    assert rec3.outcome == "incomplete"
    assert rec3.finished_at is None
    assert rec3.duration_seconds is None


def test_execution_history_repository_isolation(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repo = ProjectRepository(db)

    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()

    id_a = repo.record_execution_start("analyze", repo_a)
    repo.record_execution_finish(id_a, outcome="success")

    id_b = repo.record_execution_start("refresh", repo_b)
    repo.record_execution_finish(id_b, outcome="success")

    history_a = repo.get_execution_history(repository_path=repo_a)
    history_b = repo.get_execution_history(repository_path=repo_b)

    assert len(history_a) == 1
    assert history_a[0].id == id_a
    assert history_a[0].repository_path == str(repo_a.resolve())

    assert len(history_b) == 1
    assert history_b[0].id == id_b
    assert history_b[0].repository_path == str(repo_b.resolve())


def test_execution_history_deterministic_ordering(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repo = ProjectRepository(db)

    # Insert executions with distinct and tied timestamps
    id_old = repo.record_execution_start(
        "analyze",
        tmp_path,
        execution_id="id-001",
        started_at="2026-10-28T10:00:00+00:00",
    )
    id_mid1 = repo.record_execution_start(
        "analyze",
        tmp_path,
        execution_id="id-002",
        started_at="2026-10-28T10:00:01+00:00",
    )
    id_mid2 = repo.record_execution_start(
        "analyze",
        tmp_path,
        execution_id="id-003",
        started_at="2026-10-28T10:00:01+00:00",
    )
    id_new = repo.record_execution_start(
        "analyze",
        tmp_path,
        execution_id="id-004",
        started_at="2026-10-28T10:00:02+00:00",
    )

    history = repo.get_execution_history(repository_path=tmp_path, limit=10)
    returned_ids = [r.id for r in history]

    # Newest first; on timestamp tie, deterministic id tie-break (DESC)
    assert returned_ids == [id_new, id_mid2, id_mid1, id_old]


def test_execution_history_invalid_limit(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repo = ProjectRepository(db)

    with pytest.raises(ValueError, match="History limit must be a positive integer"):
        repo.get_execution_history(limit=0)

    with pytest.raises(ValueError, match="History limit must be a positive integer"):
        repo.get_execution_history(limit=-5)

    with pytest.raises(ValueError, match="History limit must be a positive integer"):
        repo.get_execution_history(limit=True)  # type: ignore[arg-type]


def test_execution_history_read_only_does_not_create_database(
    tmp_path: Path,
) -> None:
    non_existent = tmp_path / "does_not_exist.db"
    assert not non_existent.exists()

    db = Database(non_existent)
    repo = ProjectRepository(db)

    # Calling get_execution_history must return empty list without creating the database file
    history = repo.get_execution_history(repository_path=tmp_path)
    assert history == []
    assert not non_existent.exists()


def test_execution_history_error_message_bounding(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    repo = ProjectRepository(db)

    long_error = "x" * 1500
    exec_id = repo.record_execution_start("analyze", tmp_path)
    repo.record_execution_finish(
        exec_id,
        outcome="failed",
        error_type="MassiveError",
        error_message=long_error,
    )

    history = repo.get_execution_history(repository_path=tmp_path)
    assert len(history) == 1
    assert len(history[0].error_message) == 500
    assert history[0].error_message == "x" * 500


def test_record_execution_finish_nonexistent_id_and_invalid_outcome(
    tmp_path: Path,
) -> None:
    db = Database(tmp_path / "test.db")
    repo = ProjectRepository(db)
    valid_id = repo.record_execution_start("analyze", tmp_path)

    with pytest.raises(KeyError, match="Execution record not found"):
        repo.record_execution_finish("nonexistent-id", outcome="success")

    # Valid execution must remain untouched in incomplete state
    history = repo.get_execution_history(repository_path=tmp_path)
    assert len(history) == 1
    assert history[0].id == valid_id
    assert history[0].outcome == "incomplete"

    with pytest.raises(ValueError, match="Invalid execution outcome"):
        repo.record_execution_finish(valid_id, outcome="bogus_outcome")


def test_get_execution_history_legacy_database_without_table_is_read_only(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "legacy.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE dummy (id TEXT PRIMARY KEY, val TEXT)")
        conn.execute("INSERT INTO dummy VALUES ('1', 'hello')")

    repo = ProjectRepository(Database(db_file))
    history = repo.get_execution_history(repository_path=tmp_path)
    assert history == []

    # Verify no execution_history table was created
    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "execution_history" not in tables
