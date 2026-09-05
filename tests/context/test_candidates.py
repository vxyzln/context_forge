import subprocess
from pathlib import Path

from context_forge.context.candidates import CandidateGenerator
from context_forge.context.types import ContextUnitType
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.task.models import (
    GroundedEntity,
    GroundedTask,
    RepositoryGrounding,
    TaskInterpretation,
)


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


def test_candidate_generator_adds_git_relevance_signal(
    tmp_path: Path,
) -> None:
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


def test_grounded_entity_becomes_candidate() -> None:
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

    from context_forge.models.symbol import Symbol

    symbol = Symbol(
        file_id=file.id,
        name="AuthenticationService",
        qualified_name="AuthenticationService",
        kind="class",
        start_line=1,
        end_line=10,
    )

    project.add_symbol(symbol)

    interpretation = TaskInterpretation(
        task=f"Fix {symbol.name}",
        intent="fix",
        target=symbol.name,
    )

    grounded_task = GroundedTask(
        interpretation=interpretation,
        entities=(
            GroundedEntity(
                entity_id=symbol.id,
                entity_type="symbol",
                reference=symbol.name,
                confidence=1.0,
                provenance="exact symbol qualified name",
            ),
        ),
    )

    grounding = RepositoryGrounding(
        task=grounded_task,
    )

    generator = CandidateGenerator()

    candidates, _ = generator.generate(
        project,
        interpretation.task,
        interpretation,
        grounding,
    )

    grounded_candidates = [
        candidate for candidate in candidates if candidate.entity_id == symbol.id
    ]

    assert grounded_candidates
    assert grounded_candidates[0].unit_type == ContextUnitType.SYMBOL


def test_repository_related_entity_becomes_candidate() -> None:
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

    from context_forge.models.symbol import Symbol

    source = Symbol(
        file_id=file.id,
        name="authenticate",
        qualified_name="authenticate",
        kind="function",
        start_line=1,
        end_line=5,
    )

    target = Symbol(
        file_id=file.id,
        name="validate_token",
        qualified_name="validate_token",
        kind="function",
        start_line=7,
        end_line=12,
    )

    project.add_symbol(source)
    project.add_symbol(target)

    project.add_relationship(
        Relationship(
            source_id=source.id,
            target_id=target.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    )

    interpretation = TaskInterpretation(
        task=f"Fix {source.name}",
        intent="fix",
        target=source.name,
    )

    grounded_task = GroundedTask(
        interpretation=interpretation,
        entities=(
            GroundedEntity(
                entity_id=source.id,
                entity_type="symbol",
                reference=source.name,
                confidence=1.0,
                provenance="exact symbol qualified name",
            ),
        ),
    )

    grounding = RepositoryGrounding(
        task=grounded_task,
        related_entity_ids=(target.id,),
    )

    candidates, _ = CandidateGenerator().generate(
        project,
        interpretation.task,
        interpretation,
        grounding,
    )

    candidate = next(
        candidate for candidate in candidates if candidate.entity_id == target.id
    )

    assert candidate.unit_type == ContextUnitType.SYMBOL
    assert candidate.source == "repository_grounding"
    assert candidate.score == 0.7
    assert candidate.reason == "Repository relationship traversal"


def test_grounded_candidates_are_not_duplicated() -> None:
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

    from context_forge.models.symbol import Symbol

    symbol = Symbol(
        file_id=file.id,
        name="AuthenticationService",
        qualified_name="AuthenticationService",
        kind="class",
        start_line=1,
        end_line=10,
    )

    project.add_symbol(symbol)

    interpretation = TaskInterpretation(
        task=symbol.name,
        intent="inspect",
        target=symbol.name,
    )

    grounded_task = GroundedTask(
        interpretation=interpretation,
        entities=(
            GroundedEntity(
                entity_id=symbol.id,
                entity_type="symbol",
                reference=symbol.name,
                confidence=1.0,
                provenance="exact symbol qualified name",
            ),
        ),
    )

    grounding = RepositoryGrounding(
        task=grounded_task,
        related_entity_ids=(symbol.id,),
    )

    candidates, _ = CandidateGenerator().generate(
        project,
        interpretation.task,
        interpretation,
        grounding,
    )

    matching = [
        candidate for candidate in candidates if candidate.entity_id == symbol.id
    ]

    assert len(matching) == 1


def test_candidate_generator_adds_lexical_signal_for_file_search() -> None:
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

    candidates, signals = CandidateGenerator().generate(
        project,
        "auth",
    )

    assert candidates
    assert signals[file.id].lexical == candidates[0].score


def test_candidate_generator_adds_symbol_signal_for_symbol_search() -> None:
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

    symbol = Symbol(
        file_id=file.id,
        name="authenticate",
        qualified_name="authenticate",
        kind="function",
        start_line=1,
        end_line=3,
    )
    project.add_symbol(symbol)

    candidates, signals = CandidateGenerator().generate(
        project,
        "authenticate",
    )

    assert candidates
    assert candidates[0].unit_type == ContextUnitType.SYMBOL
    assert signals[symbol.id].symbol == candidates[0].score


def test_grounded_candidate_does_not_receive_lexical_signal() -> None:
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

    interpretation = TaskInterpretation(
        task="Fix AuthenticationService",
        intent="fix",
        target="AuthenticationService",
    )

    grounded_task = GroundedTask(
        interpretation=interpretation,
        entities=(
            GroundedEntity(
                entity_id=file.id,
                entity_type="file",
                reference="src/auth.py",
                confidence=1.0,
                provenance="exact repository-relative file path",
            ),
        ),
    )

    grounding = RepositoryGrounding(task=grounded_task)

    _, signals = CandidateGenerator().generate(
        project,
        "Fix AuthenticationService",
        interpretation=interpretation,
        grounding=grounding,
    )

    assert signals[file.id].lexical == 0.0
