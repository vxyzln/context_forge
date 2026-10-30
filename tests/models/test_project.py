from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.models.directory import Directory
from context_forge.models.file import File
from context_forge.models.project import Project


def test_project_creation() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    assert project.name == "Context Forge"
    assert project.root_path == Path.cwd()
    assert project.languages == []
    assert project.frameworks == []
    assert project.directories == []
    assert project.files == []
    assert project.analysis_status == "not_analyzed"


def test_project_adds_directory() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    directory = Directory(
        project_id=project.id,
        path=Path("src"),
        name="src",
    )

    project.add_directory(directory)

    assert project.directories == [directory]


def test_project_adds_file() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file = File(
        project_id=project.id,
        path=Path("README.md"),
        name="README.md",
        extension=".md",
    )

    project.add_file(file)

    assert project.files == [file]


def test_project_rejects_foreign_directory() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    directory = Directory(
        project_id=uuid4(),
        path=Path("src"),
        name="src",
    )

    with pytest.raises(ValueError, match="Directory belongs to a different project"):
        project.add_directory(directory)


def test_project_rejects_foreign_file() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file = File(
        project_id=uuid4(),
        path=Path("README.md"),
        name="README.md",
        extension=".md",
    )

    with pytest.raises(ValueError, match="File belongs to a different project"):
        project.add_file(file)


def test_project_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="Project name cannot be empty"):
        Project(
            name="   ",
            root_path=Path.cwd(),
        )


def test_project_rejects_relative_root() -> None:
    with pytest.raises(ValueError, match="Project root path must be absolute"):
        Project(
            name="Context Forge",
            root_path=Path("context_forge"),
        )


def test_project_git_activity_defaults_to_none() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    assert project.git_activity is None


def test_project_adds_symbol_from_project_file() -> None:
    from context_forge.models.symbol import Symbol

    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file = File(
        project_id=project.id,
        path=Path("main.py"),
        name="main.py",
        extension=".py",
    )

    project.add_file(file)

    symbol = Symbol(
        file_id=file.id,
        name="main",
        kind="function",
        start_line=1,
        end_line=2,
    )

    project.add_symbol(symbol)

    assert project.symbols == [symbol]


def test_project_same_length_file_replacement_invalidates_membership_cache() -> None:
    from context_forge.models.symbol import Symbol

    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file_a = File(
        project_id=project.id,
        path=Path("a.py"),
        name="a.py",
        extension=".py",
    )
    project.add_file(file_a)

    symbol_a = Symbol(
        file_id=file_a.id,
        name="func_a",
        kind="function",
        start_line=1,
        end_line=2,
    )
    # 2. Trigger construction of cached file-ID set
    project.add_symbol(symbol_a)
    assert symbol_a.file_id in project._file_ids()

    # 3. Replace file collection with different file B while keeping collection length unchanged
    file_b = File(
        project_id=project.id,
        path=Path("b.py"),
        name="b.py",
        extension=".py",
    )
    project.files = [file_b]

    # 4. Add valid symbol associated with file B
    symbol_b = Symbol(
        file_id=file_b.id,
        name="func_b",
        kind="function",
        start_line=1,
        end_line=2,
    )
    # 5. Confirm that the operation succeeds
    project.add_symbol(symbol_b)
    assert symbol_b in project.symbols

    # 6. Confirm that a symbol referencing removed file A is rejected
    symbol_a_extra = Symbol(
        file_id=file_a.id,
        name="func_a_extra",
        kind="function",
        start_line=3,
        end_line=4,
    )
    with pytest.raises(ValueError, match="Symbol file does not belong to project"):
        project.add_symbol(symbol_a_extra)


def test_project_same_length_symbol_replacement_invalidates_membership_cache() -> None:
    from context_forge.models.symbol import Symbol
    from context_forge.parser.result import InheritanceReference

    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file = File(
        project_id=project.id,
        path=Path("models.py"),
        name="models.py",
        extension=".py",
    )
    project.add_file(file)

    class_a = Symbol(
        file_id=file.id,
        name="ClassA",
        kind="class",
        start_line=1,
        end_line=10,
    )
    project.add_symbol(class_a)

    ref_a = InheritanceReference(
        file_id=file.id,
        class_symbol_id=class_a.id,
        name="Base",
        line=2,
    )
    # 2. Trigger construction of cached symbol-ID set
    project.add_inheritance_reference(ref_a)
    assert class_a.id in project._symbol_ids()

    # 3. Replace symbol collection with different symbol while preserving collection length
    class_b = Symbol(
        file_id=file.id,
        name="ClassB",
        kind="class",
        start_line=11,
        end_line=20,
    )
    project.symbols = [class_b]

    # 4. Confirm that an inheritance reference to the new valid class symbol is accepted
    ref_b = InheritanceReference(
        file_id=file.id,
        class_symbol_id=class_b.id,
        name="Base",
        line=12,
    )
    project.add_inheritance_reference(ref_b)
    assert ref_b in project.inheritance_references

    # 5. Confirm that a reference to the removed class symbol is rejected
    ref_a_rejected = InheritanceReference(
        file_id=file.id,
        class_symbol_id=class_a.id,
        name="Base",
        line=5,
    )
    with pytest.raises(
        ValueError,
        match="Inheritance reference class does not belong to project",
    ):
        project.add_inheritance_reference(ref_a_rejected)


def test_project_clear_membership_caches_resets_internal_cache_state() -> None:
    project = Project(
        name="Context Forge",
        root_path=Path.cwd(),
    )

    file_1 = File(
        project_id=project.id,
        path=Path("one.py"),
        name="one.py",
        extension=".py",
    )
    project.add_file(file_1)
    file_ids = project._file_ids()
    assert file_ids == {file_1.id}
    assert getattr(project, "_cached_file_ids", None) is not None
    assert getattr(project, "_cached_files_ref", None) is not None

    project.clear_membership_caches()
    assert getattr(project, "_cached_file_ids", None) is None
    assert getattr(project, "_cached_files_ref", None) is None
    assert getattr(project, "_cached_symbol_ids", None) is None
    assert getattr(project, "_cached_symbols_ref", None) is None

    assert project._file_ids() == {file_1.id}
