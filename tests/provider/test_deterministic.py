import json

from context_forge.provider import (
    DeterministicProvider,
    GenerationRequest,
    ProviderConfig,
)


def make_request() -> GenerationRequest:
    return GenerationRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
        prompt="Prepared generation prompt",
        config=ProviderConfig(model="deterministic-test"),
    )


def test_deterministic_provider_returns_response() -> None:
    response = DeterministicProvider().generate(make_request())

    assert response.provider == "deterministic"
    assert response.model == "deterministic-test"
    assert response.metadata["mode"] == "deterministic"
    assert response.content.startswith("Task: authenticate user")
    assert "Context received:" in response.content


def test_deterministic_provider_is_repeatable() -> None:
    provider = DeterministicProvider()

    first = provider.generate(make_request())
    second = provider.generate(make_request())

    assert first == second


def test_deterministic_provider_returns_task_interpretation() -> None:
    provider = DeterministicProvider()

    request = GenerationRequest(
        task="Fix scrolling",
        context="",
        prompt=("Interpret the following software-development task. Fix scrolling."),
        config=ProviderConfig(model="deterministic-test"),
    )

    response = provider.generate(request)

    assert response.provider == "deterministic"
    assert response.model == "deterministic-test"
    assert response.metadata["purpose"] == "task_interpretation"

    data = json.loads(response.content)

    assert data["intent"] == "development"
    assert data["requested_action"] == "work"
    assert data["ambiguity"] is None
    assert "scrolling" in data["concepts"]
