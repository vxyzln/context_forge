from context_forge.task import (
    TaskInterpretation,
    TaskState,
    TaskValidator,
)


def make_interpretation(
    *,
    task: str = "Fix settings scrolling",
    intent: str = "bug_fix",
    target: str | None = "settings page",
    concepts: tuple[str, ...] = ("scrolling",),
    requested_action: str | None = "fix",
    constraints: tuple[str, ...] = (),
    ambiguity: str | None = None,
) -> TaskInterpretation:
    return TaskInterpretation(
        task=task,
        intent=intent,
        target=target,
        concepts=concepts,
        requested_action=requested_action,
        constraints=constraints,
        ambiguity=ambiguity,
    )


def test_clear_task() -> None:
    result = TaskValidator().validate(make_interpretation())

    assert result.state is TaskState.CLEAR
    assert result.reasons == ()


def test_ambiguous_task() -> None:
    result = TaskValidator().validate(
        make_interpretation(
            ambiguity="The target component is unclear.",
        )
    )

    assert result.state is TaskState.AMBIGUOUS
    assert result.reasons == ("The target component is unclear.",)


def test_missing_task_is_insufficient() -> None:
    result = TaskValidator().validate(
        make_interpretation(task=""),
    )

    assert result.state is TaskState.INSUFFICIENT
    assert "task is empty" in result.reasons


def test_missing_intent_is_insufficient() -> None:
    result = TaskValidator().validate(
        make_interpretation(intent=""),
    )

    assert result.state is TaskState.INSUFFICIENT
    assert "task intent is missing" in result.reasons


def test_missing_concepts_is_recorded() -> None:
    result = TaskValidator().validate(
        make_interpretation(concepts=()),
    )

    assert result.state is TaskState.CLEAR
    assert result.reasons == ("task concepts are missing",)


def test_missing_requested_action_is_recorded() -> None:
    result = TaskValidator().validate(
        make_interpretation(requested_action=None),
    )

    assert result.state is TaskState.CLEAR
    assert result.reasons == ("requested action is missing",)


def test_ambiguity_takes_precedence_over_noncritical_missing_fields() -> None:
    result = TaskValidator().validate(
        make_interpretation(
            concepts=(),
            requested_action=None,
            ambiguity="The requested behavior is unclear.",
        )
    )

    assert result.state is TaskState.AMBIGUOUS
    assert result.reasons == (
        "task concepts are missing",
        "requested action is missing",
        "The requested behavior is unclear.",
    )
