from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from context_forge.comparison.models import (
    StructuralComparisonResult,
    is_terminal_complete_status,
)
from context_forge.comparison.service import compare_states
from context_forge.config.project import PackageBoundaryPolicy, StructuralRule
from context_forge.models.project import Project
from context_forge.pipeline.freshness import (
    FreshnessState,
    WorkflowFreshness,
    WorkflowFreshnessGuard,
)
from context_forge.query.changeset import (
    ChangeSetImpactResult,
    ChangeSetInputResolution,
    analyze_changeset,
)
from context_forge.query.impact import (
    DEFAULT_IMPACT_MAX_DEPTH,
)
from context_forge.query.package_boundary import (
    DEFAULT_REPORT_LIMIT,
    PackageBoundaryReport,
    analyze_package_boundaries,
)
from context_forge.query.regression_rules import (
    StructuralRulesReport,
    evaluate_structural_rules,
)
from context_forge.query.risk import (
    ChangeRiskReport,
    generate_change_risk_report,
)
from context_forge.query.verification import (
    VerificationChecklist,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)


class CheckExecutionStatus(str, Enum):
    SUGGESTED = "suggested"
    AVAILABLE_UNRUN = "available_unrun"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class VerificationCheckRecord:
    check_id: str
    category: str
    action: str
    target: str | None = None
    command: str | None = None
    status: str = CheckExecutionStatus.SUGGESTED.value
    executed: bool = False
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "category": self.category,
            "check_id": self.check_id,
            "command": self.command,
            "evidence": list(self.evidence),
            "executed": self.executed,
            "status": self.status,
            "target": self.target,
        }


@dataclass(frozen=True)
class PostChangeSummary:
    changed_files_count: int
    directly_affected_count: int
    downstream_affected_count: int
    associated_tests_count: int
    suggested_checks_count: int
    rule_violations_count: int
    rule_unevaluable_count: int
    package_violations_count: int
    risk_concerns_count: int
    incomplete_operations_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "associated_tests_count": self.associated_tests_count,
            "changed_files_count": self.changed_files_count,
            "directly_affected_count": self.directly_affected_count,
            "downstream_affected_count": self.downstream_affected_count,
            "incomplete_operations_count": self.incomplete_operations_count,
            "package_violations_count": self.package_violations_count,
            "risk_concerns_count": self.risk_concerns_count,
            "rule_unevaluable_count": self.rule_unevaluable_count,
            "rule_violations_count": self.rule_violations_count,
            "suggested_checks_count": self.suggested_checks_count,
        }


@dataclass(frozen=True)
class PostChangeVerificationReport:
    repository_path: str
    change_set: tuple[str, ...]
    resolved_inputs: tuple[ChangeSetInputResolution, ...]
    freshness_state: str
    refreshed: bool
    comparison_performed: bool
    comparison_status: str
    structural_comparison: StructuralComparisonResult | None = None
    changeset_impact: ChangeSetImpactResult | None = None
    verification_checklist: VerificationChecklist | None = None
    suggested_checks: tuple[VerificationCheckRecord, ...] = ()
    change_risk: ChangeRiskReport | None = None
    package_boundaries: PackageBoundaryReport | None = None
    regression_rules: StructuralRulesReport | None = None
    summary: PostChangeSummary | None = None
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    outcome: OperationOutcome = field(default_factory=OperationOutcome.success)

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_risk": (
                self.change_risk.to_dict() if self.change_risk is not None else None
            ),
            "change_set": list(self.change_set),
            "changeset_impact": (
                self.changeset_impact.to_dict()
                if self.changeset_impact is not None
                else None
            ),
            "comparison_performed": self.comparison_performed,
            "comparison_status": self.comparison_status,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "freshness_state": self.freshness_state,
            "limitations": list(self.limitations),
            "outcome": self.outcome.to_dict(),
            "package_boundaries": (
                self.package_boundaries.to_dict()
                if self.package_boundaries is not None
                else None
            ),
            "refreshed": self.refreshed,
            "regression_rules": (
                self.regression_rules.to_dict()
                if self.regression_rules is not None
                else None
            ),
            "repository_path": self.repository_path,
            "resolved_inputs": [r.to_dict() for r in self.resolved_inputs],
            "structural_comparison": (
                self.structural_comparison.to_dict()
                if self.structural_comparison is not None
                else None
            ),
            "suggested_checks": [c.to_dict() for c in self.suggested_checks],
            "summary": self.summary.to_dict() if self.summary is not None else None,
            "verification_checklist": (
                self.verification_checklist.to_dict()
                if self.verification_checklist is not None
                else None
            ),
        }


def _discover_changed_paths_from_git(root: Path) -> list[str]:
    try:
        from context_forge.git.repository import GitRepository

        repo = GitRepository(root)
        if not repo.is_git_repository():
            return []
        status = repo.get_status()
        changed: list[str] = []
        for entry in status.entries:
            if entry.path and entry.path not in changed:
                changed.append(entry.path)
        return changed
    except (OSError, RuntimeError, ValueError, KeyError):
        return []


def run_post_change_verification(
    project: Project,
    paths: Sequence[str | Path] | None = None,
    *,
    before_state: Any | None = None,
    rules: Sequence[StructuralRule | dict[str, Any]] | None = None,
    package_policy: PackageBoundaryPolicy | None = None,
    allow_refresh: bool = True,
    limit: int = DEFAULT_REPORT_LIMIT,
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    freshness: WorkflowFreshness | None = None,
    guard: WorkflowFreshnessGuard | None = None,
) -> PostChangeVerificationReport:
    root_path = project.root_path or Path(".")
    repo_path = root_path.as_posix()

    workflow_diagnostics: list[DiagnosticItem] = []
    workflow_limitations: list[str] = []
    incomplete_operations = 0

    freshness_state_str = "current"
    refreshed = False
    freshness_guard = guard or WorkflowFreshnessGuard(root_path)

    if freshness is None:
        try:
            assessment = freshness_guard.assess_freshness(project=project)
            if assessment.is_stale and allow_refresh:
                freshness = freshness_guard.guard(
                    allow_refresh=True,
                    project=project,
                )
            else:
                freshness = assessment
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            workflow_diagnostics.append(
                DiagnosticItem.warning(
                    f"Freshness assessment failed: {e}",
                    code="FRESHNESS_CHECK_FAILED",
                    source="post_change",
                )
            )

    if freshness is not None:
        freshness_state_str = (
            freshness.state.value
            if isinstance(freshness.state, FreshnessState)
            else str(freshness.state)
        )
        refreshed = bool(freshness.refreshed)
        workflow_diagnostics.extend(freshness.diagnostics)
        workflow_limitations.extend(freshness.limitations)

        if refreshed and freshness.project is not None:
            project = freshness.project

        if freshness.refresh_error:
            workflow_limitations.append(
                f"Repository refresh issue: {freshness.refresh_error}"
            )

        if freshness.is_stale and not refreshed:
            workflow_limitations.append(
                "Repository analysis is stale and refresh was not performed"
            )
            workflow_diagnostics.append(
                DiagnosticItem.warning(
                    "Repository analysis is stale; rerun with refresh enabled for current results",
                    code="STALE_REPOSITORY",
                    source="post_change",
                )
            )

        if freshness.state == FreshnessState.INCOMPLETE:
            incomplete_operations += 1
            workflow_limitations.append("Repository freshness status is incomplete")
        elif freshness.state == FreshnessState.INDETERMINATE:
            workflow_limitations.append("Repository freshness status is indeterminate")

    change_paths: list[str] = []
    if paths:
        change_paths = [str(p) for p in paths]
    else:
        git_discovered = _discover_changed_paths_from_git(root_path)
        if git_discovered:
            change_paths = git_discovered
        else:
            workflow_limitations.append(
                "No changed paths supplied or detected from Git repository"
            )
            workflow_diagnostics.append(
                DiagnosticItem.info(
                    "No changed paths supplied or detected; changeset impact skipped",
                    code="NO_CHANGED_PATHS",
                    source="post_change",
                )
            )

    comparison_performed = False
    comparison_status = "not_performed"
    structural_comparison: StructuralComparisonResult | None = None

    if before_state is not None:
        comparison_performed = True
        try:
            structural_comparison = compare_states(before_state, project)
            if (
                structural_comparison.outcome.is_success
                or structural_comparison.outcome.is_partial
            ):
                comparison_status = "completed"
            elif structural_comparison.outcome.is_incomplete:
                comparison_status = "incomplete"
                incomplete_operations += 1
            elif structural_comparison.outcome.is_blocked:
                comparison_status = "blocked"
            else:
                comparison_status = "failed"
            workflow_diagnostics.extend(structural_comparison.diagnostics)
            workflow_limitations.extend(structural_comparison.limitations)
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            comparison_status = "failed"
            diag = DiagnosticItem.error(
                f"Structural comparison failed: {e}",
                code="COMPARISON_FAILED",
                source="post_change",
            )
            workflow_diagnostics.append(diag)
            workflow_limitations.append(
                "Structural comparison failed with an exception"
            )
    else:
        comparison_performed = False
        comparison_status = "not_performed"
        workflow_limitations.append(
            "Before-state was not provided; structural comparison between versions was not performed"
        )
        workflow_diagnostics.append(
            DiagnosticItem.info(
                "Before-state was not provided; structural comparison between versions was not performed",
                code="COMPARISON_NOT_PERFORMED",
                source="post_change",
            )
        )

    changeset_impact: ChangeSetImpactResult | None = None
    verification_checklist: VerificationChecklist | None = None
    resolved_inputs: tuple[ChangeSetInputResolution, ...] = ()

    if change_paths:
        try:
            changeset_impact = analyze_changeset(
                project,
                change_paths,
                include_checklist=True,
                limit=limit,
                max_depth=max_depth,
                direction=direction,
                relationship_types=relationship_types,
            )
            resolved_inputs = changeset_impact.resolved_inputs
            verification_checklist = changeset_impact.verification_checklist
            workflow_diagnostics.extend(changeset_impact.diagnostics)
            workflow_limitations.extend(changeset_impact.limitations)
            if changeset_impact.outcome.is_incomplete:
                incomplete_operations += 1
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            diag = DiagnosticItem.error(
                f"Changeset impact analysis failed: {e}",
                code="CHANGESET_FAILED",
                source="post_change",
            )
            workflow_diagnostics.append(diag)
            workflow_limitations.append(
                "Changeset impact analysis failed with an exception"
            )

    suggested_checks: list[VerificationCheckRecord] = []

    if verification_checklist and verification_checklist.items:
        for idx, item in enumerate(verification_checklist.items):
            target_str = item.test_file_path or (
                item.target_entities[0] if item.target_entities else None
            )
            check_rec = VerificationCheckRecord(
                check_id=item.item_id or f"check_{idx + 1}",
                category=item.category,
                action=item.action,
                target=target_str,
                command=item.suggested_command,
                status=CheckExecutionStatus.SUGGESTED.value,
                executed=False,
                evidence=item.supporting_evidence,
            )
            suggested_checks.append(check_rec)

    change_risk: ChangeRiskReport | None = None
    if change_paths:
        try:
            change_risk = generate_change_risk_report(
                project,
                change_paths,
                comparison=structural_comparison,
                direction=direction,
                relationship_types=relationship_types,
                max_depth=max_depth,
                limit=limit,
                policy=package_policy,
            )
            workflow_diagnostics.extend(change_risk.diagnostics)
            workflow_limitations.extend(change_risk.limitations)
            if change_risk.outcome.is_incomplete:
                incomplete_operations += 1
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            diag = DiagnosticItem.error(
                f"Change risk analysis failed: {e}",
                code="CHANGE_RISK_FAILED",
                source="post_change",
            )
            workflow_diagnostics.append(diag)
            workflow_limitations.append("Change risk analysis failed with an exception")

    package_boundaries: PackageBoundaryReport | None = None
    try:
        package_boundaries = analyze_package_boundaries(
            project,
            policy=package_policy,
            limit=limit,
            relationship_types=relationship_types,
        )
        workflow_diagnostics.extend(package_boundaries.diagnostics)
        workflow_limitations.extend(package_boundaries.limitations)
        if package_boundaries.outcome.is_incomplete:
            incomplete_operations += 1
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        AttributeError,
        TypeError,
    ) as e:
        diag = DiagnosticItem.error(
            f"Package boundary analysis failed: {e}",
            code="PACKAGE_BOUNDARY_FAILED",
            source="post_change",
        )
        workflow_diagnostics.append(diag)
        workflow_limitations.append(
            "Package boundary analysis failed with an exception"
        )

    regression_rules: StructuralRulesReport | None = None
    if rules:
        try:
            regression_rules = evaluate_structural_rules(
                project,
                rules,
                limit=limit,
                package_policy=package_policy,
            )
            workflow_diagnostics.extend(regression_rules.diagnostics)
            workflow_limitations.extend(regression_rules.limitations)
            if regression_rules.outcome.is_incomplete:
                incomplete_operations += 1
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
        ) as e:
            diag = DiagnosticItem.error(
                f"Structural rule evaluation failed: {e}",
                code="RULES_EVALUATION_FAILED",
                source="post_change",
            )
            workflow_diagnostics.append(diag)
            workflow_limitations.append(
                "Structural rule evaluation failed with an exception"
            )

    direct_count = changeset_impact.direct_count if changeset_impact else 0
    downstream_count = changeset_impact.downstream_count if changeset_impact else 0
    associated_tests = (
        len(verification_checklist.items) if verification_checklist else 0
    )
    rule_violations = regression_rules.violations_count if regression_rules else 0
    rule_unevaluable = regression_rules.unevaluable_count if regression_rules else 0
    pkg_violations = (
        len(package_boundaries.policy_violations) if package_boundaries else 0
    )
    risk_concerns = len(change_risk.inferred_concerns) if change_risk else 0

    summary = PostChangeSummary(
        changed_files_count=len(change_paths),
        directly_affected_count=direct_count,
        downstream_affected_count=downstream_count,
        associated_tests_count=associated_tests,
        suggested_checks_count=len(suggested_checks),
        rule_violations_count=rule_violations,
        rule_unevaluable_count=rule_unevaluable,
        package_violations_count=pkg_violations,
        risk_concerns_count=risk_concerns,
        incomplete_operations_count=incomplete_operations,
    )

    has_blockers = any(
        d.severity == DiagnosticSeverity.BLOCKER for d in workflow_diagnostics
    )
    has_fatal_errors = any(
        d.severity == DiagnosticSeverity.ERROR
        and d.code
        in {
            "CHANGESET_FAILED",
            "CHANGE_RISK_FAILED",
            "PACKAGE_BOUNDARY_FAILED",
            "RULES_EVALUATION_FAILED",
            "COMPARISON_FAILED",
        }
        for d in workflow_diagnostics
    )

    comparison_blocked = before_state is not None and (
        comparison_status == "blocked"
        or (
            structural_comparison is not None
            and structural_comparison.outcome.is_blocked
        )
    )
    comparison_failed = before_state is not None and (
        comparison_status == "failed"
        or (
            structural_comparison is not None
            and structural_comparison.outcome.is_failed
        )
    )
    comparison_incomplete = before_state is not None and (
        comparison_status == "incomplete"
        or (
            structural_comparison is not None
            and structural_comparison.outcome.is_incomplete
        )
    )

    if has_blockers or comparison_blocked:
        overall_status = OperationStatus.BLOCKED
        overall_msg = (
            "Post-change verification blocked by structural comparison blocker or "
            "fatal diagnostics"
        )
    elif has_fatal_errors or comparison_failed:
        overall_status = OperationStatus.FAILED
        overall_msg = (
            "Post-change verification failed: required stage or comparison failed"
        )
    elif (
        incomplete_operations > 0
        or comparison_incomplete
        or not is_terminal_complete_status(project.analysis_status)
    ):
        overall_status = OperationStatus.INCOMPLETE
        overall_msg = (
            f"Post-change verification completed with incomplete operations "
            f"({incomplete_operations} incomplete stage(s))"
        )
    elif rule_violations > 0 or pkg_violations > 0 or risk_concerns > 0:
        overall_status = OperationStatus.PARTIAL
        findings: list[str] = []
        if rule_violations > 0:
            findings.append(f"{rule_violations} rule violation(s)")
        if pkg_violations > 0:
            findings.append(f"{pkg_violations} package policy violation(s)")
        if risk_concerns > 0:
            findings.append(f"{risk_concerns} risk concern(s)")
        overall_msg = (
            f"Post-change verification detected findings: {', '.join(findings)}"
        )
    else:
        overall_status = OperationStatus.SUCCESS
        overall_msg = "Post-change verification completed cleanly"

    seen_diag: set[tuple[str, str, str | None]] = set()
    dedup_diagnostics: list[DiagnosticItem] = []
    for d in workflow_diagnostics:
        key = (d.severity.value, d.message, d.code)
        if key not in seen_diag:
            seen_diag.add(key)
            dedup_diagnostics.append(d)

    outcome = OperationOutcome(
        status=overall_status,
        message=overall_msg,
        diagnostics=tuple(dedup_diagnostics),
        limitations=tuple(sorted(set(workflow_limitations))),
    )

    return PostChangeVerificationReport(
        repository_path=repo_path,
        change_set=tuple(change_paths),
        resolved_inputs=resolved_inputs,
        freshness_state=freshness_state_str,
        refreshed=refreshed,
        comparison_performed=comparison_performed,
        comparison_status=comparison_status,
        structural_comparison=structural_comparison,
        changeset_impact=changeset_impact,
        verification_checklist=verification_checklist,
        suggested_checks=tuple(suggested_checks),
        change_risk=change_risk,
        package_boundaries=package_boundaries,
        regression_rules=regression_rules,
        summary=summary,
        diagnostics=tuple(dedup_diagnostics),
        limitations=tuple(sorted(set(workflow_limitations))),
        outcome=outcome,
    )
