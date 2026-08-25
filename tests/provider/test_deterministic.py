from context_forge.provider import DeterministicProvider, ProviderRequest


def test_deterministic_provider_returns_response() -> None:
    request = ProviderRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
    )

    response = DeterministicProvider().generate(request)

    assert response.provider == "deterministic"
    assert response.metadata["mode"] == "deterministic"
    assert response.content.startswith("Task: authenticate user")
    assert "Context received:" in response.content


def test_deterministic_provider_is_repeatable() -> None:
    request = ProviderRequest(
        task="authenticate user",
        context='{"task":"authenticate user","units":[]}',
    )

    provider = DeterministicProvider()

    first = provider.generate(request)
    second = provider.generate(request)

    assert first == second
