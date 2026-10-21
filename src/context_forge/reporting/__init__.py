"""Shared reporting, status, and diagnostic outcome contracts."""

from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)
from context_forge.reporting.errors import (
    BlockedOperationError,
    ContextForgeError,
    MissingAnalysisError,
    OperationalError,
    StaleAnalysisError,
)
from context_forge.reporting.formatter import (
    format_diagnostic_line,
    render_outcome_text,
)

__all__ = [
    "BlockedOperationError",
    "ContextForgeError",
    "DiagnosticItem",
    "DiagnosticSeverity",
    "MissingAnalysisError",
    "OperationOutcome",
    "OperationStatus",
    "OperationalError",
    "StaleAnalysisError",
    "format_diagnostic_line",
    "render_outcome_text",
]
