from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from context_forge.models.project import Project
from context_forge.pipeline.analyzer import ProjectAnalyzer
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
)
from context_forge.scanner.repository import RepositoryScanner
from context_forge.storage.cache import (
    ANALYZER_VERSION,
    CACHE_SCHEMA_VERSION,
    FileChangeSet,
    FileFingerprint,
    RepositoryCacheMetadata,
    RepositoryIdentity,
    detect_file_changes,
    fingerprint_file,
)
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


class FreshnessState(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    INDETERMINATE = "indeterminate"

    @property
    def is_current(self) -> bool:
        return self is FreshnessState.CURRENT

    @property
    def is_stale(self) -> bool:
        return self is FreshnessState.STALE

    @property
    def is_incomplete(self) -> bool:
        return self is FreshnessState.INCOMPLETE

    @property
    def is_indeterminate(self) -> bool:
        return self is FreshnessState.INDETERMINATE


@dataclass(frozen=True)
class WorkflowFreshness:
    state: FreshnessState
    reason: str
    changes: FileChangeSet | None = None
    analysis_status: str | None = None
    analysis_errors: tuple[str, ...] = ()
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    outcome: OperationOutcome = field(
        default_factory=lambda: OperationOutcome.success()
    )
    refreshed: bool = False
    refresh_error: str | None = None
    project: Project | None = None
    metadata: RepositoryCacheMetadata | None = None

    def __post_init__(self) -> None:
        if isinstance(self.state, str) and not isinstance(self.state, FreshnessState):
            object.__setattr__(self, "state", FreshnessState(self.state))
        if isinstance(self.analysis_errors, list):
            object.__setattr__(self, "analysis_errors", tuple(self.analysis_errors))
        if isinstance(self.diagnostics, list):
            object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if isinstance(self.limitations, list):
            object.__setattr__(self, "limitations", tuple(self.limitations))

    @property
    def is_current(self) -> bool:
        return self.state == FreshnessState.CURRENT

    @property
    def is_stale(self) -> bool:
        return self.state == FreshnessState.STALE

    @property
    def is_incomplete(self) -> bool:
        return self.state == FreshnessState.INCOMPLETE

    @property
    def is_indeterminate(self) -> bool:
        return self.state == FreshnessState.INDETERMINATE

    def to_dict(self) -> dict[str, Any]:
        changes_dict: dict[str, Any] | None = None
        if self.changes is not None:
            changes_dict = {
                "unchanged": sorted(p.as_posix() for p in self.changes.unchanged),
                "modified": sorted(p.as_posix() for p in self.changes.modified),
                "added": sorted(p.as_posix() for p in self.changes.added),
                "deleted": sorted(p.as_posix() for p in self.changes.deleted),
            }

        return {
            "state": self.state.value,
            "is_current": self.is_current,
            "reason": self.reason,
            "analysis_status": self.analysis_status,
            "analysis_errors": list(self.analysis_errors),
            "changes": changes_dict,
            "refreshed": self.refreshed,
            "refresh_error": self.refresh_error,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "limitations": list(self.limitations),
            "outcome": self.outcome.to_dict(),
        }


def _compute_current_fingerprints(root_path: Path) -> dict[Path, FileFingerprint]:
    scanned_project = RepositoryScanner(root_path).scan()
    fingerprints: dict[Path, FileFingerprint] = {}
    for file in scanned_project.files:
        abs_path = (root_path / file.path).resolve()
        if abs_path.is_file():
            fingerprints[file.path] = fingerprint_file(root_path, file.path)
    return fingerprints


class WorkflowFreshnessGuard:
    def __init__(
        self,
        root_path: Path | str,
        *,
        database_path: Path | None = None,
        repository: ProjectRepository | None = None,
        analyzer: ProjectAnalyzer | None = None,
    ) -> None:
        self.root_path = Path(root_path).resolve()
        self.database_path = database_path
        self.repository = repository
        self.analyzer = analyzer
        self._refresh_attempted = False

    def assess_freshness(
        self,
        *,
        project: Project | None = None,
        metadata: RepositoryCacheMetadata | None = None,
        cached_fingerprints: dict[Path, FileFingerprint] | None = None,
        current_fingerprints: dict[Path, FileFingerprint] | None = None,
    ) -> WorkflowFreshness:
        root = self.root_path
        db_path = self.database_path or (root / ".context_forge.db")
        identity = RepositoryIdentity(root)
        repo = self.repository or ProjectRepository(Database(db_path))

        loaded_project: Project | None = project
        loaded_metadata: RepositoryCacheMetadata | None = metadata

        if loaded_project is None or loaded_metadata is None:
            if self.repository is None and not db_path.exists():
                diag = DiagnosticItem.blocker(
                    "No persisted analysis found; run 'context-forge analyze' first",
                    code="MISSING_ANALYSIS",
                    source="storage",
                )
                return WorkflowFreshness(
                    state=FreshnessState.INDETERMINATE,
                    reason="missing_analysis",
                    project=loaded_project,
                    metadata=loaded_metadata,
                    diagnostics=(diag,),
                    limitations=(
                        "No persisted analysis found; freshness cannot be determined.",
                    ),
                    outcome=OperationOutcome.blocked(
                        "No persisted analysis found; run 'context-forge analyze' first",
                        diagnostics=(diag,),
                        limitations=(
                            "No persisted analysis found; freshness cannot be determined.",
                        ),
                    ),
                )

            try:
                if loaded_metadata is None:
                    loaded_metadata = repo.load_cache_metadata(identity.key)

                if loaded_project is None:
                    if loaded_metadata is not None:
                        loaded_project = repo.load(loaded_metadata.project_id)
                    else:
                        loaded = repo.load_analysis(identity.key)
                        if loaded is not None:
                            loaded_project, loaded_metadata = loaded
            except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
                if "no such table: repository_cache" in str(exc):
                    diag = DiagnosticItem.blocker(
                        "No persisted analysis found; run 'context-forge analyze' first",
                        code="MISSING_ANALYSIS",
                        source="storage",
                    )
                    return WorkflowFreshness(
                        state=FreshnessState.INDETERMINATE,
                        reason="missing_analysis",
                        project=loaded_project,
                        metadata=loaded_metadata,
                        diagnostics=(diag,),
                        limitations=(
                            "No persisted analysis found; freshness cannot be determined.",
                        ),
                        outcome=OperationOutcome.blocked(
                            "No persisted analysis found; run 'context-forge analyze' first",
                            diagnostics=(diag,),
                            limitations=(
                                "No persisted analysis found; freshness cannot be determined.",
                            ),
                        ),
                    )
                diag = DiagnosticItem.blocker(
                    f"Failed to load persisted analysis: {exc}",
                    code="INDETERMINATE_FRESHNESS",
                    source="storage",
                )
                return WorkflowFreshness(
                    state=FreshnessState.INDETERMINATE,
                    reason=f"unreadable_cache: {exc}",
                    project=loaded_project,
                    metadata=loaded_metadata,
                    diagnostics=(diag,),
                    limitations=(f"Persisted analysis could not be loaded: {exc}",),
                    outcome=OperationOutcome.blocked(
                        f"Failed to load persisted analysis: {exc}",
                        diagnostics=(diag,),
                        limitations=(f"Persisted analysis could not be loaded: {exc}",),
                    ),
                )

            if loaded_project is None or loaded_metadata is None:
                diag = DiagnosticItem.blocker(
                    "No persisted analysis found for repository",
                    code="MISSING_ANALYSIS",
                    source="storage",
                )
                return WorkflowFreshness(
                    state=FreshnessState.INDETERMINATE,
                    reason="missing_analysis",
                    project=loaded_project,
                    metadata=loaded_metadata,
                    diagnostics=(diag,),
                    limitations=("No persisted analysis found for repository.",),
                    outcome=OperationOutcome.blocked(
                        "No persisted analysis found for repository",
                        diagnostics=(diag,),
                        limitations=("No persisted analysis found for repository.",),
                    ),
                )

        if loaded_metadata.cache_schema_version != CACHE_SCHEMA_VERSION:
            diag = DiagnosticItem.blocker(
                f"Cache schema version mismatch (found {loaded_metadata.cache_schema_version}, "
                f"expected {CACHE_SCHEMA_VERSION})",
                code="SCHEMA_VERSION_MISMATCH",
                source="storage",
            )
            return WorkflowFreshness(
                state=FreshnessState.INDETERMINATE,
                reason="schema_version_mismatch",
                project=loaded_project,
                metadata=loaded_metadata,
                diagnostics=(diag,),
                limitations=("Cache schema version mismatch; reanalysis required.",),
                outcome=OperationOutcome.blocked(
                    "Cache schema version mismatch",
                    diagnostics=(diag,),
                    limitations=(
                        "Cache schema version mismatch; reanalysis required.",
                    ),
                ),
            )

        if loaded_metadata.analyzer_version != ANALYZER_VERSION:
            diag = DiagnosticItem.blocker(
                f"Analyzer version mismatch (found '{loaded_metadata.analyzer_version}', "
                f"expected '{ANALYZER_VERSION}')",
                code="ANALYZER_VERSION_MISMATCH",
                source="storage",
            )
            return WorkflowFreshness(
                state=FreshnessState.INDETERMINATE,
                reason="analyzer_version_mismatch",
                project=loaded_project,
                metadata=loaded_metadata,
                diagnostics=(diag,),
                limitations=("Analyzer version mismatch; reanalysis required.",),
                outcome=OperationOutcome.blocked(
                    "Analyzer version mismatch",
                    diagnostics=(diag,),
                    limitations=("Analyzer version mismatch; reanalysis required.",),
                ),
            )

        cf_map = cached_fingerprints
        if cf_map is None:
            try:
                cf_map = repo.load_file_fingerprints(identity.key)
            except (sqlite3.Error, OSError, ValueError) as exc:
                diag = DiagnosticItem.blocker(
                    f"Failed to load cached file fingerprints: {exc}",
                    code="INDETERMINATE_FRESHNESS",
                    source="storage",
                )
                return WorkflowFreshness(
                    state=FreshnessState.INDETERMINATE,
                    reason=f"fingerprint_load_error: {exc}",
                    project=loaded_project,
                    metadata=loaded_metadata,
                    diagnostics=(diag,),
                    limitations=(
                        f"Cached file fingerprints could not be loaded: {exc}",
                    ),
                    outcome=OperationOutcome.blocked(
                        f"Failed to load cached file fingerprints: {exc}",
                        diagnostics=(diag,),
                        limitations=(
                            f"Cached file fingerprints could not be loaded: {exc}",
                        ),
                    ),
                )

        if cf_map is None or (
            len(cf_map) == 0
            and loaded_project is not None
            and len(loaded_project.files) > 0
        ):
            diag = DiagnosticItem.blocker(
                "Cached file fingerprints missing from repository storage",
                code="MISSING_FINGERPRINTS",
                source="storage",
            )
            return WorkflowFreshness(
                state=FreshnessState.INDETERMINATE,
                reason="missing_fingerprints",
                project=loaded_project,
                metadata=loaded_metadata,
                diagnostics=(diag,),
                limitations=(
                    "Cached file fingerprints missing; freshness cannot be verified.",
                ),
                outcome=OperationOutcome.blocked(
                    "Cached file fingerprints missing",
                    diagnostics=(diag,),
                    limitations=(
                        "Cached file fingerprints missing; freshness cannot be verified.",
                    ),
                ),
            )

        cur_fingerprints = current_fingerprints
        if cur_fingerprints is None:
            try:
                cur_fingerprints = _compute_current_fingerprints(root)
            except (OSError, RuntimeError, ValueError) as exc:
                diag = DiagnosticItem.blocker(
                    f"Failed to scan working tree files on disk: {exc}",
                    code="INDETERMINATE_FRESHNESS",
                    source="filesystem",
                )
                return WorkflowFreshness(
                    state=FreshnessState.INDETERMINATE,
                    reason=f"filesystem_error: {exc}",
                    project=loaded_project,
                    metadata=loaded_metadata,
                    diagnostics=(diag,),
                    limitations=(f"Working tree scan failed: {exc}",),
                    outcome=OperationOutcome.blocked(
                        f"Failed to scan working tree: {exc}",
                        diagnostics=(diag,),
                        limitations=(f"Working tree scan failed: {exc}",),
                    ),
                )

        changes = detect_file_changes(cf_map, cur_fingerprints)
        has_file_changes = not changes.is_unchanged

        analysis_status = getattr(loaded_project, "analysis_status", "not_analyzed")
        raw_errors = getattr(loaded_project, "errors", [])
        analysis_errors = tuple(str(e) for e in raw_errors)
        is_incomplete = (
            analysis_status in ("failed", "not_analyzed", "partial", "analyzing")
            or len(analysis_errors) > 0
        )

        if has_file_changes:
            change_parts: list[str] = []
            if changes.modified:
                change_parts.append(f"{len(changes.modified)} modified")
            if changes.added:
                change_parts.append(f"{len(changes.added)} added")
            if changes.deleted:
                change_parts.append(f"{len(changes.deleted)} deleted")
            reason = f"files changed ({', '.join(change_parts)})"

            diag_list: list[DiagnosticItem] = [
                DiagnosticItem.warning(
                    f"Repository analysis is stale: {reason}",
                    code="STALE_ANALYSIS",
                    source="cache",
                    details={
                        "modified": sorted(p.as_posix() for p in changes.modified),
                        "added": sorted(p.as_posix() for p in changes.added),
                        "deleted": sorted(p.as_posix() for p in changes.deleted),
                    },
                )
            ]
            for err in analysis_errors:
                diag_list.append(
                    DiagnosticItem.error(err, code="ANALYSIS_ERROR", source="analyzer")
                )

            limitations = (
                f"Cached analysis is stale ({reason}); recent source changes are not reflected.",
            )
            return WorkflowFreshness(
                state=FreshnessState.STALE,
                reason=reason,
                changes=changes,
                analysis_status=analysis_status,
                analysis_errors=analysis_errors,
                diagnostics=tuple(diag_list),
                limitations=limitations,
                outcome=OperationOutcome.partial(
                    f"Repository analysis is stale: {reason}",
                    diagnostics=tuple(diag_list),
                    limitations=limitations,
                ),
                project=loaded_project,
                metadata=loaded_metadata,
            )

        if is_incomplete:
            if analysis_status == "failed":
                reason = "analysis_failed"
                msg = "Repository analysis failed and is incomplete"
            elif analysis_status in ("not_analyzed", "analyzing"):
                reason = f"analysis_status_{analysis_status}"
                msg = f"Repository analysis has status '{analysis_status}'"
            elif analysis_status == "partial":
                reason = "analysis_partial"
                msg = "Repository analysis was partially completed"
            else:
                reason = f"{len(analysis_errors)} analysis errors recorded"
                msg = f"Repository analysis contains {len(analysis_errors)} recorded errors"

            diag_list = [
                DiagnosticItem.error(
                    msg,
                    code="INCOMPLETE_ANALYSIS",
                    source="analyzer",
                    details={
                        "analysis_status": analysis_status,
                        "error_count": len(analysis_errors),
                    },
                )
            ]
            for err in analysis_errors:
                diag_list.append(
                    DiagnosticItem.error(err, code="ANALYSIS_ERROR", source="analyzer")
                )

            limitations = (
                f"Analysis is incomplete ({reason}); results may be missing symbols or relationships.",
            )
            return WorkflowFreshness(
                state=FreshnessState.INCOMPLETE,
                reason=reason,
                changes=changes,
                analysis_status=analysis_status,
                analysis_errors=analysis_errors,
                diagnostics=tuple(diag_list),
                limitations=limitations,
                outcome=OperationOutcome.incomplete(
                    msg,
                    diagnostics=tuple(diag_list),
                    limitations=limitations,
                ),
                project=loaded_project,
                metadata=loaded_metadata,
            )

        return WorkflowFreshness(
            state=FreshnessState.CURRENT,
            reason="fresh",
            changes=changes,
            analysis_status=analysis_status,
            analysis_errors=(),
            diagnostics=(),
            limitations=(),
            outcome=OperationOutcome.success("Repository analysis is current"),
            project=loaded_project,
            metadata=loaded_metadata,
        )

    def guard(self, *, allow_refresh: bool = False) -> WorkflowFreshness:
        assessment = self.assess_freshness()

        if assessment.is_current:
            return assessment

        if not allow_refresh:
            return assessment

        # Keep indeterminate states from triggering automatic refresh.
        if assessment.is_indeterminate:
            return assessment

        if self._refresh_attempted:
            return assessment

        self._refresh_attempted = True
        root = self.root_path
        db_path = self.database_path or (root / ".context_forge.db")

        try:
            analyzer = self.analyzer or ProjectAnalyzer(root, db_path)
            refreshed_project = analyzer.analyze()
        except (sqlite3.Error, OSError, RuntimeError, ValueError) as exc:
            fail_diag = DiagnosticItem.error(
                f"Refresh failed: {exc}",
                code="REFRESH_FAILED",
                source="analyzer",
            )
            diag_list = list(assessment.diagnostics) + [fail_diag]
            limitations = list(assessment.limitations) + [f"Refresh failed: {exc}"]
            return WorkflowFreshness(
                state=FreshnessState.INCOMPLETE
                if assessment.is_current
                else assessment.state,
                reason=f"refresh_failed: {exc}",
                changes=assessment.changes,
                analysis_status="failed",
                analysis_errors=assessment.analysis_errors + (str(exc),),
                diagnostics=tuple(diag_list),
                limitations=tuple(limitations),
                outcome=OperationOutcome.failed(
                    f"Refresh failed: {exc}",
                    diagnostics=tuple(diag_list),
                    limitations=tuple(limitations),
                ),
                refreshed=True,
                refresh_error=str(exc),
                project=assessment.project,
                metadata=assessment.metadata,
            )

        post_assessment = self.assess_freshness()
        return WorkflowFreshness(
            state=post_assessment.state,
            reason=post_assessment.reason,
            changes=post_assessment.changes,
            analysis_status=post_assessment.analysis_status,
            analysis_errors=post_assessment.analysis_errors,
            diagnostics=post_assessment.diagnostics,
            limitations=post_assessment.limitations,
            outcome=post_assessment.outcome,
            refreshed=True,
            refresh_error=None,
            project=post_assessment.project or refreshed_project,
            metadata=post_assessment.metadata,
        )
