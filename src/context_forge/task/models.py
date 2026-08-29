from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskInterpretation:
    task: str
    intent: str
    target: str | None
    concepts: tuple[str, ...] = field(default_factory=tuple)
    requested_action: str | None = None
    constraints: tuple[str, ...] = field(default_factory=tuple)
    ambiguity: str | None = None
