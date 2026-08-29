from dataclasses import dataclass
from enum import Enum

from .models import TaskInterpretation


class TaskState(str, Enum):
    CLEAR = "clear"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class TaskValidation:
    state: TaskState
    reasons: tuple[str, ...] = ()


class TaskValidator:
    """Validate whether a structured task is sufficiently clear."""

    def validate(
        self,
        interpretation: TaskInterpretation,
    ) -> TaskValidation:
        reasons: list[str] = []

        if not interpretation.task.strip():
            reasons.append("task is empty")

        if not interpretation.intent.strip():
            reasons.append("task intent is missing")

        if not interpretation.concepts:
            reasons.append("task concepts are missing")

        if not interpretation.requested_action:
            reasons.append("requested action is missing")

        if interpretation.ambiguity:
            reasons.append(interpretation.ambiguity)

        if not interpretation.task.strip() or not interpretation.intent.strip():
            return TaskValidation(
                state=TaskState.INSUFFICIENT,
                reasons=tuple(reasons),
            )

        if interpretation.ambiguity:
            return TaskValidation(
                state=TaskState.AMBIGUOUS,
                reasons=tuple(reasons),
            )

        return TaskValidation(
            state=TaskState.CLEAR,
            reasons=tuple(reasons),
        )
