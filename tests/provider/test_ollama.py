from unittest.mock import Mock, patch

import pytest
from ollama import Message, ResponseError

from context_forge.provider import (
    GenerationRequest,
    OllamaProvider,
    ProviderConfig,
    ProviderTransportConfig,
)


def make_request(
    *,
    max_tokens: int | None = 2048,
) -> GenerationRequest:
    return GenerationRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
        config=ProviderConfig(
            model="qwen2.5-coder:7b",
            temperature=0.0,
            max_tokens=max_tokens,
        ),
    )


def make_response(
    *,
    model: str | None = "qwen2.5-coder:7b",
    content: str | None = "Authentication is handled by auth.py.",
    thinking: str | None = None,
    prompt_eval_count: int | None = 100,
    eval_count: int | None = 25,
    done_reason: str | None = "stop",
) -> Mock:
    response = Mock()
    response.model = model
    response.message = Message(
        role="assistant",
        content=content,
        thinking=thinking,
    )
    response.prompt_eval_count = prompt_eval_count
    response.eval_count = eval_count
    response.done_reason = done_reason
    return response


def test_ollama_provider_returns_response() -> None:
    response = make_response()

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        result = OllamaProvider().generate(make_request())

    assert result.provider == "ollama"
    assert result.model == "qwen2.5-coder:7b"
    assert result.content == "Authentication is handled by auth.py."
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 25
    assert result.usage.total_tokens == 125
    assert result.metadata["done_reason"] == "stop"


def test_ollama_provider_configures_client() -> None:
    transport = ProviderTransportConfig(timeout=30.0)

    with patch("context_forge.provider.ollama.Client") as client_class:
        OllamaProvider(
            base_url="http://example.test/",
            transport=transport,
        )

    client_class.assert_called_once_with(
        host="http://example.test",
        timeout=30.0,
    )


def test_ollama_provider_sends_expected_chat_request() -> None:
    response = make_response()

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        OllamaProvider().generate(make_request())

    client.chat.assert_called_once_with(
        model="qwen2.5-coder:7b",
        messages=[
            {
                "role": "user",
                "content": (
                    "Use the following task and project context to answer "
                    "the user's request.\n\n"
                    "Task:\nauthenticate user\n\n"
                    'Context:\n{"task":"authenticate user","units":[]}'
                ),
            }
        ],
        stream=False,
        options={
            "temperature": 0.0,
            "num_predict": 2048,
        },
    )


def test_ollama_provider_omits_num_predict_without_max_tokens() -> None:
    response = make_response()

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        OllamaProvider().generate(make_request(max_tokens=None))

    assert client.chat.call_args.kwargs["options"] == {
        "temperature": 0.0,
    }


def test_ollama_provider_handles_missing_usage() -> None:
    response = make_response(
        prompt_eval_count=None,
        eval_count=None,
    )

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        result = OllamaProvider().generate(make_request())

    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert result.usage.total_tokens is None


def test_ollama_provider_handles_incomplete_usage() -> None:
    response = make_response(
        prompt_eval_count=100,
        eval_count=None,
    )

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        result = OllamaProvider().generate(make_request())

    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens is None
    assert result.usage.total_tokens is None


def test_ollama_provider_uses_configured_model_when_response_model_missing() -> None:
    response = make_response(model=None)

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        result = OllamaProvider().generate(make_request())

    assert result.model == "qwen2.5-coder:7b"


def test_ollama_provider_rejects_missing_content() -> None:
    response = make_response(content=None)

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        with pytest.raises(
            TypeError,
            match="Ollama provider response is missing message content",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_rejects_empty_content() -> None:
    response = make_response(content="   ")

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        with pytest.raises(
            ValueError,
            match="Ollama provider response contains empty message content",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_wraps_response_error() -> None:
    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.side_effect = ResponseError(
            "model not found",
            status_code=404,
        )

        with pytest.raises(
            RuntimeError,
            match="Ollama provider request failed: model not found",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_wraps_timeout_error() -> None:
    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.side_effect = TimeoutError("request timed out")

        with pytest.raises(
            RuntimeError,
            match="Ollama provider request timed out after 60 seconds",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_wraps_connection_error() -> None:
    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.side_effect = ConnectionError("connection refused")

        with pytest.raises(
            RuntimeError,
            match="Ollama provider could not connect to http://localhost:11434",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_does_not_expose_thinking() -> None:
    response = make_response(
        thinking="Internal model reasoning that must not escape.",
    )

    with patch("context_forge.provider.ollama.Client") as client_class:
        client = client_class.return_value
        client.chat.return_value = response

        result = OllamaProvider().generate(make_request())

    assert result.content == "Authentication is handled by auth.py."
    assert result.metadata.get("thinking") is None
    assert not hasattr(result, "reasoning")
