from pathlib import Path

from context_forge.parser.detector import LanguageDetector
from context_forge.parser.language import Language


def test_detector_recognizes_python() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("main.py")) == Language.PYTHON


def test_detector_recognizes_javascript() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("app.js")) == Language.JAVASCRIPT


def test_detector_recognizes_typescript() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("app.ts")) == Language.TYPESCRIPT


def test_detector_recognizes_tsx() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("component.tsx")) == Language.TYPESCRIPT


def test_detector_recognizes_java() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("Main.java")) == Language.JAVA


def test_detector_recognizes_go() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("main.go")) == Language.GO


def test_detector_recognizes_rust() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("main.rs")) == Language.RUST


def test_detector_recognizes_c() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("main.c")) == Language.C


def test_detector_recognizes_cpp() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("main.cpp")) == Language.CPP


def test_detector_returns_unknown_for_unsupported_extension() -> None:
    detector = LanguageDetector()

    assert detector.detect(Path("README.md")) == Language.UNKNOWN
