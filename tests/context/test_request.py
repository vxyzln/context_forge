from pathlib import Path

import pytest

from context_forge.context import ContextRequest
from context_forge.models.project import Project
from context_forge.task import TaskInterpretation


def test_context_request_stores_task_interpretation() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    interpretation = TaskInterpretation(
        task="Fix settings scrolling",
        intent="bug_fix",
        target="settings page",
        concepts=("scrolling", "settings"),
        requested_action="fix",
        constraints=("preserve existing behavior",),
    )

    request = ContextRequest(
        project=project,
        task="Fix settings scrolling",
        interpretation=interpretation,
    )

    assert request.project is project
    assert request.task == "Fix settings scrolling"
    assert request.interpretation is interpretation


def test_context_request_is_immutable() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    request = ContextRequest(
        project=project,
        task="Fix scrolling",
    )

    with pytest.raises(AttributeError):
        request.task = "Change feature"


def test_context_request_defaults_interpretation() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    request = ContextRequest(
        project=project,
        task="Explain authentication",
    )

    assert request.interpretation is None
