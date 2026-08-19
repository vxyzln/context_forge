import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL,
                    repository_url TEXT,
                    default_branch TEXT,
                    project_type TEXT,
                    package_manager TEXT,
                    analysis_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS directories (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    parent_id TEXT,
                    depth INTEGER NOT NULL,
                    directory_type TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                );

                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    directory_id TEXT,
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    is_generated INTEGER NOT NULL,
                    is_ignored INTEGER NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id),
                    FOREIGN KEY (directory_id) REFERENCES directories(id)
                );

                CREATE TABLE IF NOT EXISTS symbols (
                    id TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    qualified_name TEXT,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    parent_symbol_id TEXT,
                    signature TEXT,
                    visibility TEXT,
                    FOREIGN KEY (file_id) REFERENCES files(id)
                );

                CREATE TABLE IF NOT EXISTS relationships (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    metadata TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_directories_project
                ON directories(project_id);

                CREATE INDEX IF NOT EXISTS idx_files_project
                ON files(project_id);

                CREATE INDEX IF NOT EXISTS idx_files_directory
                ON files(directory_id);

                CREATE INDEX IF NOT EXISTS idx_symbols_file
                ON symbols(file_id);

                CREATE INDEX IF NOT EXISTS idx_relationships_source
                ON relationships(source_id);

                CREATE INDEX IF NOT EXISTS idx_relationships_target
                ON relationships(target_id);
                """
            )
