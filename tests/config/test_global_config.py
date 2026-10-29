import sys
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("platform", ["darwin", "linux"])
@pytest.mark.parametrize(
    "xdg_val",
    [
        None,
        "",
        "   ",
        "relative/path",
        "/custom/absolute/path",
    ],
)
def test_global_config_directory_macos_and_linux_always_use_dot_config(
    monkeypatch,
    tmp_path: Path,
    platform: str,
    xdg_val: str | None,
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if xdg_val is None:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", xdg_val)

    assert global_config_directory() == tmp_path / ".config" / APPLICATION_NAME
    assert (
        global_config_path()
        == tmp_path / ".config" / APPLICATION_NAME / GLOBAL_CONFIG_FILENAME
    )


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


def test_global_config_directory_windows_appdata_whitespace_falls_back(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "   ")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert (
        global_config_directory() == tmp_path / "AppData" / "Roaming" / APPLICATION_NAME
    )


def test_global_config_directory_windows_appdata_trimmed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", f"  {tmp_path}  ")

    assert global_config_directory() == tmp_path / APPLICATION_NAME
