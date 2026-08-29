from context_forge.context.engine import ContextEngine
from context_forge.context.serialization import ContextPackageSerializer
from context_forge.models.project import Project
from context_forge.provider.base import ContextProvider
from context_forge.provider.config import ProviderConfig
from context_forge.provider.models import GenerationRequest, GenerationResponse
from context_forge.task import TaskState, TaskUnderstandingService, TaskValidator


class ContextGenerationService:
    """Generate a provider response from project context."""

    def __init__(
        self,
        engine: ContextEngine,
        serializer: ContextPackageSerializer,
        provider: ContextProvider,
        task_understanding: TaskUnderstandingService | None = None,
        task_validator: TaskValidator | None = None,
    ) -> None:
        self.engine = engine
        self.serializer = serializer
        self.provider = provider
        self.task_understanding = task_understanding
        self.task_validator = task_validator

    def generate(
        self,
        project: Project,
        task: str,
        config: ProviderConfig,
    ) -> GenerationResponse:
        if self.task_understanding is not None and self.task_validator is not None:
            interpretation = self.task_understanding.understand(task)
            validation = self.task_validator.validate(interpretation)

            if validation.state.value != TaskState.CLEAR:
                raise ValueError(f"task validation failed: {validation.state.value}")

        package = self.engine.build(project, task)
        context = self.serializer.serialize(package)

        request = GenerationRequest(
            task=task,
            context=context,
            config=config,
        )

        return self.provider.generate(request)
