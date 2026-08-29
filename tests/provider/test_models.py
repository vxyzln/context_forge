from context_forge.provider import (
    GenerationRequest,
    GenerationResponse,
    ProviderConfig,
    ProviderUsage,
)


def test_provider_request_stores_task_context_and_config() -> None:
    config = ProviderConfig(model="test-model")

    request = GenerationRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
        config=config,
    )

    assert request.task == "authenticate user"
    assert request.context == '{"task":"authenticate user","units":[]}'
    assert request.config == config


def test_provider_response_stores_result() -> None:
    response = GenerationResponse(
        content="generated response",
        provider="deterministic",
        model="test-model",
        usage=ProviderUsage(
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
        ),
        reasoning="test reasoning",
        metadata={"mode": "deterministic"},
    )

    assert response.content == "generated response"
    assert response.provider == "deterministic"
    assert response.model == "test-model"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 20
    assert response.usage.total_tokens == 30
    assert response.reasoning == "test reasoning"
    assert response.metadata["mode"] == "deterministic"


def test_provider_response_defaults_optional_fields() -> None:
    response = GenerationResponse(
        content="generated response",
        provider="test",
        model="test-model",
    )

    assert response.usage == ProviderUsage()
    assert response.reasoning is None
    assert response.metadata == {}
