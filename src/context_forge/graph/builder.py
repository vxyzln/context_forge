import ast

from context_forge.models.project import Project
from context_forge.models.relationship import Relationship


class RelationshipBuilder:
    def build(self, project: Project) -> None:
        self._build_definition_relationships(project)
        self._build_import_relationships(project)

    def _build_definition_relationships(self, project: Project) -> None:
        for symbol in project.symbols:
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

        for file in project.files:
            if file.extension != ".py":
                continue

            path = project.root_path / file.path

            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._add_import_relationship(
                            project,
                            file,
                            alias.name,
                            file_by_module,
                        )

                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    self._add_import_relationship(
                        project,
                        file,
                        node.module,
                        file_by_module,
                    )

    def _add_import_relationship(
        self,
        project: Project,
        source_file,
        module_name: str,
        file_by_module: dict[str, object],
    ) -> None:
        target_file = file_by_module.get(module_name)

        if target_file is None:
            return

        relationship = Relationship(
            source_id=source_file.id,
            target_id=target_file.id,
            relationship_type="imports",
        )

        project.add_relationship(relationship)
