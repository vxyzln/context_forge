from __future__ import annotations

from context_forge.comparison.models import (
    AffectedComponent,
    AmbiguousMatch,
    ComparisonState,
    FileDiff,
    RelationshipDiff,
    StateValidationResult,
    StructuralComparisonResult,
    SymbolDiff,
)
from context_forge.comparison.service import (
    compare_states,
    validate_comparison_states,
)

__all__ = [
    "AffectedComponent",
    "AmbiguousMatch",
    "ComparisonState",
    "FileDiff",
    "RelationshipDiff",
    "StateValidationResult",
    "StructuralComparisonResult",
    "SymbolDiff",
    "compare_states",
    "validate_comparison_states",
]
