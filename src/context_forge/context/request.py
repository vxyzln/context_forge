from dataclasses import dataclass, field

from context_forge.models.project import Project
from context_forge.task import TaskInterpretation


@dataclass(frozen=True)
class ContextRequest:
    project: Project
    task: str
    interpretation: TaskInterpretation | None = None
    intent: str | None = None
    target: str | None = None
    concepts: tuple[str, ...] = field(default_factory=tuple)
    requested_action: str | None = None
    constraints: tuple[str, ...] = field(default_factory=tuple)
