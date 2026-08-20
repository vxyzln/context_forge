import ast

from context_forge.models.file import File
from context_forge.models.symbol import Symbol
from context_forge.parser.base import Parser
from context_forge.parser.language import Language
from context_forge.parser.result import ParseError, ParseResult


class PythonParser(Parser):
    @property
    def language(self) -> Language:
        return Language.PYTHON

    def parse(self, source: str, file: File) -> ParseResult:
        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            return ParseResult(
                errors=[
                    ParseError(
                        message=str(error),
                        file_id=file.id,
                        line=error.lineno,
                        column=error.offset,
                    )
                ]
            )

        visitor = SymbolVisitor(file)
        visitor.visit(tree)

        return ParseResult(
            symbols=visitor.symbols,
        )


class SymbolVisitor(ast.NodeVisitor):
    def __init__(self, file: File) -> None:
        self.file = file
        self.symbols: list[Symbol] = []
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

        self.symbols.append(symbol)
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

        self.symbols.append(symbol)
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

            self.symbols.append(symbol)

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

            self.symbols.append(symbol)

        self.generic_visit(node)
