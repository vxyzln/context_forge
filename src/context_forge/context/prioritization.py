from typing import ClassVar

from context_forge.context.models import ContextUnit
from context_forge.context.priority import ContextPriority
from context_forge.context.types import ContextUnitType


class DeterministicPrioritizer:
    """Assign deterministic priority scores to context units."""

    _TYPE_WEIGHTS: ClassVar[dict[ContextUnitType, float]] = {
        ContextUnitType.SYMBOL: 1.0,
        ContextUnitType.FILE: 0.85,
        ContextUnitType.DIRECTORY: 0.65,
    }

    def prioritize(self, unit: ContextUnit) -> ContextPriority:
        relevance = unit.relevance
        type_weight = self._TYPE_WEIGHTS.get(unit.unit_type, 0.5)

        evidence_count = sum(len(signal.evidence) for signal in unit.signals)

        evidence_count += sum(len(fact.evidence) for fact in unit.facts)

        evidence_count += sum(len(inference.evidence) for inference in unit.inferences)

        evidence_bonus = min(evidence_count * 0.05, 0.15)

        score = (relevance * 0.70) + (type_weight * 0.20) + (evidence_bonus * 0.10)

        score = min(max(score, 0.0), 1.0)

        return ContextPriority(
            score=score,
            reason=self._build_reason(
                relevance=relevance,
                type_weight=type_weight,
                evidence_count=evidence_count,
            ),
        )

    def _build_reason(
        self,
        relevance: float,
        type_weight: float,
        evidence_count: int,
    ) -> str:
        return (
            f"relevance={relevance:.3f};"
            f"type_weight={type_weight:.3f};"
            f"evidence_count={evidence_count}"
        )
