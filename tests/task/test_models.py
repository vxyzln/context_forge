import pytest

from context_forge.task import TaskInterpretation


def test_task_interpretation_is_immutable() -> None:
    interpretation = TaskInterpretation(
        task="Fix settings scrolling",
        intent="bug_fix",
        target="settings page",
        concepts=("scrolling", "settings"),
        requested_action="fix",
        constraints=("preserve existing behavior",),
        ambiguity=None,
    )

    assert interpretation.task == "Fix settings scrolling"
    assert interpretation.intent == "bug_fix"
    assert interpretation.target == "settings page"
    assert interpretation.concepts == ("scrolling", "settings")
    assert interpretation.requested_action == "fix"
    assert interpretation.constraints == ("preserve existing behavior",)


def test_task_interpretation_is_frozen() -> None:
    interpretation = TaskInterpretation(
        task="Fix scrolling",
        intent="bug_fix",
        target="settings",
    )

    with pytest.raises(AttributeError):
        interpretation.intent = "feature"
