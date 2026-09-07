from context_forge.context.candidate import ContextCandidate
from context_forge.context.expansion import ContextExpansion
from context_forge.context.models import (
    ContextPackage,
    ContextSignal,
    ContextUnit,
    Evidence,
)
from context_forge.context.retrieval import RetrievalEvidence
from context_forge.context.signals import RelevanceSignals


class ContextPackageBuilder:
    def build(
        self,
        task: str,
        expansions: list[ContextExpansion],
        signals: dict[object, RelevanceSignals] | None = None,
        retrieval_evidence: dict[object, RetrievalEvidence] | None = None,
        selection_confidence: dict[object, float] | None = None,
    ) -> ContextPackage:
        units: list[ContextUnit] = []
        signals = signals or {}
        retrieval_evidence = retrieval_evidence or {}
        selection_confidence = selection_confidence or {}

        for expansion in expansions:
            candidate = expansion.candidate

            units.append(
                self._build_unit(
                    candidate,
                    signals.get(candidate.entity_id),
                    retrieval_evidence.get(candidate.entity_id),
                    selection_confidence.get(candidate.entity_id),
                )
            )

            for related in expansion.related:
                units.append(
                    self._build_unit(
                        related,
                        signals.get(related.entity_id),
                        retrieval_evidence.get(related.entity_id),
                        selection_confidence.get(related.entity_id),
                    ),
                )

        return ContextPackage(
            task=task.strip(),
            units=tuple(units),
        )

    @staticmethod
    def _build_unit(
        candidate: ContextCandidate,
        relevance_signals: RelevanceSignals | None = None,
        retrieval_evidence: RetrievalEvidence | None = None,
        selection_confidence: float | None = None,
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

        if selection_confidence is not None:
            context_signals.append(
                ContextSignal(
                    name="selection_confidence",
                    value=selection_confidence,
                    evidence=(
                        Evidence(
                            source_id=candidate.entity_id,
                            description="LLM context-selection confidence",
                        ),
                    ),
                )
            )

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

        if retrieval_evidence is not None:
            relationship_type = retrieval_evidence.relationship_type

            if hasattr(relationship_type, "value"):
                relationship_type = relationship_type.value

            context_signals.append(
                ContextSignal(
                    name="relationship_retrieval",
                    value=retrieval_evidence.candidate_confidence,
                    evidence=(
                        Evidence(
                            source_id=candidate.entity_id,
                            description=(
                                f"Retrieved through {relationship_type} relationship "
                                f"at depth {retrieval_evidence.depth}"
                                f"{retrieval_evidence.provenance}"
                            ),
                        ),
                    ),
                ),
            )

        return ContextUnit(
            entity_id=candidate.entity_id,
            unit_type=candidate.unit_type,
            relevance=candidate.score,
            signals=tuple(context_signals),
        )
