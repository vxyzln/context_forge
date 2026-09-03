from pathlib import Path
from uuid import uuid4

from context_forge.models.file import File
from context_forge.parser.language import Language
from context_forge.parser.python import PythonParser


def create_python_file() -> File:
    return File(
        project_id=uuid4(),
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )


def test_python_parser_reports_python_language() -> None:
    parser = PythonParser()

    assert parser.language == Language.PYTHON


def test_python_parser_finds_functions_and_classes() -> None:
    source = """
class Calculator:
    def add(self, a, b):
        return a + b


def hello():
    return "hello"
"""

    result = PythonParser().parse(source, create_python_file())

    symbols = {(symbol.kind, symbol.name) for symbol in result.symbols}

    assert ("class", "Calculator") in symbols
    assert ("method", "add") in symbols
    assert ("function", "hello") in symbols
    assert result.success is True


def test_python_parser_sets_parent_symbol() -> None:
    source = """
class Calculator:
    def add(self, a, b):
        return a + b
"""

    result = PythonParser().parse(source, create_python_file())

    method = next(symbol for symbol in result.symbols if symbol.name == "add")
    calculator = next(
        symbol for symbol in result.symbols if symbol.name == "Calculator"
    )

    assert method.parent_symbol_id == calculator.id


def test_python_parser_builds_qualified_names() -> None:
    source = """
class Calculator:
    def add(self):
        return 1
"""

    result = PythonParser().parse(source, create_python_file())

    calculator = next(
        symbol for symbol in result.symbols if symbol.name == "Calculator"
    )
    method = next(symbol for symbol in result.symbols if symbol.name == "add")

    assert calculator.qualified_name == "Calculator"
    assert method.qualified_name == "Calculator.add"


def test_python_parser_finds_imports() -> None:
    source = """
import os
from pathlib import Path
"""

    result = PythonParser().parse(source, create_python_file())

    imports = {
        symbol.qualified_name for symbol in result.symbols if symbol.kind == "import"
    }

    assert "os" in imports
    assert "pathlib.Path" in imports


def test_python_parser_handles_async_functions() -> None:
    source = """
async def fetch_data():
    return 42
"""

    result = PythonParser().parse(source, create_python_file())

    assert len(result.symbols) == 1
    assert result.symbols[0].kind == "function"
    assert result.symbols[0].name == "fetch_data"


def test_python_parser_reports_syntax_errors() -> None:
    source = """
def broken(
"""

    file = create_python_file()
    result = PythonParser().parse(source, file)

    assert result.success is False
    assert len(result.errors) == 1
    assert result.errors[0].file_id == file.id
    assert result.errors[0].line is not None
    assert result.errors[0].column is not None


def test_python_parser_records_source_locations() -> None:
    source = """\
class Calculator:
    def add(self):
        return 1
"""

    result = PythonParser().parse(source, create_python_file())

    calculator = next(
        symbol for symbol in result.symbols if symbol.name == "Calculator"
    )
    method = next(symbol for symbol in result.symbols if symbol.name == "add")

    assert calculator.start_line == 1
    assert calculator.end_line == 3

    assert method.start_line == 2
    assert method.end_line == 3


def test_python_parser_records_import_references() -> None:
    source = """
from app.utils import hello
"""

    result = PythonParser().parse(source, create_python_file())

    assert len(result.imports) == 1
    assert result.imports[0].module_name == "app.utils"


def test_python_parser_builds_function_signatures() -> None:
    source = """\
def calculate(value: int, multiplier: int = 2) -> int:
    return value * multiplier
"""

    result = PythonParser().parse(source, create_python_file())

    function = next(symbol for symbol in result.symbols if symbol.name == "calculate")

    assert function.signature == ("calculate(value: int, multiplier: int = 2)")


def test_python_parser_distinguishes_nested_function_from_method() -> None:
    source = """\
def outer():
    def inner():
        return 1

    return inner
"""

    result = PythonParser().parse(source, create_python_file())

    inner = next(symbol for symbol in result.symbols if symbol.name == "inner")

    assert inner.kind == "function"
    assert inner.qualified_name == "outer.inner"


def test_python_parser_builds_nested_class_qualified_name() -> None:
    source = """\
class Outer:
    class Inner:
        pass
"""

    result = PythonParser().parse(source, create_python_file())

    inner = next(symbol for symbol in result.symbols if symbol.name == "Inner")

    assert inner.qualified_name == "Outer.Inner"
    assert inner.kind == "class"


def test_python_parser_records_import_alias() -> None:
    source = """\
import pathlib as path
"""

    result = PythonParser().parse(source, create_python_file())

    assert result.imports[0].module_name == "pathlib"
    assert result.imports[0].alias == "path"

    symbol = next(symbol for symbol in result.symbols if symbol.kind == "import")

    assert symbol.name == "path"
    assert symbol.qualified_name == "pathlib"


def test_python_parser_records_from_import_alias() -> None:
    source = """\
from pathlib import Path as FilePath
"""

    result = PythonParser().parse(source, create_python_file())

    assert result.imports[0].module_name == "pathlib"
    assert result.imports[0].imported_name == "Path"
    assert result.imports[0].alias == "FilePath"


def test_python_parser_finds_variables_and_constants() -> None:
    source = """\
MAX_RETRIES = 3
name = "Context Forge"
"""

    result = PythonParser().parse(source, create_python_file())

    symbols = {(symbol.kind, symbol.name) for symbol in result.symbols}

    assert ("constant", "MAX_RETRIES") in symbols
    assert ("variable", "name") in symbols


def test_python_parser_handles_relative_imports() -> None:
    source = """\
from .utils import helper
"""

    result = PythonParser().parse(source, create_python_file())

    assert result.imports[0].module_name == ".utils"
    assert result.imports[0].imported_name == "helper"
    assert result.imports[0].level == 1
