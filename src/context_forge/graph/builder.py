from context_forge.models.project import Project
from context_forge.models.relationship import Relationship


class RelationshipBuilder:
    def build(self, project: Project) -> None:
        self._remove_existing_relationships(project)

        self._build_definition_relationships(project)
        self._build_import_relationships(project)

    def _remove_existing_relationships(self, project: Project) -> None:
        project.relationships.clear()

    def _build_definition_relationships(self, project: Project) -> None:
        seen: set[tuple] = set()

        for symbol in project.symbols:
            key = (
                symbol.file_id,
                symbol.id,
                "defines",
            )

            if key in seen:
                continue

            seen.add(key)

            relationship = Relationship(
                source_id=symbol.file_id,
                target_id=symbol.id,
                relationship_type="defines",
            )

            project.add_relationship(relationship)

    def _build_import_relationships(self, project: Project) -> None:
        file_by_module = {
            file.path.with_suffix("").as_posix().replace("/", "."): file
            for file in project.files
            if file.extension == ".py"
        }

        seen: set[tuple] = set()

        for import_reference in project.imports:
            target_file = file_by_module.get(import_reference.module_name)

            if target_file is None:
                continue

            key = (
                import_reference.file_id,
                target_file.id,
                "imports",
            )

            if key in seen:
                continue

            seen.add(key)

            relationship = Relationship(
                source_id=import_reference.file_id,
                target_id=target_file.id,
                relationship_type="imports",
            )

            project.add_relationship(relationship)
