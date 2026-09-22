from context_forge.context.engine import ContextEngine
from context_forge.context.request import ContextRequest
from context_forge.context.serialization import ContextPackageSerializer
from context_forge.models.project import Project
from context_forge.provider.base import ContextProvider
from context_forge.provider.config import ProviderConfig
from context_forge.provider.models import GenerationRequest, GenerationResponse
from context_forge.provider.runtime import OllamaRuntime
from context_forge.task import (
    TaskGroundingService,
    TaskRepositoryGroundingService,
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
        task_repository_grounding: TaskRepositoryGroundingService | None = None,
        ollama_runtime: OllamaRuntime | None = None,
    ) -> None:
        self.engine = engine
        self.serializer = serializer
        self.provider = provider
        self.task_understanding = task_understanding
        self.task_validator = task_validator
        self.task_grounding = task_grounding
        self.task_repository_grounding = task_repository_grounding
        self.ollama_runtime = ollama_runtime

    def _validate_runtime(self, config: ProviderConfig) -> None:
        if config.provider != "ollama":
            return

        if self.ollama_runtime is None:
            return

        status = self.ollama_runtime.check(config.model)

        if not status.available:
            raise RuntimeError(f"Ollama runtime is unavailable at {config.base_url}")

        if not status.model_available:
            raise RuntimeError(
                f"Ollama model '{config.model}' is not available at {config.base_url}"
            )

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

        self._validate_runtime(config)

        if interpretation is not None and self.task_grounding is not None:
            grounded_task = self.task_grounding.ground(
                project,
                interpretation,
            )

            if self.task_repository_grounding is not None:
                grounding = self.task_repository_grounding.ground(
                    project,
                    grounded_task,
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
