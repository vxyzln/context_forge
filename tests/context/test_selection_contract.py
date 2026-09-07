import json
from uuid import UUID, uuid4

import pytest

from context_forge.context.candidate import ContextCandidate
from context_forge.context.selection_contract import (
    ContextSelectionContract,
    ContextSelectionDecision,
    ContextSelectionRequest,
)
from context_forge.context.types import ContextUnitType


def make_candidate(
    entity_id: UUID | None = None,
    score: float = 0.9,
) -> ContextCandidate:
    return ContextCandidate(
        entity_id=entity_id or uuid4(),
        unit_type=ContextUnitType.FILE,
        score=score,
        source="deterministic_search",
        reason="matched task",
    )


def make_request(*candidates: ContextCandidate) -> ContextSelectionRequest:
    return ContextSelectionRequest(
        task="Explain authentication",
        candidates=tuple(candidates),
    )


def test_request_serialization_is_deterministic() -> None:
    candidate = make_candidate()
    request = make_request(candidate)

    assert request.serialize() == request.serialize()

    payload = json.loads(request.serialize())

    assert payload["task"] == "Explain authentication"
    assert payload["candidates"][0]["entity_id"] == str(candidate.entity_id)
    assert payload["candidates"][0]["unit_type"] == "file"
    assert payload["candidates"][0]["score"] == 0.9
    assert payload["candidates"][0]["source"] == "deterministic_search"
    assert payload["candidates"][0]["reason"] == "matched task"


def test_request_rejects_empty_task() -> None:
    with pytest.raises(ValueError, match="empty"):
        ContextSelectionRequest(task="   ", candidates=())


def test_decision_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="between 0.0 and 1.0"):
        ContextSelectionDecision(
            entity_id=uuid4(),
            include=True,
            confidence=1.1,
        )


def test_response_parses_valid_decisions() -> None:
    first = make_candidate()
    second = make_candidate()

    request = make_request(first, second)

    raw = json.dumps(
        {
            "decisions": [
                {
                    "entity_id": str(second.entity_id),
                    "include": False,
                    "confidence": 0.4,
                },
                {
                    "entity_id": str(first.entity_id),
                    "include": True,
                    "confidence": 0.9,
                },
            ]
        }
    )

    response = ContextSelectionContract.parse_response(raw, request)

    assert len(response.decisions) == 2
    assert {decision.entity_id for decision in response.decisions} == {
        first.entity_id,
        second.entity_id,
    }


def test_response_is_normalized_deterministically() -> None:
    first = make_candidate()
    second = make_candidate()

    request = make_request(first, second)

    raw = json.dumps(
        {
            "decisions": [
                {
                    "entity_id": str(second.entity_id),
                    "include": False,
                    "confidence": 0.4,
                },
                {
                    "entity_id": str(first.entity_id),
                    "include": True,
                    "confidence": 0.9,
                },
            ]
        }
    )

    response = ContextSelectionContract.parse_response(raw, request)

    assert [str(decision.entity_id) for decision in response.decisions] == sorted(
        [str(first.entity_id), str(second.entity_id)]
    )


def test_response_rejects_unknown_entity() -> None:
    candidate = make_candidate()
    request = make_request(candidate)

    raw = json.dumps(
        {
            "decisions": [
                {
                    "entity_id": str(uuid4()),
                    "include": True,
                    "confidence": 0.9,
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="unknown entity_id"):
        ContextSelectionContract.parse_response(raw, request)


def test_response_rejects_duplicate_entity() -> None:
    candidate = make_candidate()
    request = make_request(candidate)

    raw = json.dumps(
        {
            "decisions": [
                {
                    "entity_id": str(candidate.entity_id),
                    "include": True,
                    "confidence": 0.9,
                },
                {
                    "entity_id": str(candidate.entity_id),
                    "include": False,
                    "confidence": 0.2,
                },
            ]
        }
    )

    with pytest.raises(ValueError, match="duplicate entity_id"):
        ContextSelectionContract.parse_response(raw, request)


def test_response_rejects_missing_candidate_decision() -> None:
    first = make_candidate()
    second = make_candidate()

    request = make_request(first, second)

    raw = json.dumps(
        {
            "decisions": [
                {
                    "entity_id": str(first.entity_id),
                    "include": True,
                    "confidence": 0.9,
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="missing candidate"):
        ContextSelectionContract.parse_response(raw, request)


def test_response_rejects_invalid_json() -> None:
    request = make_request(make_candidate())

    with pytest.raises(ValueError, match="Invalid selection response JSON"):
        ContextSelectionContract.parse_response("not json", request)


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        '{"decisions": {}}',
        '{"decisions": [null]}',
    ],
)
def test_response_rejects_invalid_structure(raw: str) -> None:
    request = make_request(make_candidate())

    with pytest.raises(TypeError):
        ContextSelectionContract.parse_response(raw, request)


def test_response_rejects_non_boolean_include() -> None:
    candidate = make_candidate()
    request = make_request(candidate)

    raw = json.dumps(
        {
            "decisions": [
                {
                    "entity_id": str(candidate.entity_id),
                    "include": "true",
                    "confidence": 0.9,
                }
            ]
        }
    )

    with pytest.raises(TypeError, match="include must be boolean"):
        ContextSelectionContract.parse_response(raw, request)


def test_response_rejects_boolean_confidence() -> None:
    candidate = make_candidate()
    request = make_request(candidate)

    raw = json.dumps(
        {
            "decisions": [
                {
                    "entity_id": str(candidate.entity_id),
                    "include": True,
                    "confidence": True,
                }
            ]
        }
    )

    with pytest.raises(TypeError, match="confidence must be numeric"):
        ContextSelectionContract.parse_response(raw, request)
