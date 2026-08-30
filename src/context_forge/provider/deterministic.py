import json

from context_forge.provider.base import ContextProvider
from context_forge.provider.models import GenerationRequest, GenerationResponse


class DeterministicProvider(ContextProvider):
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        if request.context == "":
            return GenerationResponse(
                content=json.dumps(
                    {
                        "intent": "development",
                        "target": None,
                        "concepts": self._extract_concepts(request.task),
                        "requested_action": "work",
                        "constraints": [],
                        "ambiguity": None,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                provider="deterministic",
                model=request.config.model,
                metadata={
                    "mode": "deterministic",
                    "purpose": "task_interpretation",
                },
            )

        return GenerationResponse(
            content=(
                f"Task: {request.task}\n"
                f"Context received: {len(request.context)} characters"
            ),
            provider="deterministic",
            model=request.config.model,
            metadata={
                "mode": "deterministic",
            },
        )

    @staticmethod
    def _extract_concepts(task: str) -> list[str]:
        words = [word.strip(".,!?;:()[]{}").lower() for word in task.split()]

        return [word for word in words if len(word) >= 3]
