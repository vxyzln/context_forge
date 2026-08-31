from pathlib import Path

import pytest

from context_forge.config import (
    ConfigurationValidationError,
    ProjectConfiguration,
    ProjectGenerationConfiguration,
    ProjectProviderConfiguration,
    load_global_configuration,
    load_project_configuration,
)


def test_load_project_configuration_returns_empty_configuration_when_missing(
    tmp_path: Path,
) -> None:
    assert load_project_configuration(tmp_path) == ProjectConfiguration()


def test_load_project_configuration_returns_typed_configuration(
    tmp_path: Path,
) -> None:
    (tmp_path / ".contextforge.toml").write_text(
        """
[provider]
provider = "ollama"
model = "qwen2.5-coder:7b"
base_url = "http://localhost:11434"

[generation]
temperature = 0.2
max_tokens = 2048
""",
        encoding="utf-8",
    )

    result = load_project_configuration(tmp_path)

    assert result == ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            provider="ollama",
            model="qwen2.5-coder:7b",
            base_url="http://localhost:11434",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.2,
            max_tokens=2048,
        ),
    )


def test_load_project_configuration_validates_loaded_values(
    tmp_path: Path,
) -> None:
    (tmp_path / ".contextforge.toml").write_text(
        """
[generation]
temperature = 3.0
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'temperature' must be between 0.0 and 2.0",
    ):
        load_project_configuration(tmp_path)


def test_load_global_configuration_returns_empty_configuration_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    assert load_global_configuration() == ProjectConfiguration()


def test_load_global_configuration_returns_typed_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[provider]
model = "qwen2.5-coder:7b"

[generation]
temperature = 0.5
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    result = load_global_configuration()

    assert result == ProjectConfiguration(
        provider=ProjectProviderConfiguration(
            model="qwen2.5-coder:7b",
        ),
        generation=ProjectGenerationConfiguration(
            temperature=0.5,
        ),
    )


def test_load_global_configuration_validates_loaded_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[provider]
model = ""
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'model' cannot be empty",
    ):
        load_global_configuration()
