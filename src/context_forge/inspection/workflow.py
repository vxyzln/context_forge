from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from context_forge.git.navigation import GitNavigationContext, map_changed_paths
from context_forge.git.repository import GitRepository
from context_forge.inspection.models import PreChangeInspectionResult
from context_forge.models.project import Project
from context_forge.pipeline.freshness import (
    FreshnessState,
    WorkflowFreshness,
    WorkflowFreshnessGuard,
)
from context_forge.preflight.readiness import build_preflight_report
from context_forge.query.impact import (
    DEFAULT_IMPACT_MAX_DEPTH,
    ImpactResult,
    TargetResolution,
    find_impact,
)
from context_forge.query.locator import (
    DEFAULT_EXCERPT_MAX_LINES,
    SourceExcerpt,
    get_source_evidence,
    locate_symbol,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
)
from context_forge.storage.cache import RepositoryCacheMetadata, RepositoryIdentity
from context_forge.storage.database import Database, project_database_path
from context_forge.storage.repository import ProjectRepository


def _deduplicate_diagnostics(
    items: list[DiagnosticItem],
) -> tuple[DiagnosticItem, ...]:
    seen: set[tuple[str, str | None, str, str | None, int | None]] = set()
    result: list[DiagnosticItem] = []
    for item in items:
        key = (
            item.severity.value,
            item.code,
            item.message,
            item.path,
            item.line,
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return tuple(result)


def _deduplicate_limitations(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for lim in items:
        s = lim.strip()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return tuple(result)


def inspect_pre_change(
    repository_path: str | Path = ".",
    target: str = "",
    *,
    file_path: str | Path | None = None,
    symbol_type: str | None = None,
    direction: str = "both",
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    max_excerpt_lines: int = DEFAULT_EXCERPT_MAX_LINES,
    include_git: bool = True,
    guard: WorkflowFreshnessGuard | None = None,
    git_repository: Any | None = None,
    project: Project | None = None,
    metadata: RepositoryCacheMetadata | None = None,
    preflight_report: dict[str, Any] | None = None,
) -> PreChangeInspectionResult:
    all_diagnostics: list[DiagnosticItem] = []
    all_limitations: list[str] = []

    repo_path = Path(repository_path).expanduser()
    if repo_path.exists():
        repo_path = repo_path.resolve()
    norm_repo_str = str(repo_path).replace("\\", "/")

    query_str = target.strip() if isinstance(target, str) else str(target)
    is_query_empty = not bool(query_str)

    if preflight_report is None:
        preflight_report = build_preflight_report(repo_path)

    preflight_diags_raw = preflight_report.get("diagnostics") or preflight_report.get(
        "outcome", {}
    ).get("diagnostics", [])
    for d in preflight_diags_raw:
        all_diagnostics.append(
            DiagnosticItem(
                severity=DiagnosticSeverity(d["severity"]),
                message=d["message"],
                code=d.get("code"),
                path=d.get("path"),
                line=d.get("line"),
                source=d.get("source"),
            )
        )
    preflight_lims_raw = preflight_report.get("limitations") or preflight_report.get(
        "outcome", {}
    ).get("limitations", [])
    all_limitations.extend(preflight_lims_raw)

    is_preflight_blocked = (
        preflight_report.get("readiness") == "blocked"
        or not repo_path.exists()
        or not repo_path.is_dir()
    )

    if is_preflight_blocked:
        outcome = OperationOutcome.blocked(
            preflight_report.get("outcome", {}).get(
                "message", "Repository preflight check blocked inspection"
            ),
            diagnostics=_deduplicate_diagnostics(all_diagnostics),
            limitations=_deduplicate_limitations(all_limitations),
        )
        return PreChangeInspectionResult(
            repository_path=norm_repo_str,
            target_query=query_str,
            readiness=preflight_report,
            outcome=outcome,
            limitations=_deduplicate_limitations(all_limitations),
            diagnostics=_deduplicate_diagnostics(all_diagnostics),
        )

    db_path = project_database_path(repo_path)
    has_db_file = db_path.exists()
    freshness_guard = guard or WorkflowFreshnessGuard(repo_path, database_path=db_path)

    loaded_project = project
    loaded_metadata = metadata
    freshness: WorkflowFreshness | None = None

    if loaded_project is None and not has_db_file:
        freshness = freshness_guard.assess_freshness()
        all_diagnostics.extend(freshness.diagnostics)
        all_limitations.extend(freshness.limitations)

        git_ctx: GitNavigationContext | None = None
        if include_git:
            try:
                repo = git_repository or GitRepository(repo_path)
                git_status = repo.get_status()
                empty_proj = Project(
                    name=repo_path.name,
                    root_path=repo_path,
                    analysis_status="not_analyzed",
                )
                git_ctx = map_changed_paths(empty_proj, git_status)
                if git_ctx.is_git_repository:
                    all_diagnostics.extend(git_ctx.diagnostics)
                all_limitations.extend(git_ctx.limitations)
            except (
                subprocess.SubprocessError,
                OSError,
                ValueError,
                RuntimeError,
            ) as exc:
                git_diag = DiagnosticItem.warning(
                    f"Git status inspection failed: {exc}",
                    code="GIT_INSPECTION_FAILED",
                    source="git",
                )
                all_diagnostics.append(git_diag)

        target_res = (
            TargetResolution(
                status="invalid",
                message="Target query cannot be empty",
            )
            if is_query_empty
            else TargetResolution(
                status="not_found",
                message="Repository has not been analyzed; no symbol metadata available",
            )
        )
        if is_query_empty:
            all_diagnostics.append(
                DiagnosticItem.blocker(
                    "Target query cannot be empty",
                    code="TARGET_INVALID",
                    source="inspection",
                )
            )

        outcome = OperationOutcome.blocked(
            freshness.outcome.message
            or "Repository has not been analyzed; run 'context-forge analyze' first",
            diagnostics=_deduplicate_diagnostics(all_diagnostics),
            limitations=_deduplicate_limitations(all_limitations),
        )
        return PreChangeInspectionResult(
            repository_path=norm_repo_str,
            target_query=query_str,
            readiness=preflight_report,
            target_resolution=target_res,
            freshness=freshness,
            git_context=git_ctx,
            outcome=outcome,
            limitations=_deduplicate_limitations(all_limitations),
            diagnostics=_deduplicate_diagnostics(all_diagnostics),
        )

    try:
        freshness = freshness_guard.assess_freshness(
            project=loaded_project, metadata=loaded_metadata
        )
        all_diagnostics.extend(freshness.diagnostics)
        all_limitations.extend(freshness.limitations)

        if loaded_project is None:
            loaded_project = freshness.project
            loaded_metadata = freshness.metadata

        if loaded_project is None and has_db_file:
            db = Database(db_path)
            repo = ProjectRepository(db)
            identity = RepositoryIdentity(repo_path)
            loaded = repo.load_analysis(identity.key)
            if loaded is not None:
                loaded_project, loaded_metadata = loaded
    except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
        diag = DiagnosticItem.error(
            f"Failed to read repository analysis: {exc}",
            code="STORAGE_READ_ERROR",
            source="storage",
        )
        all_diagnostics.append(diag)
        all_limitations.append(f"Storage read error: {exc}")

    if loaded_project is None:
        target_res = (
            TargetResolution(
                status="invalid",
                message="Target query cannot be empty",
            )
            if is_query_empty
            else TargetResolution(
                status="not_found",
                message="Failed to load repository project analysis",
            )
        )
        outcome = OperationOutcome.failed(
            "Failed to load repository analysis",
            diagnostics=_deduplicate_diagnostics(all_diagnostics),
            limitations=_deduplicate_limitations(all_limitations),
        )
        return PreChangeInspectionResult(
            repository_path=norm_repo_str,
            target_query=query_str,
            readiness=preflight_report,
            target_resolution=target_res,
            freshness=freshness,
            outcome=outcome,
            limitations=_deduplicate_limitations(all_limitations),
            diagnostics=_deduplicate_diagnostics(all_diagnostics),
        )

    target_res: TargetResolution
    if is_query_empty:
        target_res = TargetResolution(
            status="invalid",
            message="Target query cannot be empty",
        )
        all_diagnostics.append(
            DiagnosticItem.blocker(
                "Target query cannot be empty",
                code="TARGET_INVALID",
                source="inspection",
            )
        )
    else:
        try:
            target_res = locate_symbol(
                loaded_project,
                query_str,
                file_path=file_path,
                symbol_type=symbol_type,
            )
            all_diagnostics.extend(target_res.outcome.diagnostics)
            all_limitations.extend(target_res.outcome.limitations)
        except (
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            target_res = TargetResolution(
                status="invalid",
                message=f"Target resolution error: {exc}",
            )
            all_diagnostics.append(
                DiagnosticItem.error(
                    f"Target resolution failed: {exc}",
                    code="TARGET_RESOLUTION_ERROR",
                    source="inspection",
                )
            )

    source_ev: SourceExcerpt | None = None
    structural_ev: ImpactResult | None = None

    if target_res.is_resolved and target_res.target is not None:
        try:
            source_ev = get_source_evidence(
                loaded_project,
                target_res.target,
                root_path=repo_path,
                max_lines=max_excerpt_lines,
            )
            all_diagnostics.extend(source_ev.outcome.diagnostics)
            all_limitations.extend(source_ev.limitations)
        except (
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            source_ev = SourceExcerpt(
                target_id=target_res.target.id,
                target_name=target_res.target.name,
                path=target_res.target.path,
                start_line=target_res.target.start_line or 0,
                end_line=target_res.target.end_line or 0,
                content="",
                total_lines=0,
                status="unreadable_file",
                message=f"Failed to read source file: {exc}",
            )
            all_diagnostics.append(
                DiagnosticItem.warning(
                    f"Failed to read source evidence: {exc}",
                    code="SOURCE_READ_ERROR",
                    source="evidence",
                )
            )

        try:
            target_entity = (
                next(
                    (s for s in loaded_project.symbols if s.id == target_res.target.id),
                    None,
                )
                or next(
                    (f for f in loaded_project.files if f.id == target_res.target.id),
                    None,
                )
                or target_res.target.qualified_name
                or target_res.target.name
            )
            structural_ev = find_impact(
                loaded_project,
                target_entity,
                direction=direction,
                max_depth=max_depth,
            )
            all_diagnostics.extend(structural_ev.outcome.diagnostics)
            all_limitations.extend(structural_ev.limitations)
        except (
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            all_diagnostics.append(
                DiagnosticItem.warning(
                    f"Structural impact analysis failed: {exc}",
                    code="IMPACT_ANALYSIS_FAILED",
                    source="impact",
                )
            )

    git_ctx: GitNavigationContext | None = None
    if include_git:
        try:
            repo = git_repository or GitRepository(repo_path)
            git_status = repo.get_status()
            git_ctx = map_changed_paths(loaded_project, git_status)
            if git_ctx.is_git_repository:
                all_diagnostics.extend(git_ctx.diagnostics)
            all_limitations.extend(git_ctx.limitations)
        except (
            subprocess.SubprocessError,
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            git_diag = DiagnosticItem.warning(
                f"Git inspection failed: {exc}",
                code="GIT_INSPECTION_FAILED",
                source="git",
            )
            all_diagnostics.append(git_diag)
            all_limitations.append(f"Git inspection unavailable: {exc}")

    outcome = _resolve_inspection_outcome(
        target_resolution=target_res,
        freshness=freshness,
        source_evidence=source_ev,
        structural_evidence=structural_ev,
        git_context=git_ctx,
        diagnostics=all_diagnostics,
        limitations=all_limitations,
    )

    return PreChangeInspectionResult(
        repository_path=norm_repo_str,
        target_query=query_str,
        readiness=preflight_report,
        target_resolution=target_res,
        freshness=freshness,
        source_evidence=source_ev,
        structural_evidence=structural_ev,
        git_context=git_ctx,
        outcome=outcome,
        limitations=_deduplicate_limitations(all_limitations),
        diagnostics=_deduplicate_diagnostics(all_diagnostics),
    )


def _resolve_inspection_outcome(
    *,
    target_resolution: TargetResolution,
    freshness: WorkflowFreshness | None,
    source_evidence: SourceExcerpt | None,
    structural_evidence: ImpactResult | None,
    git_context: GitNavigationContext | None,
    diagnostics: list[DiagnosticItem],
    limitations: list[str],
) -> OperationOutcome:
    dedup_diags = _deduplicate_diagnostics(diagnostics)
    dedup_lims = _deduplicate_limitations(limitations)

    has_operational_errors = any(
        d.severity == DiagnosticSeverity.ERROR
        and d.code not in ("INCOMPLETE_ANALYSIS", "ANALYSIS_ERROR")
        for d in dedup_diags
    )
    if has_operational_errors:
        return OperationOutcome.failed(
            "Inspection failed with operational errors",
            diagnostics=dedup_diags,
            limitations=dedup_lims,
        )

    if freshness is not None and freshness.state == FreshnessState.INCOMPLETE:
        return OperationOutcome.incomplete(
            f"Pre-change inspection incomplete: {freshness.reason}",
            diagnostics=dedup_diags,
            limitations=dedup_lims,
        )

    if target_resolution.is_not_found:
        return OperationOutcome.blocked(
            target_resolution.message or "Target symbol not found in repository",
            diagnostics=dedup_diags,
            limitations=dedup_lims,
        )

    if target_resolution.is_invalid:
        return OperationOutcome.blocked(
            target_resolution.message or "Invalid target query",
            diagnostics=dedup_diags,
            limitations=dedup_lims,
        )

    if freshness is not None and freshness.state == FreshnessState.INDETERMINATE:
        return OperationOutcome.blocked(
            freshness.outcome.message or "Repository analysis is indeterminate",
            diagnostics=dedup_diags,
            limitations=dedup_lims,
        )

    is_partial = False
    partial_reasons: list[str] = []

    if target_resolution.is_ambiguous:
        is_partial = True
        partial_reasons.append("ambiguous target")

    if freshness is not None and freshness.state == FreshnessState.STALE:
        is_partial = True
        partial_reasons.append("stale analysis")

    if source_evidence is not None:
        if not source_evidence.is_success:
            is_partial = True
            partial_reasons.append(f"source {source_evidence.status}")
        elif source_evidence.status == "stale_location":
            is_partial = True
            partial_reasons.append("stale source location")

    if (
        git_context is not None
        and git_context.is_git_repository
        and (
            git_context.outcome.is_partial
            or git_context.outcome.is_failed
            or git_context.outcome.is_blocked
        )
    ):
        is_partial = True
        partial_reasons.append("git context limitations")

    if any(d.code == "GIT_INSPECTION_FAILED" for d in dedup_diags):
        is_partial = True
        partial_reasons.append("git inspection failed")

    if any(d.code == "IMPACT_ANALYSIS_FAILED" for d in dedup_diags):
        is_partial = True
        partial_reasons.append("impact analysis failed")

    if is_partial:
        reason_str = ", ".join(partial_reasons)
        return OperationOutcome.partial(
            f"Pre-change inspection completed with partial evidence ({reason_str})",
            diagnostics=dedup_diags,
            limitations=dedup_lims,
        )

    return OperationOutcome.success(
        "Pre-change inspection completed successfully",
        diagnostics=dedup_diags,
        limitations=dedup_lims,
    )


def format_pre_change_inspection_summary(
    result: PreChangeInspectionResult,
) -> list[str]:
    lines: list[str] = []

    lines.append(f"Repository: {result.repository_path}")
    lines.append(f"Target query: {result.target_query}")
    lines.append("")

    readiness_status = result.readiness.get("readiness", "unknown").upper()
    lines.append(f"Readiness: {readiness_status}")
    repo_status = result.readiness.get("repository_status", {})
    if repo_status:
        is_git = repo_status.get("is_git_repository", False)
        lines.append(
            f"  Git repository: {'yes' if is_git else 'no'} | Accessible: {'yes' if repo_status.get('is_accessible') else 'no'}"
        )
    lines.append("")

    lines.append("Target Resolution:")
    if result.target_resolution is None:
        lines.append("  Not evaluated.")
    elif result.target_resolution.is_resolved and result.target_resolution.target:
        t = result.target_resolution.target
        sig = f" | Signature: {t.signature}" if t.signature else ""
        qual = f" ({t.qualified_name})" if t.qualified_name else ""
        lines.append(f"  Target: [{t.kind}] {t.name}{qual}")
        lines.append(f"  Location: {t.path}:{t.start_line}-{t.end_line}{sig}")
    elif result.target_resolution.is_ambiguous:
        lines.append(
            f"  Ambiguous: {len(result.target_resolution.candidates)} candidate(s) found"
        )
        for c in result.target_resolution.candidates:
            qual = f" ({c.qualified_name})" if c.qualified_name else ""
            lines.append(
                f"    - [{c.kind}] {c.name}{qual} in {c.path}:{c.start_line}-{c.end_line}"
            )
    elif result.target_resolution.is_not_found:
        lines.append(f"  Not found: {result.target_resolution.message}")
    else:
        lines.append(f"  Invalid: {result.target_resolution.message}")
    lines.append("")

    lines.append("Freshness:")
    if result.freshness is None:
        lines.append("  Not evaluated.")
    else:
        lines.append(
            f"  State: {result.freshness.state.value.upper()} (reason: {result.freshness.reason})"
        )
        if result.freshness.changes is not None:
            c = result.freshness.changes
            lines.append(
                f"  Changes: {len(c.modified)} modified, {len(c.added)} added, {len(c.deleted)} deleted, {len(c.unchanged)} unchanged"
            )
    lines.append("")

    lines.append("Source Evidence:")
    if result.source_evidence is None:
        lines.append("  None available.")
    elif result.source_evidence.is_success:
        ev = result.source_evidence
        lines.append(
            f"  Excerpt: {ev.path}:{ev.start_line}-{ev.end_line} ({ev.total_lines} lines)"
        )
        for content_line in ev.content.splitlines():
            lines.append(f"    {content_line}")
        if ev.is_truncated:
            lines.append(f"    [Truncated: showing {ev.total_lines} lines]")
        if ev.status == "stale_location":
            lines.append(f"    Warning: {ev.message}")
    else:
        lines.append(f"  Unavailable: {result.source_evidence.message}")
    lines.append("")

    lines.append("Structural Evidence:")
    if result.structural_evidence is None:
        lines.append("  None evaluated.")
    else:
        st = result.structural_evidence
        lines.append(
            f"  Components: {st.total} ({st.direct_count} direct, {st.indirect_count} indirect) | Depth: {st.max_depth}"
        )
        if st.items:
            for item in st.items[:10]:
                loc = f" ({item.related_path})" if item.related_path else ""
                lines.append(
                    f"    [{item.classification}] {item.direction} {item.relationship_type}: {item.related_name} [{item.related_kind}]{loc}"
                )
            if len(st.items) > 10:
                lines.append(f"    ... showing 10 of {len(st.items)} components")
    lines.append("")

    lines.append("Git Context:")
    if result.git_context is None:
        lines.append("  Not evaluated.")
    elif not result.git_context.is_git_repository:
        lines.append("  Not a Git repository.")
    elif result.git_context.is_clean:
        lines.append("  Working tree is clean; no uncommitted changes.")
    else:
        lines.append(f"  Changed paths: {len(result.git_context.mappings)}")
        for m in result.git_context.mappings:
            mapped_label = (
                f" -> {m.matched_entity.name} [{m.matched_entity.entity_type}]"
                if m.matched_entity
                else f" -> {m.status.value}"
            )
            lines.append(f"    {m.git_path}{mapped_label}")
    lines.append("")

    if result.limitations:
        lines.append("Limitations:")
        for lim in result.limitations:
            lines.append(f"  - {lim}")
        lines.append("")

    if result.diagnostics:
        actionable = [d for d in result.diagnostics if d.severity.is_actionable]
        if actionable:
            lines.append("Diagnostics:")
            for d in actionable:
                loc = f" ({d.path}:{d.line})" if d.path and d.line else ""
                lines.append(f"  - [{d.severity.value.upper()}] {d.message}{loc}")
            lines.append("")

    lines.append(f"Overall Status: {result.outcome.status.value.upper()}")
    if result.outcome.message:
        lines.append(f"Message: {result.outcome.message}")

    return lines
