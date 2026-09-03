import subprocess
from pathlib import Path

from context_forge.models.relationship import RelationshipType
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
