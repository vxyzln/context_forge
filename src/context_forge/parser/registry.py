from context_forge.parser.base import Parser
from context_forge.parser.language import Language


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[Language, Parser] = {}

    def register(self, parser: Parser) -> None:
        language = parser.language

        if language == Language.UNKNOWN:
            raise ValueError("Cannot register a parser for unknown language")

        if language in self._parsers:
            raise ValueError(f"A parser is already registered for {language.value}")

        self._parsers[language] = parser

    def get(self, language: Language) -> Parser | None:
        return self._parsers.get(language)

    def has(self, language: Language) -> bool:
        return language in self._parsers
