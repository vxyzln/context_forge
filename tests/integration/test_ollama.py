import httpx
import pytest

from context_forge.provider import (
    OllamaProvider,
    ProviderConfig,
    ProviderTransportConfig,
)
from context_forge.provider.models import GenerationRequest

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3:8b"


def ollama_available() -> bool:
    try:
        response = httpx.get(
            f"{OLLAMA_URL}/api/tags",
            timeout=2.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        return False

    return True


@pytest.mark.integration
@pytest.mark.skipif(
    not ollama_available(),
    reason="Ollama server is not available",
)
def test_ollama_provider_live_generation() -> None:
    provider = OllamaProvider(
        base_url=OLLAMA_URL,
        transport=ProviderTransportConfig(timeout=60.0),
    )

    request = GenerationRequest(
        task="Reply with exactly: Context Forge works.",
        context='{"task":"Context Forge smoke test","units":[]}',
        config=ProviderConfig(
            provider="ollama",
            model=OLLAMA_MODEL,
            temperature=0.0,
            max_tokens=256,
        ),
    )

    response = provider.generate(request)

    assert response.provider == "ollama"
    assert response.model == OLLAMA_MODEL
    assert response.content.strip()
