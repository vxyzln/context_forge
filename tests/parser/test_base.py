from pathlib import Path
from uuid import uuid4

from context_forge.models.file import File
from context_forge.parser.language import Language
from context_forge.parser.python import PythonParser


def test_python_parser_reports_python_language() -> None:
    parser = PythonParser()

    assert parser.language == Language.PYTHON


def test_python_parser_returns_parse_result() -> None:
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

    assert result.success is False
    assert len(result.errors) == 1
    assert result.errors[0].file_id == file.id
    assert result.errors[0].message == "Python parsing is not implemented yet"
