import pytest

from context_forge.config import (
    ConfigurationValidationError,
    ProjectConfiguration,
    ProjectGenerationConfiguration,
    ProjectProviderConfiguration,
    validate_project_config,
)


def test_validate_project_config_uses_empty_sections_when_missing() -> None:
    result = validate_project_config({})

    assert result == ProjectConfiguration()


def test_validate_project_config_reads_provider_configuration() -> None:
    result = validate_project_config(
        {
            "provider": {
                "provider": "ollama",
                "model": "qwen2.5-coder:7b",
                "base_url": "http://localhost:11434",
            }
        }
    )

    assert result.provider == ProjectProviderConfiguration(
        provider="ollama",
        model="qwen2.5-coder:7b",
        base_url="http://localhost:11434",
    )


def test_validate_project_config_reads_generation_configuration() -> None:
    result = validate_project_config(
        {
            "generation": {
                "temperature": 0.2,
                "max_tokens": 2048,
            }
        }
    )

    assert result.generation == ProjectGenerationConfiguration(
        temperature=0.2,
        max_tokens=2048,
    )


def test_validate_project_config_preserves_partial_configuration() -> None:
    result = validate_project_config(
        {
            "provider": {
                "model": "qwen2.5-coder:7b",
            },
            "generation": {
                "temperature": 0.2,
            },
        }
    )

    assert result.provider.model == "qwen2.5-coder:7b"
    assert result.provider.provider is None
    assert result.provider.base_url is None
    assert result.generation.temperature == 0.2
    assert result.generation.max_tokens is None


@pytest.mark.parametrize(
    "data",
    (
        {"unknown": {}},
        {"provider": {}, "unknown": {}},
    ),
)
def test_validate_project_config_rejects_unknown_sections(
    data: dict[str, object],
) -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Unknown configuration section",
    ):
        validate_project_config(data)


@pytest.mark.parametrize(
    "value",
    (123, True, [], {}),
)
def test_validate_project_config_validates_provider_name(
    value: object,
) -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'provider' must be a string",
    ):
        validate_project_config({"provider": {"provider": value}})


def test_validate_project_config_rejects_empty_model() -> None:
    with pytest.raises(
        ConfigurationValidationError,
        match="Configuration value 'model' cannot be empty",
    ):
        validate_project_config({"provider": {"model": "   "}})


@pytest.mark.parametrize(
    "value",
    (-0.1, 2.1, "0.5", True),
)
def test_validate_project_config_validates_temperature(
    value: object,
) -> None:
    with pytest.raises(
        ConfigurationValidationError,
    ):
        validate_project_config({"generation": {"temperature": value}})


@pytest.mark.parametrize(
    "value",
    (0, -1, 1.5, "512", True),
)
def test_validate_project_config_validates_max_tokens(
    value: object,
) -> None:
    with pytest.raises(
        ConfigurationValidationError,
    ):
        validate_project_config({"generation": {"max_tokens": value}})


@pytest.mark.parametrize(
    "section",
    (
        ("provider", "invalid"),
        ("generation", "invalid"),
    ),
)
def test_validate_project_config_rejects_non_table_sections(
    section: tuple[str, object],
) -> None:
    name, value = section

    with pytest.raises(
        ConfigurationValidationError,
        match=f"Configuration section '{name}' must be a table",
    ):
        validate_project_config({name: value})
