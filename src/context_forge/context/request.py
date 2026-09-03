from dataclasses import dataclass

from context_forge.models.project import Project
from context_forge.task import GroundedTask, TaskInterpretation


@dataclass(frozen=True)
class ContextRequest:
    project: Project
    task: str
    interpretation: TaskInterpretation | None = None
    grounding: GroundedTask | None = None
