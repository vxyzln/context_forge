from context_forge.context.candidate import ContextCandidate
from context_forge.context.signals import RelevanceSignals


class DeterministicRanker:
    def __init__(self, max_candidates: int | None = None) -> None:
        if max_candidates is not None and max_candidates < 1:
            raise ValueError("Maximum candidate count must be positive")
        self.max_candidates = max_candidates

    def score(
        self,
        candidate: ContextCandidate,
        signals: RelevanceSignals,
    ) -> float:
        return min(1.0, candidate.score + signals.total())

    def rank(
        self,
        candidates: list[ContextCandidate],
        signals: dict[object, RelevanceSignals],
    ) -> list[ContextCandidate]:
        scored = [
            (
                candidate,
                self.score(
                    candidate,
                    signals.get(candidate.entity_id, RelevanceSignals()),
                ),
            )
            for candidate in candidates
        ]

        scored.sort(
            key=lambda item: (
                -item[1],
                item[0].unit_type.value,
                str(item[0].entity_id),
            )
        )

        ranked = [
            ContextCandidate(
                entity_id=candidate.entity_id,
                unit_type=candidate.unit_type,
                score=score,
                source=candidate.source,
                reason=candidate.reason,
            )
            for candidate, score in scored
        ]

        if self.max_candidates is not None:
            return ranked[: self.max_candidates]

        return ranked
