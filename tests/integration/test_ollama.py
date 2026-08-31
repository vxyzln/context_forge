from pathlib import Path

import httpx
import pytest

from context_forge.application import build_generation_service
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.provider import (
    OllamaProvider,
    ProviderConfig,
    ProviderTransportConfig,
)
from context_forge.provider.models import GenerationRequest

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:7b"


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
            max_tokens=32,
        ),
    )

    response = provider.generate(request)

    assert response.provider == "ollama"
    assert response.model == OLLAMA_MODEL
    assert response.content.strip()


@pytest.mark.integration
@pytest.mark.skipif(
    not ollama_available(),
    reason="Ollama server is not available",
)
def test_ollama_generation_uses_analyzed_project_context(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "auth.py"
    source_file.write_text(
        """
class AuthService:
    def authenticate(self, username, password):
        return username == "admin" and password == "secret"
""",
        encoding="utf-8",
    )

    project = ProjectAnalyzer(
        root_path=tmp_path,
        database_path=tmp_path / ".context_forge.db",
    ).analyze()

    config = ProviderConfig(
        provider="ollama",
        model=OLLAMA_MODEL,
        temperature=0.0,
        max_tokens=32,
    )

    service = build_generation_service(config)

    response = service.generate(
        project=project,
        task="Explain the AuthService class in auth.py.",
        config=config,
    )

    assert response.provider == "ollama"
    assert response.model == OLLAMA_MODEL
    assert response.content.strip()

    assert project.files
    auth_file = next(file for file in project.files if file.name == "auth.py")

    # Verify the analyzed project actually contains the target file.
    assert auth_file.path == Path("auth.py")
