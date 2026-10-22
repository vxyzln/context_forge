from abc import ABC, abstractmethod

from context_forge.models.file import File
from context_forge.parser.language import Language
from context_forge.parser.result import ParseResult


class Parser(ABC):
    @property
    @abstractmethod
    def language(self) -> Language:
        raise NotImplementedError

    @abstractmethod
    def parse(self, source: str, file: File) -> ParseResult:
        raise NotImplementedError
