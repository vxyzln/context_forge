from dataclasses import dataclass

from context_forge.context.candidate import ContextCandidate


@dataclass(frozen=True)
class SelectedContextCandidate:
    candidate: ContextCandidate
    confidence: float = 1.0


@dataclass(frozen=True)
class ContextSelectionResult:
    candidates: tuple[SelectedContextCandidate, ...]

    @property
    def selected_candidates(self) -> list[ContextCandidate]:
        return [item.candidate for item in self.candidates]


class ContextSelector:
    def select(
        self,
        candidates: list[ContextCandidate],
        limit: int | None = None,
    ) -> list[ContextCandidate]:
        if limit is None:
            return candidates.copy()
        if limit < 0:
            raise ValueError("Selection limit cannot be negative")

        return candidates[:limit]

    def select_result(
        self,
        candidates: list[ContextCandidate],
        limit: int | None = None,
    ) -> ContextSelectionResult:
        selected = self.select(candidates, limit)
        return ContextSelectionResult(
            candidates=tuple(
                SelectedContextCandidate(candidate=c, confidence=1.0) for c in selected
            )
        )
