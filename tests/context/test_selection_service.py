import json
from uuid import uuid4

import pytest

from context_forge.context.candidate import ContextCandidate
from context_forge.context.selection_service import (
    ContextSelectionService,
)
from context_forge.context.types import ContextUnitType
from context_forge.provider import (
    ContextProvider,
    GenerationRequest,
    GenerationResponse,
    ProviderConfig,
)


class StubProvider(ContextProvider):
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)

        return GenerationResponse(
            content=self.content,
            provider="stub",
            model=request.config.model,
        )


def make_candidate(
    *,
    entity_id=None,
    score: float = 0.9,
) -> ContextCandidate:
    return ContextCandidate(
        entity_id=entity_id or uuid4(),
        unit_type=ContextUnitType.FILE,
        score=score,
        source="deterministic_search",
        reason="matched task",
    )


def make_service(
    content: str,
) -> tuple[ContextSelectionService, StubProvider]:
    provider = StubProvider(content)

    service = ContextSelectionService(
        provider=provider,
        config=ProviderConfig(
            provider="deterministic",
            model="selection-test",
        ),
    )

    return service, provider


def make_response(*decisions: dict) -> str:
    return json.dumps({"decisions": list(decisions)})


def test_selection_service_selects_included_candidates() -> None:
    first = make_candidate()
    second = make_candidate()

    service, _ = make_service(
        make_response(
            {
                "entity_id": str(first.entity_id),
                "include": True,
                "confidence": 0.9,
            },
            {
                "entity_id": str(second.entity_id),
                "include": False,
                "confidence": 0.3,
            },
        )
    )

    result = service.select(
        "Explain authentication",
        [first, second],
    )

    assert result.selected_candidates == [first]
    assert len(result.candidates) == 1
    assert result.candidates[0].confidence == 0.9


def test_selection_service_returns_deterministic_contract_order() -> None:
    first = make_candidate()
    second = make_candidate()

    service, _ = make_service(
        make_response(
            {
                "entity_id": str(second.entity_id),
                "include": True,
                "confidence": 0.8,
            },
            {
                "entity_id": str(first.entity_id),
                "include": True,
                "confidence": 0.9,
            },
        )
    )

    result = service.select(
        "Explain authentication",
        [first, second],
    )

    expected = sorted(
        [first, second],
        key=lambda candidate: candidate.entity_id,
    )

    assert result.selected_candidates == expected


def test_selection_service_preserves_confidence() -> None:
    candidate = make_candidate()

    service, _ = make_service(
        make_response(
            {
                "entity_id": str(candidate.entity_id),
                "include": True,
                "confidence": 0.73,
            },
        )
    )

    result = service.select(
        "Explain authentication",
        [candidate],
    )

    assert result.candidates[0].candidate == candidate
    assert result.candidates[0].confidence == 0.73


def test_selection_service_builds_structured_provider_request() -> None:
    candidate = make_candidate()

    service, provider = make_service(
        make_response(
            {
                "entity_id": str(candidate.entity_id),
                "include": True,
                "confidence": 1.0,
            },
        )
    )

    service.select(
        "Explain authentication",
        [candidate],
    )

    assert len(provider.requests) == 1

    request = provider.requests[0]

    assert request.task == "Explain authentication"
    assert request.config.model == "selection-test"

    payload = json.loads(request.context)

    assert payload["task"] == "Explain authentication"
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["entity_id"] == str(candidate.entity_id)

    assert "reasoning" not in request.prompt.lower()
    assert "additional text" in request.prompt.lower()


def test_selection_service_rejects_invalid_provider_response() -> None:
    candidate = make_candidate()

    service, _ = make_service("not json")

    with pytest.raises(
        ValueError,
        match="Invalid selection response JSON",
    ):
        service.select(
            "Explain authentication",
            [candidate],
        )


def test_selection_service_rejects_unknown_entity() -> None:
    candidate = make_candidate()

    service, _ = make_service(
        make_response(
            {
                "entity_id": str(uuid4()),
                "include": True,
                "confidence": 0.9,
            },
        )
    )

    with pytest.raises(
        ValueError,
        match="unknown entity_id",
    ):
        service.select(
            "Explain authentication",
            [candidate],
        )


def test_selection_service_rejects_missing_decision() -> None:
    first = make_candidate()
    second = make_candidate()

    service, _ = make_service(
        make_response(
            {
                "entity_id": str(first.entity_id),
                "include": True,
                "confidence": 0.9,
            },
        )
    )

    with pytest.raises(
        ValueError,
        match="missing candidate",
    ):
        service.select(
            "Explain authentication",
            [first, second],
        )


def test_selection_service_propagates_provider_errors() -> None:
    candidate = make_candidate()

    class FailingProvider(ContextProvider):
        def generate(
            self,
            request: GenerationRequest,
        ) -> GenerationResponse:
            raise RuntimeError("selection provider failed")

    service = ContextSelectionService(
        provider=FailingProvider(),
        config=ProviderConfig(
            provider="deterministic",
            model="selection-test",
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="selection provider failed",
    ):
        service.select(
            "Explain authentication",
            [candidate],
        )
