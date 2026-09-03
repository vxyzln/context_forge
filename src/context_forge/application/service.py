from context_forge.context.engine import ContextEngine
from context_forge.context.request import ContextRequest
from context_forge.context.serialization import ContextPackageSerializer
from context_forge.models.project import Project
from context_forge.provider.base import ContextProvider
from context_forge.provider.config import ProviderConfig
from context_forge.provider.models import GenerationRequest, GenerationResponse
from context_forge.task import (
    TaskGroundingService,
    TaskState,
    TaskUnderstandingService,
    TaskValidator,
)


class ContextGenerationService:
    def __init__(
        self,
        engine: ContextEngine,
        serializer: ContextPackageSerializer,
        provider: ContextProvider,
        task_understanding: TaskUnderstandingService | None = None,
        task_validator: TaskValidator | None = None,
        task_grounding: TaskGroundingService | None = None,
    ) -> None:
        self.engine = engine
        self.serializer = serializer
        self.provider = provider
        self.task_understanding = task_understanding
        self.task_validator = task_validator
        self.task_grounding = task_grounding

    def generate(
        self,
        project: Project,
        task: str,
        config: ProviderConfig,
    ) -> GenerationResponse:
        interpretation = None
        grounding = None

        if self.task_understanding is not None and self.task_validator is not None:
            interpretation = self.task_understanding.understand(task)
            validation = self.task_validator.validate(interpretation)

            if validation.state != TaskState.CLEAR:
                raise ValueError(f"task validation failed: {validation.state.value}")

        if interpretation is not None and self.task_grounding is not None:
            grounding = self.task_grounding.ground(
                project,
                interpretation,
            )

        package = self.engine.build(
            ContextRequest(
                project=project,
                task=task,
                interpretation=interpretation,
                grounding=grounding,
            )
        )

        context = self.serializer.serialize(package)
        prompt = self._build_prompt(task=task, context=context)

        request = GenerationRequest(
            task=task,
            context=context,
            prompt=prompt,
            config=config,
        )

        return self.provider.generate(request)

    @staticmethod
    def _build_prompt(*, task: str, context: str) -> str:
        return (
            "Use the following task and project context to answer "
            "the user's request.\n\n"
            f"Task:\n{task}\n\n"
            f"Context:\n{context}"
        )
