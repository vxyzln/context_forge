import json

from context_forge.provider import (
    ContextProvider,
    GenerationRequest,
    ProviderConfig,
)

from .models import TaskInterpretation


class TaskUnderstandingService:
    """Interpret a natural-language task using a context provider."""

    def __init__(
        self,
        provider: ContextProvider,
        config: ProviderConfig,
    ) -> None:
        self._provider = provider
        self._config = config

    def understand(self, task: str) -> TaskInterpretation:
        if not task.strip():
            raise ValueError("task must not be empty")

        request = GenerationRequest(
            task=self._build_prompt(task),
            context="",
            config=self._config,
        )

        response = self._provider.generate(request)

        return self._parse_response(
            task=task,
            content=response.content,
        )

    @staticmethod
    def _build_prompt(task: str) -> str:
        return (
            "Interpret the following software-development task. "
            "Return ONLY valid JSON with exactly these fields: "
            "intent, target, concepts, requested_action, constraints, "
            "ambiguity. "
            "intent must be a string. "
            "target must be a string or null. "
            "concepts must be an array of strings. "
            "requested_action must be a string or null. "
            "constraints must be an array of strings. "
            "ambiguity must be a string or null. "
            "Do not invent repository facts.\n\n"
            f"Task:\n{task}"
        )

    @staticmethod
    def _parse_response(
        task: str,
        content: str,
    ) -> TaskInterpretation:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "provider returned invalid task interpretation JSON"
            ) from exc

        if not isinstance(data, dict):
            raise TypeError(
                "provider returned a task interpretation that is not an object"
            )

        return TaskInterpretation(
            task=task,
            intent=TaskUnderstandingService._require_string(
                data,
                "intent",
            ),
            target=TaskUnderstandingService._optional_string(
                data,
                "target",
            ),
            concepts=TaskUnderstandingService._string_tuple(
                data,
                "concepts",
            ),
            requested_action=TaskUnderstandingService._optional_string(
                data,
                "requested_action",
            ),
            constraints=TaskUnderstandingService._string_tuple(
                data,
                "constraints",
            ),
            ambiguity=TaskUnderstandingService._optional_string(
                data,
                "ambiguity",
            ),
        )

    @staticmethod
    def _require_string(
        data: dict[str, object],
        field: str,
    ) -> str:
        value = data.get(field)

        if not isinstance(value, str):
            raise TypeError(f"task interpretation field '{field}' must be a string")

        return value

    @staticmethod
    def _optional_string(
        data: dict[str, object],
        field: str,
    ) -> str | None:
        value = data.get(field)

        if value is None:
            return None

        if not isinstance(value, str):
            raise TypeError(
                f"task interpretation field '{field}' must be a string or null"
            )

        return value

    @staticmethod
    def _string_tuple(
        data: dict[str, object],
        field: str,
    ) -> tuple[str, ...]:
        value = data.get(field, [])

        if not isinstance(value, list):
            raise TypeError(f"task interpretation field '{field}' must be an array")

        if not all(isinstance(item, str) for item in value):
            raise TypeError(
                f"task interpretation field '{field}' must contain only strings"
            )

        return tuple(value)
