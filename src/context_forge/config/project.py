from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProjectStorageConfiguration:
    database_path: str | None = None


@dataclass(frozen=True)
class ProjectAnalysisConfiguration:
    max_context_units: int | None = None


@dataclass(frozen=True)
class ProjectConfiguration:
    storage: ProjectStorageConfiguration = field(
        default_factory=ProjectStorageConfiguration
    )
    analysis: ProjectAnalysisConfiguration = field(
        default_factory=ProjectAnalysisConfiguration
    )
