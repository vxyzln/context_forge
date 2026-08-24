from context_forge.context.candidate import ContextCandidate


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
