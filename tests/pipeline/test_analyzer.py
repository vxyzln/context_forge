from pathlib import Path

from context_forge.pipeline.analyzer import ProjectAnalyzer


def test_analyzer_runs_full_pipeline(tmp_path: Path) -> None:
    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
def hello():
    return "hello"
"""
    )

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.name == tmp_path.name
    assert len(project.files) == 1
    assert len(project.symbols) == 1
    assert len(project.relationships) == 1
    assert project.relationships[0].relationship_type == "defines"
    assert project.analysis_status == "analyzed"
    assert database_path.exists()


def test_analyzer_persists_project(tmp_path: Path) -> None:
    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
def hello():
    return "hello"
"""
    )

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()
    loaded = analyzer.repository.load(project.id)

    assert loaded is not None
    assert loaded.id == project.id
    assert loaded.name == project.name
    assert loaded.root_path == project.root_path
    assert loaded.analysis_status == "analyzed"


def test_analyzer_continues_after_python_syntax_error(tmp_path: Path) -> None:
    valid_file = tmp_path / "valid.py"
    valid_file.write_text(
        """
def hello():
    return "hello"
"""
    )

    invalid_file = tmp_path / "invalid.py"
    invalid_file.write_text(
        """
def broken(
"""
    )

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert len(project.symbols) == 1
    assert len(project.errors) == 1
    assert "invalid.py" in project.errors[0]
    assert project.analysis_status == "analyzed"
    assert database_path.exists()
