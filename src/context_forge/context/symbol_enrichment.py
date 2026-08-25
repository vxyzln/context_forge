from context_forge.context.models import ContextUnit, Evidence, Fact
from context_forge.context.types import ContextUnitType
from context_forge.models.project import Project


class SymbolContextEnricher:
    def enrich(self, project: Project, unit: ContextUnit) -> ContextUnit:
        if unit.unit_type != ContextUnitType.SYMBOL:
            return unit

        symbol = next(
            (item for item in project.symbols if item.id == unit.entity_id),
            None,
        )

        if symbol is None:
            return unit

        evidence = Evidence(
            source_id=symbol.id,
            description=f"symbol metadata: {symbol.name}",
        )

        facts = (
            Fact(
                fact_type="symbol_name",
                value=symbol.name,
                evidence=(evidence,),
            ),
            Fact(
                fact_type="symbol_kind",
                value=symbol.kind,
                evidence=(evidence,),
            ),
            Fact(
                fact_type="start_line",
                value=str(symbol.start_line),
                evidence=(evidence,),
            ),
            Fact(
                fact_type="end_line",
                value=str(symbol.end_line),
                evidence=(evidence,),
            ),
        )

        if symbol.qualified_name is not None:
            facts += (
                Fact(
                    fact_type="qualified_name",
                    value=symbol.qualified_name,
                    evidence=(evidence,),
                ),
            )

        if symbol.signature is not None:
            facts += (
                Fact(
                    fact_type="signature",
                    value=symbol.signature,
                    evidence=(evidence,),
                ),
            )

        if symbol.parent_symbol_id is not None:
            facts += (
                Fact(
                    fact_type="parent_symbol",
                    value=str(symbol.parent_symbol_id),
                    evidence=(evidence,),
                ),
            )

        return ContextUnit(
            entity_id=unit.entity_id,
            unit_type=unit.unit_type,
            relevance=unit.relevance,
            signals=unit.signals,
            facts=unit.facts + facts,
            inferences=unit.inferences,
        )
