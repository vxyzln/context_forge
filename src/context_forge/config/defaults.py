from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigurationDefaults:
    database_path: str = ".context_forge.db"
    max_context_units: int = 20


DEFAULTS = ConfigurationDefaults()
