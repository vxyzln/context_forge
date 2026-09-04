from dataclasses import dataclass

from context_forge.models.project import Project
from context_forge.task import RepositoryGrounding, TaskInterpretation


@dataclass(frozen=True)
class ContextRequest:
    project: Project
    task: str
    interpretation: TaskInterpretation | None = None
    grounding: RepositoryGrounding | None = None
