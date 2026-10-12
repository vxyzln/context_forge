import re

from .models import TaskInterpretation


class TaskUnderstandingService:
    """Deterministically interpret a natural-language development task."""

    _ACTION_WORDS = frozenset(
        {
            "add",
            "analyze",
            "build",
            "check",
            "clean",
            "create",
            "debug",
            "delete",
            "describe",
            "explain",
            "find",
            "fix",
            "generate",
            "get",
            "implement",
            "inspect",
            "list",
            "locate",
            "modify",
            "refactor",
            "remove",
            "retrieve",
            "search",
            "show",
            "test",
            "trace",
            "update",
            "validate",
            "verify",
        }
    )

    _WORD_PATTERN = re.compile(r"[A-Za-z0-9_./\\-]+")

    def __init__(self) -> None:
        pass

    def understand(self, task: str) -> TaskInterpretation:
        if not task.strip():
            raise ValueError("task must not be empty")

        normalized = task.strip()
        tokens = self._WORD_PATTERN.findall(normalized)

        requested_action: str | None = None
        target: str | None = None
        concepts: list[str] = []

        for token in tokens:
            clean = token.strip()
            if not clean:
                continue

            lower = clean.lower()
            if requested_action is None and lower in self._ACTION_WORDS:
                requested_action = lower
            elif target is None and (
                "/" in clean
                or "." in clean
                or "_" in clean
                or any(c.isupper() for c in clean[1:])
                or (
                    clean.isidentifier()
                    and clean[0].isupper()
                    and lower
                    not in {
                        "class",
                        "function",
                        "method",
                        "module",
                        "file",
                        "error",
                        "test",
                        "tests",
                    }
                )
            ):
                target = clean

            if clean not in concepts:
                concepts.append(clean)

        return TaskInterpretation(
            task=normalized,
            intent=normalized,
            target=target,
            concepts=tuple(concepts),
            requested_action=requested_action,
            constraints=(),
            ambiguity=None,
        )
