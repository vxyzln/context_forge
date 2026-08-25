from context_forge.context.models import ContextUnit, Evidence, Fact
from context_forge.models.project import Project


class RelationshipContextEnricher:
    def enrich(self, project: Project, unit: ContextUnit) -> ContextUnit:
        relationships = [
            relationship
            for relationship in project.relationships
            if relationship.source_id == unit.entity_id
            or relationship.target_id == unit.entity_id
        ]

        if not relationships:
            return unit

        facts = tuple(
            Fact(
                fact_type="relationship",
                value=(
                    f"{relationship.relationship_type}:"
                    f"{relationship.source_id}:"
                    f"{relationship.target_id}"
                ),
                evidence=(
                    Evidence(
                        source_id=relationship.id,
                        description=(f"relationship: {relationship.relationship_type}"),
                    ),
                ),
            )
            for relationship in relationships
        )

        return ContextUnit(
            entity_id=unit.entity_id,
            unit_type=unit.unit_type,
            relevance=unit.relevance,
            signals=unit.signals,
            facts=unit.facts + facts,
            inferences=unit.inferences,
        )
