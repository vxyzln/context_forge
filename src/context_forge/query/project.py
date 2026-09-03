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

    def get_relationships(
        self,
        entity_id: UUID,
        relationship_type: str | None = None,
    ) -> list[Relationship]:
        relationships = [
            relationship
            for relationship in self.project.relationships
            if (
                relationship.source_id == entity_id
                or relationship.target_id == entity_id
            )
        ]

        if relationship_type is not None:
            relationships = [
                relationship
                for relationship in relationships
                if self._relationship_type_value(relationship) == relationship_type
            ]

        return self._sort_relationships(
            relationships,
            entity_id,
        )

    def get_outgoing_relationships(
        self,
        entity_id: UUID,
        relationship_type: str | None = None,
    ) -> list[Relationship]:
        relationships = [
            relationship
            for relationship in self.project.relationships
            if relationship.source_id == entity_id
        ]

        if relationship_type is not None:
            relationships = [
                relationship
                for relationship in relationships
                if self._relationship_type_value(relationship) == relationship_type
            ]

        return self._sort_relationships(
            relationships,
            entity_id,
        )

    def get_incoming_relationships(
        self,
        entity_id: UUID,
        relationship_type: str | None = None,
    ) -> list[Relationship]:
        relationships = [
            relationship
            for relationship in self.project.relationships
            if relationship.target_id == entity_id
        ]

        if relationship_type is not None:
            relationships = [
                relationship
                for relationship in relationships
                if self._relationship_type_value(relationship) == relationship_type
            ]

        return self._sort_relationships(
            relationships,
            entity_id,
        )

    def get_related_entity_ids(
        self,
        entity_id: UUID,
        relationship_type: str | None = None,
    ) -> set[UUID]:
        related_ids: set[UUID] = set()

        for relationship in self.get_relationships(
            entity_id,
            relationship_type,
        ):
            if relationship.source_id == entity_id:
                related_ids.add(relationship.target_id)
            elif relationship.target_id == entity_id:
                related_ids.add(relationship.source_id)

        return related_ids

    def get_outgoing_entity_ids(
        self,
        entity_id: UUID,
        relationship_type: str | None = None,
    ) -> list[UUID]:
        return [
            relationship.target_id
            for relationship in self.get_outgoing_relationships(
                entity_id,
                relationship_type,
            )
        ]

    def get_incoming_entity_ids(
        self,
        entity_id: UUID,
        relationship_type: str | None = None,
    ) -> list[UUID]:
        return [
            relationship.source_id
            for relationship in self.get_incoming_relationships(
                entity_id,
                relationship_type,
            )
        ]

    def traverse(
        self,
        entity_id: UUID,
        max_depth: int = 1,
        relationship_types: set[str] | None = None,
        direction: str = "both",
    ) -> list[UUID]:
        if max_depth < 0:
            raise ValueError("Traversal depth cannot be negative")

        if direction not in {"outgoing", "incoming", "both"}:
            raise ValueError(
                "Traversal direction must be 'outgoing', 'incoming', or 'both'"
            )

        visited: set[UUID] = {entity_id}
        discovered: list[UUID] = []
        frontier: list[UUID] = [entity_id]

        for _ in range(max_depth):
            next_frontier: list[UUID] = []

            for current_id in frontier:
                if direction == "outgoing":
                    relationships = self.get_outgoing_relationships(current_id)
                elif direction == "incoming":
                    relationships = self.get_incoming_relationships(current_id)
                else:
                    relationships = self.get_relationships(current_id)

                if relationship_types is not None:
                    relationships = [
                        relationship
                        for relationship in relationships
                        if self._relationship_type_value(relationship)
                        in relationship_types
                    ]

                for relationship in relationships:
                    neighbor = self._neighbor_id(
                        relationship,
                        current_id,
                        direction,
                    )

                    if neighbor is None or neighbor in visited:
                        continue

                    visited.add(neighbor)
                    discovered.append(neighbor)
                    next_frontier.append(neighbor)

            frontier = next_frontier

            if not frontier:
                break

        return discovered

    def get_related_entities(
        self,
        entity_id: UUID,
        relationship_type: str | None = None,
    ) -> list[object]:
        entity_ids = self.get_related_entity_ids(
            entity_id,
            relationship_type,
        )

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

    def _neighbor_id(
        self,
        relationship: Relationship,
        entity_id: UUID,
        direction: str,
    ) -> UUID | None:
        if direction == "outgoing":
            if relationship.source_id != entity_id:
                return None
            return relationship.target_id

        if direction == "incoming":
            if relationship.target_id != entity_id:
                return None
            return relationship.source_id

        if relationship.source_id == entity_id:
            return relationship.target_id

        if relationship.target_id == entity_id:
            return relationship.source_id

        return None

    def _sort_relationships(
        self,
        relationships: list[Relationship],
        entity_id: UUID,
    ) -> list[Relationship]:
        return sorted(
            relationships,
            key=lambda relationship: (
                self._relationship_type_value(relationship),
                (
                    relationship.target_id
                    if relationship.source_id == entity_id
                    else relationship.source_id
                ).hex,
                relationship.id.hex,
            ),
        )

    def search(self, query: str) -> list[SearchResult]:
        normalized_query = query.strip().lower()

        if not normalized_query:
            return []

        results: list[SearchResult] = []

        for directory in self.project.directories:
            name = directory.name.lower()
            path = directory.path.as_posix().lower()

            score = 0.0
            reason = None

            if name == normalized_query:
                score = 1.0
                reason = "Exact directory name match"
            elif normalized_query in name:
                score = 0.8
                reason = "Directory name contains query"
            elif normalized_query in path:
                score = 0.5
                reason = "Directory path contains query"

            if score > 0:
                results.append(
                    SearchResult(
                        result_type=SearchResultType.DIRECTORY,
                        entity_id=directory.id,
                        name=directory.name,
                        path=directory.path.as_posix(),
                        score=score,
                        reason=reason,
                    )
                )

        for file in self.project.files:
            name = file.name.lower()
            path = file.path.as_posix().lower()

            score = 0.0
            reason = None

            if name == normalized_query:
                score = 1.0
                reason = "Exact file name match"
            elif normalized_query in name:
                score = 0.8
                reason = "File name contains query"
            elif normalized_query in path:
                score = 0.5
                reason = "File path contains query"

            if score > 0:
                results.append(
                    SearchResult(
                        result_type=SearchResultType.FILE,
                        entity_id=file.id,
                        name=file.name,
                        path=file.path.as_posix(),
                        score=score,
                        reason=reason,
                    )
                )

        file_by_id = {file.id: file for file in self.project.files}

        for symbol in self.project.symbols:
            name = symbol.name.lower()
            qualified_name = (symbol.qualified_name or symbol.name).lower()

            score = 0.0
            reason = None

            if name == normalized_query:
                score = 1.0
                reason = "Exact symbol name match"
            elif qualified_name == normalized_query:
                score = 0.95
                reason = "Exact qualified symbol name match"
            elif normalized_query in name:
                score = 0.8
                reason = "Symbol name contains query"
            elif normalized_query in qualified_name:
                score = 0.7
                reason = "Qualified symbol name contains query"

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
                        reason=reason,
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

    def get_directory(
        self,
        directory: UUID | str,
    ) -> Directory | None:
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

    def get_files_in_directory(
        self,
        directory_id: UUID,
    ) -> list[File]:
        return [
            file for file in self.project.files if file.directory_id == directory_id
        ]

    def get_child_directories(
        self,
        directory_id: UUID,
    ) -> list[Directory]:
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

    def _relationship_type_value(
        self,
        relationship: Relationship,
    ) -> str:
        relationship_type = relationship.relationship_type

        if hasattr(relationship_type, "value"):
            return relationship_type.value

        return relationship_type
