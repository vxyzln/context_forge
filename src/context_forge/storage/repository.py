import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from context_forge.git.models import GitActivitySummary
from context_forge.models.directory import Directory
from context_forge.models.enums import DirectoryType, FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol
from context_forge.storage.cache import (
    ANALYZER_VERSION,
    CACHE_SCHEMA_VERSION,
    CacheFreshness,
    FileFingerprint,
    RepositoryCacheMetadata,
    validate_cache_freshness,
)
from context_forge.storage.database import Database


class ProjectRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_cache_metadata(
        self,
        metadata: RepositoryCacheMetadata,
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO repository_cache (
                    repository_key,
                    project_id,
                    cache_schema_version,
                    analyzer_version
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    metadata.repository_key,
                    str(metadata.project_id),
                    metadata.cache_schema_version,
                    metadata.analyzer_version,
                ),
            )

    def load_cache_metadata(
        self,
        repository_key: str,
    ) -> RepositoryCacheMetadata | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    repository_key,
                    project_id,
                    cache_schema_version,
                    analyzer_version
                FROM repository_cache
                WHERE repository_key = ?
                """,
                (repository_key,),
            ).fetchone()

        if row is None:
            return None

        return RepositoryCacheMetadata(
            repository_key=row["repository_key"],
            project_id=UUID(row["project_id"]),
            cache_schema_version=row["cache_schema_version"],
            analyzer_version=row["analyzer_version"],
        )

    def save_file_fingerprints(
        self,
        repository_key: str,
        fingerprints: list[FileFingerprint],
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                DELETE FROM repository_file_fingerprints
                WHERE repository_key = ?
                """,
                (repository_key,),
            )

            for fingerprint in fingerprints:
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
                        repository_key,
                        fingerprint.path.as_posix(),
                        fingerprint.size,
                        fingerprint.modified_at_ns,
                        fingerprint.content_hash,
                    ),
                )

    def load_file_fingerprints(
        self,
        repository_key: str,
    ) -> dict[Path, FileFingerprint]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    path,
                    size,
                    modified_at_ns,
                    content_hash
                FROM repository_file_fingerprints
                WHERE repository_key = ?
                ORDER BY path
                """,
                (repository_key,),
            ).fetchall()

        return {
            Path(row["path"]): FileFingerprint(
                path=Path(row["path"]),
                size=row["size"],
                modified_at_ns=row["modified_at_ns"],
                content_hash=row["content_hash"],
            )
            for row in rows
        }

    def check_cache_freshness(
        self,
        repository_key: str,
        current_fingerprints: dict[Path, FileFingerprint],
    ) -> CacheFreshness:
        metadata = self.load_cache_metadata(repository_key)

        if metadata is None:
            return validate_cache_freshness(
                metadata=None,
                current_schema_version=CACHE_SCHEMA_VERSION,
                current_analyzer_version=ANALYZER_VERSION,
                cached_fingerprints=None,
                current_fingerprints=current_fingerprints,
            )

        cached_fingerprints = self.load_file_fingerprints(repository_key)

        return validate_cache_freshness(
            metadata=metadata,
            current_schema_version=CACHE_SCHEMA_VERSION,
            current_analyzer_version=ANALYZER_VERSION,
            cached_fingerprints=cached_fingerprints,
            current_fingerprints=current_fingerprints,
        )

    def save(self, project: Project) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM analysis_errors WHERE project_id = ?",
                (str(project.id),),
            )

            connection.execute(
                """
                DELETE FROM symbols
                WHERE file_id IN (
                    SELECT id FROM files WHERE project_id = ?
                )
                """,
                (str(project.id),),
            )

            connection.execute(
                """
                DELETE FROM relationships
                WHERE source_id IN (
                    SELECT id FROM files WHERE project_id = ?
                )
                OR target_id IN (
                    SELECT id FROM files WHERE project_id = ?
                )
                """,
                (str(project.id), str(project.id)),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO projects (
                    id,
                    name,
                    root_path,
                    repository_url,
                    default_branch,
                    project_type,
                    package_manager,
                    analysis_status,
                    created_at,
                    updated_at,
                    git_total_commits,
                    git_total_authors,
                    git_files_changed,
                    git_total_additions,
                    git_total_deletions
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(project.id),
                    project.name,
                    str(project.root_path),
                    project.repository_url,
                    project.default_branch,
                    project.project_type,
                    project.package_manager,
                    project.analysis_status,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                    (
                        project.git_activity.total_commits
                        if project.git_activity is not None
                        else None
                    ),
                    (
                        project.git_activity.total_authors
                        if project.git_activity is not None
                        else None
                    ),
                    (
                        project.git_activity.files_changed
                        if project.git_activity is not None
                        else None
                    ),
                    (
                        project.git_activity.total_additions
                        if project.git_activity is not None
                        else None
                    ),
                    (
                        project.git_activity.total_deletions
                        if project.git_activity is not None
                        else None
                    ),
                ),
            )

            for directory in project.directories:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO directories (
                        id,
                        project_id,
                        path,
                        name,
                        parent_id,
                        depth,
                        directory_type
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(directory.id),
                        str(directory.project_id),
                        str(directory.path),
                        directory.name,
                        str(directory.parent_id) if directory.parent_id else None,
                        directory.depth,
                        directory.directory_type.value,
                    ),
                )

            for file in project.files:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO files (
                        id,
                        project_id,
                        directory_id,
                        path,
                        name,
                        extension,
                        file_type,
                        size,
                        is_generated,
                        is_ignored
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(file.id),
                        str(file.project_id),
                        str(file.directory_id) if file.directory_id else None,
                        str(file.path),
                        file.name,
                        file.extension,
                        file.file_type.value,
                        file.size,
                        int(file.is_generated),
                        int(file.is_ignored),
                    ),
                )

            for symbol in project.symbols:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO symbols (
                        id,
                        file_id,
                        name,
                        kind,
                        qualified_name,
                        start_line,
                        end_line,
                        parent_symbol_id,
                        signature
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(symbol.id),
                        str(symbol.file_id),
                        symbol.name,
                        symbol.kind,
                        symbol.qualified_name,
                        symbol.start_line,
                        symbol.end_line,
                        str(symbol.parent_symbol_id)
                        if symbol.parent_symbol_id
                        else None,
                        symbol.signature,
                    ),
                )

            for relationship in project.relationships:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO relationships (
                        id,
                        source_id,
                        target_id,
                        relationship_type,
                        confidence,
                        metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(relationship.id),
                        str(relationship.source_id),
                        str(relationship.target_id),
                        relationship.relationship_type,
                        relationship.confidence,
                        json.dumps(relationship.metadata),
                    ),
                )
            for error in project.errors:
                connection.execute(
                    """
                    INSERT INTO analysis_errors (
                        project_id,
                        message
                    )
                    VALUES (?, ?)
                    """,
                    (
                        str(project.id),
                        error,
                    ),
                )

    def save_analysis(
        self,
        project: Project,
        metadata: RepositoryCacheMetadata,
        fingerprints: list[FileFingerprint] | None = None,
    ) -> None:
        self.save(project)
        self.save_cache_metadata(metadata)

        if fingerprints is not None:
            self.save_file_fingerprints(metadata.repository_key, fingerprints)

    def load_analysis(
        self,
        repository_key: str,
    ) -> tuple[Project, RepositoryCacheMetadata] | None:
        metadata = self.load_cache_metadata(repository_key)

        if metadata is None:
            return None

        project = self.load(metadata.project_id)

        if project is None:
            return None

        return project, metadata

    def load(self, project_id: UUID) -> Project | None:
        with self.database.connect() as connection:
            project_row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (str(project_id),),
            ).fetchone()

            if project_row is None:
                return None

            directory_rows = connection.execute(
                """
                SELECT *
                FROM directories
                WHERE project_id = ?
                ORDER BY depth, path
                """,
                (str(project_id),),
            ).fetchall()

            file_rows = connection.execute(
                """
                SELECT *
                FROM files
                WHERE project_id = ?
                ORDER BY path
                """,
                (str(project_id),),
            ).fetchall()

            file_ids = [row["id"] for row in file_rows]

            symbol_rows = []
            if file_ids:
                placeholders = ",".join("?" for _ in file_ids)
                symbol_rows = connection.execute(
                    f"""
                    SELECT *
                    FROM symbols
                    WHERE file_id IN ({placeholders})
                    ORDER BY file_id, start_line
                    """,
                    file_ids,
                ).fetchall()

            relationship_rows = connection.execute(
                """
                SELECT *
                FROM relationships
                WHERE source_id IN (
                    SELECT id FROM files WHERE project_id = ?
                )
                OR target_id IN (
                    SELECT id FROM files WHERE project_id = ?
                )
                """,
                (str(project_id), str(project_id)),
            ).fetchall()

            error_rows = connection.execute(
                """
                SELECT message
                FROM analysis_errors
                WHERE project_id = ?
                ORDER BY id
                """,
                (str(project_id),),
            ).fetchall()

        git_activity = None

        if project_row["git_total_commits"] is not None:
            git_activity = GitActivitySummary(
                total_commits=project_row["git_total_commits"],
                total_authors=project_row["git_total_authors"],
                files_changed=project_row["git_files_changed"],
                total_additions=project_row["git_total_additions"],
                total_deletions=project_row["git_total_deletions"],
            )

        project = Project(
            name=project_row["name"],
            root_path=Path(project_row["root_path"]),
            id=UUID(project_row["id"]),
            repository_url=project_row["repository_url"],
            default_branch=project_row["default_branch"],
            project_type=project_row["project_type"],
            package_manager=project_row["package_manager"],
            analysis_status=project_row["analysis_status"],
            created_at=datetime.fromisoformat(project_row["created_at"]),
            updated_at=datetime.fromisoformat(project_row["updated_at"]),
            git_activity=git_activity,
        )

        for row in directory_rows:
            directory = Directory(
                project_id=UUID(row["project_id"]),
                path=Path(row["path"]),
                name=row["name"],
                id=UUID(row["id"]),
                parent_id=UUID(row["parent_id"]) if row["parent_id"] else None,
                depth=row["depth"],
                directory_type=DirectoryType(row["directory_type"]),
            )
            project.add_directory(directory)

        for row in file_rows:
            file = File(
                project_id=UUID(row["project_id"]),
                path=Path(row["path"]),
                name=row["name"],
                extension=row["extension"],
                id=UUID(row["id"]),
                directory_id=UUID(row["directory_id"]) if row["directory_id"] else None,
                file_type=FileType(row["file_type"]),
                size=row["size"],
                is_generated=bool(row["is_generated"]),
                is_ignored=bool(row["is_ignored"]),
            )
            project.add_file(file)

        for row in symbol_rows:
            symbol = Symbol(
                file_id=UUID(row["file_id"]),
                name=row["name"],
                kind=row["kind"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                id=UUID(row["id"]),
                qualified_name=row["qualified_name"],
                parent_symbol_id=(
                    UUID(row["parent_symbol_id"]) if row["parent_symbol_id"] else None
                ),
                signature=row["signature"],
            )
            project.add_symbol(symbol)

        for row in relationship_rows:
            relationship = Relationship(
                source_id=UUID(row["source_id"]),
                target_id=UUID(row["target_id"]),
                relationship_type=row["relationship_type"],
                id=UUID(row["id"]),
                confidence=row["confidence"],
                metadata=json.loads(row["metadata"]),
            )
            project.add_relationship(relationship)

        project.errors.extend(row["message"] for row in error_rows)

        return project
