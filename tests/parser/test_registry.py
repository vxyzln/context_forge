import pytest

from context_forge.models.file import File
from context_forge.parser.base import Parser
from context_forge.parser.language import Language
from context_forge.parser.registry import ParserRegistry
from context_forge.parser.result import ParseResult


class FakePythonParser(Parser):
    @property
    def language(self) -> Language:
        return Language.PYTHON

    def parse(self, source: str, file: File) -> ParseResult:
        return ParseResult()


class FakeJavaScriptParser(Parser):
    @property
    def language(self) -> Language:
        return Language.JAVASCRIPT

    def parse(self, source: str, file: File) -> ParseResult:
        return ParseResult()


class FakeUnknownParser(Parser):
    @property
    def language(self) -> Language:
        return Language.UNKNOWN

    def parse(self, source: str, file: File) -> ParseResult:
        return ParseResult()


def test_registry_registers_parser() -> None:
    registry = ParserRegistry()
    parser = FakePythonParser()

    registry.register(parser)

    assert registry.has(Language.PYTHON) is True
    assert registry.get(Language.PYTHON) is parser


def test_registry_returns_none_for_missing_parser() -> None:
    registry = ParserRegistry()

    assert registry.get(Language.PYTHON) is None
    assert registry.has(Language.PYTHON) is False


def test_registry_supports_multiple_languages() -> None:
    registry = ParserRegistry()

    python_parser = FakePythonParser()
    javascript_parser = FakeJavaScriptParser()

    registry.register(python_parser)
    registry.register(javascript_parser)

    assert registry.get(Language.PYTHON) is python_parser
    assert registry.get(Language.JAVASCRIPT) is javascript_parser


def test_registry_rejects_duplicate_language() -> None:
    registry = ParserRegistry()

    registry.register(FakePythonParser())

    with pytest.raises(
        ValueError,
        match="A parser is already registered for python",
    ):
        registry.register(FakePythonParser())


def test_registry_rejects_unknown_language() -> None:
    registry = ParserRegistry()

    with pytest.raises(
        ValueError,
        match="Cannot register a parser for unknown language",
    ):
        registry.register(FakeUnknownParser())
