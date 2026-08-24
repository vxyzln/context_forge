from pathlib import Path

from context_forge.context.candidates import CandidateGenerator
from context_forge.context.types import ContextUnitType
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project


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

    candidates = CandidateGenerator().generate(project, "auth")

    assert len(candidates) == 1
    assert candidates[0].entity_id == file.id
    assert candidates[0].unit_type == ContextUnitType.FILE
    assert candidates[0].score > 0
