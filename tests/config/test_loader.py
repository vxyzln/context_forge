from pathlib import Path

import pytest

from context_forge.config import (
    PROJECT_CONFIG_FILENAME,
    ConfigurationLoadError,
    load_project_config,
    project_config_path,
)


def test_project_config_path_uses_canonical_filename(
    tmp_path: Path,
) -> None:
    assert project_config_path(tmp_path) == (tmp_path / PROJECT_CONFIG_FILENAME)


def test_load_project_config_returns_empty_mapping_when_missing(
    tmp_path: Path,
) -> None:
    assert load_project_config(tmp_path) == {}


def test_load_project_config_reads_toml(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / PROJECT_CONFIG_FILENAME
    config_path.write_text(
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

    assert load_project_config(tmp_path) == {
        "provider": {
            "provider": "ollama",
            "model": "qwen2.5-coder:7b",
            "base_url": "http://localhost:11434",
        },
        "generation": {
            "temperature": 0.2,
            "max_tokens": 2048,
        },
    }


def test_load_project_config_preserves_toml_types(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / PROJECT_CONFIG_FILENAME
    config_path.write_text(
        """
[provider]
enabled = true

[generation]
temperature = 0.5
max_tokens = 512
""",
        encoding="utf-8",
    )

    result = load_project_config(tmp_path)

    assert result["provider"]["enabled"] is True
    assert result["generation"]["temperature"] == 0.5
    assert result["generation"]["max_tokens"] == 512


def test_load_project_config_rejects_invalid_toml(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / PROJECT_CONFIG_FILENAME
    config_path.write_text(
        """
[provider
model = "qwen2.5-coder:7b"
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ConfigurationLoadError,
        match="Invalid project configuration",
    ):
        load_project_config(tmp_path)


def test_load_project_config_rejects_directory_at_config_path(
    tmp_path: Path,
) -> None:
    (tmp_path / PROJECT_CONFIG_FILENAME).mkdir()

    with pytest.raises(
        ConfigurationLoadError,
        match="is not a file",
    ):
        load_project_config(tmp_path)
