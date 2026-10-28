from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from context_forge.graph.builder import RelationshipBuilder
from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.pipeline.freshness import (
    FreshnessState,
    WorkflowFreshness,
    WorkflowFreshnessGuard,
)

if TYPE_CHECKING:
    from context_forge.inspection.models import PreChangeInspectionResult
from context_forge.query.architecture import (
    ArchitectureInventory,
    ContainmentEdge,
    StructuralIntegrityFinding,
    UnresolvedImport,
)
from context_forge.query.changeset import (
    ChangeSetImpactResult,
    analyze_changeset,
)
from context_forge.query.health import DEFAULT_HEALTH_LIMIT, build_health_report
from context_forge.query.impact import (
    DEFAULT_IMPACT_LIMIT,
    DEFAULT_IMPACT_MAX_DEPTH,
    DirectImpactResult,
    ImpactResult,
    ResolvedTarget,
    TargetResolution,
    find_direct_impact,
    find_impact,
    resolve_impact_target,
)
from context_forge.query.locator import (
    DEFAULT_EXCERPT_MAX_LINES,
    SourceExcerpt,
    get_source_evidence,
    locate_and_get_evidence,
    locate_symbol,
)
from context_forge.query.package_boundary import (
    PackageBoundaryReport,
    analyze_package_boundaries,
)
from context_forge.query.path import (
    DEFAULT_PATH_MAX_DEPTH,
    DEFAULT_PATH_MAX_EXPANSIONS,
    RelationshipPathResult,
    find_relationship_path,
)
from context_forge.query.post_change import (
    PostChangeVerificationReport,
    run_post_change_verification,
)
from context_forge.query.regression_rules import (
    StructuralRulesReport,
    evaluate_structural_rules,
)
from context_forge.query.result import SearchResult, SearchResultType
from context_forge.query.risk import (
    ChangeRiskReport,
    generate_change_risk_report,
)
from context_forge.query.unused import (
    DEFAULT_UNUSED_LIMIT,
    UnusedEntitiesReport,
    find_unused_candidates,
)
from context_forge.query.verification import (
    VerificationChecklist,
    generate_verification_checklist,
)
from context_forge.reporting.contract import DiagnosticItem, OperationOutcome
from context_forge.storage.cache import (
    CacheFreshness,
    FileFingerprint,
    RepositoryCacheMetadata,
)


class ProjectQuery:
    def __init__(self, project: Project) -> None:
        self.project = project

    def get_file(self, path: str) -> File | None:
        normalized_path = path.replace("\\", "/").strip()
        normalized_path = normalized_path.removeprefix("./")

        root_path = getattr(self.project, "root_path", None)
        if root_path is not None:
            as_path = Path(path)
            if as_path.is_absolute():
                try:
                    normalized_path = (
                        as_path.resolve()
                        .relative_to(Path(root_path).resolve())
                        .as_posix()
                    )
                except ValueError:
                    return None

        for file in self.project.files:
            if file.path.as_posix() == normalized_path:
                return file

        return None

    def find_symbols(self, name: str) -> list[Symbol]:
        return [symbol for symbol in self.project.symbols if symbol.name == name]

    def find_symbols_by_qualified_name(self, qualified_name: str) -> list[Symbol]:
        return [
            symbol
            for symbol in self.project.symbols
            if symbol.qualified_name == qualified_name
        ]

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

    def get_direct_dependencies(self, file_id: UUID) -> list[File]:
        dependency_ids = {
            relationship.target_id
            for relationship in self.get_outgoing_relationships(
                file_id,
                relationship_type=RelationshipType.IMPORTS.value,
            )
        }

        return sorted(
            (file for file in self.project.files if file.id in dependency_ids),
            key=lambda file: file.path.as_posix(),
        )

    def get_direct_dependents(self, file_id: UUID) -> list[File]:
        dependent_ids = {
            relationship.source_id
            for relationship in self.get_incoming_relationships(
                file_id,
                relationship_type=RelationshipType.IMPORTS.value,
            )
        }

        return sorted(
            (file for file in self.project.files if file.id in dependent_ids),
            key=lambda file: file.path.as_posix(),
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
        normalized_query = query.strip().replace("\\", "/").lower()

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
            elif path == normalized_query:
                score = 1.0
                reason = "Exact directory path match"
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
            elif path == normalized_query:
                score = 1.0
                reason = "Exact file path match"
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
                result.entity_id.hex,
            )
        )

        return results

    def get_architecture_inventory(
        self,
        entity_types: set[str] | None = None,
    ) -> ArchitectureInventory:
        supported_types = {"directory", "file", "symbol"}

        if entity_types is not None:
            unsupported_types = entity_types - supported_types

            if unsupported_types:
                unsupported = ", ".join(sorted(unsupported_types))
                raise ValueError(
                    f"Unsupported architecture entity types: {unsupported}"
                )

        selected_types = supported_types if entity_types is None else entity_types

        directories = tuple(
            sorted(
                (
                    directory
                    for directory in self.project.directories
                    if "directory" in selected_types
                ),
                key=lambda directory: (
                    directory.path.as_posix(),
                    directory.id.hex,
                ),
            )
        )

        files = tuple(
            sorted(
                (file for file in self.project.files if "file" in selected_types),
                key=lambda file: (
                    file.path.as_posix(),
                    file.id.hex,
                ),
            )
        )

        symbols = tuple(
            sorted(
                (
                    symbol
                    for symbol in self.project.symbols
                    if "symbol" in selected_types
                ),
                key=lambda symbol: (
                    symbol.qualified_name or symbol.name,
                    symbol.name,
                    symbol.file_id.hex,
                    symbol.id.hex,
                ),
            )
        )

        entity_types_by_id = {
            entity.id: entity_type
            for entity_type, entities in (
                ("directory", directories),
                ("file", files),
                ("symbol", symbols),
            )
            for entity in entities
        }

        entity_paths_by_id = {
            directory.id: directory.path.as_posix() for directory in directories
        }
        entity_paths_by_id.update({file.id: file.path.as_posix() for file in files})

        file_by_id = {file.id: file for file in files}

        for symbol in symbols:
            file = file_by_id.get(symbol.file_id)
            if file is not None:
                entity_paths_by_id[symbol.id] = (
                    f"{file.path.as_posix()}::{symbol.qualified_name or symbol.name}"
                )

        containment_edges: set[ContainmentEdge] = set()

        if "directory" in selected_types:
            for directory in directories:
                if (
                    directory.parent_id in entity_types_by_id
                    and entity_types_by_id[directory.parent_id] == "directory"
                ):
                    containment_edges.add(
                        ContainmentEdge(
                            source_type="directory",
                            source_id=directory.parent_id,
                            target_type="directory",
                            target_id=directory.id,
                        )
                    )

        if "directory" in selected_types and "file" in selected_types:
            for file in files:
                if (
                    file.directory_id in entity_types_by_id
                    and entity_types_by_id[file.directory_id] == "directory"
                ):
                    containment_edges.add(
                        ContainmentEdge(
                            source_type="directory",
                            source_id=file.directory_id,
                            target_type="file",
                            target_id=file.id,
                        )
                    )

        structural_relationship_types = {
            RelationshipType.DEFINES.value,
            RelationshipType.CONTAINS.value,
        }

        for relationship in self.project.relationships:
            relationship_type = self._relationship_type_value(relationship)

            if relationship_type not in structural_relationship_types:
                continue

            source_type = entity_types_by_id.get(relationship.source_id)
            target_type = entity_types_by_id.get(relationship.target_id)

            if source_type is None or target_type is None:
                continue

            if relationship_type == RelationshipType.DEFINES.value and (
                source_type != "file" or target_type != "symbol"
            ):
                continue

            if relationship_type == RelationshipType.CONTAINS.value and (
                source_type != "symbol" or target_type != "symbol"
            ):
                continue

            containment_edges.add(
                ContainmentEdge(
                    source_type=source_type,
                    source_id=relationship.source_id,
                    target_type=target_type,
                    target_id=relationship.target_id,
                )
            )

        containment = tuple(
            sorted(
                containment_edges,
                key=lambda edge: (
                    edge.source_type,
                    entity_paths_by_id.get(edge.source_id, ""),
                    edge.target_type,
                    entity_paths_by_id.get(edge.target_id, ""),
                    edge.source_id.hex,
                    edge.target_id.hex,
                ),
            )
        )

        all_files_by_id = {file.id: file for file in self.project.files}

        dependencies = tuple(
            sorted(
                (
                    relationship
                    for relationship in self.project.relationships
                    if self._relationship_type_value(relationship)
                    == RelationshipType.IMPORTS.value
                    and relationship.source_id in all_files_by_id
                    and relationship.target_id in all_files_by_id
                ),
                key=lambda relationship: (
                    all_files_by_id[relationship.source_id].path.as_posix(),
                    all_files_by_id[relationship.target_id].path.as_posix(),
                    relationship.id.hex,
                ),
            )
        )

        builder = RelationshipBuilder()
        file_by_module = builder.build_module_index(self.project)

        unresolved_imports_list: list[UnresolvedImport] = []
        integrity_findings_list: list[StructuralIntegrityFinding] = []

        if self.project.analysis_status != "analyzed":
            integrity_findings_list.append(
                StructuralIntegrityFinding(
                    finding_type="incomplete_analysis",
                    message=(
                        f"Project analysis status is '{self.project.analysis_status}'; "
                        "structural findings may be incomplete."
                    ),
                    source_type="project",
                    source_id=self.project.id,
                    source_path=(
                        self.project.root_path.as_posix()
                        if self.project.root_path
                        else None
                    ),
                )
            )

        for import_reference in self.project.imports:
            source_file = all_files_by_id.get(import_reference.file_id)
            if source_file is None:
                integrity_findings_list.append(
                    StructuralIntegrityFinding(
                        finding_type="missing_import_file",
                        message=(
                            f"Import '{import_reference.module_name}' references "
                            f"non-existent file {import_reference.file_id}."
                        ),
                        source_type="file",
                        source_id=import_reference.file_id,
                    )
                )
                continue

            target = builder.resolve_import_target(
                self.project,
                import_reference,
                file_by_module,
            )

            if target is None:
                unresolved_imports_list.append(
                    UnresolvedImport(
                        file_id=import_reference.file_id,
                        module_name=import_reference.module_name,
                        imported_name=import_reference.imported_name,
                        alias=import_reference.alias,
                        level=import_reference.level,
                        source_path=source_file.path,
                    )
                )

        unresolved_imports = tuple(
            sorted(
                unresolved_imports_list,
                key=lambda item: (
                    item.source_path.as_posix() if item.source_path else "",
                    item.file_id.hex,
                    item.module_name,
                    item.imported_name or "",
                    item.alias or "",
                    item.level,
                ),
            )
        )

        entity_types_by_id_all: dict[UUID, str] = {}
        for directory in self.project.directories:
            entity_types_by_id_all[directory.id] = "directory"
        for file in self.project.files:
            entity_types_by_id_all[file.id] = "file"
        for symbol in self.project.symbols:
            entity_types_by_id_all[symbol.id] = "symbol"

        symbols_by_id = {symbol.id: symbol for symbol in self.project.symbols}

        for directory in self.project.directories:
            if directory.parent_id is not None:
                parent_type = entity_types_by_id_all.get(directory.parent_id)
                if parent_type is None:
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="missing_directory_parent",
                            message=(
                                f"Directory '{directory.path.as_posix()}' references "
                                f"non-existent parent directory {directory.parent_id}."
                            ),
                            source_type="directory",
                            source_id=directory.id,
                            source_path=directory.path.as_posix(),
                            target_type="directory",
                            target_id=directory.parent_id,
                        )
                    )
                elif parent_type != "directory":
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="invalid_directory_parent_type",
                            message=(
                                f"Directory '{directory.path.as_posix()}' references "
                                f"{parent_type} ({directory.parent_id}) as parent directory."
                            ),
                            source_type="directory",
                            source_id=directory.id,
                            source_path=directory.path.as_posix(),
                            target_type=parent_type,
                            target_id=directory.parent_id,
                        )
                    )

        for file in self.project.files:
            if file.directory_id is not None:
                dir_type = entity_types_by_id_all.get(file.directory_id)
                if dir_type is None:
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="missing_file_directory",
                            message=(
                                f"File '{file.path.as_posix()}' references "
                                f"non-existent directory {file.directory_id}."
                            ),
                            source_type="file",
                            source_id=file.id,
                            source_path=file.path.as_posix(),
                            target_type="directory",
                            target_id=file.directory_id,
                        )
                    )
                elif dir_type != "directory":
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="invalid_file_directory_type",
                            message=(
                                f"File '{file.path.as_posix()}' references "
                                f"{dir_type} ({file.directory_id}) as directory."
                            ),
                            source_type="file",
                            source_id=file.id,
                            source_path=file.path.as_posix(),
                            target_type=dir_type,
                            target_id=file.directory_id,
                        )
                    )

        for symbol in self.project.symbols:
            file_type = entity_types_by_id_all.get(symbol.file_id)
            if file_type is None:
                integrity_findings_list.append(
                    StructuralIntegrityFinding(
                        finding_type="missing_symbol_file",
                        message=(
                            f"Symbol '{symbol.qualified_name or symbol.name}' "
                            f"references non-existent file {symbol.file_id}."
                        ),
                        source_type="symbol",
                        source_id=symbol.id,
                        source_path=symbol.qualified_name or symbol.name,
                        target_type="file",
                        target_id=symbol.file_id,
                    )
                )
            elif file_type != "file":
                integrity_findings_list.append(
                    StructuralIntegrityFinding(
                        finding_type="invalid_symbol_file_type",
                        message=(
                            f"Symbol '{symbol.qualified_name or symbol.name}' "
                            f"references {file_type} ({symbol.file_id}) as file."
                        ),
                        source_type="symbol",
                        source_id=symbol.id,
                        source_path=symbol.qualified_name or symbol.name,
                        target_type=file_type,
                        target_id=symbol.file_id,
                    )
                )

            if symbol.parent_symbol_id is not None:
                parent_type = entity_types_by_id_all.get(symbol.parent_symbol_id)
                if parent_type is None:
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="missing_parent_symbol",
                            message=(
                                f"Symbol '{symbol.qualified_name or symbol.name}' "
                                f"references non-existent parent symbol {symbol.parent_symbol_id}."
                            ),
                            source_type="symbol",
                            source_id=symbol.id,
                            source_path=symbol.qualified_name or symbol.name,
                            target_type="symbol",
                            target_id=symbol.parent_symbol_id,
                        )
                    )
                elif parent_type != "symbol":
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="invalid_parent_symbol_type",
                            message=(
                                f"Symbol '{symbol.qualified_name or symbol.name}' "
                                f"references {parent_type} ({symbol.parent_symbol_id}) as parent symbol."
                            ),
                            source_type="symbol",
                            source_id=symbol.id,
                            source_path=symbol.qualified_name or symbol.name,
                            target_type=parent_type,
                            target_id=symbol.parent_symbol_id,
                        )
                    )
                else:
                    parent_symbol = symbols_by_id[symbol.parent_symbol_id]
                    if parent_symbol.file_id != symbol.file_id:
                        integrity_findings_list.append(
                            StructuralIntegrityFinding(
                                finding_type="inconsistent_symbol_parent",
                                message=(
                                    f"Symbol '{symbol.qualified_name or symbol.name}' "
                                    f"in file {symbol.file_id} references parent symbol "
                                    f"{symbol.parent_symbol_id} in different file {parent_symbol.file_id}."
                                ),
                                source_type="symbol",
                                source_id=symbol.id,
                                source_path=symbol.qualified_name or symbol.name,
                                target_type="symbol",
                                target_id=symbol.parent_symbol_id,
                            )
                        )

        for relationship in self.project.relationships:
            rel_type = self._relationship_type_value(relationship)

            if rel_type == RelationshipType.DEFINES.value:
                source_type = entity_types_by_id_all.get(relationship.source_id)
                target_type = entity_types_by_id_all.get(relationship.target_id)

                if source_type is None:
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="missing_relationship_endpoint",
                            message=(
                                f"DEFINES relationship {relationship.id} "
                                f"references non-existent source file {relationship.source_id}."
                            ),
                            source_type="file",
                            source_id=relationship.source_id,
                            target_type=target_type or "symbol",
                            target_id=relationship.target_id,
                        )
                    )
                if target_type is None:
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="missing_relationship_endpoint",
                            message=(
                                f"DEFINES relationship {relationship.id} "
                                f"references non-existent target symbol {relationship.target_id}."
                            ),
                            source_type=source_type or "file",
                            source_id=relationship.source_id,
                            target_type="symbol",
                            target_id=relationship.target_id,
                        )
                    )
                if (
                    source_type is not None
                    and target_type is not None
                    and (source_type != "file" or target_type != "symbol")
                ):
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="invalid_relationship_endpoint_type",
                            message=(
                                f"DEFINES relationship {relationship.id} requires "
                                f"file -> symbol endpoints, but connects {source_type} "
                                f"({relationship.source_id}) to {target_type} ({relationship.target_id})."
                            ),
                            source_type=source_type,
                            source_id=relationship.source_id,
                            target_type=target_type,
                            target_id=relationship.target_id,
                        )
                    )

            elif rel_type == RelationshipType.CONTAINS.value:
                source_type = entity_types_by_id_all.get(relationship.source_id)
                target_type = entity_types_by_id_all.get(relationship.target_id)

                if source_type is None:
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="missing_relationship_endpoint",
                            message=(
                                f"CONTAINS relationship {relationship.id} "
                                f"references non-existent source symbol {relationship.source_id}."
                            ),
                            source_type="symbol",
                            source_id=relationship.source_id,
                            target_type=target_type or "symbol",
                            target_id=relationship.target_id,
                        )
                    )
                if target_type is None:
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="missing_relationship_endpoint",
                            message=(
                                f"CONTAINS relationship {relationship.id} "
                                f"references non-existent target symbol {relationship.target_id}."
                            ),
                            source_type=source_type or "symbol",
                            source_id=relationship.source_id,
                            target_type="symbol",
                            target_id=relationship.target_id,
                        )
                    )
                if (
                    source_type is not None
                    and target_type is not None
                    and (source_type != "symbol" or target_type != "symbol")
                ):
                    integrity_findings_list.append(
                        StructuralIntegrityFinding(
                            finding_type="invalid_relationship_endpoint_type",
                            message=(
                                f"CONTAINS relationship {relationship.id} requires "
                                f"symbol -> symbol endpoints, but connects {source_type} "
                                f"({relationship.source_id}) to {target_type} ({relationship.target_id})."
                            ),
                            source_type=source_type,
                            source_id=relationship.source_id,
                            target_type=target_type,
                            target_id=relationship.target_id,
                        )
                    )

        integrity_findings = tuple(
            sorted(
                integrity_findings_list,
                key=lambda finding: (
                    finding.finding_type,
                    finding.source_type or "",
                    finding.source_path or "",
                    finding.source_id.hex if finding.source_id else "",
                    finding.target_type or "",
                    finding.target_id.hex if finding.target_id else "",
                    finding.message,
                ),
            )
        )

        return ArchitectureInventory(
            project_id=self.project.id,
            analysis_status=self.project.analysis_status,
            errors=tuple(self.project.errors),
            directories=directories,
            files=files,
            symbols=symbols,
            containment=containment,
            dependencies=dependencies,
            unresolved_imports=unresolved_imports,
            integrity_findings=integrity_findings,
        )

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

    def resolve_target(
        self,
        target: str | File | Symbol,
    ) -> TargetResolution:
        return resolve_impact_target(self.project, target)

    def find_direct_impact(
        self,
        target: str | File | Symbol,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        target_types: set[str] | None = None,
        limit: int | None = None,
    ) -> DirectImpactResult:
        return find_direct_impact(
            self.project,
            target,
            direction=direction,
            relationship_types=relationship_types,
            target_types=target_types,
            limit=limit,
        )

    def find_impact(
        self,
        target: str | File | Symbol,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        target_types: set[str] | None = None,
        max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
        limit: int | None = DEFAULT_IMPACT_LIMIT,
    ) -> ImpactResult:
        return find_impact(
            self.project,
            target,
            direction=direction,
            relationship_types=relationship_types,
            target_types=target_types,
            max_depth=max_depth,
            limit=limit,
        )

    def find_transitive_impact(
        self,
        target: str | File | Symbol,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        target_types: set[str] | None = None,
        max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
        limit: int | None = DEFAULT_IMPACT_LIMIT,
    ) -> ImpactResult:
        return self.find_impact(
            target,
            direction=direction,
            relationship_types=relationship_types,
            target_types=target_types,
            max_depth=max_depth,
            limit=limit,
        )

    def analyze_changeset(
        self,
        paths: Any,
        *,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
        limit: int | None = DEFAULT_IMPACT_LIMIT,
        include_checklist: bool = False,
    ) -> ChangeSetImpactResult:
        return analyze_changeset(
            self.project,
            paths,
            direction=direction,
            relationship_types=relationship_types,
            max_depth=max_depth,
            limit=limit,
            include_checklist=include_checklist,
        )

    def generate_verification_checklist(
        self,
        paths: Any,
        *,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
        limit: int | None = DEFAULT_IMPACT_LIMIT,
    ) -> VerificationChecklist:
        return generate_verification_checklist(
            self.project,
            paths,
            direction=direction,
            relationship_types=relationship_types,
            max_depth=max_depth,
            limit=limit,
        )

    def generate_change_risk_report(
        self,
        paths: Any,
        *,
        comparison: Any | None = None,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
        limit: int | None = DEFAULT_IMPACT_LIMIT,
        policy: Any | None = None,
    ) -> ChangeRiskReport:
        return generate_change_risk_report(
            self.project,
            paths,
            comparison=comparison,
            direction=direction,
            relationship_types=relationship_types,
            max_depth=max_depth,
            limit=limit,
            policy=policy,
        )

    def analyze_package_boundaries(
        self,
        *,
        policy: Any | None = None,
        limit: int = 50,
        relationship_types: set[str] | None = None,
    ) -> PackageBoundaryReport:
        return analyze_package_boundaries(
            self.project,
            policy=policy,
            limit=limit,
            relationship_types=relationship_types,
        )

    def evaluate_structural_rules(
        self,
        rules: Any,
        *,
        limit: int | None = None,
        package_policy: Any | None = None,
    ) -> StructuralRulesReport:
        return evaluate_structural_rules(
            self.project,
            rules,
            limit=limit,
            package_policy=package_policy,
        )

    def run_post_change_verification(
        self,
        paths: Any | None = None,
        *,
        before_state: Any | None = None,
        rules: Any | None = None,
        package_policy: Any | None = None,
        allow_refresh: bool = True,
        limit: int = 50,
        max_depth: int = 5,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        freshness: Any | None = None,
        guard: Any | None = None,
    ) -> PostChangeVerificationReport:
        return run_post_change_verification(
            self.project,
            paths=paths,
            before_state=before_state,
            rules=rules,
            package_policy=package_policy,
            allow_refresh=allow_refresh,
            limit=limit,
            max_depth=max_depth,
            direction=direction,
            relationship_types=relationship_types,
            freshness=freshness,
            guard=guard,
        )

    def find_relationship_path(
        self,
        start: str | File | Symbol,
        end: str | File | Symbol,
        *,
        direction: str = "both",
        relationship_types: set[str] | None = None,
        max_depth: int = DEFAULT_PATH_MAX_DEPTH,
        max_expansions: int | None = DEFAULT_PATH_MAX_EXPANSIONS,
    ) -> RelationshipPathResult:
        return find_relationship_path(
            self.project,
            start,
            end,
            direction=direction,
            relationship_types=relationship_types,
            max_depth=max_depth,
            max_expansions=max_expansions,
        )

    def get_health_report(
        self,
        metadata: RepositoryCacheMetadata | None = None,
        freshness: CacheFreshness | None = None,
        limit: int = DEFAULT_HEALTH_LIMIT,
    ) -> dict[str, Any]:
        return build_health_report(
            project=self.project,
            repository_path=self.project.root_path,
            metadata=metadata,
            freshness=freshness,
            limit=limit,
        )

    def locate_symbol(
        self,
        name: str,
        *,
        file_path: str | Path | None = None,
        symbol_type: str | None = None,
        qualified_name: str | None = None,
    ) -> TargetResolution:
        return locate_symbol(
            self.project,
            name,
            file_path=file_path,
            symbol_type=symbol_type,
            qualified_name=qualified_name,
        )

    def get_source_evidence(
        self,
        target: ResolvedTarget | Symbol,
        *,
        root_path: Path | None = None,
        max_lines: int = DEFAULT_EXCERPT_MAX_LINES,
    ) -> SourceExcerpt:
        return get_source_evidence(
            self.project,
            target,
            root_path=root_path,
            max_lines=max_lines,
        )

    def locate_and_get_evidence(
        self,
        name: str,
        *,
        file_path: str | Path | None = None,
        symbol_type: str | None = None,
        qualified_name: str | None = None,
        root_path: Path | None = None,
        max_lines: int = DEFAULT_EXCERPT_MAX_LINES,
    ) -> tuple[TargetResolution, SourceExcerpt | None]:
        return locate_and_get_evidence(
            self.project,
            name,
            file_path=file_path,
            symbol_type=symbol_type,
            qualified_name=qualified_name,
            root_path=root_path,
            max_lines=max_lines,
        )

    def assess_freshness(
        self,
        *,
        metadata: RepositoryCacheMetadata | None = None,
        current_fingerprints: dict[Path, FileFingerprint] | None = None,
        database_path: Path | None = None,
    ) -> WorkflowFreshness:
        root = self.project.root_path
        if root is None:
            diag = DiagnosticItem.blocker(
                "Project has no root_path configured; cannot assess freshness",
                code="MISSING_ROOT_PATH",
                source="project",
            )
            return WorkflowFreshness(
                state=FreshnessState.INDETERMINATE,
                reason="missing_root_path",
                project=self.project,
                metadata=metadata,
                diagnostics=(diag,),
                limitations=(
                    "Project has no root_path; freshness cannot be assessed.",
                ),
                outcome=OperationOutcome.blocked(
                    "Project has no root_path configured",
                    diagnostics=(diag,),
                    limitations=(
                        "Project has no root_path; freshness cannot be assessed.",
                    ),
                ),
            )

        guard = WorkflowFreshnessGuard(root, database_path=database_path)
        return guard.assess_freshness(
            project=self.project,
            metadata=metadata,
            current_fingerprints=current_fingerprints,
        )

    def navigate_git(
        self,
        *,
        git_repository: Any | None = None,
        untracked_mode: str = "all",
        timeout_seconds: float = 15.0,
    ) -> Any:
        from context_forge.git import (
            GitNavigationContext,
            GitRepository,
            GitStatusResult,
            map_changed_paths,
        )

        root = self.project.root_path
        if root is None:
            diag = DiagnosticItem.blocker(
                "Project has no root_path configured; cannot navigate Git",
                code="MISSING_ROOT_PATH",
                source="project",
            )
            empty_status = GitStatusResult(
                is_repository=False,
                root_path=None,
                branch=None,
                head_hash=None,
                entries=(),
                outcome=OperationOutcome.blocked(
                    "Project has no root_path configured",
                    diagnostics=(diag,),
                ),
            )
            return GitNavigationContext(
                git_root=None,
                project_root=Path("."),
                is_git_repository=False,
                git_status=empty_status,
                mappings=(),
                outcome=OperationOutcome.blocked(
                    "Project has no root_path configured",
                    diagnostics=(diag,),
                ),
                diagnostics=(diag,),
            )

        repo = git_repository or GitRepository(root)
        status_result = repo.get_status(
            untracked_mode=untracked_mode,
            timeout_seconds=timeout_seconds,
        )
        return map_changed_paths(self.project, status_result)

    def inspect_pre_change(
        self,
        target: str,
        *,
        file_path: str | Path | None = None,
        symbol_type: str | None = None,
        direction: str = "both",
        max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
        max_excerpt_lines: int = DEFAULT_EXCERPT_MAX_LINES,
        include_git: bool = True,
        guard: WorkflowFreshnessGuard | None = None,
        git_repository: Any | None = None,
        metadata: RepositoryCacheMetadata | None = None,
    ) -> PreChangeInspectionResult:
        from context_forge.inspection import inspect_pre_change

        root = self.project.root_path or Path(".")
        return inspect_pre_change(
            repository_path=root,
            target=target,
            file_path=file_path,
            symbol_type=symbol_type,
            direction=direction,
            max_depth=max_depth,
            max_excerpt_lines=max_excerpt_lines,
            include_git=include_git,
            guard=guard,
            git_repository=git_repository,
            project=self.project,
            metadata=metadata,
        )

    def find_unused_candidates(
        self,
        *,
        kind: str | None = "all",
        limit: int | None = DEFAULT_UNUSED_LIMIT,
    ) -> UnusedEntitiesReport:
        return find_unused_candidates(
            self.project,
            kind=kind,
            limit=limit,
        )
