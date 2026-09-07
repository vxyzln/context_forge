from dataclasses import dataclass
from json import dumps, loads
from uuid import UUID

from context_forge.context.candidate import ContextCandidate


@dataclass(frozen=True)
class ContextSelectionRequest:
    task: str
    candidates: tuple[ContextCandidate, ...]

    def __post_init__(self) -> None:
        if not self.task.strip():
            raise ValueError("Selection task cannot be empty")

    def serialize(self) -> str:
        payload = {
            "task": self.task.strip(),
            "candidates": [
                {
                    "entity_id": str(candidate.entity_id),
                    "unit_type": candidate.unit_type.value,
                    "score": candidate.score,
                    "source": candidate.source,
                    "reason": candidate.reason,
                }
                for candidate in self.candidates
            ],
        }
        return dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ContextSelectionDecision:
    entity_id: UUID
    include: bool
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Selection confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class ContextSelectionResponse:
    decisions: tuple[ContextSelectionDecision, ...]


class ContextSelectionContract:
    @staticmethod
    def parse_response(
        raw_response: str,
        request: ContextSelectionRequest,
    ) -> ContextSelectionResponse:
        try:
            payload = loads(raw_response)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid selection response JSON") from exc

        if not isinstance(payload, dict):
            raise TypeError("Selection response must be a JSON object")

        decisions = payload.get("decisions")
        if not isinstance(decisions, list):
            raise TypeError("Selection response must contain a decisions list")

        candidate_ids = {candidate.entity_id for candidate in request.candidates}
        parsed: dict[UUID, ContextSelectionDecision] = {}

        for item in decisions:
            if not isinstance(item, dict):
                raise TypeError("Each selection decision must be an object")

            entity_id_value = item.get("entity_id")
            if not isinstance(entity_id_value, str):
                raise TypeError("Selection decision entity_id must be a string")

            try:
                entity_id = UUID(entity_id_value)
            except ValueError as exc:
                raise ValueError("Selection decision entity_id must be a UUID") from exc

            if entity_id not in candidate_ids:
                raise ValueError("Selection response contains an unknown entity_id")

            if entity_id in parsed:
                raise ValueError("Selection response contains duplicate entity_id")

            include = item.get("include")
            if not isinstance(include, bool):
                raise TypeError("Selection decision include must be boolean")

            confidence = item.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise TypeError("Selection decision confidence must be numeric")

            parsed[entity_id] = ContextSelectionDecision(
                entity_id=entity_id,
                include=include,
                confidence=float(confidence),
            )

        missing = candidate_ids - parsed.keys()
        if missing:
            raise ValueError("Selection response is missing candidate decisions")

        ordered = tuple(
            parsed[candidate.entity_id]
            for candidate in sorted(
                request.candidates,
                key=lambda candidate: str(candidate.entity_id),
            )
        )

        return ContextSelectionResponse(decisions=ordered)
