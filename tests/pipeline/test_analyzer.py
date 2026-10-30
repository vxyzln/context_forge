import subprocess
from pathlib import Path

import pytest

from context_forge.models.file import File
from context_forge.models.relationship import RelationshipType
from context_forge.parser.python import PythonParser
from context_forge.parser.result import ParseResult
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.query import ProjectQuery
from context_forge.storage.cache import (
    RepositoryIdentity,
    fingerprint_file,
)


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


def test_analyzer_handles_missing_git_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
def hello():
    return "hello"
"""
    )

    def mock_run_git_missing(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    from context_forge.git.repository import GitRepository

    monkeypatch.setattr(GitRepository, "_run_git", mock_run_git_missing)

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.analysis_status == "analyzed"
    assert project.git_activity is None
    assert not project.errors


def test_analyzer_surfaces_git_permission_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
def hello():
    return "hello"
"""
    )

    def mock_run_git_permission(*args, **kwargs):
        raise PermissionError(13, "Permission denied: 'git'")

    from context_forge.git.repository import GitRepository

    monkeypatch.setattr(GitRepository, "_run_git", mock_run_git_permission)

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.analysis_status == "analyzed"
    assert project.git_activity is None
    assert len(project.errors) == 1
    assert "Git activity extraction failed" in project.errors[0]


def test_analyzer_repeated_analysis_is_deterministic(
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

    database_path = tmp_path / ".context_forge.db"

    first = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    second = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert first.git_activity == second.git_activity


def test_analyzer_persists_git_activity(
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

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()

    loaded = analyzer.repository.load(project.id)

    assert loaded is not None
    assert loaded.git_activity == project.git_activity


def test_git_activity_does_not_break_context_query(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add calculator")

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()

    assert project.git_activity is not None

    loaded = analyzer.repository.load(project.id)

    assert loaded is not None

    query = ProjectQuery(loaded)

    results = query.search("Calculator")

    assert results
    assert results[0].name == "Calculator"
    assert results[0].score == 1.0


def test_analyzer_persists_no_git_activity_for_non_git_project(
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

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()
    loaded = analyzer.repository.load(project.id)

    assert loaded is not None
    assert project.git_activity is None
    assert loaded.git_activity is None


def test_analyzer_repeated_analysis_produces_identical_git_activity(
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

    first = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    second = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert first.git_activity is not None
    assert second.git_activity is not None
    assert first.git_activity == second.git_activity


def test_analyzer_repeated_analysis_does_not_duplicate_project_records(
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

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    first = analyzer.analyze()
    second = analyzer.analyze()

    assert first.git_activity is not None
    assert second.git_activity is not None
    assert first.git_activity == second.git_activity

    loaded = analyzer.repository.load(second.id)

    assert loaded is not None
    assert loaded.git_activity == second.git_activity


def test_analyzer_repeated_analysis_preserves_project_context(
    tmp_path: Path,
) -> None:
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

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    first = analyzer.analyze()
    second = analyzer.analyze()

    assert first.analysis_status == "analyzed"
    assert second.analysis_status == "analyzed"

    assert [file.path for file in first.files] == [file.path for file in second.files]

    assert [symbol.name for symbol in first.symbols] == [
        symbol.name for symbol in second.symbols
    ]

    assert [relationship.relationship_type for relationship in first.relationships] == [
        relationship.relationship_type for relationship in second.relationships
    ]

    assert first.git_activity == second.git_activity


def test_analyzer_git_activity_is_stable_across_repeated_runs(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    source_file = tmp_path / "main.py"

    for index in range(3):
        source_file.write_text(f"print({index})\n")
        run_git(tmp_path, "add", "main.py")
        run_git(tmp_path, "commit", "-m", f"commit {index}")

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    first = analyzer.analyze()
    second = analyzer.analyze()

    assert first.git_activity is not None
    assert second.git_activity is not None

    assert first.git_activity.total_commits == 3
    assert second.git_activity.total_commits == 3

    assert first.git_activity.total_authors == 1
    assert second.git_activity.total_authors == 1

    assert first.git_activity.files_changed == 1
    assert second.git_activity.files_changed == 1

    assert first.git_activity.total_additions == second.git_activity.total_additions
    assert first.git_activity.total_deletions == second.git_activity.total_deletions


def test_git_activity_survives_project_query(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(
        tmp_path,
        "config",
        "user.name",
        "Context Forge Test",
    )
    run_git(
        tmp_path,
        "config",
        "user.email",
        "test@example.com",
    )

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add calculator")

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()

    assert project.git_activity is not None
    assert project.git_activity.total_commits == 1

    query = ProjectQuery(project)

    results = query.search("Calculator")

    assert results
    assert results[0].name == "Calculator"
    assert results[0].score == 1.0


def test_git_history_does_not_distort_symbol_ranking(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(
        tmp_path,
        "config",
        "user.name",
        "Context Forge Test",
    )
    run_git(
        tmp_path,
        "config",
        "user.email",
        "test@example.com",
    )

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b

def calculator_helper():
    return 1
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add calculator")

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    assert project.git_activity is not None

    results = ProjectQuery(project).search("Calculator")

    assert results
    assert results[0].name == "Calculator"
    assert results[0].score == 1.0


def test_git_history_preserves_deterministic_query_ranking(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(
        tmp_path,
        "config",
        "user.name",
        "Context Forge Test",
    )
    run_git(
        tmp_path,
        "config",
        "user.email",
        "test@example.com",
    )

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b

class CalculatorFactory:
    def create(self):
        return Calculator()
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add calculator")

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    query = ProjectQuery(project)

    first = query.search("Calculator")
    second = query.search("Calculator")

    assert first == second


def test_git_activity_persistence_preserves_query_behavior(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(
        tmp_path,
        "config",
        "user.name",
        "Context Forge Test",
    )
    run_git(
        tmp_path,
        "config",
        "user.email",
        "test@example.com",
    )

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add calculator")

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()

    loaded = analyzer.repository.load(project.id)

    assert loaded is not None
    assert loaded.git_activity == project.git_activity

    original_results = ProjectQuery(project).search("Calculator")
    loaded_results = ProjectQuery(loaded).search("Calculator")

    assert original_results == loaded_results


def test_non_git_project_preserves_query_behavior(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    )

    project = analyzer.analyze()

    assert project.git_activity is None

    results = ProjectQuery(project).search("Calculator")

    assert results
    assert results[0].name == "Calculator"
    assert results[0].score == 1.0


def test_analyzer_preserves_git_activity_when_analysis_has_errors(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(
        tmp_path,
        "config",
        "user.name",
        "Context Forge Test",
    )
    run_git(
        tmp_path,
        "config",
        "user.email",
        "test@example.com",
    )

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

    run_git(tmp_path, "add", "valid.py", "invalid.py")
    run_git(tmp_path, "commit", "-m", "add valid and invalid files")

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    )

    project = analyzer.analyze()

    assert project.analysis_status == "analyzed"
    assert project.git_activity is not None
    assert project.git_activity.total_commits == 1
    assert project.errors


def test_git_activity_does_not_change_query_explanation(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(
        tmp_path,
        "config",
        "user.name",
        "Context Forge Test",
    )
    run_git(
        tmp_path,
        "config",
        "user.email",
        "test@example.com",
    )

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add calculator")

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    assert project.git_activity is not None

    results = ProjectQuery(project).search("Calculator")

    assert results
    assert results[0].score == 1.0
    assert results[0].reason == "Exact symbol name match"


def test_full_project_context_survives_git_persistence_and_query(
    tmp_path: Path,
) -> None:
    run_git(tmp_path, "init")
    run_git(
        tmp_path,
        "config",
        "user.name",
        "Context Forge Test",
    )
    run_git(
        tmp_path,
        "config",
        "user.email",
        "test@example.com",
    )

    source_file = tmp_path / "main.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b

def hello():
    return "hello"
"""
    )

    run_git(tmp_path, "add", "main.py")
    run_git(tmp_path, "commit", "-m", "add calculator")

    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    )

    project = analyzer.analyze()

    assert project.git_activity is not None

    loaded = analyzer.repository.load(project.id)

    assert loaded is not None
    assert loaded.git_activity == project.git_activity

    original_results = ProjectQuery(project).search("Calculator")
    loaded_results = ProjectQuery(loaded).search("Calculator")

    assert original_results == loaded_results

    assert loaded_results
    assert loaded_results[0].name == "Calculator"
    assert loaded_results[0].score == 1.0
    assert loaded_results[0].reason == "Exact symbol name match"


def test_analyzer_builds_complete_multi_file_python_project(
    tmp_path: Path,
) -> None:
    app_directory = tmp_path / "app"
    services_directory = app_directory / "services"

    services_directory.mkdir(parents=True)

    (app_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )

    (services_directory / "__init__.py").write_text(
        "",
        encoding="utf-8",
    )

    (services_directory / "auth.py").write_text(
        """
class AuthService:
    def authenticate(self, username: str) -> bool:
        return bool(username)
""",
        encoding="utf-8",
    )

    (app_directory / "main.py").write_text(
        """
from app.services.auth import AuthService


def run(username: str) -> bool:
    service = AuthService()
    return service.authenticate(username)
""",
        encoding="utf-8",
    )

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.analysis_status == "analyzed"
    assert not project.errors

    file_paths = {file.path for file in project.files}

    assert Path("app/__init__.py") in file_paths
    assert Path("app/main.py") in file_paths
    assert Path("app/services/__init__.py") in file_paths
    assert Path("app/services/auth.py") in file_paths

    symbol_names = {symbol.name for symbol in project.symbols}

    assert "AuthService" in symbol_names
    assert "authenticate" in symbol_names
    assert "run" in symbol_names

    assert project.imports

    relationship_types = {
        relationship.relationship_type for relationship in project.relationships
    }

    assert "defines" in relationship_types


def test_analyzer_builds_relationships_across_python_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "auth.py").write_text(
        """
def authenticate(username: str) -> bool:
    return bool(username)
""",
        encoding="utf-8",
    )

    (tmp_path / "main.py").write_text(
        """
from auth import authenticate


def run(username: str) -> bool:
    return authenticate(username)
""",
        encoding="utf-8",
    )

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    assert project.analysis_status == "analyzed"
    assert not project.errors

    relationship_types = {
        relationship.relationship_type for relationship in project.relationships
    }

    assert "defines" in relationship_types
    assert "imports" in relationship_types


def test_analyzer_persists_python_analysis(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "main.py"

    source_file.write_text(
        """
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
""",
        encoding="utf-8",
    )

    analyzer = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    )

    project = analyzer.analyze()
    loaded = analyzer.repository.load(project.id)

    assert loaded is not None
    assert loaded.analysis_status == "analyzed"

    loaded_symbol_names = {symbol.name for symbol in loaded.symbols}

    assert "Calculator" in loaded_symbol_names
    assert "add" in loaded_symbol_names


def test_analyzer_builds_reference_and_inheritance_relationships(
    tmp_path: Path,
) -> None:
    (tmp_path / "base.py").write_text(
        """
class Base:
    pass
""",
        encoding="utf-8",
    )

    (tmp_path / "child.py").write_text(
        """
from base import Base


class Child(Base):
    def run(self) -> None:
        Base()
""",
        encoding="utf-8",
    )

    database_path = tmp_path / ".context_forge.db"

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=database_path,
    ).analyze()

    assert project.errors == []

    base = next(symbol for symbol in project.symbols if symbol.name == "Base")
    child = next(symbol for symbol in project.symbols if symbol.name == "Child")

    assert any(
        relationship.source_id == child.id
        and relationship.target_id == base.id
        and relationship.relationship_type == RelationshipType.INHERITS
        for relationship in project.relationships
    )

    assert any(
        relationship.target_id == base.id
        and relationship.relationship_type == RelationshipType.REFERENCES
        for relationship in project.relationships
    )

    assert database_path.exists()


def test_analyzer_persists_repository_cache_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        'def hello() -> str:\n    return "hello"\n',
        encoding="utf-8",
    )

    database_path = tmp_path / "context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path)

    project = analyzer.analyze()

    metadata = analyzer.repository.load_cache_metadata(
        RepositoryIdentity(tmp_path).key,
    )

    assert metadata is not None
    assert metadata.repository_key == RepositoryIdentity(tmp_path).key
    assert metadata.project_id == project.id


def test_analyzer_cache_identity_resolves_persisted_project(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        'def hello() -> str:\n    return "hello"\n',
        encoding="utf-8",
    )

    database_path = tmp_path / "context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path)

    project = analyzer.analyze()

    loaded = analyzer.repository.load_analysis(
        RepositoryIdentity(tmp_path).key,
    )

    assert loaded is not None

    loaded_project, metadata = loaded

    assert loaded_project.id == project.id
    assert loaded_project.name == project.name
    assert loaded_project.root_path == tmp_path.resolve()
    assert metadata.project_id == project.id


def test_analyzer_persists_file_fingerprints(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        'def hello() -> str:\n    return "hello"\n',
        encoding="utf-8",
    )

    database_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path)

    analyzer.analyze()

    repository_key = RepositoryIdentity(tmp_path).key
    fingerprints = analyzer.repository.load_file_fingerprints(
        repository_key,
    )

    assert fingerprints == {
        Path("main.py"): fingerprint_file(
            tmp_path,
            Path("main.py"),
        )
    }

    assert fingerprints[Path("main.py")].content_hash


def test_analyzer_reuses_cached_analysis_when_repository_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        "def hello() -> str:\n    return 'hello'\n",
        encoding="utf-8",
    )

    database_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path)

    first_project = analyzer.analyze()

    def fail_parse(*args: object, **kwargs: object) -> None:
        raise AssertionError("unchanged files must not be parsed")

    monkeypatch.setattr(
        PythonParser,
        "parse",
        fail_parse,
    )

    second_project = ProjectAnalyzer(
        tmp_path,
        database_path,
    ).analyze()

    assert second_project.id == first_project.id
    assert second_project.files == first_project.files
    assert second_project.symbols == first_project.symbols
    assert second_project.relationships == first_project.relationships


def test_analyzer_reparses_only_modified_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_source = tmp_path / "first.py"
    second_source = tmp_path / "second.py"

    first_source.write_text(
        "def first() -> str:\n    return 'first'\n",
        encoding="utf-8",
    )
    second_source.write_text(
        "def second() -> str:\n    return 'second'\n",
        encoding="utf-8",
    )

    database_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = analyzer.analyze()

    parsed_paths: list[Path] = []
    original_parse = PythonParser.parse

    def tracking_parse(
        parser: PythonParser,
        source: str,
        file: File,
    ) -> ParseResult:
        parsed_paths.append(file.path)
        return original_parse(parser, source, file)

    monkeypatch.setattr(
        PythonParser,
        "parse",
        tracking_parse,
    )

    first_source.write_text(
        "def first() -> str:\n    return 'updated'\n",
        encoding="utf-8",
    )

    second_project = ProjectAnalyzer(
        tmp_path,
        database_path,
    ).analyze()

    assert parsed_paths == [Path("first.py")]
    assert second_project.id == first_project.id
    assert {symbol.name for symbol in second_project.symbols} == {"first", "second"}


def test_analyzer_detects_added_and_deleted_files_incrementally(
    tmp_path: Path,
) -> None:
    retained_source = tmp_path / "retained.py"
    deleted_source = tmp_path / "deleted.py"

    retained_source.write_text(
        "def retained() -> str:\n    return 'retained'\n",
        encoding="utf-8",
    )
    deleted_source.write_text(
        "def deleted() -> str:\n    return 'deleted'\n",
        encoding="utf-8",
    )

    database_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = analyzer.analyze()

    retained_file = next(
        file for file in first_project.files if file.path == Path("retained.py")
    )

    deleted_source.unlink()

    added_source = tmp_path / "added.py"
    added_source.write_text(
        "def added() -> str:\n    return 'added'\n",
        encoding="utf-8",
    )

    second_analyzer = ProjectAnalyzer(tmp_path, database_path)
    second_project = second_analyzer.analyze()

    assert second_project.id == first_project.id
    assert {file.path for file in second_project.files} == {
        Path("retained.py"),
        Path("added.py"),
    }

    retained_after = next(
        file for file in second_project.files if file.path == Path("retained.py")
    )

    assert retained_after.id == retained_file.id

    assert {symbol.name for symbol in second_project.symbols} == {"retained", "added"}

    loaded_analysis = second_analyzer.repository.load_analysis(
        second_analyzer.identity.key,
    )

    assert loaded_analysis is not None
    loaded_project, _ = loaded_analysis

    assert {file.path for file in loaded_project.files} == {
        Path("retained.py"),
        Path("added.py"),
    }
    assert {symbol.name for symbol in loaded_project.symbols} == {
        "retained",
        "added",
    }

    fingerprints = second_analyzer.repository.load_file_fingerprints(
        second_analyzer.identity.key,
    )

    assert set(fingerprints) == {
        Path("retained.py"),
        Path("added.py"),
    }


def test_incremental_analysis_preserves_errors_from_unchanged_files(
    tmp_path: Path,
) -> None:
    broken_source = tmp_path / "broken.py"
    changing_source = tmp_path / "changing.py"
    database_path = tmp_path / ".context_forge.db"

    broken_source.write_text(
        "def broken(:\n    pass\n",
        encoding="utf-8",
    )
    changing_source.write_text(
        "def original() -> str:\n    return 'original'\n",
        encoding="utf-8",
    )

    first_project = ProjectAnalyzer(
        tmp_path,
        database_path,
    ).analyze()

    original_errors = [
        error for error in first_project.errors if error.startswith("broken.py:")
    ]

    assert original_errors
    assert first_project.analysis_status == "analyzed"

    changing_source.write_text(
        "def updated() -> str:\n    return 'updated'\n",
        encoding="utf-8",
    )

    second_project = ProjectAnalyzer(
        tmp_path,
        database_path,
    ).analyze()

    preserved_errors = [
        error for error in second_project.errors if error.startswith("broken.py:")
    ]

    assert preserved_errors == original_errors
    assert second_project.analysis_status == "analyzed"
    assert "updated" in {symbol.name for symbol in second_project.symbols}


def test_failed_source_read_does_not_persist_new_fingerprint(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    database_path = tmp_path / ".context_forge.db"

    source.write_text(
        "def hello() -> str:\n    return 'hello'\n",
        encoding="utf-8",
    )

    analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = analyzer.analyze()

    assert first_project.analysis_status == "analyzed"
    assert Path("main.py") in analyzer.repository.load_file_fingerprints(
        analyzer.identity.key,
    )

    source.write_bytes(b"\xff\xfe\xfa")

    failing_analyzer = ProjectAnalyzer(tmp_path, database_path)

    with pytest.raises(
        RuntimeError,
        match="Unable to read source file 'main.py'",
    ):
        failing_analyzer.analyze()

    fingerprints = failing_analyzer.repository.load_file_fingerprints(
        failing_analyzer.identity.key,
    )

    assert Path("main.py") not in fingerprints


def test_incremental_analysis_recovers_after_source_read_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    database_path = tmp_path / ".context_forge.db"

    source.write_text(
        "def original() -> str:\n    return 'original'\n",
        encoding="utf-8",
    )

    ProjectAnalyzer(tmp_path, database_path).analyze()

    source.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(RuntimeError, match="Unable to read source file"):
        ProjectAnalyzer(tmp_path, database_path).analyze()

    source.write_text(
        "def recovered() -> str:\n    return 'recovered'\n",
        encoding="utf-8",
    )

    recovered_project = ProjectAnalyzer(
        tmp_path,
        database_path,
    ).analyze()

    assert recovered_project.analysis_status == "analyzed"
    assert "recovered" in {symbol.name for symbol in recovered_project.symbols}


def test_analyzer_handles_file_rename_incrementally(
    tmp_path: Path,
) -> None:
    original_source = tmp_path / "original.py"
    retained_source = tmp_path / "retained.py"
    database_path = tmp_path / ".context_forge.db"

    original_source.write_text(
        "def original_name() -> str:\n    return 'original'\n",
        encoding="utf-8",
    )
    retained_source.write_text(
        "def retained_name() -> str:\n    return 'retained'\n",
        encoding="utf-8",
    )

    first_analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = first_analyzer.analyze()

    original_file = next(
        file for file in first_project.files if file.path == Path("original.py")
    )
    retained_file = next(
        file for file in first_project.files if file.path == Path("retained.py")
    )
    original_symbol_ids = {
        symbol.id
        for symbol in first_project.symbols
        if symbol.file_id == original_file.id
    }

    assert original_symbol_ids

    renamed_source = tmp_path / "renamed.py"
    original_source.rename(renamed_source)

    second_analyzer = ProjectAnalyzer(tmp_path, database_path)
    second_project = second_analyzer.analyze()

    current_paths = {file.path for file in second_project.files}

    assert current_paths == {
        Path("renamed.py"),
        Path("retained.py"),
    }

    symbol_names = {symbol.name for symbol in second_project.symbols}

    assert "original_name" in symbol_names
    assert "retained_name" in symbol_names

    retained_after = next(
        file for file in second_project.files if file.path == Path("retained.py")
    )
    renamed_file = next(
        file for file in second_project.files if file.path == Path("renamed.py")
    )

    assert retained_after.id == retained_file.id
    assert renamed_file.id != original_file.id

    current_symbol_ids = {symbol.id for symbol in second_project.symbols}
    assert original_symbol_ids.isdisjoint(current_symbol_ids)

    loaded_analysis = second_analyzer.repository.load_analysis(
        second_analyzer.identity.key,
    )

    assert loaded_analysis is not None
    loaded_project, _ = loaded_analysis

    assert {file.path for file in loaded_project.files} == current_paths
    assert {symbol.name for symbol in loaded_project.symbols} == symbol_names

    fingerprints = second_analyzer.repository.load_file_fingerprints(
        second_analyzer.identity.key,
    )

    assert set(fingerprints) == current_paths
    assert Path("original.py") not in fingerprints


def test_analyzer_fresh_cache_hit_retains_raw_imports(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("import os\nimport sys\n", encoding="utf-8")
    database_path = tmp_path / ".context_forge.db"

    first_analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = first_analyzer.analyze()

    assert len(first_project.imports) == 2
    modules = {imp.module_name for imp in first_project.imports}
    assert modules == {"os", "sys"}

    second_analyzer = ProjectAnalyzer(tmp_path, database_path)
    second_project = second_analyzer.analyze()

    assert second_project.id == first_project.id
    assert len(second_project.imports) == 2
    assert {imp.module_name for imp in second_project.imports} == {"os", "sys"}


def test_analyzer_incremental_analysis_preserves_and_replaces_imports(
    tmp_path: Path,
) -> None:
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"

    file_a.write_text("import math\n", encoding="utf-8")
    file_b.write_text("import json\n", encoding="utf-8")

    database_path = tmp_path / ".context_forge.db"
    first_analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = first_analyzer.analyze()

    assert len(first_project.imports) == 2

    file_b.write_text("import re\nimport csv\n", encoding="utf-8")

    second_analyzer = ProjectAnalyzer(tmp_path, database_path)
    second_project = second_analyzer.analyze()

    assert len(second_project.imports) == 3
    imports_by_file: dict[Path, list[str]] = {}
    for file in second_project.files:
        imports_by_file[file.path] = [
            imp.module_name for imp in second_project.imports if imp.file_id == file.id
        ]

    assert imports_by_file[Path("a.py")] == ["math"]
    assert sorted(imports_by_file[Path("b.py")]) == ["csv", "re"]


def test_analyzer_incremental_analysis_removes_imports_for_deleted_file(
    tmp_path: Path,
) -> None:
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"

    file_a.write_text("import math\n", encoding="utf-8")
    file_b.write_text("import json\n", encoding="utf-8")

    database_path = tmp_path / ".context_forge.db"
    first_analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = first_analyzer.analyze()
    assert len(first_project.imports) == 2

    file_b.unlink()

    second_analyzer = ProjectAnalyzer(tmp_path, database_path)
    second_project = second_analyzer.analyze()

    assert len(second_project.files) == 1
    assert len(second_project.imports) == 1
    assert second_project.imports[0].module_name == "math"

    loaded = second_analyzer.repository.load(second_project.id)
    assert loaded is not None
    assert len(loaded.imports) == 1
    assert loaded.imports[0].module_name == "math"


def test_analyzer_cache_schema_mismatch_triggers_safe_reanalysis(
    tmp_path: Path,
) -> None:
    source = tmp_path / "main.py"
    source.write_text("import sys\n", encoding="utf-8")
    database_path = tmp_path / ".context_forge.db"

    analyzer = ProjectAnalyzer(tmp_path, database_path)
    analyzer.analyze()

    with analyzer.database.connect() as connection:
        connection.execute(
            "UPDATE repository_cache SET cache_schema_version = ?",
            (0,),
        )

    second_analyzer = ProjectAnalyzer(tmp_path, database_path)
    reanalyzed = second_analyzer.analyze()

    assert reanalyzed.analysis_status == "analyzed"
    assert len(reanalyzed.imports) == 1
    assert reanalyzed.imports[0].module_name == "sys"


def test_analyzer_graph_relationships_consistent_with_cached_imports(
    tmp_path: Path,
) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    helper = src_dir / "helper.py"
    main = src_dir / "main.py"

    helper.write_text("def assist(): pass\n", encoding="utf-8")
    main.write_text("from helper import assist\n", encoding="utf-8")

    database_path = tmp_path / ".context_forge.db"
    first_analyzer = ProjectAnalyzer(tmp_path, database_path)
    first_project = first_analyzer.analyze()

    import_rels = [
        r
        for r in first_project.relationships
        if r.relationship_type == RelationshipType.IMPORTS
    ]
    assert len(import_rels) == 1

    second_analyzer = ProjectAnalyzer(tmp_path, database_path)
    second_project = second_analyzer.analyze()

    cached_import_rels = [
        r
        for r in second_project.relationships
        if r.relationship_type == RelationshipType.IMPORTS
    ]
    assert len(cached_import_rels) == 1
    assert len(second_project.imports) == 1


def test_current_fingerprints_handles_disappearing_file(tmp_path: Path) -> None:
    from context_forge.pipeline.analyzer import current_fingerprints
    from context_forge.scanner.repository import RepositoryScanner

    a = tmp_path / "a.py"
    a.write_text("def a(): pass\n", encoding="utf-8")
    b = tmp_path / "b.py"
    b.write_text("def b(): pass\n", encoding="utf-8")

    project = RepositoryScanner(tmp_path).scan()
    assert len(project.files) == 2

    # b.py disappears right after scan
    b.unlink()

    fps = current_fingerprints(project)
    assert Path("a.py") in fps
    assert Path("b.py") not in fps


def test_large_project_analysis_incremental_and_warm_correctness(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src"
    for pkg_idx in range(3):
        pkg_dir = src / f"pkg_{pkg_idx}"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
        for mod_idx in range(5):
            mod_file = pkg_dir / f"mod_{mod_idx}.py"
            mod_file.write_text(
                f"class Service_{pkg_idx}_{mod_idx}:\n"
                f"    def compute(self, x: int) -> int:\n"
                f"        return x + 1\n",
                encoding="utf-8",
            )

    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path=db_path)

    # 1. Cold analysis
    project_cold = analyzer.analyze()
    assert project_cold.analysis_status == "analyzed"
    assert len(project_cold.files) == 18
    assert len(project_cold.symbols) >= 30

    # 2. Warm analysis produces identical structure
    analyzer_warm = ProjectAnalyzer(tmp_path, database_path=db_path)
    project_warm = analyzer_warm.analyze()
    assert len(project_warm.files) == len(project_cold.files)
    assert len(project_warm.symbols) == len(project_cold.symbols)

    # 3. Modify single file
    target_file = src / "pkg_0" / "mod_0.py"
    target_file.write_text(
        "class Service_0_0:\n"
        "    def compute(self, x: int) -> int:\n"
        "        return x + 999\n"
        "    def extra(self) -> str:\n"
        "        return 'new'\n",
        encoding="utf-8",
    )

    analyzer_inc = ProjectAnalyzer(tmp_path, database_path=db_path)
    project_inc = analyzer_inc.analyze()
    assert project_inc.analysis_status == "analyzed"
    names = {s.name for s in project_inc.symbols}
    assert "extra" in names


def test_incremental_analysis_same_length_entity_replacement_preserves_membership_and_relationships(
    tmp_path: Path,
) -> None:
    from context_forge.models.symbol import Symbol

    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    file_a = src / "alpha.py"
    file_a.write_text(
        "class AlphaService:\n    def run(self) -> str:\n        return 'alpha'\n",
        encoding="utf-8",
    )

    file_b = src / "beta.py"
    file_b.write_text(
        "class BetaService:\n    def execute(self) -> int:\n        return 42\n",
        encoding="utf-8",
    )

    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path=db_path)

    project_1 = analyzer.analyze()
    assert project_1.analysis_status == "analyzed"
    names_1 = {s.name for s in project_1.symbols}
    assert "AlphaService" in names_1
    assert "BetaService" in names_1

    # Modify alpha.py by replacing AlphaService with GammaService (same number of classes and methods)
    file_a.write_text(
        "class GammaService:\n"
        "    def execute_gamma(self) -> str:\n"
        "        return 'gamma'\n",
        encoding="utf-8",
    )

    analyzer_inc = ProjectAnalyzer(tmp_path, database_path=db_path)
    project_2 = analyzer_inc.analyze()
    assert project_2.analysis_status == "analyzed"

    # New entity recognized
    names_2 = {s.name for s in project_2.symbols}
    assert "GammaService" in names_2
    assert "execute_gamma" in names_2

    # Removed entity not treated as current
    assert "AlphaService" not in names_2
    assert "run" not in names_2

    # Unchanged entities retained
    assert "BetaService" in names_2
    assert "execute" in names_2

    # Membership validation on merged project: can add valid new symbol for alpha.py
    file_a_entity = next(f for f in project_2.files if f.path == Path("src/alpha.py"))
    new_symbol = Symbol(
        file_id=file_a_entity.id,
        name="additional_func",
        kind="function",
        start_line=10,
        end_line=12,
    )
    project_2.add_symbol(new_symbol)
    assert new_symbol in project_2.symbols


def test_analyzer_fresh_cache_with_incomplete_or_failed_status_triggers_full_reanalysis(
    tmp_path: Path,
) -> None:
    import sqlite3

    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    app = src / "app.py"
    app.write_text("class Original:\n    pass\n", encoding="utf-8")

    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(tmp_path, database_path=db_path)

    # 1. Initial complete analysis
    first_project = analyzer.analyze()
    assert first_project.analysis_status == "analyzed"

    # 2. Corrupt/mark status as 'failed' in SQLite projects table while fingerprints remain fresh
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE projects SET analysis_status = 'failed'")
    conn.commit()
    conn.close()

    # 3. Analyze again with unchanged files
    second_analyzer = ProjectAnalyzer(tmp_path, database_path=db_path)
    second_project = second_analyzer.analyze()

    # Must not return the failed project; must reanalyze fully to 'analyzed'
    assert second_project.analysis_status == "analyzed"
    names = {s.name for s in second_project.symbols}
    assert "Original" in names
