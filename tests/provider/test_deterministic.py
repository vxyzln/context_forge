from context_forge.provider import (
    DeterministicProvider,
    GenerationRequest,
    ProviderConfig,
)


def make_request() -> GenerationRequest:
    return GenerationRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
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
