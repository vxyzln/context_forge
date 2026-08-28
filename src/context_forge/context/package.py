from context_forge.context.candidate import ContextCandidate
from context_forge.context.expansion import ContextExpansion
from context_forge.context.models import (
    ContextPackage,
    ContextSignal,
    ContextUnit,
    Evidence,
)
from context_forge.context.signals import RelevanceSignals


class ContextPackageBuilder:
    def build(
        self,
        task: str,
        expansions: list[ContextExpansion],
        signals: dict[object, RelevanceSignals] | None = None,
    ) -> ContextPackage:
        units: list[ContextUnit] = []
        signals = signals or {}

        for expansion in expansions:
            candidate = expansion.candidate

            units.append(
                self._build_unit(
                    candidate,
                    signals.get(candidate.entity_id),
                )
            )

            for related in expansion.related:
                units.append(
                    self._build_unit(
                        related,
                        signals.get(related.entity_id),
                    )
                )

        return ContextPackage(
            task=task.strip(),
            units=tuple(units),
        )

    @staticmethod
    def _build_unit(
        candidate: ContextCandidate,
        relevance_signals: RelevanceSignals | None = None,
    ) -> ContextUnit:
        selection_description = (
            f"{candidate.reason}; "
            f"selected from {candidate.source} "
            f"with relevance score {candidate.score:.3f}"
            if candidate.reason
            else (
                f"Selected from {candidate.source} "
                f"with relevance score {candidate.score:.3f}"
            )
        )

        selection_signal = ContextSignal(
            name="selection",
            value=candidate.score,
            evidence=(
                Evidence(
                    source_id=candidate.entity_id,
                    description=selection_description,
                ),
            ),
        )

        context_signals = [selection_signal]

        if relevance_signals is not None and relevance_signals.git > 0:
            context_signals.append(
                ContextSignal(
                    name="git_relevance",
                    value=relevance_signals.git,
                    evidence=(
                        Evidence(
                            source_id=candidate.entity_id,
                            description=(
                                "Git history indicates repeated changes to this file"
                            ),
                        ),
                    ),
                )
            )

        return ContextUnit(
            entity_id=candidate.entity_id,
            unit_type=candidate.unit_type,
            relevance=candidate.score,
            signals=tuple(context_signals),
        )
