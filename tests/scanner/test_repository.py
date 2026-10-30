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


def test_scanner_handles_disappearing_file_gracefully(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    app_file = src / "app.py"
    app_file.write_text("print('app')")
    transient_file = src / "transient.py"
    transient_file.write_text("print('transient')")

    scanner = RepositoryScanner(tmp_path)
    original_iter_files = scanner._iter_files

    def iter_files_and_delete() -> list[Path]:
        files = original_iter_files()
        # Delete transient file between file discovery and file scanning
        if transient_file.exists():
            transient_file.unlink()
        return files

    scanner._iter_files = iter_files_and_delete
    project = scanner.scan()

    file_paths = {f.path for f in project.files}
    assert Path("src/app.py") in file_paths
    assert Path("src/transient.py") not in file_paths


def test_scanner_reports_inconsistent_directory_structure(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    child = src / "child"
    child.mkdir()
    f = child / "mod.py"
    f.write_text("x = 1")

    scanner = RepositoryScanner(tmp_path)
    # Simulate an inconsistent scan where parent directory 'src' is missing from directory discovery
    scanner._iter_directories = lambda: [child]
    project = scanner.scan()

    assert any(
        "Inconsistent directory structure: parent directory" in err
        for err in project.errors
    )
    assert any(
        "Inconsistent directory structure: directory" in err for err in project.errors
    )


def test_scanner_traversal_and_globally_sorted_contracts(
    tmp_path: Path,
) -> None:
    # Nested fixture designed to distinguish depth-first traversal from globally sorted output.
    # root_z.py and root_a.py are at depth 0.
    # In depth-first traversal (_iter_files), root files are discovered before descending into subdirectories.
    # In globally sorted output (project.files), files are sorted by normalized relative POSIX path.
    (tmp_path / "beta" / "sub").mkdir(parents=True)
    (tmp_path / "alpha").mkdir(parents=True)

    (tmp_path / "root_z.py").write_text("z = 1")
    (tmp_path / "root_a.py").write_text("a = 1")
    (tmp_path / "alpha" / "a.py").write_text("a = 1")
    (tmp_path / "beta" / "b.py").write_text("b = 1")
    (tmp_path / "beta" / "sub" / "s.py").write_text("s = 1")

    scanner = RepositoryScanner(tmp_path)

    # 1. Assert exact expected depth-first traversal order
    iter_files = [
        p.relative_to(scanner.root_path).as_posix() for p in scanner._iter_files()
    ]
    expected_iter_files = [
        "root_a.py",
        "root_z.py",
        "alpha/a.py",
        "beta/b.py",
        "beta/sub/s.py",
    ]
    assert iter_files == expected_iter_files

    iter_dirs = [
        p.relative_to(scanner.root_path).as_posix() for p in scanner._iter_directories()
    ]
    expected_iter_dirs = [
        "alpha",
        "beta",
        "beta/sub",
    ]
    assert iter_dirs == expected_iter_dirs

    # 2. Assert exact expected globally sorted output in project.files and project.directories
    project = scanner.scan()
    project_files = [f.path.as_posix() for f in project.files]
    expected_project_files = [
        "alpha/a.py",
        "beta/b.py",
        "beta/sub/s.py",
        "root_a.py",
        "root_z.py",
    ]
    assert project_files == expected_project_files

    project_dirs = [d.path.as_posix() for d in project.directories]
    expected_project_dirs = [
        ".",
        "alpha",
        "beta",
        "beta/sub",
    ]
    assert project_dirs == expected_project_dirs

    # 3. Assert repeated scan equality
    second_scanner = RepositoryScanner(tmp_path)
    second_project = second_scanner.scan()
    assert [f.path.as_posix() for f in second_project.files] == expected_project_files
    assert [
        d.path.as_posix() for d in second_project.directories
    ] == expected_project_dirs


def test_scanner_respects_is_ignored_path_override_and_nested_ignores(
    tmp_path: Path,
) -> None:
    class CustomScanner(RepositoryScanner):
        def _is_ignored_path(self, path: Path) -> bool:
            return super()._is_ignored_path(path) or any(
                p.startswith("custom_") for p in path.relative_to(self.root_path).parts
            )

    (tmp_path / "custom_dir" / "nested").mkdir(parents=True)
    (tmp_path / "custom_dir" / "nested" / "file.py").write_text("c = 1")
    (tmp_path / "normal_dir").mkdir()
    (tmp_path / "normal_dir" / "file.py").write_text("n = 1")

    scanner = CustomScanner(tmp_path)
    dirs = [
        p.relative_to(scanner.root_path).as_posix() for p in scanner._iter_directories()
    ]
    files = [p.relative_to(scanner.root_path).as_posix() for p in scanner._iter_files()]

    assert "custom_dir" not in dirs
    assert "custom_dir/nested" not in dirs
    assert "custom_dir/nested/file.py" not in files
    assert dirs == ["normal_dir"]
    assert files == ["normal_dir/file.py"]
