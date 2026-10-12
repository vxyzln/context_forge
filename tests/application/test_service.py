from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.application.factory import build_context_service
from context_forge.application.service import RepositoryContextService
from context_forge.context.engine import ContextEngine
from context_forge.context.models import ContextPackage, ContextUnit
from context_forge.context.request import ContextRequest
from context_forge.context.types import ContextUnitType
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.task import (
    TaskInterpretation,
    TaskState,
    TaskValidation,
    TaskValidator,
)


class FakeEngine(ContextEngine):
    def __init__(self) -> None:
        self.requests: list[ContextRequest] = []

    def build(self, request: ContextRequest) -> ContextPackage:
        self.requests.append(request)
        unit = ContextUnit(
            entity_id=uuid4(),
            unit_type=ContextUnitType.FILE,
            relevance=1.0,
        )
        return ContextPackage(
            task=request.task,
            units=(unit,),
        )


def test_repository_context_service_retrieves_context() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )
    engine = FakeEngine()
    service = RepositoryContextService(engine=engine)

    package = service.retrieve_context(project, "Explain authentication")

    assert package.task == "Explain authentication"
    assert len(package.units) == 1
    assert len(engine.requests) == 1
    assert engine.requests[0].task == "Explain authentication"
    assert engine.requests[0].project is project


def test_repository_context_service_rejects_empty_task() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )
    service = RepositoryContextService(engine=FakeEngine())

    with pytest.raises(ValueError, match="task must not be empty"):
        service.retrieve_context(project, "   ")


def test_repository_context_service_rejects_ambiguous_task() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )

    class AmbiguousValidator(TaskValidator):
        def validate(self, interpretation: TaskInterpretation) -> TaskValidation:
            return TaskValidation(
                state=TaskState.AMBIGUOUS,
                reasons=("Task is too vague",),
            )

    service = RepositoryContextService(
        engine=FakeEngine(),
        task_validator=AmbiguousValidator(),
    )

    with pytest.raises(ValueError, match="task validation failed: ambiguous"):
        service.retrieve_context(project, "do something")


def test_repository_context_service_grounds_task_entities() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )
    auth_file = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    project.add_file(auth_file)

    engine = FakeEngine()
    service = RepositoryContextService(engine=engine)

    package = service.retrieve_context(project, "Inspect auth.py")

    assert package.task == "Inspect auth.py"
    assert len(engine.requests) == 1
    request = engine.requests[0]
    assert request.grounding is not None


def test_build_context_service_end_to_end() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/demo"),
    )
    main_file = File(
        project_id=project.id,
        path=Path("src/main.py"),
        name="main.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    project.add_file(main_file)

    service = build_context_service()
    package = service.retrieve_context(project, "Inspect main.py")

    assert package.task == "Inspect main.py"
    assert isinstance(package, ContextPackage)
