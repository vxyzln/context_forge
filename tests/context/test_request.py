from pathlib import Path

import pytest

from context_forge.context import ContextRequest
from context_forge.models.project import Project


def test_context_request_stores_task_context() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    request = ContextRequest(
        project=project,
        task="Fix settings scrolling",
        intent="bug_fix",
        target="settings page",
        concepts=("scrolling", "settings"),
        requested_action="fix",
        constraints=("preserve existing behavior",),
    )

    assert request.project is project
    assert request.task == "Fix settings scrolling"
    assert request.intent == "bug_fix"
    assert request.target == "settings page"
    assert request.concepts == ("scrolling", "settings")
    assert request.requested_action == "fix"
    assert request.constraints == ("preserve existing behavior",)


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


def test_context_request_defaults_optional_task_metadata() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    request = ContextRequest(
        project=project,
        task="Explain authentication",
    )

    assert request.intent is None
    assert request.target is None
    assert request.concepts == ()
    assert request.requested_action is None
    assert request.constraints == ()