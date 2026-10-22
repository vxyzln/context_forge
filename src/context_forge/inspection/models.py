from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context_forge.git.navigation import GitNavigationContext
from context_forge.pipeline.freshness import WorkflowFreshness
from context_forge.query.impact import ImpactResult, TargetResolution
from context_forge.query.locator import SourceExcerpt
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)


@dataclass(frozen=True)
class PreChangeInspectionResult:
    repository_path: str
    target_query: str
    readiness: dict[str, Any]
    target_resolution: TargetResolution | None = None
    freshness: WorkflowFreshness | None = None
    source_evidence: SourceExcerpt | None = None
    structural_evidence: ImpactResult | None = None
    git_context: GitNavigationContext | None = None
    outcome: OperationOutcome = field(
        default_factory=lambda: OperationOutcome.success()
    )
    limitations: tuple[str, ...] = ()
    diagnostics: tuple[DiagnosticItem, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.limitations, list):
            object.__setattr__(self, "limitations", tuple(self.limitations))
        if isinstance(self.diagnostics, list):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    @property
    def is_success(self) -> bool:
        return self.outcome.status == OperationStatus.SUCCESS

    @property
    def is_partial(self) -> bool:
        return self.outcome.status == OperationStatus.PARTIAL

    @property
    def is_incomplete(self) -> bool:
        return self.outcome.status == OperationStatus.INCOMPLETE

    @property
    def is_blocked(self) -> bool:
        return self.outcome.status == OperationStatus.BLOCKED

    @property
    def is_failed(self) -> bool:
        return self.outcome.status == OperationStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        target_res_dict: dict[str, Any] | None = None
        if self.target_resolution is not None:
            target_res_dict = {
                "status": self.target_resolution.status,
                "is_resolved": self.target_resolution.is_resolved,
                "is_ambiguous": self.target_resolution.is_ambiguous,
                "is_not_found": self.target_resolution.is_not_found,
                "is_invalid": self.target_resolution.is_invalid,
                "target": (
                    self.target_resolution.target.to_dict()
                    if self.target_resolution.target is not None
                    else None
                ),
                "candidates": [c.to_dict() for c in self.target_resolution.candidates],
                "message": self.target_resolution.message,
            }

        return {
            "schema_version": self.schema_version,
            "repository_path": self.repository_path,
            "target_query": self.target_query,
            "readiness": self.readiness,
            "target_resolution": target_res_dict,
            "freshness": (
                self.freshness.to_dict() if self.freshness is not None else None
            ),
            "source_evidence": (
                self.source_evidence.to_dict()
                if self.source_evidence is not None
                else None
            ),
            "structural_evidence": (
                self.structural_evidence.to_dict()
                if self.structural_evidence is not None
                else None
            ),
            "git_context": (
                self.git_context.to_dict() if self.git_context is not None else None
            ),
            "outcome": self.outcome.to_dict(),
            "limitations": list(self.limitations),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
        }
