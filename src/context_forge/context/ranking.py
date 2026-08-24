from context_forge.context.candidate import ContextCandidate
from context_forge.context.signals import RelevanceSignals


class DeterministicRanker:
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

        return [
            ContextCandidate(
                entity_id=candidate.entity_id,
                unit_type=candidate.unit_type,
                score=score,
                source=candidate.source,
            )
            for candidate, score in scored
        ]
