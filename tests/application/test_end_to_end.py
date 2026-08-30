from pathlib import Path

from context_forge.application import build_generation_service
from context_forge.models.project import Project
from context_forge.provider import ProviderConfig


def test_generation_service_runs_end_to_end() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    service = build_generation_service(
        ProviderConfig(
            provider="deterministic",
            model="deterministic",
        )
    )

    response = service.generate(
        project=project,
        task="authenticate user",
        config=ProviderConfig(model="deterministic"),
    )

    assert response.provider == "deterministic"
    assert response.model == "deterministic"
    assert response.content.startswith("Task: authenticate user")
    assert "Context received:" in response.content


def test_generation_service_rejects_empty_task() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    service = build_generation_service(
        ProviderConfig(
            provider="deterministic",
            model="deterministic",
        )
    )

    try:
        service.generate(
            project=project,
            task="   ",
            config=ProviderConfig(model="deterministic"),
        )
    except ValueError as exc:
        assert str(exc) == "task must not be empty"
    else:
        raise AssertionError("Expected ValueError")
