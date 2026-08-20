from context_forge.models.file import File
from context_forge.parser.base import Parser
from context_forge.parser.language import Language
from context_forge.parser.result import ParseError, ParseResult


class PythonParser(Parser):
    @property
    def language(self) -> Language:
        return Language.PYTHON

    def parse(self, source: str, file: File) -> ParseResult:
        return ParseResult(
            errors=[
                ParseError(
                    message="Python parsing is not implemented yet",
                    file_id=file.id,
                )
            ]
        )
