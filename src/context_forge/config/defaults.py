from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigurationDefaults:
    provider: str = "ollama"
    model: str = "qwen2.5-coder:7b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.0
    max_tokens: int | None = None


DEFAULTS = ConfigurationDefaults()
