import subprocess
from pathlib import Path

from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.query import ProjectQuery


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


def test_analyzer_adds_parsed_symbols_to_project(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    analyzer = ProjectAnalyzer(
        tmp_path,
        tmp_path / "context_forge.db",
    )

    project = analyzer.analyze()

    names = {symbol.name for symbol in project.symbols}

    assert "Calculator" in names
    assert "add" in names


def test_analyzer_records_parser_errors_without_failing_project(
    tmp_path: Path,
) -> None:
    source = tmp_path / "broken.py"
    source.write_text(
        """
def broken(
"""
    )

    analyzer = ProjectAnalyzer(
        tmp_path,
        tmp_path / "context_forge.db",
    )

    project = analyzer.analyze()

    assert project.analysis_status == "analyzed"
    assert project.errors
    assert "broken.py" in project.errors[0]


def test_analyzer_records_unsupported_language(tmp_path: Path) -> None:
    source_file = tmp_path / "main.js"
    source_file.write_text(
        """
function hello() {
    return "hello";
}
"""
    )

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.analysis_status == "analyzed"
    assert project.errors
    assert "main.js" in project.errors[0]
    assert "no parser available" in project.errors[0]
    assert "javascript" in project.errors[0]


def test_analyzer_builds_complete_project_context(tmp_path: Path) -> None:
    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
import os


class Calculator:
    def add(self, a, b):
        return a + b


def hello():
    return os.getcwd()
"""
    )

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.analysis_status == "analyzed"
    assert len(project.files) == 1
    assert len(project.symbols) >= 4
    assert len(project.imports) == 1
    assert len(project.relationships) > 0
    assert not project.errors


def test_analyzer_result_can_be_queried(tmp_path: Path) -> None:
    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()

    loaded_project = analyzer.repository.load(project.id)
    assert loaded_project is not None
    query = ProjectQuery(loaded_project)

    assert query is not None

    results = query.search("Calculator")

    assert results
    assert results[0].name == "Calculator"
    assert results[0].score == 1.0


def test_analyzer_persists_complete_context(tmp_path: Path) -> None:
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
    assert loaded.analysis_status == "analyzed"
    assert len(loaded.files) == len(project.files)
    assert len(loaded.symbols) == len(project.symbols)
    assert len(loaded.relationships) == len(project.relationships)
    assert len(loaded.errors) == len(project.errors)


def run_git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_analyzer_adds_git_activity(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
def hello():
    return "hello"
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "initial commit")

    source_file.write_text(
        """
def hello():
    return "hello"

def goodbye():
    return "goodbye"
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add goodbye")

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.git_activity is not None
    assert project.git_activity.total_commits == 2
    assert project.git_activity.total_authors == 1
    assert project.git_activity.files_changed == 1
    assert project.git_activity.total_additions == 6
    assert project.git_activity.total_deletions == 0


def test_analyzer_handles_non_git_project(
    tmp_path: Path,
) -> None:
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

    assert project.analysis_status == "analyzed"
    assert project.git_activity is None
