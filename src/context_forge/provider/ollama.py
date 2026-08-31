from typing import Any

import httpx
from ollama import Client, ResponseError

from context_forge.provider.base import ContextProvider
from context_forge.provider.models import (
    GenerationRequest,
    GenerationResponse,
    ProviderUsage,
)
from context_forge.provider.transport import ProviderTransportConfig


class OllamaProvider(ContextProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        transport: ProviderTransportConfig | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport or ProviderTransportConfig()
        self.client = Client(
            host=self.base_url,
            timeout=self.transport.timeout,
        )

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        try:
            response = self.client.chat(
                model=request.config.model,
                messages=[
                    {
                        "role": "user",
                        "content": self._build_prompt(request),
                    }
                ],
                stream=False,
                options=self._build_options(request),
            )

        except ResponseError as exc:
            raise RuntimeError(f"Ollama provider request failed: {exc}") from exc

        except (TimeoutError, httpx.TimeoutException) as exc:
            raise RuntimeError(
                f"Ollama provider request timed out after "
                f"{self.transport.timeout:g} seconds"
            ) from exc

        except ConnectionError as exc:
            raise RuntimeError(
                f"Ollama provider could not connect to {self.base_url}"
            ) from exc

        content = response.message.content

        if not isinstance(content, str):
            raise TypeError("Ollama provider response is missing message content")

        if not content.strip():
            raise ValueError("Ollama provider response contains empty message content")

        return GenerationResponse(
            content=content,
            provider="ollama",
            model=response.model or request.config.model,
            usage=ProviderUsage(
                input_tokens=_optional_int(response.prompt_eval_count),
                output_tokens=_optional_int(response.eval_count),
                total_tokens=_total_tokens(response),
            ),
            metadata={
                "done_reason": response.done_reason,
            },
        )

    @staticmethod
    def _build_options(
        request: GenerationRequest,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": request.config.temperature,
        }

        if request.config.max_tokens is not None:
            options["num_predict"] = request.config.max_tokens

        return options

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


def _total_tokens(response: object) -> int | None:
    prompt_tokens = _optional_int(getattr(response, "prompt_eval_count", None))
    output_tokens = _optional_int(getattr(response, "eval_count", None))

    if prompt_tokens is None or output_tokens is None:
        return None

    return prompt_tokens + output_tokens
