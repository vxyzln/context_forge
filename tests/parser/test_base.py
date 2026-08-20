from pathlib import Path
from uuid import uuid4

from context_forge.models.file import File
from context_forge.parser.language import Language
from context_forge.parser.python import PythonParser


def test_python_parser_reports_python_language() -> None:
    parser = PythonParser()

    assert parser.language == Language.PYTHON


def test_python_parser_returns_successful_parse_result() -> None:
    file = File(
        project_id=uuid4(),
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )

    result = PythonParser().parse(
        "def hello():\n    return 'hello'\n",
        file,
    )

    assert result.success is True
    assert len(result.errors) == 0
    assert len(result.symbols) == 1
    assert result.symbols[0].name == "hello"
    assert result.symbols[0].kind == "function"
