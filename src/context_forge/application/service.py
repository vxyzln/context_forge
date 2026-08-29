from context_forge.context.engine import ContextEngine
from context_forge.context.serialization import ContextPackageSerializer
from context_forge.models.project import Project
from context_forge.provider.base import ContextProvider
from context_forge.provider.config import ProviderConfig
from context_forge.provider.models import GenerationRequest, GenerationResponse


class ContextGenerationService:
    """Generate a provider response from project context."""

    def __init__(
        self,
        engine: ContextEngine,
        serializer: ContextPackageSerializer,
        provider: ContextProvider,
    ) -> None:
        self.engine = engine
        self.serializer = serializer
        self.provider = provider

    def generate(
        self,
        project: Project,
        task: str,
        config: ProviderConfig,
    ) -> GenerationResponse:
        package = self.engine.build(project, task)
        context = self.serializer.serialize(package)

        request = GenerationRequest(
            task=task,
            context=context,
            config=config,
        )

        return self.provider.generate(request)
