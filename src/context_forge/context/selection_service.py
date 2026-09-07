from dataclasses import dataclass

from context_forge.context.candidate import ContextCandidate
from context_forge.context.selection_contract import (
    ContextSelectionContract,
    ContextSelectionRequest,
)
from context_forge.provider.base import ContextProvider
from context_forge.provider.config import ProviderConfig
from context_forge.provider.models import GenerationRequest


@dataclass(frozen=True)
class SelectedContextCandidate:
    candidate: ContextCandidate
    confidence: float


@dataclass(frozen=True)
class ContextSelectionResult:
    candidates: tuple[SelectedContextCandidate, ...]

    @property
    def selected_candidates(self) -> list[ContextCandidate]:
        return [item.candidate for item in self.candidates]


class ContextSelectionService:
    def __init__(
        self,
        provider: ContextProvider,
        config: ProviderConfig,
    ) -> None:
        self.provider = provider
        self.config = config

    def select(
        self,
        task: str,
        candidates: list[ContextCandidate],
    ) -> ContextSelectionResult:
        request = ContextSelectionRequest(
            task=task,
            candidates=tuple(candidates),
        )

        generation_request = GenerationRequest(
            task=task,
            context=request.serialize(),
            prompt=self._build_prompt(request),
            config=self.config,
        )

        response = self.provider.generate(generation_request)

        selection = ContextSelectionContract.parse_response(
            response.content,
            request,
        )

        candidate_by_id = {candidate.entity_id: candidate for candidate in candidates}

        selected = tuple(
            SelectedContextCandidate(
                candidate=candidate_by_id[decision.entity_id],
                confidence=decision.confidence,
            )
            for decision in selection.decisions
            if decision.include
        )

        return ContextSelectionResult(candidates=selected)

    @staticmethod
    def _build_prompt(request: ContextSelectionRequest) -> str:
        return (
            "Select which retrieved repository candidates should be included "
            "in the final context.\n\n"
            "Return JSON only using this exact structure:\n"
            '{"decisions":[{"entity_id":"<UUID>","include":true,'
            '"confidence":0.9}]}\n\n'
            "Every candidate must have exactly one decision. "
            "Use only the provided entity IDs. "
            "Return no additional text.\n\n"
            f"Candidates:\n{request.serialize()}"
        )
