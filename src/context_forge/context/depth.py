from dataclasses import dataclass
from enum import StrEnum

from context_forge.context.candidate import ContextCandidate


class ContextDepth(StrEnum):
    MINIMAL = "minimal"
    RECOMMENDED = "recommended"
    DEEP = "deep"


@dataclass(frozen=True)
class ContextDepthDecision:
    depth: int
    mode: ContextDepth
    reason: str

    def __post_init__(self) -> None:
        if self.depth < 0:
            raise ValueError("Context depth cannot be negative")


class ContextDepthSelector:
    def select(
        self,
        candidates: list[ContextCandidate],
        mode: ContextDepth | None = None,
    ) -> ContextDepthDecision:
        if mode is not None:
            return self._explicit(mode)

        return self._automatic(candidates)

    @staticmethod
    def _explicit(mode: ContextDepth) -> ContextDepthDecision:
        depths = {
            ContextDepth.MINIMAL: 0,
            ContextDepth.RECOMMENDED: 1,
            ContextDepth.DEEP: 2,
        }
        return ContextDepthDecision(
            depth=depths[mode],
            mode=mode,
            reason=f"Explicit context depth mode: {mode.value}",
        )

    @staticmethod
    def _automatic(
        candidates: list[ContextCandidate],
    ) -> ContextDepthDecision:
        if not candidates:
            return ContextDepthDecision(
                depth=0,
                mode=ContextDepth.MINIMAL,
                reason="No relevant candidates were found",
            )

        high_relevance_count = sum(candidate.score >= 0.8 for candidate in candidates)

        if len(candidates) >= 5 or high_relevance_count >= 3:
            return ContextDepthDecision(
                depth=2,
                mode=ContextDepth.DEEP,
                reason="Multiple highly relevant candidates require broader context",
            )

        if len(candidates) >= 2:
            return ContextDepthDecision(
                depth=1,
                mode=ContextDepth.RECOMMENDED,
                reason="Multiple relevant candidates require dependency context",
            )

        return ContextDepthDecision(
            depth=1,
            mode=ContextDepth.RECOMMENDED,
            reason="A focused candidate still benefits from direct relationships",
        )
