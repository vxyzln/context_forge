from unittest.mock import Mock, patch

import httpx
import pytest

from context_forge.provider import OllamaRuntime


def make_model(name: str) -> Mock:
    model = Mock()
    model.model = name
    return model


def make_response(*model_names: str) -> Mock:
    response = Mock()
    response.models = [make_model(name) for name in model_names]
    return response


def test_ollama_runtime_reports_ready_when_model_exists() -> None:
    with patch("context_forge.provider.runtime.Client") as client_class:
        client = client_class.return_value
        client.list.return_value = make_response(
            "qwen2.5-coder:7b",
            "another-model",
        )

        runtime = OllamaRuntime(
            base_url="http://localhost:11434/",
            timeout=3.0,
        )

        status = runtime.check("qwen2.5-coder:7b")

    assert status.available is True
    assert status.model_available is True
    assert status.ready is True
    assert status.base_url == "http://localhost:11434"
    assert status.model == "qwen2.5-coder:7b"
    assert status.reason == "ready"


def test_ollama_runtime_reports_missing_model() -> None:
    with patch("context_forge.provider.runtime.Client") as client_class:
        client_class.return_value.list.return_value = make_response(
            "another-model",
        )

        runtime = OllamaRuntime()

        status = runtime.check("qwen2.5-coder:7b")

    assert status.available is True
    assert status.model_available is False
    assert status.ready is False
    assert status.reason == "model_unavailable"


@pytest.mark.parametrize(
    "error",
    (
        ConnectionError("connection refused"),
        TimeoutError("timed out"),
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("timed out"),
    ),
)
def test_ollama_runtime_reports_unavailable(error: Exception) -> None:
    with patch("context_forge.provider.runtime.Client") as client_class:
        client_class.return_value.list.side_effect = error

        runtime = OllamaRuntime()

        status = runtime.check("qwen2.5-coder:7b")

    assert status.available is False
    assert status.model_available is False
    assert status.ready is False
    assert status.reason == "ollama_unavailable"


def test_ollama_runtime_rejects_empty_model() -> None:
    runtime = OllamaRuntime()

    with pytest.raises(
        ValueError,
        match="Ollama runtime model cannot be empty",
    ):
        runtime.check("   ")


def test_ollama_runtime_configures_client() -> None:
    with patch("context_forge.provider.runtime.Client") as client_class:
        OllamaRuntime(
            base_url="http://example.test/",
            timeout=4.0,
        )

    client_class.assert_called_once_with(
        host="http://example.test",
        timeout=4.0,
    )


def test_ollama_runtime_accepts_mapping_model() -> None:
    response = Mock()
    response.models = [{"model": "qwen2.5-coder:7b"}]

    with patch("context_forge.provider.runtime.Client") as client_class:
        client_class.return_value.list.return_value = response

        status = OllamaRuntime().check("qwen2.5-coder:7b")

    assert status.ready is True


def test_ollama_runtime_ignores_models_without_names() -> None:
    response = Mock()
    unnamed = Mock()
    unnamed.model = None
    response.models = [unnamed]

    with patch("context_forge.provider.runtime.Client") as client_class:
        client_class.return_value.list.return_value = response

        status = OllamaRuntime().check("qwen2.5-coder:7b")

    assert status.available is True
    assert status.model_available is False
    assert status.reason == "model_unavailable"
