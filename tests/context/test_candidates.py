import subprocess
from pathlib import Path

from context_forge.context.candidates import CandidateGenerator
from context_forge.context.types import ContextUnitType
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.task import TaskInterpretation


def run_git(path: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_candidate_generator_generates_candidates() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    file = File(
        project_id=project.id,
        path=Path("src/auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(file)

    candidates, signals = CandidateGenerator().generate(project, "auth")

    assert len(candidates) == 1
    assert candidates[0].entity_id == file.id
    assert candidates[0].unit_type == ContextUnitType.FILE
    assert candidates[0].score > 0
    assert signals[file.id].git == 0.0


def test_candidate_generator_preserves_selection_reason() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    file = File(
        project_id=project.id,
        path=Path("src/auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(file)

    candidates, _ = CandidateGenerator().generate(project, "auth")

    assert len(candidates) == 1
    assert candidates[0].reason == "File name contains query"


def test_git_relevance_changes_candidate_signal(
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

    source = tmp_path / "auth.py"
    source.write_text(
        """
def auth():
    return True
"""
    )

    run_git(tmp_path, "add", "auth.py")
    run_git(tmp_path, "commit", "-m", "add auth")

    source.write_text(
        """
def auth():
    return False
"""
    )

    run_git(tmp_path, "add", "auth.py")
    run_git(tmp_path, "commit", "-m", "change auth")

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    candidates, signals = CandidateGenerator().generate(
        project,
        "auth.py",
    )

    assert candidates
    assert signals

    candidate = candidates[0]

    assert candidate.entity_id in signals
    assert signals[candidate.entity_id].git == 0.2


def test_candidate_generator_adds_git_relevance_signal(tmp_path: Path) -> None:
    run_git(tmp_path, "init")
    run_git(tmp_path, "config", "user.name", "Context Forge Test")
    run_git(tmp_path, "config", "user.email", "test@example.com")

    source_file = tmp_path / "auth.py"
    source_file.write_text(
        """
def authenticate():
    return True
"""
    )

    run_git(tmp_path, "add", "auth.py")
    run_git(tmp_path, "commit", "-m", "add auth")

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    candidates, signals = CandidateGenerator().generate(
        project,
        "auth.py",
    )

    assert candidates
    assert candidates[0].source == "deterministic_search"

    git_signal = signals[candidates[0].entity_id]

    assert git_signal.git == 0.1


def test_candidate_generator_uses_task_interpretation_for_symbols(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "calculator.py"
    source_file.write_text(
        """
class Calculator:
    def add(self, a, b):
        return a + b
""",
        encoding="utf-8",
    )

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    interpretation = TaskInterpretation(
        task="Where is Calculator used?",
        intent="question",
        target="Calculator",
        concepts=("Calculator",),
        requested_action="find",
        constraints=(),
        ambiguity=None,
    )

    _, signals = CandidateGenerator().generate(
        project,
        "Where is Calculator used?",
        interpretation=interpretation,
    )

    calculator_file = next(
        file for file in project.files if file.name == "calculator.py"
    )

    assert calculator_file.id in signals
    assert signals[calculator_file.id].task == 1.0
