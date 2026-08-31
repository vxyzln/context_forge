from pathlib import Path

from context_forge.config.loader import (
    load_global_config,
    load_project_config,
)
from context_forge.config.project import ProjectConfiguration
from context_forge.config.validation import validate_project_config


def load_global_configuration() -> ProjectConfiguration:
    return validate_project_config(load_global_config())


def load_project_configuration(project_root: Path) -> ProjectConfiguration:
    return validate_project_config(load_project_config(project_root))
