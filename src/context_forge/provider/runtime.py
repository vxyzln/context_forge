from dataclasses import dataclass

import httpx
from ollama import Client, ResponseError


@dataclass(frozen=True)
class OllamaRuntimeStatus:
    available: bool
    model_available: bool
    base_url: str
    model: str
    reason: str

    @property
    def ready(self) -> bool:
        return self.available and self.model_available


class OllamaRuntime:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = 2.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("Ollama runtime timeout must be positive")

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = Client(
            host=self.base_url,
            timeout=self.timeout,
        )

    def check(self, model: str) -> OllamaRuntimeStatus:
        normalized_model = model.strip()

        if not normalized_model:
            raise ValueError("Ollama runtime model cannot be empty")

        try:
            response = self.client.list()
        except (ResponseError, TimeoutError, httpx.HTTPError, ConnectionError):
            return OllamaRuntimeStatus(
                available=False,
                model_available=False,
                base_url=self.base_url,
                model=normalized_model,
                reason="ollama_unavailable",
            )

        available_models = {
            self._model_name(item)
            for item in response.models
            if self._model_name(item) is not None
        }

        if normalized_model not in available_models:
            return OllamaRuntimeStatus(
                available=True,
                model_available=False,
                base_url=self.base_url,
                model=normalized_model,
                reason="model_unavailable",
            )

        return OllamaRuntimeStatus(
            available=True,
            model_available=True,
            base_url=self.base_url,
            model=normalized_model,
            reason="ready",
        )

    @staticmethod
    def _model_name(model: object) -> str | None:
        name = getattr(model, "model", None)

        if isinstance(name, str):
            return name

        if isinstance(model, dict):
            name = model.get("model")
            if isinstance(name, str):
                return name

        return None
