from pathlib import Path
from typing import ClassVar

from context_forge.parser.language import Language


class LanguageDetector:
    _EXTENSION_MAP: ClassVar[dict[str, Language]] = {
        ".py": Language.PYTHON,
        ".js": Language.JAVASCRIPT,
        ".jsx": Language.JAVASCRIPT,
        ".ts": Language.TYPESCRIPT,
        ".tsx": Language.TYPESCRIPT,
        ".java": Language.JAVA,
        ".go": Language.GO,
        ".rs": Language.RUST,
        ".c": Language.C,
        ".h": Language.C,
        ".cc": Language.CPP,
        ".cpp": Language.CPP,
        ".cxx": Language.CPP,
        ".hpp": Language.CPP,
    }

    def detect(self, path: Path) -> Language:
        return self._EXTENSION_MAP.get(path.suffix.lower(), Language.UNKNOWN)
