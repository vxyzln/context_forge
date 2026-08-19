from pathlib import Path

from context_forge.extractor.python import PythonExtractor
from context_forge.scanner.repository import RepositoryScanner


def test_python_extractor_finds_functions_and_classes(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b


def hello():
    return "hello"
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    PythonExtractor().extract(project)

    symbols = {(symbol.kind, symbol.name) for symbol in project.symbols}

    assert ("class", "Calculator") in symbols
    assert ("method", "add") in symbols
    assert ("function", "hello") in symbols


def test_python_extractor_sets_parent_symbol(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    PythonExtractor().extract(project)

    method = next(symbol for symbol in project.symbols if symbol.name == "add")

    calculator = next(
        symbol for symbol in project.symbols if symbol.name == "Calculator"
    )

    assert method.parent_symbol_id == calculator.id


def test_python_extractor_finds_imports(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
import os
from pathlib import Path
"""
    )

    project = RepositoryScanner(tmp_path).scan()
    PythonExtractor().extract(project)

    imports = {
        symbol.qualified_name for symbol in project.symbols if symbol.kind == "import"
    }

    assert "os" in imports
    assert "pathlib.Path" in imports
