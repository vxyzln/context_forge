from context_forge.provider import ProviderRequest, ProviderResponse


def test_provider_request_stores_task_and_context() -> None:
    request = ProviderRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
    )

    assert request.task == "authenticate user"
    assert request.context == '{"task":"authenticate user","units":[]}'


def test_provider_response_stores_result() -> None:
    response = ProviderResponse(
        content="generated response",
        provider="deterministic",
        metadata={"mode": "deterministic"},
    )

    assert response.content == "generated response"
    assert response.provider == "deterministic"
    assert response.metadata["mode"] == "deterministic"
