import sys
from pathlib import Path

from context_forge.config import (
    APPLICATION_NAME,
    GLOBAL_CONFIG_FILENAME,
    global_config_directory,
    global_config_path,
    load_global_config,
)


def test_global_config_path_uses_canonical_filename() -> None:
    assert global_config_path().name == GLOBAL_CONFIG_FILENAME


def test_global_config_path_is_inside_application_directory() -> None:
    assert global_config_path().parent == global_config_directory()
    assert global_config_path().parent.name == APPLICATION_NAME


def test_global_config_directory_uses_macos_application_support(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")

    assert global_config_directory() == (
        tmp_path / "Library" / "Application Support" / APPLICATION_NAME
    )


def test_global_config_directory_uses_xdg_on_linux(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert global_config_directory() == tmp_path / APPLICATION_NAME


def test_global_config_directory_uses_default_linux_location(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert global_config_directory() == (tmp_path / ".config" / APPLICATION_NAME)


def test_global_config_directory_uses_appdata_on_windows(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert global_config_directory() == tmp_path / APPLICATION_NAME


def test_load_global_config_returns_empty_mapping_when_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / GLOBAL_CONFIG_FILENAME
    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    assert load_global_config() == {}


def test_load_global_config_reads_toml(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / GLOBAL_CONFIG_FILENAME
    config_path.write_text(
        """
[provider]
model = "qwen2.5-coder:7b"

[generation]
temperature = 0.2
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "context_forge.config.loader.global_config_path",
        lambda: config_path,
    )

    assert load_global_config() == {
        "provider": {
            "model": "qwen2.5-coder:7b",
        },
        "generation": {
            "temperature": 0.2,
        },
    }
