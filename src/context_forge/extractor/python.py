import ast

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol


class PythonExtractor:
    def extract(self, project: Project) -> None:
        for file in project.files:
            if file.extension != ".py":
                continue

            self._extract_file(project, file)

    def _extract_file(self, project: Project, file: File) -> None:
        path = project.root_path / file.path

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeDecodeError, SyntaxError):
            return

        visitor = SymbolVisitor(project, file)
        visitor.visit(tree)


class SymbolVisitor(ast.NodeVisitor):
    def __init__(self, project: Project, file: File) -> None:
        self.project = project
        self.file = file
        self.parent_stack: list[Symbol] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        symbol = Symbol(
            file_id=self.file.id,
            name=node.name,
            kind="class",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            qualified_name=node.name,
        )

        self.project.add_symbol(symbol)
        self.parent_stack.append(symbol)

        self.generic_visit(node)

        self.parent_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._add_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add_function(node)

    def _add_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        parent = self.parent_stack[-1] if self.parent_stack else None

        kind = "method" if parent is not None else "function"

        qualified_name = f"{parent.qualified_name}.{node.name}" if parent else node.name

        symbol = Symbol(
            file_id=self.file.id,
            name=node.name,
            kind=kind,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            qualified_name=qualified_name,
            parent_symbol_id=parent.id if parent else None,
        )

        self.project.add_symbol(symbol)
        self.parent_stack.append(symbol)

        self.generic_visit(node)

        self.parent_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            symbol = Symbol(
                file_id=self.file.id,
                name=alias.name,
                kind="import",
                start_line=node.lineno,
                end_line=node.lineno,
                qualified_name=alias.name,
            )

            self.project.add_symbol(symbol)

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""

        for alias in node.names:
            name = f"{module}.{alias.name}" if module else alias.name

            symbol = Symbol(
                file_id=self.file.id,
                name=alias.name,
                kind="import",
                start_line=node.lineno,
                end_line=node.lineno,
                qualified_name=name,
            )

            self.project.add_symbol(symbol)

        self.generic_visit(node)
