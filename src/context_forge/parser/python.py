import ast

from context_forge.models.file import File
from context_forge.models.symbol import Symbol
from context_forge.parser.base import Parser
from context_forge.parser.language import Language
from context_forge.parser.result import (
    ImportReference,
    ParseError,
    ParseResult,
)


class PythonParser(Parser):
    @property
    def language(self) -> Language:
        return Language.PYTHON

    def parse(self, source: str, file: File) -> ParseResult:
        try:
            tree = ast.parse(
                source,
                filename=str(file.path),
                type_comments=True,
            )
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
            imports=visitor.imports,
        )


class SymbolVisitor(ast.NodeVisitor):
    def __init__(self, file: File) -> None:
        self.file = file
        self.symbols: list[Symbol] = []
        self.imports: list[ImportReference] = []
        self.parent_stack: list[Symbol] = []

    def _qualified_name(self, name: str) -> str:
        if not self.parent_stack:
            return name

        return ".".join([symbol.name for symbol in self.parent_stack] + [name])

    def _add_symbol(
        self,
        *,
        name: str,
        kind: str,
        node: ast.AST,
        signature: str | None = None,
    ) -> Symbol:
        parent = self.parent_stack[-1] if self.parent_stack else None

        symbol = Symbol(
            file_id=self.file.id,
            name=name,
            kind=kind,
            start_line=getattr(node, "lineno", 1),
            end_line=getattr(node, "end_lineno", None) or getattr(node, "lineno", 1),
            qualified_name=self._qualified_name(name),
            parent_symbol_id=parent.id if parent else None,
            signature=signature,
        )

        self.symbols.append(symbol)
        return symbol

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        symbol = self._add_symbol(
            name=node.name,
            kind="class",
            node=node,
        )

        self.parent_stack.append(symbol)
        self.generic_visit(node)
        self.parent_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        parent = self.parent_stack[-1] if self.parent_stack else None
        kind = "method" if self._is_class_scope(parent) else "function"

        symbol = self._add_symbol(
            name=node.name,
            kind=kind,
            node=node,
            signature=self._build_signature(node),
        )

        self.parent_stack.append(symbol)
        self.generic_visit(node)
        self.parent_stack.pop()

    def _is_class_scope(self, parent: Symbol | None) -> bool:
        return parent is not None and parent.kind == "class"

    def _build_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> str:
        arguments = node.args

        positional = [
            *arguments.posonlyargs,
            *arguments.args,
        ]

        defaults = [None] * (len(positional) - len(arguments.defaults)) + list(
            arguments.defaults
        )

        parts: list[str] = []

        for argument, default in zip(positional, defaults):
            parts.append(self._format_argument(argument, default))

        if arguments.vararg is not None:
            parts.append(f"*{arguments.vararg.arg}")

        for argument, default in zip(
            arguments.kwonlyargs,
            arguments.kw_defaults,
        ):
            parts.append(self._format_argument(argument, default))

        if arguments.kwarg is not None:
            parts.append(f"**{arguments.kwarg.arg}")

        return f"{node.name}({', '.join(parts)})"

    def _format_argument(
        self,
        argument: ast.arg,
        default: ast.expr | None,
    ) -> str:
        annotation = (
            f": {ast.unparse(argument.annotation)}"
            if argument.annotation is not None
            else ""
        )

        default_text = f" = {ast.unparse(default)}" if default is not None else ""

        return f"{argument.arg}{annotation}{default_text}"

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ImportReference(
                    file_id=self.file.id,
                    module_name=alias.name,
                    alias=alias.asname,
                )
            )

            symbol = self._add_symbol(
                name=alias.asname or alias.name,
                kind="import",
                node=node,
            )

            symbol.qualified_name = alias.name

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        prefix = "." * node.level + module

        for alias in node.names:
            self.imports.append(
                ImportReference(
                    file_id=self.file.id,
                    module_name=prefix,
                    imported_name=alias.name,
                    alias=alias.asname,
                    level=node.level,
                )
            )

            symbol = self._add_symbol(
                name=alias.asname or alias.name,
                kind="import",
                node=node,
            )

            symbol.qualified_name = f"{prefix}.{alias.name}" if prefix else alias.name

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._visit_assignment_target(target, node)

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._visit_assignment_target(node.target, node)
        self.generic_visit(node)

    def _visit_assignment_target(
        self,
        target: ast.expr,
        node: ast.AST,
    ) -> None:
        if isinstance(target, ast.Name):
            kind = "constant" if target.id.isupper() else "variable"

            self._add_symbol(
                name=target.id,
                kind=kind,
                node=node,
            )
