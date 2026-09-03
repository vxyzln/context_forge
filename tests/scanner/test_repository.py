from pathlib import Path

import pytest

from context_forge.scanner.repository import RepositoryScanner


def test_scanner_requires_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello")

    with pytest.raises(ValueError, match="must be a directory"):
        RepositoryScanner(file_path)


def test_scanner_detects_files_and_directories(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()

    main_file = src / "main.py"
    main_file.write_text("print('hello')")

    project = RepositoryScanner(tmp_path).scan()

    assert len(project.directories) == 2

    directory_paths = {directory.path for directory in project.directories}

    assert Path(".") in directory_paths
    assert Path("src") in directory_paths

    assert len(project.files) == 1
    file = project.files[0]

    assert file.name == "main.py"
    assert file.extension == ".py"
    assert file.path == Path("src/main.py")
    assert file.size > 0


def test_scanner_sets_parent_directory(tmp_path: Path) -> None:
    src = tmp_path / "src"
    models = src / "models"

    models.mkdir(parents=True)

    project = RepositoryScanner(tmp_path).scan()

    directories = {directory.path: directory for directory in project.directories}

    assert directories[Path("src")].parent_id is not None
    assert directories[Path("src/models")].parent_id == directories[Path("src")].id


def test_scanner_ignores_git_and_venv(tmp_path: Path) -> None:
    src = tmp_path / "src"
    git = tmp_path / ".git"
    venv = tmp_path / ".venv"

    src.mkdir()
    git.mkdir()
    venv.mkdir()

    (src / "main.py").write_text("print('hello')")
    (git / "config").write_text("ignored")
    (venv / "python").write_text("ignored")

    project = RepositoryScanner(tmp_path).scan()

    paths = {file.path for file in project.files}

    assert Path("src/main.py") in paths
    assert Path(".git/config") not in paths
    assert Path(".venv/python") not in paths


def test_scanner_ignores_context_forge_database(tmp_path: Path) -> None:
    database = tmp_path / ".context_forge.db"
    database.write_text("database")

    source = tmp_path / "main.py"
    source.write_text("print('hello')")

    project = RepositoryScanner(tmp_path).scan()

    paths = {file.path for file in project.files}

    assert Path("main.py") in paths
    assert Path(".context_forge.db") not in paths


def test_scanner_classifies_source_and_test_files(tmp_path: Path) -> None:
    from context_forge.models.enums import FileType

    src = tmp_path / "src"
    tests = tmp_path / "tests"

    src.mkdir()
    tests.mkdir()

    (src / "main.py").write_text("print('hello')")
    (tests / "test_main.py").write_text("def test_main(): pass")

    project = RepositoryScanner(tmp_path).scan()

    files = {file.path: file for file in project.files}

    assert files[Path("src/main.py")].file_type == FileType.SOURCE
    assert files[Path("tests/test_main.py")].file_type == FileType.TEST


def test_scanner_classifies_documentation_and_configuration(
    tmp_path: Path,
) -> None:
    from context_forge.models.enums import FileType

    (tmp_path / "README.md").write_text("# Project")
    (tmp_path / "pyproject.toml").write_text("[project]")

    project = RepositoryScanner(tmp_path).scan()

    files = {file.path: file for file in project.files}

    assert files[Path("README.md")].file_type == FileType.DOCUMENTATION
    assert files[Path("pyproject.toml")].file_type == FileType.CONFIGURATION


def test_scanner_marks_generated_files(tmp_path: Path) -> None:

    generated = tmp_path / "__pycache__"
    generated.mkdir()

    (generated / "module.pyc").write_bytes(b"generated")

    project = RepositoryScanner(tmp_path).scan()

    paths = {file.path for file in project.files}

    assert Path("__pycache__/module.pyc") not in paths


def test_scanner_classifies_directory_types(tmp_path: Path) -> None:
    from context_forge.models.enums import DirectoryType

    src = tmp_path / "src"
    tests = tmp_path / "tests"
    docs = tmp_path / "docs"

    src.mkdir()
    tests.mkdir()
    docs.mkdir()

    project = RepositoryScanner(tmp_path).scan()

    directories = {directory.path: directory for directory in project.directories}

    assert directories[Path("src")].directory_type == DirectoryType.SOURCE
    assert directories[Path("tests")].directory_type == DirectoryType.TESTS
    assert directories[Path("docs")].directory_type == DirectoryType.DOCUMENTATION


def test_scanner_is_deterministic_in_structure(tmp_path: Path) -> None:
    (tmp_path / "b.py").write_text("def b(): pass")
    (tmp_path / "a.py").write_text("def a(): pass")

    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "main.py").write_text("def main(): pass")

    first = RepositoryScanner(tmp_path).scan()
    second = RepositoryScanner(tmp_path).scan()

    first_structure = [
        (
            file.path,
            file.name,
            file.extension,
            file.size,
            file.file_type,
            file.is_generated,
            file.is_ignored,
        )
        for file in first.files
    ]

    second_structure = [
        (
            file.path,
            file.name,
            file.extension,
            file.size,
            file.file_type,
            file.is_generated,
            file.is_ignored,
        )
        for file in second.files
    ]

    assert first_structure == second_structure
