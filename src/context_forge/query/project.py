from uuid import UUID

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol
from context_forge.query.result import SearchResult, SearchResultType
from context_forge.storage.repository import ProjectRepository


class ProjectQuery:
    def __init__(self, project: Project) -> None:
        self.project = project

    @classmethod
    def from_repository(
        cls,
        repository: ProjectRepository,
        project_id: UUID,
    ) -> "ProjectQuery | None":
        project = repository.load(project_id)

        if project is None:
            return None

        return cls(project)

    def get_file(self, path: str) -> File | None:
        normalized_path = path.replace("\\", "/")

        for file in self.project.files:
            if file.path.as_posix() == normalized_path:
                return file

        return None

    def find_symbols(self, name: str) -> list[Symbol]:
        return [symbol for symbol in self.project.symbols if symbol.name == name]

    def find_symbols_in_file(self, file_id: UUID) -> list[Symbol]:
        return [symbol for symbol in self.project.symbols if symbol.file_id == file_id]

    def get_relationships(self, entity_id: UUID) -> list[Relationship]:
        return [
            relationship
            for relationship in self.project.relationships
            if relationship.source_id == entity_id
            or relationship.target_id == entity_id
        ]

    def search(self, query: str) -> list[SearchResult]:
        normalized_query = query.strip().lower()

        if not normalized_query:
            return []

        results: list[SearchResult] = []

        for file in self.project.files:
            if (
                normalized_query in file.name.lower()
                or normalized_query in file.path.as_posix().lower()
            ):
                results.append(
                    SearchResult(
                        result_type=SearchResultType.FILE,
                        entity_id=file.id,
                        name=file.name,
                        path=file.path.as_posix(),
                    )
                )

        file_by_id = {file.id: file for file in self.project.files}

        for symbol in self.project.symbols:
            qualified_name = symbol.qualified_name or symbol.name

            if (
                normalized_query in symbol.name.lower()
                or normalized_query in qualified_name.lower()
            ):
                file = file_by_id.get(symbol.file_id)

                results.append(
                    SearchResult(
                        result_type=SearchResultType.SYMBOL,
                        entity_id=symbol.id,
                        name=symbol.name,
                        path=file.path.as_posix() if file else None,
                        qualified_name=symbol.qualified_name,
                    )
                )

        return results
