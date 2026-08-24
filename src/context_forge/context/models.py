from dataclasses import dataclass, field
from uuid import UUID

from context_forge.context.types import ContextUnitType


@dataclass(frozen=True)
class Evidence:
    source_id: UUID
    description: str


@dataclass(frozen=True)
class Fact:
    fact_type: str
    value: str
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class ContextSignal:
    name: str
    value: float
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class Inference:
    claim: str
    confidence: float
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Inference confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class ContextUnit:
    entity_id: UUID
    unit_type: ContextUnitType
    relevance: float = 0.0
    signals: tuple[ContextSignal, ...] = ()
    facts: tuple[Fact, ...] = ()
    inferences: tuple[Inference, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.relevance <= 1.0:
            raise ValueError("Context relevance must be between 0.0 and 1.0")


@dataclass(frozen=True)
class ContextPackage:
    task: str
    units: tuple[ContextUnit, ...] = field(default_factory=tuple)
