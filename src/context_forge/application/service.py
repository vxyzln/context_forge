from context_forge.context.engine import ContextEngine
from context_forge.context.models import ContextPackage
from context_forge.context.request import ContextRequest
from context_forge.models.project import Project
from context_forge.task import (
    TaskGroundingService,
    TaskRepositoryGroundingService,
    TaskState,
    TaskUnderstandingService,
    TaskValidator,
)


class RepositoryContextService:
    """Orchestrates deterministic repository context retrieval for development tasks."""

    def __init__(
        self,
        engine: ContextEngine,
        task_understanding: TaskUnderstandingService | None = None,
        task_validator: TaskValidator | None = None,
        task_grounding: TaskGroundingService | None = None,
        task_repository_grounding: TaskRepositoryGroundingService | None = None,
    ) -> None:
        self.engine = engine
        self.task_understanding = task_understanding or TaskUnderstandingService()
        self.task_validator = task_validator or TaskValidator()
        self.task_grounding = task_grounding or TaskGroundingService()
        self.task_repository_grounding = (
            task_repository_grounding or TaskRepositoryGroundingService()
        )

    def retrieve_context(
        self,
        project: Project,
        task: str,
    ) -> ContextPackage:
        if not task.strip():
            raise ValueError("task must not be empty")

        interpretation = self.task_understanding.understand(task)
        validation = self.task_validator.validate(interpretation)

        if validation.state != TaskState.CLEAR:
            raise ValueError(f"task validation failed: {validation.state.value}")

        grounded_task = self.task_grounding.ground(
            project,
            interpretation,
        )

        grounding = self.task_repository_grounding.ground(
            project,
            grounded_task,
        )

        return self.engine.build(
            ContextRequest(
                project=project,
                task=task,
                interpretation=interpretation,
                grounding=grounding,
            )
        )
