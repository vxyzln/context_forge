# tests/provider/test_ollama.py

from unittest.mock import Mock, patch

import httpx
import pytest

from context_forge.provider import (
    GenerationRequest,
    OllamaProvider,
    ProviderConfig,
    ProviderTransportConfig,
)


def make_request() -> GenerationRequest:
    return GenerationRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
        config=ProviderConfig(
            model="qwen2.5-coder:7b",
            temperature=0.0,
            max_tokens=2048,
        ),
    )


def make_response(
    *,
    content: str = "Authentication is handled by auth.py.",
) -> httpx.Response:
    response = httpx.Response(
        status_code=200,
        json={
            "model": "qwen2.5-coder:7b",
            "message": {
                "role": "assistant",
                "content": content,
            },
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 100,
            "eval_count": 25,
        },
        request=httpx.Request(
            "POST",
            "http://localhost:11434/api/chat",
        ),
    )
    return response


def test_ollama_provider_returns_response() -> None:
    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = make_response()

        response = OllamaProvider().generate(make_request())

    assert response.provider == "ollama"
    assert response.model == "qwen2.5-coder:7b"
    assert response.content == "Authentication is handled by auth.py."
    assert response.usage.input_tokens == 100
    assert response.usage.output_tokens == 25
    assert response.usage.total_tokens == 125
    assert response.metadata["done_reason"] == "stop"


def test_ollama_provider_sends_expected_request() -> None:
    request = make_request()

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = make_response()

        OllamaProvider(
            transport=ProviderTransportConfig(timeout=30.0),
        ).generate(request)

    post.assert_called_once()

    args, kwargs = post.call_args

    assert args[0] == "http://localhost:11434/api/chat"
    assert kwargs["timeout"] == 30.0
    assert kwargs["json"]["model"] == "qwen2.5-coder:7b"
    assert kwargs["json"]["stream"] is False
    assert kwargs["json"]["think"] is False
    assert kwargs["json"]["options"]["temperature"] == 0.0
    assert kwargs["json"]["options"]["num_predict"] == 2048

    message = kwargs["json"]["messages"][0]

    assert message["role"] == "user"
    assert "authenticate user" in message["content"]
    assert '{"task":"authenticate user","units":[]}' in message["content"]


def test_ollama_provider_uses_custom_base_url() -> None:
    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = make_response()

        OllamaProvider("http://example.test/").generate(make_request())

    assert post.call_args.args[0] == "http://example.test/api/chat"


def test_ollama_provider_omits_num_predict_without_max_tokens() -> None:
    request = GenerationRequest(
        task="authenticate user",
        context="{}",
        config=ProviderConfig(model="qwen2.5-coder:7b"),
    )

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = make_response()

        OllamaProvider().generate(request)

    options = post.call_args.kwargs["json"]["options"]

    assert options == {"temperature": 0.0}


def test_ollama_provider_handles_missing_usage() -> None:
    response = httpx.Response(
        status_code=200,
        json={
            "model": "qwen2.5-coder:7b",
            "message": {
                "role": "assistant",
                "content": "Done.",
            },
        },
        request=httpx.Request(
            "POST",
            "http://localhost:11434/api/chat",
        ),
    )

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = response

        result = OllamaProvider().generate(make_request())

    assert result.usage.input_tokens is None
    assert result.usage.output_tokens is None
    assert result.usage.total_tokens is None


def test_ollama_provider_raises_on_connection_error() -> None:
    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(
            RuntimeError,
            match="Ollama provider could not connect to http://localhost:11434",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_raises_on_invalid_json() -> None:
    response = Mock(spec=httpx.Response)
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("invalid json")

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = response

        with pytest.raises(
            RuntimeError,
            match="Ollama provider returned invalid JSON",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_raises_when_message_is_missing() -> None:
    response = httpx.Response(
        status_code=200,
        json={"model": "qwen2.5-coder:7b"},
        request=httpx.Request(
            "POST",
            "http://localhost:11434/api/chat",
        ),
    )

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = response

        with pytest.raises(
            TypeError,
            match="missing a valid message",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_rejects_non_object_json() -> None:
    response = httpx.Response(
        status_code=200,
        json=[],
        request=httpx.Request(
            "POST",
            "http://localhost:11434/api/chat",
        ),
    )

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = response

        with pytest.raises(
            TypeError,
            match="response must be a JSON object",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_uses_default_transport_timeout() -> None:
    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = make_response()

        OllamaProvider().generate(make_request())

    assert post.call_args.kwargs["timeout"] == 60.0


def test_ollama_provider_raises_on_timeout() -> None:
    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.side_effect = httpx.ReadTimeout("request timed out")

        with pytest.raises(
            RuntimeError,
            match="Ollama provider request timed out after 60 seconds",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_rejects_empty_content() -> None:
    response = httpx.Response(
        status_code=200,
        json={
            "model": "qwen2.5-coder:7b",
            "message": {
                "role": "assistant",
                "content": "   ",
            },
        },
        request=httpx.Request(
            "POST",
            "http://localhost:11434/api/chat",
        ),
    )

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = response

        with pytest.raises(
            ValueError,
            match="response contains empty message content",
        ):
            OllamaProvider().generate(make_request())


def test_ollama_provider_ignores_thinking_field() -> None:
    response = httpx.Response(
        status_code=200,
        json={
            "model": "qwen2.5-coder:7b",
            "message": {
                "role": "assistant",
                "content": "Authentication is handled by auth.py.",
                "thinking": "Internal model reasoning that must not escape.",
            },
            "done": True,
            "done_reason": "stop",
        },
        request=httpx.Request(
            "POST",
            "http://localhost:11434/api/chat",
        ),
    )

    with patch("context_forge.provider.ollama.httpx.post") as post:
        post.return_value = response

        result = OllamaProvider().generate(make_request())

    assert result.content == "Authentication is handled by auth.py."
    assert result.metadata.get("thinking") is None
    assert not hasattr(result, "reasoning")
