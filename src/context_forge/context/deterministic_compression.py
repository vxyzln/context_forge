from context_forge.context.compression import ContextCompressor
from context_forge.context.models import (
    ContextPackage,
    ContextSignal,
    ContextUnit,
    Evidence,
    Fact,
    Inference,
)


class DeterministicContextCompressor(ContextCompressor):
    """Deterministically remove duplicate context units."""

    def compress(self, package: ContextPackage) -> ContextPackage:
        merged: dict[tuple[object, object], ContextUnit] = {}

        for unit in package.units:
            key = (unit.entity_id, unit.unit_type)

            if key not in merged:
                merged[key] = unit
            else:
                merged[key] = self._merge_units(merged[key], unit)

        return ContextPackage(
            task=package.task,
            units=tuple(merged.values()),
        )

    def _merge_units(
        self,
        first: ContextUnit,
        second: ContextUnit,
    ) -> ContextUnit:
        return ContextUnit(
            entity_id=first.entity_id,
            unit_type=first.unit_type,
            relevance=max(first.relevance, second.relevance),
            content=first.content if first.content is not None else second.content,
            signals=self._merge_signals(first.signals, second.signals),
            facts=self._merge_facts(first.facts, second.facts),
            inferences=self._merge_inferences(
                first.inferences,
                second.inferences,
            ),
        )

    @staticmethod
    def _merge_signals(
        first: tuple[ContextSignal, ...],
        second: tuple[ContextSignal, ...],
    ) -> tuple[ContextSignal, ...]:
        merged: dict[tuple[str, float], ContextSignal] = {}

        for signal in (*first, *second):
            key = (signal.name, signal.value)

            if key not in merged:
                merged[key] = signal
            else:
                merged[key] = ContextSignal(
                    name=signal.name,
                    value=signal.value,
                    evidence=DeterministicContextCompressor._merge_evidence(
                        merged[key].evidence,
                        signal.evidence,
                    ),
                )

        return tuple(merged.values())

    @staticmethod
    def _merge_facts(
        first: tuple[Fact, ...],
        second: tuple[Fact, ...],
    ) -> tuple[Fact, ...]:
        merged: dict[tuple[str, str], Fact] = {}

        for fact in (*first, *second):
            key = (fact.fact_type, fact.value)

            if key not in merged:
                merged[key] = fact
            else:
                merged[key] = Fact(
                    fact_type=fact.fact_type,
                    value=fact.value,
                    evidence=DeterministicContextCompressor._merge_evidence(
                        merged[key].evidence,
                        fact.evidence,
                    ),
                )

        return tuple(merged.values())

    @staticmethod
    def _merge_inferences(
        first: tuple[Inference, ...],
        second: tuple[Inference, ...],
    ) -> tuple[Inference, ...]:
        merged: dict[tuple[str, float], Inference] = {}

        for inference in (*first, *second):
            key = (inference.claim, inference.confidence)

            if key not in merged:
                merged[key] = inference
            else:
                merged[key] = Inference(
                    claim=inference.claim,
                    confidence=inference.confidence,
                    evidence=DeterministicContextCompressor._merge_evidence(
                        merged[key].evidence,
                        inference.evidence,
                    ),
                )

        return tuple(merged.values())

    @staticmethod
    def _merge_evidence(
        first: tuple[Evidence, ...],
        second: tuple[Evidence, ...],
    ) -> tuple[Evidence, ...]:
        merged: dict[tuple[object, str], Evidence] = {}

        for evidence in (*first, *second):
            key = (evidence.source_id, evidence.description)

            if key not in merged:
                merged[key] = evidence

        return tuple(merged.values())
