from context_forge.context.models import (
    ContextSignal,
    ContextUnit,
    Fact,
    Inference,
)


class ContextUnitMerger:
    """Deterministically merges duplicate context units."""

    def merge(
        self,
        units: list[ContextUnit],
    ) -> list[ContextUnit]:
        merged: dict[tuple[object, object], ContextUnit] = {}

        for unit in units:
            key = (unit.entity_id, unit.unit_type)

            if key not in merged:
                merged[key] = unit
            else:
                merged[key] = self._merge_units(
                    merged[key],
                    unit,
                )

        return list(merged.values())

    def _merge_units(
        self,
        first: ContextUnit,
        second: ContextUnit,
    ) -> ContextUnit:
        return ContextUnit(
            entity_id=first.entity_id,
            unit_type=first.unit_type,
            relevance=max(first.relevance, second.relevance),
            signals=self._merge_signals(
                first.signals,
                second.signals,
            ),
            facts=self._merge_facts(
                first.facts,
                second.facts,
            ),
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
        result = list(first)

        for signal in second:
            matching = next(
                (
                    existing
                    for existing in result
                    if existing.name == signal.name and existing.value == signal.value
                ),
                None,
            )

            if matching is None:
                result.append(signal)
                continue

            merged = ContextSignal(
                name=matching.name,
                value=matching.value,
                evidence=tuple(
                    dict.fromkeys(
                        (*matching.evidence, *signal.evidence),
                    )
                ),
            )

            result[result.index(matching)] = merged

        return tuple(result)

    @staticmethod
    def _merge_facts(
        first: tuple[Fact, ...],
        second: tuple[Fact, ...],
    ) -> tuple[Fact, ...]:
        result = list(first)

        for fact in second:
            matching = next(
                (
                    existing
                    for existing in result
                    if existing.fact_type == fact.fact_type
                    and existing.value == fact.value
                ),
                None,
            )

            if matching is None:
                result.append(fact)
                continue

            merged = Fact(
                fact_type=fact.fact_type,
                value=fact.value,
                evidence=tuple(
                    dict.fromkeys(
                        (*matching.evidence, *fact.evidence),
                    )
                ),
            )

            result[result.index(matching)] = merged

        return tuple(result)

    @staticmethod
    def _merge_inferences(
        first: tuple[Inference, ...],
        second: tuple[Inference, ...],
    ) -> tuple[Inference, ...]:
        result = list(first)

        for inference in second:
            matching = next(
                (existing for existing in result if existing.claim == inference.claim),
                None,
            )

            if matching is None:
                result.append(inference)
                continue

            merged = Inference(
                claim=inference.claim,
                confidence=max(
                    matching.confidence,
                    inference.confidence,
                ),
                evidence=tuple(
                    dict.fromkeys(
                        (*matching.evidence, *inference.evidence),
                    )
                ),
            )

            result[result.index(matching)] = merged

        return tuple(result)
