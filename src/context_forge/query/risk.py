"""Change-risk evidence report.

Explains the possible implications of a structural change using observable
structural evidence, test associations, package boundary crossings, and explicit
uncertainty without defect prediction or arbitrary scoring.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.comparison.models import (
    StructuralComparisonResult,
    is_terminal_complete_status,
)
from context_forge.config.project import PackageBoundaryPolicy
from context_forge.models.project import Project
from context_forge.query.package_boundary import (
    analyze_package_boundaries,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    DiagnosticSeverity,
    OperationOutcome,
    OperationStatus,
)

DEFAULT_REPORT_LIMIT: int = 50
DEFAULT_IMPACT_MAX_DEPTH: int = 3

RISK_REPORT_DISCLAIMER: str = (
    "Change-risk assessment provides evidence-based observations and concerns; "
    "it does not compute defect probabilities, provide runtime guarantees, or predict failures."
)


class RiskFactCategory(str, Enum):
    CHANGED_ENTITY = "changed_entity"
    AFFECTED_COMPONENT = "affected_component"
    DEPENDENCY_PATH = "dependency_path"
    TEST_ASSOCIATION = "test_association"
    PACKAGE_BOUNDARY = "package_boundary"
    ANALYSIS_STATUS = "analysis_status"
    FRESHNESS_STATE = "freshness_state"


class RiskConcernCategory(str, Enum):
    BROAD_IMPACT = "broad_impact"
    UNVERIFIED_AREA = "unverified_area"
    CROSS_PACKAGE_IMPACT = "cross_package_impact"
    DEPENDENCY_PATH_COMPLEXITY = "dependency_path_complexity"
    STALE_ANALYSIS = "stale_analysis"
    INCOMPLETE_ANALYSIS = "incomplete_analysis"
    UNRESOLVED_INPUT = "unresolved_input"
    POLICY_VIOLATION = "policy_violation"


@dataclass(frozen=True)
class ObservedFact:
    fact_id: str
    category: str
    statement: str
    entity_id: UUID | None = None
    entity_name: str | None = None
    path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "category": self.category,
            "fact_id": self.fact_id,
            "statement": self.statement,
        }
        if self.entity_id is not None:
            result["entity_id"] = str(self.entity_id)
        if self.entity_name is not None:
            result["entity_name"] = self.entity_name
        if self.path is not None:
            result["path"] = self.path
        if self.details:
            result["details"] = dict(sorted(self.details.items()))
        return result


@dataclass(frozen=True)
class InferredConcern:
    concern_id: str
    category: str
    severity: DiagnosticSeverity
    summary: str
    rationale: str
    supporting_fact_ids: tuple[str, ...]
    supporting_evidence: tuple[str, ...] = ()
    recommended_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "concern_id": self.concern_id,
            "rationale": self.rationale,
            "recommended_action": self.recommended_action,
            "severity": self.severity.value,
            "summary": self.summary,
            "supporting_evidence": list(self.supporting_evidence),
            "supporting_fact_ids": list(self.supporting_fact_ids),
        }


@dataclass(frozen=True)
class MissingEvidenceItem:
    item_id: str
    category: str
    description: str
    impact_on_assessment: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "description": self.description,
            "impact_on_assessment": self.impact_on_assessment,
            "item_id": self.item_id,
        }


@dataclass(frozen=True)
class ChangeRiskReport:
    repository_path: str
    change_inputs: tuple[str, ...]
    analysis_status: str
    freshness_state: str
    observed_facts: tuple[ObservedFact, ...]
    inferred_concerns: tuple[InferredConcern, ...]
    missing_evidence: tuple[MissingEvidenceItem, ...]
    directly_affected_count: int
    downstream_affected_count: int
    associated_tests_count: int
    unassociated_targets_count: int
    cross_package_impact_count: int
    truncated: bool = False
    limit: int | None = None
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    disclaimer: str = RISK_REPORT_DISCLAIMER
    outcome: OperationOutcome = field(default_factory=OperationOutcome.success)

    @property
    def facts_by_category(self) -> dict[str, list[ObservedFact]]:
        grouped: dict[str, list[ObservedFact]] = defaultdict(list)
        for f in self.observed_facts:
            grouped[f.category].append(f)
        return dict(grouped)

    @property
    def concerns_by_category(self) -> dict[str, list[InferredConcern]]:
        grouped: dict[str, list[InferredConcern]] = defaultdict(list)
        for c in self.inferred_concerns:
            grouped[c.category].append(c)
        return dict(grouped)

    @property
    def concerns_by_severity(self) -> dict[str, list[InferredConcern]]:
        grouped: dict[str, list[InferredConcern]] = defaultdict(list)
        for c in self.inferred_concerns:
            grouped[c.severity.value].append(c)
        return dict(grouped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_status": self.analysis_status,
            "associated_tests_count": self.associated_tests_count,
            "change_inputs": list(self.change_inputs),
            "cross_package_impact_count": self.cross_package_impact_count,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "directly_affected_count": self.directly_affected_count,
            "disclaimer": self.disclaimer,
            "downstream_affected_count": self.downstream_affected_count,
            "freshness_state": self.freshness_state,
            "inferred_concerns": [c.to_dict() for c in self.inferred_concerns],
            "limit": self.limit,
            "limitations": list(self.limitations),
            "missing_evidence": [m.to_dict() for m in self.missing_evidence],
            "observed_facts": [f.to_dict() for f in self.observed_facts],
            "outcome": self.outcome.to_dict(),
            "repository_path": self.repository_path,
            "total_concerns_count": len(self.inferred_concerns),
            "total_facts_count": len(self.observed_facts),
            "truncated": self.truncated,
            "unassociated_targets_count": self.unassociated_targets_count,
        }


def generate_change_risk_report(
    project: Project,
    paths: Sequence[str | Path],
    *,
    comparison: StructuralComparisonResult | None = None,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    limit: int | None = DEFAULT_REPORT_LIMIT,
    policy: PackageBoundaryPolicy | None = None,
) -> ChangeRiskReport:
    from context_forge.query.changeset import analyze_changeset

    repo_path = project.root_path.as_posix() if project.root_path else str(project.id)

    supplied_paths: list[str] = [str(p) for p in paths]

    # Incorporate comparison changes if provided
    comparison_facts: list[ObservedFact] = []
    comparison_limitations: list[str] = []
    if comparison is not None:
        comparison_limitations.extend(comparison.limitations)
        for mf in comparison.modified_files:
            if mf.path not in supplied_paths:
                supplied_paths.append(mf.path)
            comparison_facts.append(
                ObservedFact(
                    fact_id=f"comparison:modified_file:{mf.path}",
                    category=RiskFactCategory.CHANGED_ENTITY.value,
                    statement=f"Structural comparison identified modified file: '{mf.path}'",
                    path=mf.path,
                )
            )
        for af in comparison.added_files:
            if af.path not in supplied_paths:
                supplied_paths.append(af.path)
            comparison_facts.append(
                ObservedFact(
                    fact_id=f"comparison:added_file:{af.path}",
                    category=RiskFactCategory.CHANGED_ENTITY.value,
                    statement=f"Structural comparison identified added file: '{af.path}'",
                    path=af.path,
                )
            )
        for rf in comparison.removed_files:
            comparison_facts.append(
                ObservedFact(
                    fact_id=f"comparison:removed_file:{rf.path}",
                    category=RiskFactCategory.CHANGED_ENTITY.value,
                    statement=f"Structural comparison identified removed file: '{rf.path}'",
                    path=rf.path,
                )
            )
        for mv in comparison.moved_files:
            comparison_facts.append(
                ObservedFact(
                    fact_id=f"comparison:moved_file:{mv.path}",
                    category=RiskFactCategory.CHANGED_ENTITY.value,
                    statement=f"Structural comparison identified moved file: '{mv.path}' (from {mv.before_path})",
                    path=mv.path,
                )
            )

    if not supplied_paths:
        outcome = OperationOutcome(
            status=OperationStatus.FAILED,
            message="No change inputs or structural comparison changes were supplied.",
            diagnostics=(
                DiagnosticItem.error(
                    "No change inputs supplied for risk assessment.",
                    code="NO_INPUTS",
                    source="risk",
                ),
            ),
            limitations=("No change inputs available for risk analysis.",),
        )
        return ChangeRiskReport(
            repository_path=repo_path,
            change_inputs=(),
            analysis_status=project.analysis_status,
            freshness_state="indeterminate",
            observed_facts=(),
            inferred_concerns=(),
            missing_evidence=(
                MissingEvidenceItem(
                    item_id="missing_inputs",
                    category="inputs",
                    description="No change-set paths or modified files were provided.",
                    impact_on_assessment="Risk assessment cannot proceed without change inputs.",
                ),
            ),
            directly_affected_count=0,
            downstream_affected_count=0,
            associated_tests_count=0,
            unassociated_targets_count=0,
            cross_package_impact_count=0,
            outcome=outcome,
        )

    # 1. Execute changeset impact and checklist analysis
    impact = analyze_changeset(
        project,
        supplied_paths,
        direction=direction,
        relationship_types=relationship_types,
        max_depth=max_depth,
        limit=limit,
        include_checklist=True,
    )

    checklist = impact.verification_checklist

    # 2. Execute package boundary analysis
    pkg_report = analyze_package_boundaries(
        project,
        policy=policy,
        limit=limit or DEFAULT_REPORT_LIMIT,
        relationship_types=relationship_types,
    )

    facts: list[ObservedFact] = list(comparison_facts)
    concerns: list[InferredConcern] = []
    missing_evidence: list[MissingEvidenceItem] = []

    # Map files to packages for cross-package impact detection
    file_to_pkg: dict[str, str] = {}
    for pkg_dir in pkg_report.packages:
        for f in project.files:
            p_posix = f.path.as_posix()
            if (p_posix == pkg_dir or p_posix.startswith(f"{pkg_dir}/")) and (
                p_posix not in file_to_pkg or len(pkg_dir) > len(file_to_pkg[p_posix])
            ):
                file_to_pkg[p_posix] = pkg_dir

    # Extract direct roots
    direct_root_facts: list[ObservedFact] = []
    unresolved_input_facts: list[ObservedFact] = []
    root_paths: set[str] = set()
    root_packages: set[str] = set()

    for r in impact.resolved_inputs:
        if r.is_resolved and r.target is not None:
            r_path = r.target.path or r.target.name
            root_paths.add(r_path)
            pkg = file_to_pkg.get(r_path)
            if pkg:
                root_packages.add(pkg)
            fact = ObservedFact(
                fact_id=f"root:{r.target.id}",
                category=RiskFactCategory.CHANGED_ENTITY.value,
                statement=f"Directly changed root: '{r.target.name}' ({r_path})",
                entity_id=r.target.id,
                entity_name=r.target.name,
                path=r_path,
                details={"kind": r.target.kind, "package": pkg},
            )
            direct_root_facts.append(fact)
            facts.append(fact)
        else:
            fact = ObservedFact(
                fact_id=f"unresolved_input:{r.original_input}",
                category=RiskFactCategory.CHANGED_ENTITY.value,
                statement=f"Unresolved change-set input path: '{r.original_input}' ({r.reason})",
                path=r.original_input,
                details={"status": r.status, "reason": r.reason},
            )
            unresolved_input_facts.append(fact)
            facts.append(fact)

    # Extract downstream and directly impacted components
    direct_impact_facts: list[ObservedFact] = []
    downstream_facts: list[ObservedFact] = []
    downstream_packages: set[str] = set()
    all_affected_items = (
        impact._all_items
        if hasattr(impact, "_all_items") and impact._all_items is not None
        else impact.items
    )

    for item in all_affected_items:
        pkg = file_to_pkg.get(item.path)
        if pkg:
            downstream_packages.add(pkg)
        if item.classification == "direct":
            fact = ObservedFact(
                fact_id=f"direct_impact:{item.entity_id}",
                category=RiskFactCategory.AFFECTED_COMPONENT.value,
                statement=(
                    f"Directly affected component: '{item.name}' ({item.path}) at depth 1"
                ),
                entity_id=item.entity_id,
                entity_name=item.name,
                path=item.path,
                details={
                    "classification": "direct",
                    "min_depth": 1,
                    "package": pkg,
                    "roots": list(item.roots),
                },
            )
            direct_impact_facts.append(fact)
            facts.append(fact)
        else:
            fact = ObservedFact(
                fact_id=f"downstream:{item.entity_id}",
                category=RiskFactCategory.AFFECTED_COMPONENT.value,
                statement=(
                    f"Downstream component affected: '{item.name}' ({item.path}) "
                    f"at traversal depth {item.min_depth}"
                ),
                entity_id=item.entity_id,
                entity_name=item.name,
                path=item.path,
                details={
                    "classification": "downstream",
                    "min_depth": item.min_depth,
                    "package": pkg,
                    "roots": list(item.roots),
                },
            )
            downstream_facts.append(fact)
            facts.append(fact)

        # Record shortest path evidence if available
        if item.shortest_path:
            step_descriptions = [
                f"{step.from_name} -[{step.relationship_type}]-> {step.to_name}"
                for step in item.shortest_path
            ]
            facts.append(
                ObservedFact(
                    fact_id=f"path:{item.entity_id}",
                    category=RiskFactCategory.DEPENDENCY_PATH.value,
                    statement=(
                        f"Impact path to '{item.name}': "
                        f"{' => '.join(step_descriptions)}"
                    ),
                    entity_id=item.entity_id,
                    entity_name=item.name,
                    path=item.path,
                    details={"steps": [s.to_dict() for s in item.shortest_path]},
                )
            )

    # Extract test associations evidence
    associated_tests_count = 0
    unassociated_targets_count = 0
    unassociated_names: list[str] = []
    test_facts: list[ObservedFact] = []
    unassociated_facts: list[ObservedFact] = []

    if checklist is not None:
        for it in checklist.detected_structural_tests:
            associated_tests_count += 1
            fact = ObservedFact(
                fact_id=f"test_structural:{it.item_id}",
                category=RiskFactCategory.TEST_ASSOCIATION.value,
                statement=(
                    f"Confirmed structural test suite '{it.test_file_path}' associates with: "
                    f"{', '.join(it.target_entities)}"
                ),
                path=it.test_file_path,
                details={
                    "classification": "direct",
                    "targets": list(it.target_entities),
                    "evidence": list(it.supporting_evidence),
                },
            )
            test_facts.append(fact)
            facts.append(fact)

        for it in checklist.heuristic_tests:
            associated_tests_count += 1
            fact = ObservedFact(
                fact_id=f"test_heuristic:{it.item_id}",
                category=RiskFactCategory.TEST_ASSOCIATION.value,
                statement=(
                    f"Heuristic test suite '{it.test_file_path}' recommended for: "
                    f"{', '.join(it.target_entities)}"
                ),
                path=it.test_file_path,
                details={
                    "classification": "heuristic",
                    "targets": list(it.target_entities),
                    "evidence": list(it.supporting_evidence),
                },
            )
            test_facts.append(fact)
            facts.append(fact)

        for it in checklist.unverified_areas:
            if (
                it.item_id.startswith("missing_test:")
                or it.item_id == "unassociated_targets"
            ):
                for target_name in it.target_entities:
                    if target_name not in unassociated_names:
                        unassociated_names.append(target_name)
                        unassociated_targets_count += 1
                        fact = ObservedFact(
                            fact_id=f"unassociated_target:{target_name}",
                            category=RiskFactCategory.TEST_ASSOCIATION.value,
                            statement=f"Affected component '{target_name}' has no automated test associations in static analysis",
                            entity_name=target_name,
                        )
                        unassociated_facts.append(fact)
                        facts.append(fact)

    # Extract package boundary facts
    cross_package_facts: list[ObservedFact] = []
    affected_paths = root_paths | {item.path for item in all_affected_items}

    for cd in pkg_report.cross_package_dependencies:
        if (
            cd.source_file_path in affected_paths
            or cd.target_file_path in affected_paths
        ):
            fact = ObservedFact(
                fact_id=f"pkg_boundary:{cd.source_package}->{cd.target_package}:{cd.source_file_path}->{cd.target_file_path}",
                category=RiskFactCategory.PACKAGE_BOUNDARY.value,
                statement=(
                    f"Cross-package dependency crossing boundary from '{cd.source_package}' "
                    f"to '{cd.target_package}' ({cd.source_file_path} -> {cd.target_file_path})"
                ),
                details={
                    "direction": cd.direction,
                    "policy_status": cd.policy_status,
                    "relationship_type": cd.relationship_type,
                    "source_package": cd.source_package,
                    "target_package": cd.target_package,
                },
            )
            cross_package_facts.append(fact)
            facts.append(fact)

    # Freshness & analysis status facts
    freshness_state = checklist.freshness_state if checklist else "indeterminate"
    analysis_status = (
        checklist.analysis_status if checklist else project.analysis_status
    )
    is_complete_project = (
        is_terminal_complete_status(project.analysis_status) and not project.errors
    )

    facts.append(
        ObservedFact(
            fact_id="freshness_state",
            category=RiskFactCategory.FRESHNESS_STATE.value,
            statement=f"Repository analysis freshness state is '{freshness_state}'",
            details={"freshness_state": freshness_state},
        )
    )
    facts.append(
        ObservedFact(
            fact_id="analysis_status",
            category=RiskFactCategory.ANALYSIS_STATUS.value,
            statement=f"Repository analysis status is '{project.analysis_status}' (recorded errors: {len(project.errors)})",
            details={"errors": list(project.errors), "status": project.analysis_status},
        )
    )

    # -------------------------------------------------------------------------
    # Derive Inferred Concerns (each strictly tied to supporting facts)
    # -------------------------------------------------------------------------

    # Concern 1: Broad downstream impact
    if downstream_facts:
        count = len(downstream_facts)
        severity = DiagnosticSeverity.WARNING if count >= 3 else DiagnosticSeverity.INFO
        concerns.append(
            InferredConcern(
                concern_id="broad_downstream_impact",
                category=RiskConcernCategory.BROAD_IMPACT.value,
                severity=severity,
                summary=f"Change propagates downstream to {count} affected component(s)",
                rationale=(
                    f"Direct changes affect {count} dependent component(s) across the dependency graph. "
                    "Broad downstream reach creates risk of unintended behavioral regressions."
                ),
                supporting_fact_ids=tuple(f.fact_id for f in downstream_facts[:10]),
                supporting_evidence=tuple(f.statement for f in downstream_facts[:5]),
                recommended_action="Execute test suites for affected downstream components and review dependent call sites.",
            )
        )

    # Concern 2: Unverified areas / Missing test coverage
    if unassociated_facts:
        count = len(unassociated_facts)
        concerns.append(
            InferredConcern(
                concern_id="unverified_affected_components",
                category=RiskConcernCategory.UNVERIFIED_AREA.value,
                severity=DiagnosticSeverity.WARNING,
                summary=f"{count} directly changed or impacted component(s) lack automated test associations",
                rationale=(
                    "Static analysis did not identify direct or heuristic test associations for these components. "
                    "Changes cannot be verified against existing test suites without expanding coverage."
                ),
                supporting_fact_ids=tuple(f.fact_id for f in unassociated_facts[:10]),
                supporting_evidence=tuple(f.statement for f in unassociated_facts[:5]),
                recommended_action="Author targeted unit tests or conduct manual verification for unassociated components.",
            )
        )

    # Concern 3: Cross-package impact
    cross_pkg_count = len(cross_package_facts)
    if cross_pkg_count > 0:
        distinct_source_pkgs = sorted(
            {
                f.details["source_package"]
                for f in cross_package_facts
                if "source_package" in f.details
            }
        )
        distinct_target_pkgs = sorted(
            {
                f.details["target_package"]
                for f in cross_package_facts
                if "target_package" in f.details
            }
        )
        concerns.append(
            InferredConcern(
                concern_id="cross_package_propagation",
                category=RiskConcernCategory.CROSS_PACKAGE_IMPACT.value,
                severity=DiagnosticSeverity.INFO,
                summary=f"Change impact crosses {cross_pkg_count} package boundary relationship(s)",
                rationale=(
                    f"Structural changes propagate between packages ({', '.join(distinct_source_pkgs)} -> "
                    f"{', '.join(distinct_target_pkgs)}). Cross-package dependencies affect architectural layering."
                ),
                supporting_fact_ids=tuple(f.fact_id for f in cross_package_facts[:10]),
                supporting_evidence=tuple(f.statement for f in cross_package_facts[:5]),
                recommended_action="Review public interface contracts between the involved packages.",
            )
        )

    # Concern 4: Policy violations
    for v in pkg_report.policy_violations:
        if v.source_file_path in affected_paths or v.target_file_path in affected_paths:
            v_fact_id = f"pkg_boundary:{v.source_package}->{v.target_package}:{v.source_file_path}->{v.target_file_path}"
            matching_fact = next(
                (f for f in cross_package_facts if f.fact_id == v_fact_id), None
            )
            supporting_ids = (matching_fact.fact_id,) if matching_fact else ()
            concerns.append(
                InferredConcern(
                    concern_id=f"policy_violation:{v.rule_id}",
                    category=RiskConcernCategory.POLICY_VIOLATION.value,
                    severity=DiagnosticSeverity.ERROR,
                    summary=f"Package boundary policy violation: rule '{v.rule_id}'",
                    rationale=v.message,
                    supporting_fact_ids=supporting_ids,
                    supporting_evidence=(v.evidence,),
                    recommended_action="Refactor the dependency to comply with configured architectural policy.",
                )
            )

    ambiguous_cross_facts = [
        f for f in cross_package_facts if f.details.get("policy_status") == "ambiguous"
    ]
    if ambiguous_cross_facts:
        count = len(ambiguous_cross_facts)
        concerns.append(
            InferredConcern(
                concern_id="ambiguous_package_policy",
                category=RiskConcernCategory.POLICY_VIOLATION.value,
                severity=DiagnosticSeverity.WARNING,
                summary=f"{count} cross-package relationship(s) have ambiguous policy definitions",
                rationale=(
                    "Multiple matching wildcard rules produce conflicting allow and deny decisions. "
                    "Architectural intent cannot be determined without an explicit exact rule."
                ),
                supporting_fact_ids=tuple(
                    f.fact_id for f in ambiguous_cross_facts[:10]
                ),
                supporting_evidence=tuple(
                    f.statement for f in ambiguous_cross_facts[:5]
                ),
                recommended_action="Define explicit exact rules for the ambiguous package pairs to resolve rule conflict.",
            )
        )

    # Concern 5: Stale repository analysis
    if freshness_state == "stale":
        concerns.append(
            InferredConcern(
                concern_id="stale_analysis_risk",
                category=RiskConcernCategory.STALE_ANALYSIS.value,
                severity=DiagnosticSeverity.WARNING,
                summary="Repository analysis is stale relative to current working tree",
                rationale=(
                    "Files in the working tree have been modified since the last index analysis. "
                    "Computed impact boundaries and test associations may be outdated."
                ),
                supporting_fact_ids=("freshness_state",),
                supporting_evidence=(f"Freshness state is '{freshness_state}'",),
                recommended_action="Refresh repository analysis via 'context-forge refresh' before relying on risk assessment.",
            )
        )

    # Concern 6: Incomplete analysis
    if not is_complete_project:
        err_msg = f" (recorded errors: {len(project.errors)})" if project.errors else ""
        concerns.append(
            InferredConcern(
                concern_id="incomplete_analysis_risk",
                category=RiskConcernCategory.INCOMPLETE_ANALYSIS.value,
                severity=DiagnosticSeverity.ERROR,
                summary=f"Repository analysis is incomplete (status: '{project.analysis_status}'{err_msg})",
                rationale=(
                    "Structural analysis did not complete cleanly or encountered errors. "
                    "Missing symbols or relationships may conceal affected components and test associations."
                ),
                supporting_fact_ids=("analysis_status",),
                supporting_evidence=tuple(project.errors[:5]) if project.errors else (),
                recommended_action="Re-analyze repository to resolve analysis errors before proceeding.",
            )
        )

    # Concern 7: Unresolved inputs
    if unresolved_input_facts:
        unres_count = len(unresolved_input_facts)
        concerns.append(
            InferredConcern(
                concern_id="unresolved_inputs_risk",
                category=RiskConcernCategory.UNRESOLVED_INPUT.value,
                severity=DiagnosticSeverity.ERROR,
                summary=f"{unres_count} change-set input path(s) could not be resolved",
                rationale=(
                    "Specified input paths do not exist in the repository inventory or failed path resolution. "
                    "Their impact and risk cannot be evaluated."
                ),
                supporting_fact_ids=tuple(f.fact_id for f in unresolved_input_facts),
                supporting_evidence=tuple(f.statement for f in unresolved_input_facts),
                recommended_action="Check file path spelling and ensure targets are located within repository root.",
            )
        )

    # -------------------------------------------------------------------------
    # Record Missing Evidence
    # -------------------------------------------------------------------------
    if unassociated_names:
        missing_evidence.append(
            MissingEvidenceItem(
                item_id="missing_test_associations",
                category="test_associations",
                description=(
                    f"No automated test associations found for {len(unassociated_names)} target(s): "
                    f"{', '.join(sorted(unassociated_names)[:10])}"
                ),
                impact_on_assessment="Behavioral correctness of these components cannot be verified using static test associations.",
            )
        )

    if not is_complete_project:
        missing_evidence.append(
            MissingEvidenceItem(
                item_id="incomplete_analysis_evidence",
                category="structural_graph",
                description=f"Analysis status is '{project.analysis_status}' with {len(project.errors)} error(s)",
                impact_on_assessment="Portions of the dependency graph or symbol table may be absent.",
            )
        )

    if freshness_state in {"stale", "indeterminate"}:
        missing_evidence.append(
            MissingEvidenceItem(
                item_id="freshness_uncertainty",
                category="repository_freshness",
                description=f"Analysis freshness state is '{freshness_state}'",
                impact_on_assessment="Impact results reflect cached state rather than recent working tree edits.",
            )
        )

    for r in impact.resolved_inputs:
        if not r.is_resolved:
            missing_evidence.append(
                MissingEvidenceItem(
                    item_id=f"unresolved_input:{r.original_input}",
                    category="input_resolution",
                    description=f"Path '{r.original_input}' failed resolution: {r.reason}",
                    impact_on_assessment="No structural impact or test associations could be evaluated for this path.",
                )
            )

    # Deterministic sorting
    sorted_facts = tuple(
        sorted(
            facts,
            key=lambda f: (f.category, f.fact_id),
        )
    )

    severity_rank = {
        DiagnosticSeverity.BLOCKER: 1,
        DiagnosticSeverity.ERROR: 2,
        DiagnosticSeverity.WARNING: 3,
        DiagnosticSeverity.INFO: 4,
    }
    sorted_concerns = tuple(
        sorted(
            concerns,
            key=lambda c: (severity_rank.get(c.severity, 99), c.category, c.concern_id),
        )
    )
    sorted_missing = tuple(
        sorted(
            missing_evidence,
            key=lambda m: (m.category, m.item_id),
        )
    )

    # Limitations & Diagnostics
    limitations: list[str] = list(impact.limitations)
    limitations.extend(comparison_limitations)
    limitations.append(RISK_REPORT_DISCLAIMER)

    diagnostics: list[DiagnosticItem] = list(impact.diagnostics)
    for c in sorted_concerns:
        if c.severity in (DiagnosticSeverity.ERROR, DiagnosticSeverity.BLOCKER):
            diagnostics.append(
                DiagnosticItem.error(
                    c.summary,
                    code=c.category.upper(),
                    source="risk",
                )
            )
        elif c.severity == DiagnosticSeverity.WARNING:
            diagnostics.append(
                DiagnosticItem.warning(
                    c.summary,
                    code=c.category.upper(),
                    source="risk",
                )
            )

    # Deduplicate diagnostics
    seen_diag: set[tuple[str, str, str, str]] = set()
    unique_diagnostics: list[DiagnosticItem] = []
    for d in diagnostics:
        diag_key = (d.severity.value, d.code or "", d.path or "", d.message)
        if diag_key not in seen_diag:
            seen_diag.add(diag_key)
            unique_diagnostics.append(d)

    sorted_diagnostics = tuple(
        sorted(
            unique_diagnostics,
            key=lambda d: (d.severity.value, d.code or "", d.path or "", d.message),
        )
    )

    # Determine overall status
    if len(unresolved_input_facts) == len(supplied_paths):
        status = OperationStatus.FAILED
        message = "Change-risk assessment failed: all input paths could not be resolved"
    elif project.analysis_status == "failed":
        status = OperationStatus.FAILED
        message = "Change-risk assessment failed: repository analysis failed"
    elif (
        not is_complete_project
        or len(unresolved_input_facts) > 0
        or freshness_state == "stale"
        or impact.truncated
        or any(c.severity == DiagnosticSeverity.ERROR for c in sorted_concerns)
    ):
        status = OperationStatus.PARTIAL
        message = f"Change-risk report generated with {len(sorted_concerns)} concern(s) and partial analysis"
    else:
        status = OperationStatus.SUCCESS
        message = f"Change-risk report generated successfully with {len(sorted_concerns)} concern(s)"

    outcome = OperationOutcome(
        status=status,
        message=message,
        diagnostics=sorted_diagnostics,
        limitations=tuple(sorted(set(limitations))),
    )

    return ChangeRiskReport(
        repository_path=repo_path,
        change_inputs=tuple(supplied_paths),
        analysis_status=analysis_status,
        freshness_state=freshness_state,
        observed_facts=sorted_facts,
        inferred_concerns=sorted_concerns,
        missing_evidence=sorted_missing,
        directly_affected_count=len(direct_impact_facts),
        downstream_affected_count=len(downstream_facts),
        associated_tests_count=associated_tests_count,
        unassociated_targets_count=unassociated_targets_count,
        cross_package_impact_count=cross_pkg_count,
        truncated=impact.truncated,
        limit=limit,
        diagnostics=sorted_diagnostics,
        limitations=tuple(sorted(set(limitations))),
        disclaimer=RISK_REPORT_DISCLAIMER,
        outcome=outcome,
    )
