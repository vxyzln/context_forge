"""Structured operational exceptions that carry DiagnosticItem and OperationOutcome."""

from __future__ import annotations

from typing import Any

from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)


class ContextForgeError(ValueError):
    """Base exception for Context Forge operational errors.

    Carries structured diagnostic context and an OperationOutcome representation
    so callers and CLI handlers can access machine-readable failure details
    while preserving standard string representation and exception semantics.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
        severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
        outcome: OperationOutcome | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.path = path
        self.line = line
        self.column = column
        self.source = source
        self.details = details or {}
        self.severity = severity

        if outcome is not None:
            self.outcome = outcome
        else:
            diag = DiagnosticItem(
                severity=severity,
                message=message,
                code=code,
                path=path,
                line=line,
                column=column,
                source=source,
                details=self.details,
            )
            status = (
                OperationStatus.BLOCKED
                if severity == DiagnosticSeverity.BLOCKER
                else OperationStatus.FAILED
            )
            self.outcome = OperationOutcome(
                status=status,
                message=message,
                diagnostics=(diag,),
            )

    @property
    def diagnostic(self) -> DiagnosticItem:
        """Primary diagnostic item for this exception."""
        if self.outcome.diagnostics:
            return self.outcome.diagnostics[0]
        return DiagnosticItem(
            severity=self.severity,
            message=self.message,
            code=self.code,
            path=self.path,
            line=self.line,
            column=self.column,
            source=self.source,
            details=self.details,
        )

    def to_dict(self) -> dict[str, Any]:
        """Structured error dictionary."""
        return self.outcome.to_dict()


class OperationalError(ContextForgeError):
    """Raised when an operation encounters an unrecoverable runtime error."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
        severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
        outcome: OperationOutcome | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code,
            path=path,
            line=line,
            column=column,
            source=source,
            details=details,
            severity=severity,
            outcome=outcome,
        )


class BlockedOperationError(OperationalError):
    """Raised when an operation cannot proceed due to an unmet prerequisite or constraint."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
        outcome: OperationOutcome | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or "OPERATION_BLOCKED",
            path=path,
            line=line,
            column=column,
            source=source,
            details=details,
            severity=DiagnosticSeverity.BLOCKER,
            outcome=outcome,
        )


class MissingAnalysisError(BlockedOperationError):
    """Raised when persisted analysis is required but missing."""

    def __init__(
        self,
        message: str = "No persisted analysis found; run 'context-forge analyze' first",
        *,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="MISSING_ANALYSIS",
            path=path,
            source="storage",
            details=details,
        )


class StaleAnalysisError(BlockedOperationError):
    """Raised when cached analysis is stale and fresh analysis is required."""

    def __init__(
        self,
        message: str = (
            "Repository analysis is stale; run 'context-forge analyze' to refresh"
        ),
        *,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="STALE_ANALYSIS",
            path=path,
            source="cache",
            details=details,
        )


class IncompleteAnalysisError(BlockedOperationError):
    """Raised when analysis is incomplete, failed, or contains recorded errors."""

    def __init__(
        self,
        message: str = (
            "Repository analysis is incomplete; run 'context-forge analyze' to complete analysis"
        ),
        *,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="INCOMPLETE_ANALYSIS",
            path=path,
            source="analyzer",
            details=details,
        )


class IndeterminateFreshnessError(BlockedOperationError):
    """Raised when repository analysis freshness cannot be determined reliably."""

    def __init__(
        self,
        message: str = (
            "Repository analysis freshness is indeterminate; reanalysis is required"
        ),
        *,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="INDETERMINATE_FRESHNESS",
            path=path,
            source="storage",
            details=details,
        )
