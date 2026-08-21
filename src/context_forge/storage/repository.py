import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from context_forge.models.project import Project
from context_forge.storage.database import Database


class ProjectRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, project: Project) -> None:
        with self.database.connect() as connection:
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
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def load(self, project_id: UUID) -> Project | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?",
                (str(project_id),),
            ).fetchone()

        if row is None:
            return None

        return Project(
            name=row["name"],
            root_path=Path(row["root_path"]),
            id=UUID(row["id"]),
            repository_url=row["repository_url"],
            default_branch=row["default_branch"],
            project_type=row["project_type"],
            package_manager=row["package_manager"],
            analysis_status=row["analysis_status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
