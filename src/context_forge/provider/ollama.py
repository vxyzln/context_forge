from typing import Any

import httpx

from context_forge.provider.base import ContextProvider
from context_forge.provider.models import (
    GenerationRequest,
    GenerationResponse,
    ProviderUsage,
)
from context_forge.provider.transport import ProviderTransportConfig


class OllamaProvider(ContextProvider):
    """Context provider backed by a local Ollama server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        transport: ProviderTransportConfig | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport or ProviderTransportConfig()

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        payload: dict[str, Any] = {
            "model": request.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": self._build_prompt(request),
                }
            ],
            "stream": False,
            "options": {
                "temperature": request.config.temperature,
            },
        }

        if request.config.max_tokens is not None:
            payload["options"]["num_predict"] = request.config.max_tokens

        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.transport.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Ollama provider request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("Ollama provider returned invalid JSON") from exc

        message = data.get("message")

        if not isinstance(message, dict):
            raise TypeError("Ollama provider response is missing a valid message")

        content = message.get("content")

        if not isinstance(content, str):
            raise TypeError("Ollama provider response is missing message content")

        thinking = message.get("thinking")
        reasoning = thinking if isinstance(thinking, str) and thinking else None

        usage = ProviderUsage(
            input_tokens=_optional_int(data.get("prompt_eval_count")),
            output_tokens=_optional_int(data.get("eval_count")),
            total_tokens=_total_tokens(data),
        )

        return GenerationResponse(
            content=content,
            provider="ollama",
            model=str(data.get("model", request.config.model)),
            usage=usage,
            reasoning=reasoning,
            metadata={
                "done_reason": data.get("done_reason"),
            },
        )

    @staticmethod
    def _build_prompt(request: GenerationRequest) -> str:
        return (
            "Use the following task and project context to answer "
            "the user's request.\n\n"
            f"Task:\n{request.task}\n\n"
            f"Context:\n{request.context}"
        )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _total_tokens(data: dict[str, Any]) -> int | None:
    prompt_tokens = _optional_int(data.get("prompt_eval_count"))
    output_tokens = _optional_int(data.get("eval_count"))

    if prompt_tokens is None or output_tokens is None:
        return None

    return prompt_tokens + output_tokens
