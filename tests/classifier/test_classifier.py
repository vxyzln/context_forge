from pathlib import Path

from context_forge.classifier.project import ProjectClassifier
from context_forge.scanner.repository import RepositoryScanner


def test_classifier_detects_python_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')")

    project = RepositoryScanner(tmp_path).scan()
    ProjectClassifier().classify(project)

    assert "Python" in project.languages
    assert project.project_type == "python_project"


def test_classifier_classifies_files(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "README.md").write_text("# Demo")
    (tmp_path / "pyproject.toml").write_text("[project]")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_main(): pass")

    project = RepositoryScanner(tmp_path).scan()
    ProjectClassifier().classify(project)

    files = {file.path: file for file in project.files}

    assert files[Path("main.py")].file_type.value == "source"
    assert files[Path("README.md")].file_type.value == "documentation"
    assert files[Path("pyproject.toml")].file_type.value == "configuration"
    assert files[Path("tests/test_main.py")].file_type.value == "test"


def test_classifier_detects_uv(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]")
    (tmp_path / "uv.lock").write_text("")

    project = RepositoryScanner(tmp_path).scan()
    ProjectClassifier().classify(project)

    assert project.package_manager == "uv"


def test_classifier_detects_ruby(tmp_path: Path) -> None:
    (tmp_path / "main.rb").write_text("puts 'hello'")

    project = RepositoryScanner(tmp_path).scan()
    ProjectClassifier().classify(project)

    assert "Ruby" in project.languages
