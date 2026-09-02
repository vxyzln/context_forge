import json

from context_forge.context.models import ContextPackage


class ContextPackageSerializer:
    def serialize(self, package: ContextPackage) -> str:
        payload = {
            "task": package.task,
            "units": [
                {
                    "entity_id": str(unit.entity_id),
                    "unit_type": unit.unit_type.value,
                    "relevance": unit.relevance,
                    "content": unit.content,
                    "signals": [
                        {
                            "name": signal.name,
                            "value": signal.value,
                            "evidence": [
                                {
                                    "source_id": str(evidence.source_id),
                                    "description": evidence.description,
                                }
                                for evidence in signal.evidence
                            ],
                        }
                        for signal in unit.signals
                    ],
                    "facts": [
                        {
                            "fact_type": fact.fact_type,
                            "value": fact.value,
                            "evidence": [
                                {
                                    "source_id": str(evidence.source_id),
                                    "description": evidence.description,
                                }
                                for evidence in fact.evidence
                            ],
                        }
                        for fact in unit.facts
                    ],
                    "inferences": [
                        {
                            "claim": inference.claim,
                            "confidence": inference.confidence,
                            "evidence": [
                                {
                                    "source_id": str(evidence.source_id),
                                    "description": evidence.description,
                                }
                                for evidence in inference.evidence
                            ],
                        }
                        for inference in unit.inferences
                    ],
                }
                for unit in package.units
            ],
        }

        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
