from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from context_forge.models.project import Project
from context_forge.pipeline.freshness import FreshnessState, WorkflowFreshness
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
)
from context_forge.storage.cache import FileFingerprint, RepositoryCacheMetadata

COMPLETE_ANALYSIS_STATUSES: frozenset[str] = frozenset({"analyzed", "completed"})


def is_terminal_complete_status(status: str | None) -> bool:
    if not status or not isinstance(status, str):
        return False
    return status.strip().lower() in COMPLETE_ANALYSIS_STATUSES


@dataclass
class ComparisonState:
    project: Project | None = None
    state_id: str | None = None
    repository_path: Path | str | None = None
    metadata: RepositoryCacheMetadata | None = None
    fingerprints: dict[Path, FileFingerprint | Any] | None = None
    analysis_status: str | None = None
    analysis_errors: tuple[str, ...] = ()
    freshness: FreshnessState | WorkflowFreshness | None = None
    is_historical: bool = False
    source_label: str | None = None

    def __post_init__(self) -> None:
        if self.repository_path is not None:
            self.repository_path = Path(self.repository_path)
        elif self.project is not None:
            self.repository_path = self.project.root_path

        if self.state_id is None:
            if self.project is not None:
                self.state_id = str(self.project.id)
            elif self.metadata is not None:
                self.state_id = str(self.metadata.project_id)

        if not self.analysis_status and self.project is not None:
            self.analysis_status = self.project.analysis_status

        if (
            not self.analysis_errors
            and self.project is not None
            and self.project.errors
        ):
            self.analysis_errors = tuple(self.project.errors)
        elif isinstance(self.analysis_errors, list):
            self.analysis_errors = tuple(self.analysis_errors)

    @property
    def is_supplied(self) -> bool:
        return self.project is not None

    @property
    def is_usable(self) -> bool:
        if self.project is None:
            return False
        return bool(self.state_id)

    @property
    def repository_key(self) -> str:
        if self.metadata is not None and self.metadata.repository_key:
            return self.metadata.repository_key
        if self.repository_path is not None:
            return str(self.repository_path.resolve())
        return ""

    @property
    def is_complete(self) -> bool:
        if not self.is_supplied:
            return False
        if not is_terminal_complete_status(self.analysis_status):
            return False
        if len(self.analysis_errors) > 0:
            return False
        if self.freshness is not None:
            state_freshness = (
                self.freshness.state
                if isinstance(self.freshness, WorkflowFreshness)
                else self.freshness
            )
            if state_freshness == FreshnessState.INCOMPLETE:
                return False
            if state_freshness == FreshnessState.INDETERMINATE:
                return False
            if state_freshness == FreshnessState.STALE and not self.is_historical:
                return False
        return True

    @classmethod
    def from_project(
        cls,
        project: Project,
        *,
        state_id: str | None = None,
        metadata: RepositoryCacheMetadata | None = None,
        fingerprints: dict[Path, FileFingerprint | Any] | None = None,
        freshness: FreshnessState | WorkflowFreshness | None = None,
        is_historical: bool = False,
        source_label: str | None = None,
    ) -> ComparisonState:
        return cls(
            project=project,
            state_id=state_id or str(project.id),
            repository_path=project.root_path,
            metadata=metadata,
            fingerprints=fingerprints,
            analysis_status=project.analysis_status,
            analysis_errors=tuple(project.errors),
            freshness=freshness,
            is_historical=is_historical,
            source_label=source_label,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "is_historical": self.is_historical,
            "is_supplied": self.is_supplied,
            "is_usable": self.is_usable,
            "is_complete": self.is_complete,
            "repository_key": self.repository_key,
            "state_id": self.state_id,
        }
        if self.source_label:
            result["source_label"] = self.source_label
        if self.analysis_status:
            result["analysis_status"] = self.analysis_status
        if self.analysis_errors:
            result["analysis_errors"] = list(self.analysis_errors)
        if self.freshness is not None:
            freshness_val = (
                self.freshness.state.value
                if isinstance(self.freshness, WorkflowFreshness)
                else (
                    self.freshness.value
                    if isinstance(self.freshness, FreshnessState)
                    else str(self.freshness)
                )
            )
            result["freshness"] = freshness_val
        if self.project is not None:
            result["files_count"] = len(self.project.files)
            result["symbols_count"] = len(self.project.symbols)
            result["relationships_count"] = len(self.project.relationships)
        return result


@dataclass(frozen=True)
class StateValidationResult:
    is_valid: bool
    outcome: OperationOutcome
    before_state: ComparisonState | None = None
    after_state: ComparisonState | None = None
    is_complete: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_complete": self.is_complete,
            "is_valid": self.is_valid,
            "outcome": self.outcome.to_dict(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FileDiff:
    path: str
    change_type: str
    before_path: str | None = None
    after_path: str | None = None
    before_fingerprint: str | None = None
    after_fingerprint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "change_type": self.change_type,
            "path": self.path,
        }
        if self.before_path:
            payload["before_path"] = self.before_path
        if self.after_path:
            payload["after_path"] = self.after_path
        if self.before_fingerprint:
            payload["before_fingerprint"] = self.before_fingerprint
        if self.after_fingerprint:
            payload["after_fingerprint"] = self.after_fingerprint
        if self.details:
            payload["details"] = dict(sorted(self.details.items()))
        return payload


@dataclass(frozen=True)
class SymbolDiff:
    name: str
    kind: str
    file_path: str
    change_type: str
    qualified_name: str | None = None
    before_file_path: str | None = None
    after_file_path: str | None = None
    before_signature: str | None = None
    after_signature: str | None = None
    before_lines: tuple[int, int] | None = None
    after_lines: tuple[int, int] | None = None
    is_line_shift_only: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "change_type": self.change_type,
            "file_path": self.file_path,
            "kind": self.kind,
            "name": self.name,
        }
        if self.qualified_name:
            payload["qualified_name"] = self.qualified_name
        if self.before_file_path:
            payload["before_file_path"] = self.before_file_path
        if self.after_file_path:
            payload["after_file_path"] = self.after_file_path
        if self.before_signature:
            payload["before_signature"] = self.before_signature
        if self.after_signature:
            payload["after_signature"] = self.after_signature
        if self.before_lines:
            payload["before_lines"] = list(self.before_lines)
        if self.after_lines:
            payload["after_lines"] = list(self.after_lines)
        if self.is_line_shift_only:
            payload["is_line_shift_only"] = self.is_line_shift_only
        if self.details:
            payload["details"] = dict(sorted(self.details.items()))
        return payload


@dataclass(frozen=True)
class RelationshipDiff:
    source_key: str
    target_key: str
    relationship_type: str
    change_type: str
    before_confidence: float | None = None
    after_confidence: float | None = None
    metadata_changes: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "change_type": self.change_type,
            "relationship_type": self.relationship_type,
            "source_key": self.source_key,
            "target_key": self.target_key,
        }
        if self.before_confidence is not None:
            payload["before_confidence"] = self.before_confidence
        if self.after_confidence is not None:
            payload["after_confidence"] = self.after_confidence
        if self.metadata_changes:
            payload["metadata_changes"] = dict(sorted(self.metadata_changes.items()))
        if self.details:
            payload["details"] = dict(sorted(self.details.items()))
        return payload


@dataclass(frozen=True)
class AmbiguousMatch:
    category: str
    before_candidates: tuple[str, ...]
    after_candidates: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "after_candidates": list(self.after_candidates),
            "before_candidates": list(self.before_candidates),
            "category": self.category,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AffectedComponent:
    entity_key: str
    entity_type: str
    path: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_key": self.entity_key,
            "entity_type": self.entity_type,
            "path": self.path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class StructuralComparisonResult:
    before_state_id: str | None
    after_state_id: str | None
    repository_key: str
    outcome: OperationOutcome
    is_complete: bool = True
    added_files: tuple[FileDiff, ...] = ()
    removed_files: tuple[FileDiff, ...] = ()
    modified_files: tuple[FileDiff, ...] = ()
    moved_files: tuple[FileDiff, ...] = ()
    added_symbols: tuple[SymbolDiff, ...] = ()
    removed_symbols: tuple[SymbolDiff, ...] = ()
    modified_symbols: tuple[SymbolDiff, ...] = ()
    moved_symbols: tuple[SymbolDiff, ...] = ()
    added_relationships: tuple[RelationshipDiff, ...] = ()
    removed_relationships: tuple[RelationshipDiff, ...] = ()
    modified_relationships: tuple[RelationshipDiff, ...] = ()
    ambiguous_matches: tuple[AmbiguousMatch, ...] = ()
    affected_components: tuple[AffectedComponent, ...] = ()
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def has_structural_changes(self) -> bool:
        return bool(
            self.added_files
            or self.removed_files
            or self.modified_files
            or self.moved_files
            or self.added_symbols
            or self.removed_symbols
            or self.modified_symbols
            or self.moved_symbols
            or self.added_relationships
            or self.removed_relationships
            or self.modified_relationships
        )

    @property
    def total_changes_count(self) -> int:
        return (
            len(self.added_files)
            + len(self.removed_files)
            + len(self.modified_files)
            + len(self.moved_files)
            + len(self.added_symbols)
            + len(self.removed_symbols)
            + len(self.modified_symbols)
            + len(self.moved_symbols)
            + len(self.added_relationships)
            + len(self.removed_relationships)
            + len(self.modified_relationships)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_files": [f.to_dict() for f in self.added_files],
            "added_relationships": [r.to_dict() for r in self.added_relationships],
            "added_symbols": [s.to_dict() for s in self.added_symbols],
            "affected_components": [a.to_dict() for a in self.affected_components],
            "after_state_id": self.after_state_id,
            "ambiguous_matches": [m.to_dict() for m in self.ambiguous_matches],
            "before_state_id": self.before_state_id,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "has_structural_changes": self.has_structural_changes,
            "is_complete": self.is_complete,
            "limitations": list(self.limitations),
            "modified_files": [f.to_dict() for f in self.modified_files],
            "modified_relationships": [
                r.to_dict() for r in self.modified_relationships
            ],
            "modified_symbols": [s.to_dict() for s in self.modified_symbols],
            "moved_files": [f.to_dict() for f in self.moved_files],
            "moved_symbols": [s.to_dict() for s in self.moved_symbols],
            "outcome": self.outcome.to_dict(),
            "removed_files": [f.to_dict() for f in self.removed_files],
            "removed_relationships": [r.to_dict() for r in self.removed_relationships],
            "removed_symbols": [s.to_dict() for s in self.removed_symbols],
            "repository_key": self.repository_key,
            "total_changes_count": self.total_changes_count,
        }
