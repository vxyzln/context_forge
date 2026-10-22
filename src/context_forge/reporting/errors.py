from __future__ import annotations

from typing import Any

from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)


class ContextForgeError(ValueError):
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
        return self.outcome.to_dict()


class OperationalError(ContextForgeError):
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
