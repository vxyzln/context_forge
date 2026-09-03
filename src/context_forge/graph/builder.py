from uuid import UUID

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.parser.result import (
    ImportReference,
    InheritanceReference,
    SymbolReference,
)


class RelationshipBuilder:
    def build(
        self,
        project: Project,
        import_references: list[ImportReference],
    ) -> None:
        self._remove_existing_relationships(project)
        self._build_definition_relationships(project)
        self._build_ownership_relationships(project)
        self._build_import_relationships(project, import_references)
        self._build_reference_relationships(project)
        self._build_inheritance_relationships(project)

    def _remove_existing_relationships(self, project: Project) -> None:
        project.relationships.clear()

    def _build_definition_relationships(self, project: Project) -> None:
        seen: set[tuple[UUID, UUID, str]] = set()

        for symbol in project.symbols:
            key = (
                symbol.file_id,
                symbol.id,
                RelationshipType.DEFINES.value,
            )

            if key in seen:
                continue

            seen.add(key)

            project.add_relationship(
                Relationship(
                    source_id=symbol.file_id,
                    target_id=symbol.id,
                    relationship_type=RelationshipType.DEFINES,
                    confidence=1.0,
                    metadata={"source": "ast"},
                )
            )

    def _build_ownership_relationships(self, project: Project) -> None:
        seen: set[tuple[UUID, UUID, str]] = set()
        symbols_by_id = {
            symbol.id: symbol
            for symbol in project.symbols
        }

        for symbol in project.symbols:
            if symbol.parent_symbol_id is None:
                continue

            parent = symbols_by_id.get(symbol.parent_symbol_id)

            if parent is None:
                continue

            key = (
                parent.id,
                symbol.id,
                RelationshipType.CONTAINS.value,
            )

            if key in seen:
                continue

            seen.add(key)

            project.add_relationship(
                Relationship(
                    source_id=parent.id,
                    target_id=symbol.id,
                    relationship_type=RelationshipType.CONTAINS,
                    confidence=1.0,
                    metadata={"source": "ast"},
                )
            )

    def _build_import_relationships(
        self,
        project: Project,
        import_references: list[ImportReference],
    ) -> None:
        file_by_module = self._build_module_index(project)
        seen: set[tuple[UUID, UUID, str]] = set()

        for import_reference in import_references:
            target_file = self._resolve_import_target(
                project,
                import_reference,
                file_by_module,
            )

            if target_file is None:
                continue

            key = (
                import_reference.file_id,
                target_file.id,
                RelationshipType.IMPORTS.value,
            )

            if key in seen:
                continue

            seen.add(key)

            project.add_relationship(
                Relationship(
                    source_id=import_reference.file_id,
                    target_id=target_file.id,
                    relationship_type=RelationshipType.IMPORTS,
                    confidence=1.0,
                    metadata={
                        "source": "ast",
                        "module": import_reference.module_name,
                    },
                )
            )

    def _build_reference_relationships(self, project: Project) -> None:
        symbols_by_file_and_name: dict[
            tuple[UUID, str],
            list[Symbol],
        ] = {}

        symbols_by_name: dict[str, list[Symbol]] = {}
        symbols_by_qualified_name: dict[str, list[Symbol]] = {}

        for symbol in project.symbols:
            # Import symbols represent bindings, not definitions. They
            # should not win local symbol resolution.
            if symbol.kind != "import":
                symbols_by_file_and_name.setdefault(
                    (symbol.file_id, symbol.name),
                    [],
                ).append(symbol)

                symbols_by_name.setdefault(
                    symbol.name,
                    [],
                ).append(symbol)

                if symbol.qualified_name:
                    symbols_by_qualified_name.setdefault(
                        symbol.qualified_name,
                        [],
                    ).append(symbol)

        imports_by_file = self._build_import_index(project)
        seen: set[tuple[UUID, UUID, str]] = set()

        for reference in project.references:
            target, confidence = self._resolve_reference(
                reference,
                symbols_by_file_and_name,
                symbols_by_name,
                symbols_by_qualified_name,
                imports_by_file,
            )

            if target is None:
                continue

            key = (
                reference.file_id,
                target.id,
                RelationshipType.REFERENCES.value,
            )

            if key in seen:
                continue

            seen.add(key)

            metadata = {
                "source": "ast",
                "name": reference.name,
                "line": str(reference.line),
            }

            if reference.qualified_name:
                metadata["qualified_name"] = reference.qualified_name

            project.add_relationship(
                Relationship(
                    source_id=reference.file_id,
                    target_id=target.id,
                    relationship_type=RelationshipType.REFERENCES,
                    confidence=confidence,
                    metadata=metadata,
                )
            )

    def _build_inheritance_relationships(self, project: Project) -> None:
        symbols_by_name: dict[str, list[Symbol]] = {}
        symbols_by_qualified_name: dict[str, list[Symbol]] = {}

        for symbol in project.symbols:
            if symbol.kind != "class":
                continue

            symbols_by_name.setdefault(
                symbol.name,
                [],
            ).append(symbol)

            if symbol.qualified_name:
                symbols_by_qualified_name.setdefault(
                    symbol.qualified_name,
                    [],
                ).append(symbol)

        imports_by_file = self._build_import_index(project)
        seen: set[tuple[UUID, UUID, str]] = set()

        for reference in project.inheritance_references:
            target, confidence = self._resolve_inheritance(
                reference,
                symbols_by_name,
                symbols_by_qualified_name,
                imports_by_file,
            )

            if target is None:
                continue

            if target.id == reference.class_symbol_id:
                continue

            key = (
                reference.class_symbol_id,
                target.id,
                RelationshipType.INHERITS.value,
            )

            if key in seen:
                continue

            seen.add(key)

            metadata = {
                "source": "ast",
                "name": reference.name,
                "line": str(reference.line),
            }

            if reference.qualified_name:
                metadata["qualified_name"] = reference.qualified_name

            project.add_relationship(
                Relationship(
                    source_id=reference.class_symbol_id,
                    target_id=target.id,
                    relationship_type=RelationshipType.INHERITS,
                    confidence=confidence,
                    metadata=metadata,
                )
            )

    def _build_import_index(
        self,
        project: Project,
    ) -> dict[UUID, list[ImportReference]]:
        imports_by_file: dict[UUID, list[ImportReference]] = {}

        for reference in project.imports:
            imports_by_file.setdefault(
                reference.file_id,
                [],
            ).append(reference)

        return imports_by_file

    def _resolve_reference(
        self,
        reference: SymbolReference,
        symbols_by_file_and_name: dict[
            tuple[UUID, str],
            list[Symbol],
        ],
        symbols_by_name: dict[str, list[Symbol]],
        symbols_by_qualified_name: dict[str, list[Symbol]],
        imports_by_file: dict[UUID, list[ImportReference]],
    ) -> tuple[Symbol | None, float]:
        if reference.qualified_name:
            qualified_candidates = self._unique_symbols(
                symbols_by_qualified_name.get(
                    reference.qualified_name,
                    [],
                )
            )

            if len(qualified_candidates) == 1:
                return qualified_candidates[0], 1.0

        imported_candidates: list[Symbol] = []

        for import_reference in imports_by_file.get(
            reference.file_id,
            [],
        ):
            imported_name = (
                import_reference.imported_name
                or import_reference.module_name.rsplit(".", 1)[-1]
            )

            binding = import_reference.alias or imported_name

            if binding != reference.name:
                continue

            if import_reference.imported_name:
                qualified_name = (
                    f"{import_reference.module_name}."
                    f"{import_reference.imported_name}"
                ).lstrip(".")

                imported_candidates.extend(
                    symbols_by_qualified_name.get(
                        qualified_name,
                        [],
                    )
                )

                imported_candidates.extend(
                    symbols_by_name.get(
                        import_reference.imported_name,
                        [],
                    )
                )
            else:
                imported_candidates.extend(
                    symbols_by_qualified_name.get(
                        import_reference.module_name.lstrip("."),
                        [],
                    )
                )

                imported_candidates.extend(
                    symbols_by_name.get(
                        imported_name,
                        [],
                    )
                )

        imported_candidates = self._unique_symbols(
            imported_candidates
        )

        if len(imported_candidates) == 1:
            return imported_candidates[0], 0.9

        local_candidates = self._unique_symbols(
            symbols_by_file_and_name.get(
                (reference.file_id, reference.name),
                [],
            )
        )

        if len(local_candidates) == 1:
            return local_candidates[0], 0.8

        global_candidates = self._unique_symbols(
            symbols_by_name.get(reference.name, [])
        )

        if len(global_candidates) == 1:
            return global_candidates[0], 0.7

        return None, 0.0

    def _resolve_inheritance(
        self,
        reference: InheritanceReference,
        symbols_by_name: dict[str, list[Symbol]],
        symbols_by_qualified_name: dict[str, list[Symbol]],
        imports_by_file: dict[UUID, list[ImportReference]],
    ) -> tuple[Symbol | None, float]:
        if reference.qualified_name:
            qualified_candidates = self._unique_symbols(
                symbols_by_qualified_name.get(
                    reference.qualified_name,
                    [],
                )
            )

            if len(qualified_candidates) == 1:
                return qualified_candidates[0], 1.0

        for import_reference in imports_by_file.get(
            reference.file_id,
            [],
        ):
            imported_name = (
                import_reference.imported_name
                or import_reference.module_name.rsplit(".", 1)[-1]
            )

            binding = import_reference.alias or imported_name

            if binding != reference.name:
                continue

            imported_candidates = self._unique_symbols(
                symbols_by_name.get(
                    imported_name,
                    [],
                )
            )

            if len(imported_candidates) == 1:
                return imported_candidates[0], 0.9

        local_candidates = self._unique_symbols(
            symbols_by_name.get(reference.name, [])
        )

        if len(local_candidates) == 1:
            return local_candidates[0], 0.8

        return None, 0.0

    def _unique_symbols(
        self,
        symbols: list[Symbol],
    ) -> list[Symbol]:
        unique: dict[UUID, Symbol] = {
            symbol.id: symbol
            for symbol in symbols
        }

        return sorted(
            unique.values(),
            key=lambda symbol: (
                symbol.qualified_name or "",
                symbol.file_id.hex,
                symbol.id.hex,
            ),
        )

    def _build_module_index(
        self,
        project: Project,
    ) -> dict[str, File]:
        index: dict[str, File] = {}

        for file in project.files:
            if file.extension != ".py":
                continue

            module_parts = self._module_parts(file)

            if not module_parts:
                continue

            module = ".".join(module_parts)

            index[module] = file

        return index

    def _module_parts(self, file: File) -> list[str]:
        parts = list(file.path.parts)

        if not parts:
            return []

        filename = parts.pop()

        if filename == "__init__.py":
            return parts

        if filename.endswith(".py"):
            parts.append(filename[:-3])

        package_start = None

        for index, part in enumerate(parts):
            if part == "src":
                package_start = index + 1
                break

        if package_start is not None:
            parts = parts[package_start:]

        return parts

    def _resolve_import_target(
        self,
        project: Project,
        import_reference: ImportReference,
        file_by_module: dict[str, File],
    ) -> File | None:
        module = import_reference.module_name.lstrip(".")

        if import_reference.level == 0:
            target = file_by_module.get(module)

            if target is not None:
                return target

            if import_reference.imported_name:
                return file_by_module.get(
                    f"{module}.{import_reference.imported_name}"
                )

            return None

        source_file = next(
            (
                file
                for file in project.files
                if file.id == import_reference.file_id
            ),
            None,
        )

        if source_file is None:
            return None

        source_parts = self._module_parts(source_file)

        if source_parts:
            source_parts = source_parts[:-1]

        if import_reference.level > 1:
            levels_up = import_reference.level - 1

            if levels_up > len(source_parts):
                return None

            source_parts = source_parts[:-levels_up]

        if module:
            source_parts.extend(module.split("."))

        resolved_module = ".".join(source_parts)

        target = file_by_module.get(resolved_module)

        if target is not None:
            return target

        if import_reference.imported_name:
            return file_by_module.get(
                f"{resolved_module}.{import_reference.imported_name}"
            )

        return None