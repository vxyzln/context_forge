from dataclasses import dataclass
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
