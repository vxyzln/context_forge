from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectProviderConfiguration:
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class ProjectGenerationConfiguration:
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class ProjectConfiguration:
    provider: ProjectProviderConfiguration = ProjectProviderConfiguration()
    generation: ProjectGenerationConfiguration = ProjectGenerationConfiguration()
