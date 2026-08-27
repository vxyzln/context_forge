from uuid import UUID

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol
from context_forge.query.result import SearchResult, SearchResultType


class ProjectQuery:
    def __init__(self, project: Project) -> None:
        self.project = project

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

    def get_related_entity_ids(self, entity_id: UUID) -> set[UUID]:
        related_ids: set[UUID] = set()

        for relationship in self.project.relationships:
            if relationship.source_id == entity_id:
                related_ids.add(relationship.target_id)
            elif relationship.target_id == entity_id:
                related_ids.add(relationship.source_id)

        return related_ids

    def get_related_entities(self, entity_id: UUID) -> list[object]:
        entity_ids = self.get_related_entity_ids(entity_id)

        entities: list[object] = []

        for file in self.project.files:
            if file.id in entity_ids:
                entities.append(file)

        for directory in self.project.directories:
            if directory.id in entity_ids:
                entities.append(directory)

        for symbol in self.project.symbols:
            if symbol.id in entity_ids:
                entities.append(symbol)

        return entities

    def search(self, query: str) -> list[SearchResult]:
        normalized_query = query.strip().lower()

        if not normalized_query:
            return []

        results: list[SearchResult] = []

        for directory in self.project.directories:
            name = directory.name.lower()
            path = directory.path.as_posix().lower()

            score = 0.0

            if name == normalized_query:
                score = 1.0
            elif normalized_query in name:
                score = 0.8
            elif normalized_query in path:
                score = 0.5

            if score > 0:
                results.append(
                    SearchResult(
                        result_type=SearchResultType.DIRECTORY,
                        entity_id=directory.id,
                        name=directory.name,
                        path=directory.path.as_posix(),
                        score=score,
                    )
                )

        for file in self.project.files:
            name = file.name.lower()
            path = file.path.as_posix().lower()

            score = 0.0

            if name == normalized_query:
                score = 1.0
            elif normalized_query in name:
                score = 0.8
            elif normalized_query in path:
                score = 0.5

            if score > 0:
                results.append(
                    SearchResult(
                        result_type=SearchResultType.FILE,
                        entity_id=file.id,
                        name=file.name,
                        path=file.path.as_posix(),
                        score=score,
                    )
                )

        file_by_id = {file.id: file for file in self.project.files}

        for symbol in self.project.symbols:
            name = symbol.name.lower()
            qualified_name = (symbol.qualified_name or symbol.name).lower()

            score = 0.0

            if name == normalized_query:
                score = 1.0
            elif qualified_name == normalized_query:
                score = 0.95
            elif normalized_query in name:
                score = 0.8
            elif normalized_query in qualified_name:
                score = 0.7

            if score > 0:
                file = file_by_id.get(symbol.file_id)

                results.append(
                    SearchResult(
                        result_type=SearchResultType.SYMBOL,
                        entity_id=symbol.id,
                        name=symbol.name,
                        path=file.path.as_posix() if file else None,
                        qualified_name=symbol.qualified_name,
                        score=score,
                    )
                )

        results.sort(
            key=lambda result: (
                -result.score,
                result.result_type.value,
                result.name.lower(),
                result.path or "",
            )
        )

        return results

    def get_directory(self, directory: UUID | str) -> Directory | None:
        if isinstance(directory, UUID):
            return next(
                (item for item in self.project.directories if item.id == directory),
                None,
            )

        normalized_path = directory.replace("\\", "/")

        return next(
            (
                item
                for item in self.project.directories
                if item.path.as_posix() == normalized_path
            ),
            None,
        )

    def get_files_in_directory(self, directory_id: UUID) -> list[File]:
        return [
            file for file in self.project.files if file.directory_id == directory_id
        ]

    def get_child_directories(self, directory_id: UUID) -> list[Directory]:
        return [
            directory
            for directory in self.project.directories
            if directory.parent_id == directory_id
        ]

    def get_summary(self) -> dict[str, int]:
        return {
            "directories": len(self.project.directories),
            "files": len(self.project.files),
            "symbols": len(self.project.symbols),
            "imports": len(self.project.imports),
            "relationships": len(self.project.relationships),
            "errors": len(self.project.errors),
        }
