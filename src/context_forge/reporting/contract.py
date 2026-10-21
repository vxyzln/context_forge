"""Shared reporting, status, and diagnostic outcome contracts.

Provides unified, deterministic outcome semantics for Context Forge operations
(preflight, health, architecture, impact, inspection, etc.) distinguishing:
- complete success
- success with warnings
- partial results
- blocked operations
- operational errors and failures
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OperationStatus(str, Enum):
    """Execution status for Context Forge operations."""

    SUCCESS = "success"
    PARTIAL = "partial"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"
    FAILED = "failed"

    @property
    def is_successful(self) -> bool:
        """True if the operation completed with full success."""
        return self is OperationStatus.SUCCESS

    @property
    def is_failure(self) -> bool:
        """True if the operation failed with an error."""
        return self is OperationStatus.FAILED

    @property
    def is_blocked(self) -> bool:
        """True if the operation was blocked by a prerequisite or constraint."""
        return self is OperationStatus.BLOCKED

    @property
    def is_partial(self) -> bool:
        """True if the operation produced partial results."""
        return self is OperationStatus.PARTIAL

    @property
    def is_incomplete(self) -> bool:
        """True if the operation or underlying data is incomplete/unanalyzed."""
        return self is OperationStatus.INCOMPLETE


class DiagnosticSeverity(str, Enum):
    """Severity classification for diagnostics and findings."""

    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"
    ERROR = "error"

    @property
    def is_blocking(self) -> bool:
        """True if this diagnostic prevents or blocks successful execution."""
        return self in (DiagnosticSeverity.BLOCKER, DiagnosticSeverity.ERROR)

    @property
    def is_actionable(self) -> bool:
        """True if this diagnostic represents a warning, blocker, or error."""
        return self in (
            DiagnosticSeverity.WARNING,
            DiagnosticSeverity.BLOCKER,
            DiagnosticSeverity.ERROR,
        )


@dataclass(frozen=True)
class DiagnosticItem:
    """Structured diagnostic finding or notification."""

    severity: DiagnosticSeverity
    message: str
    code: str | None = None
    path: str | None = None
    line: int | None = None
    column: int | None = None
    source: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.severity, str) and not isinstance(
            self.severity, DiagnosticSeverity
        ):
            object.__setattr__(self, "severity", DiagnosticSeverity(self.severity))
        if not self.message.strip():
            raise ValueError("Diagnostic message cannot be empty")

    @classmethod
    def info(
        cls,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> DiagnosticItem:
        return cls(
            severity=DiagnosticSeverity.INFO,
            message=message,
            code=code,
            path=path,
            line=line,
            column=column,
            source=source,
            details=details or {},
        )

    @classmethod
    def warning(
        cls,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> DiagnosticItem:
        return cls(
            severity=DiagnosticSeverity.WARNING,
            message=message,
            code=code,
            path=path,
            line=line,
            column=column,
            source=source,
            details=details or {},
        )

    @classmethod
    def blocker(
        cls,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> DiagnosticItem:
        return cls(
            severity=DiagnosticSeverity.BLOCKER,
            message=message,
            code=code,
            path=path,
            line=line,
            column=column,
            source=source,
            details=details or {},
        )

    @classmethod
    def error(
        cls,
        message: str,
        *,
        code: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> DiagnosticItem:
        return cls(
            severity=DiagnosticSeverity.ERROR,
            message=message,
            code=code,
            path=path,
            line=line,
            column=column,
            source=source,
            details=details or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Deterministic dictionary representation."""
        payload: dict[str, Any] = {
            "severity": self.severity.value,
            "message": self.message,
            "code": self.code,
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "source": self.source,
        }
        if self.details:
            payload["details"] = dict(sorted(self.details.items()))
        return payload


@dataclass(frozen=True)
class OperationOutcome:
    """Comprehensive operation outcome representing execution status and diagnostics."""

    status: OperationStatus
    message: str = ""
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.status, str) and not isinstance(
            self.status, OperationStatus
        ):
            object.__setattr__(self, "status", OperationStatus(self.status))
        if isinstance(self.diagnostics, list):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if isinstance(self.limitations, list):
            object.__setattr__(self, "limitations", tuple(self.limitations))

    @property
    def is_success(self) -> bool:
        """True only if the operation succeeded completely without failure or blocking."""
        return self.status == OperationStatus.SUCCESS

    @property
    def is_partial(self) -> bool:
        """True if the operation returned partial results."""
        return self.status == OperationStatus.PARTIAL

    @property
    def is_incomplete(self) -> bool:
        """True if the operation or underlying analysis is incomplete."""
        return self.status == OperationStatus.INCOMPLETE

    @property
    def is_blocked(self) -> bool:
        """True if the operation was blocked from proceeding."""
        return self.status == OperationStatus.BLOCKED

    @property
    def is_failed(self) -> bool:
        """True if the operation failed with an error."""
        return self.status == OperationStatus.FAILED

    @property
    def warnings(self) -> tuple[DiagnosticItem, ...]:
        return tuple(
            d for d in self.diagnostics if d.severity == DiagnosticSeverity.WARNING
        )

    @property
    def blockers(self) -> tuple[DiagnosticItem, ...]:
        return tuple(
            d for d in self.diagnostics if d.severity == DiagnosticSeverity.BLOCKER
        )

    @property
    def errors(self) -> tuple[DiagnosticItem, ...]:
        return tuple(
            d for d in self.diagnostics if d.severity == DiagnosticSeverity.ERROR
        )

    @property
    def info_items(self) -> tuple[DiagnosticItem, ...]:
        return tuple(
            d for d in self.diagnostics if d.severity == DiagnosticSeverity.INFO
        )

    @property
    def has_warnings(self) -> bool:
        return any(d.severity == DiagnosticSeverity.WARNING for d in self.diagnostics)

    @property
    def has_blockers(self) -> bool:
        return any(d.severity == DiagnosticSeverity.BLOCKER for d in self.diagnostics)

    @property
    def has_errors(self) -> bool:
        return any(d.severity == DiagnosticSeverity.ERROR for d in self.diagnostics)

    @property
    def has_info(self) -> bool:
        return any(d.severity == DiagnosticSeverity.INFO for d in self.diagnostics)

    @classmethod
    def success(
        cls,
        message: str = "",
        *,
        diagnostics: tuple[DiagnosticItem, ...] | list[DiagnosticItem] = (),
        limitations: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> OperationOutcome:
        return cls(
            status=OperationStatus.SUCCESS,
            message=message,
            diagnostics=tuple(diagnostics),
            limitations=tuple(limitations),
            metadata=metadata or {},
        )

    @classmethod
    def partial(
        cls,
        message: str = "",
        *,
        diagnostics: tuple[DiagnosticItem, ...] | list[DiagnosticItem] = (),
        limitations: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> OperationOutcome:
        return cls(
            status=OperationStatus.PARTIAL,
            message=message,
            diagnostics=tuple(diagnostics),
            limitations=tuple(limitations),
            metadata=metadata or {},
        )

    @classmethod
    def incomplete(
        cls,
        message: str = "",
        *,
        diagnostics: tuple[DiagnosticItem, ...] | list[DiagnosticItem] = (),
        limitations: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> OperationOutcome:
        return cls(
            status=OperationStatus.INCOMPLETE,
            message=message,
            diagnostics=tuple(diagnostics),
            limitations=tuple(limitations),
            metadata=metadata or {},
        )

    @classmethod
    def blocked(
        cls,
        message: str = "",
        *,
        diagnostics: tuple[DiagnosticItem, ...] | list[DiagnosticItem] = (),
        limitations: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> OperationOutcome:
        return cls(
            status=OperationStatus.BLOCKED,
            message=message,
            diagnostics=tuple(diagnostics),
            limitations=tuple(limitations),
            metadata=metadata or {},
        )

    @classmethod
    def failed(
        cls,
        message: str = "",
        *,
        diagnostics: tuple[DiagnosticItem, ...] | list[DiagnosticItem] = (),
        limitations: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> OperationOutcome:
        return cls(
            status=OperationStatus.FAILED,
            message=message,
            diagnostics=tuple(diagnostics),
            limitations=tuple(limitations),
            metadata=metadata or {},
        )

    @classmethod
    def from_diagnostics(
        cls,
        diagnostics: tuple[DiagnosticItem, ...] | list[DiagnosticItem] = (),
        *,
        limitations: tuple[str, ...] | list[str] = (),
        message: str = "",
        is_partial: bool = False,
        is_incomplete: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> OperationOutcome:
        """Derive an appropriate OperationOutcome based on diagnostic severities and completeness.

        Rules:
        - ERROR diagnostics produce FAILED status.
        - BLOCKER diagnostics produce BLOCKED status.
        - Incomplete execution/analysis produces INCOMPLETE status.
        - Materially partial results or limitations produce PARTIAL status.
        - Complete operations with warnings remain SUCCESS with warning diagnostics.
        """
        diags = tuple(diagnostics)
        lims = tuple(limitations)

        has_err = any(d.severity == DiagnosticSeverity.ERROR for d in diags)
        has_blk = any(d.severity == DiagnosticSeverity.BLOCKER for d in diags)

        if has_err:
            status = OperationStatus.FAILED
        elif has_blk:
            status = OperationStatus.BLOCKED
        elif is_incomplete:
            status = OperationStatus.INCOMPLETE
        elif is_partial:
            status = OperationStatus.PARTIAL
        else:
            status = OperationStatus.SUCCESS

        return cls(
            status=status,
            message=message,
            diagnostics=diags,
            limitations=lims,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize outcome to a clean, deterministic dictionary."""
        return {
            "status": self.status.value,
            "is_success": self.is_success,
            "message": self.message,
            "summary": {
                "errors": len(self.errors),
                "blockers": len(self.blockers),
                "warnings": len(self.warnings),
                "info": len(self.info_items),
                "limitations": len(self.limitations),
                "total_diagnostics": len(self.diagnostics),
            },
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "limitations": list(self.limitations),
            "metadata": dict(sorted(self.metadata.items())),
        }
