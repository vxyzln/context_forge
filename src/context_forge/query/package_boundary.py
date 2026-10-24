"""Package-boundary analysis and policy evaluation.

Identifies resolved dependencies that cross package boundaries, determines
dependency direction, aggregates repeated relationships, and evaluates explicit
package boundary policies.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from context_forge.comparison.models import is_terminal_complete_status
from context_forge.config.project import PackageBoundaryPolicy
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)

DEFAULT_REPORT_LIMIT: int = 50


@dataclass(frozen=True)
class CrossPackageDependency:
    source_package: str
    source_file_path: str
    source_file_id: UUID
    source_entity_name: str
    target_package: str
    target_file_path: str
    target_file_id: UUID
    target_entity_name: str
    relationship_type: str
    evidence: str
    direction: str = "source_to_target"
    source_entity_id: UUID | None = None
    target_entity_id: UUID | None = None
    policy_status: str = "unrestricted"
    violated_rule_id: str | None = None
    violation_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "evidence": self.evidence,
            "policy_status": self.policy_status,
            "relationship_type": self.relationship_type,
            "source_entity_id": (
                str(self.source_entity_id) if self.source_entity_id else None
            ),
            "source_entity_name": self.source_entity_name,
            "source_file_id": str(self.source_file_id),
            "source_file_path": self.source_file_path,
            "source_package": self.source_package,
            "target_entity_id": (
                str(self.target_entity_id) if self.target_entity_id else None
            ),
            "target_entity_name": self.target_entity_name,
            "target_file_id": str(self.target_file_id),
            "target_file_path": self.target_file_path,
            "target_package": self.target_package,
            "violated_rule_id": self.violated_rule_id,
            "violation_reason": self.violation_reason,
        }


@dataclass(frozen=True)
class RepeatedCrossPackagePattern:
    source_package: str
    target_package: str
    relationship_type: str
    count: int
    dependencies: tuple[CrossPackageDependency, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "dependencies": [d.to_dict() for d in self.dependencies],
            "relationship_type": self.relationship_type,
            "source_package": self.source_package,
            "target_package": self.target_package,
        }


@dataclass(frozen=True)
class UnclassifiedDependency:
    source_file_path: str
    target_file_path: str
    relationship_type: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "relationship_type": self.relationship_type,
            "source_file_path": self.source_file_path,
            "target_file_path": self.target_file_path,
        }


@dataclass(frozen=True)
class PolicyViolation:
    rule_id: str
    source_package: str
    target_package: str
    source_file_path: str
    target_file_path: str
    relationship_type: str
    message: str
    evidence: str
    line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence,
            "line": self.line,
            "message": self.message,
            "relationship_type": self.relationship_type,
            "rule_id": self.rule_id,
            "source_file_path": self.source_file_path,
            "source_package": self.source_package,
            "target_file_path": self.target_file_path,
            "target_package": self.target_package,
        }


@dataclass(frozen=True)
class PackageBoundaryReport:
    repository_path: str
    packages: tuple[str, ...]
    cross_package_dependencies: tuple[CrossPackageDependency, ...]
    repeated_patterns: tuple[RepeatedCrossPackagePattern, ...]
    unclassified_dependencies: tuple[UnclassifiedDependency, ...]
    internal_dependencies_count: int
    policy_violations: tuple[PolicyViolation, ...]
    policy_evaluated: bool
    total_cross_package_count: int
    truncated: bool = False
    limit: int | None = None
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    outcome: OperationOutcome = field(default_factory=OperationOutcome.success)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cross_package_dependencies": [
                d.to_dict() for d in self.cross_package_dependencies
            ],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "internal_dependencies_count": self.internal_dependencies_count,
            "limit": self.limit,
            "limitations": list(self.limitations),
            "outcome": self.outcome.to_dict(),
            "packages": list(self.packages),
            "policy_evaluated": self.policy_evaluated,
            "policy_violations": [v.to_dict() for v in self.policy_violations],
            "repeated_patterns": [p.to_dict() for p in self.repeated_patterns],
            "repository_path": self.repository_path,
            "total_cross_package_count": self.total_cross_package_count,
            "truncated": self.truncated,
            "unclassified_dependencies": [
                u.to_dict() for u in self.unclassified_dependencies
            ],
        }


def _resolve_package_for_file(
    path_str: str,
    package_directories: Sequence[str],
) -> str | None:
    norm = path_str.replace("\\", "/")
    matching: list[str] = []
    for pkg_dir in package_directories:
        if norm == pkg_dir or norm.startswith(f"{pkg_dir}/"):
            matching.append(pkg_dir)
    if not matching:
        return None
    matching.sort(key=len, reverse=True)
    return matching[0]


def analyze_package_boundaries(
    project: Project,
    *,
    policy: PackageBoundaryPolicy | None = None,
    limit: int = DEFAULT_REPORT_LIMIT,
    relationship_types: set[str] | None = None,
) -> PackageBoundaryReport:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Report limit must be a positive integer")

    repo_path = project.root_path.as_posix() if project.root_path else str(project.id)

    files_by_id: dict[UUID, File] = {f.id: f for f in project.files}
    symbols_by_id: dict[UUID, Symbol] = {s.id: s for s in project.symbols}

    python_files = [f for f in project.files if f.path.suffix.lower() == ".py"]
    initializer_directories = sorted(
        {f.path.parent.as_posix() for f in python_files if f.path.name == "__init__.py"}
    )

    file_packages: dict[UUID, str | None] = {}
    for f in project.files:
        file_packages[f.id] = _resolve_package_for_file(
            f.path.as_posix(), initializer_directories
        )

    types_filter = (
        frozenset(str(t).lower() for t in relationship_types)
        if relationship_types is not None
        else None
    )

    cross_deps_raw: list[CrossPackageDependency] = []
    unclassified_raw: list[UnclassifiedDependency] = []
    internal_count = 0
    violations_raw: list[PolicyViolation] = []

    seen_dep_keys: set[tuple[UUID, UUID, str]] = set()

    for rel in project.relationships:
        rel_type = (
            rel.relationship_type.value
            if hasattr(rel.relationship_type, "value")
            else str(rel.relationship_type)
        ).lower()

        if types_filter is not None and rel_type not in types_filter:
            continue

        src_file = files_by_id.get(rel.source_id)
        src_sym: Symbol | None = None
        if not src_file:
            src_sym = symbols_by_id.get(rel.source_id)
            if src_sym:
                src_file = files_by_id.get(src_sym.file_id)

        tgt_file = files_by_id.get(rel.target_id)
        tgt_sym: Symbol | None = None
        if not tgt_file:
            tgt_sym = symbols_by_id.get(rel.target_id)
            if tgt_sym:
                tgt_file = files_by_id.get(tgt_sym.file_id)

        if not src_file or not tgt_file:
            unclassified_raw.append(
                UnclassifiedDependency(
                    source_file_path=src_file.path.as_posix()
                    if src_file
                    else str(rel.source_id),
                    target_file_path=tgt_file.path.as_posix()
                    if tgt_file
                    else str(rel.target_id),
                    relationship_type=rel_type,
                    reason="Entity cannot be resolved to a known source file in the repository.",
                )
            )
            continue

        dep_key = (rel.source_id, rel.target_id, rel_type)
        if dep_key in seen_dep_keys:
            continue
        seen_dep_keys.add(dep_key)

        src_pkg = file_packages.get(src_file.id)
        tgt_pkg = file_packages.get(tgt_file.id)

        src_path_str = src_file.path.as_posix()
        tgt_path_str = tgt_file.path.as_posix()

        if src_pkg is None or tgt_pkg is None:
            reason_parts: list[str] = []
            if src_pkg is None:
                reason_parts.append(
                    f"Source '{src_path_str}' does not belong to a package with '__init__.py'"
                )
            if tgt_pkg is None:
                reason_parts.append(
                    f"Target '{tgt_path_str}' does not belong to a package with '__init__.py'"
                )
            unclassified_raw.append(
                UnclassifiedDependency(
                    source_file_path=src_path_str,
                    target_file_path=tgt_path_str,
                    relationship_type=rel_type,
                    reason="; ".join(reason_parts),
                )
            )
            continue

        if src_pkg == tgt_pkg:
            internal_count += 1
            continue

        src_name = src_sym.name if src_sym else src_file.name
        tgt_name = tgt_sym.name if tgt_sym else tgt_file.name

        evidence = (
            f"Confirmed graph relationship '{rel_type}' from '{src_path_str}' "
            f"(package: {src_pkg}) to '{tgt_path_str}' (package: {tgt_pkg})"
        )

        pol_status = "unrestricted"
        violated_rule_id: str | None = None
        violation_reason: str | None = None

        if policy is not None:
            status, matched_rule = policy.evaluate(src_pkg, tgt_pkg)
            pol_status = status
            if status == "prohibited":
                rule_id = (
                    matched_rule.rule_id if matched_rule else f"{src_pkg}->{tgt_pkg}"
                )
                violated_rule_id = rule_id
                violation_reason = f"Package dependency from '{src_pkg}' to '{tgt_pkg}' is prohibited by rule '{rule_id}'"
                violations_raw.append(
                    PolicyViolation(
                        rule_id=rule_id,
                        source_package=src_pkg,
                        target_package=tgt_pkg,
                        source_file_path=src_path_str,
                        target_file_path=tgt_path_str,
                        relationship_type=rel_type,
                        message=violation_reason,
                        evidence=evidence,
                    )
                )
            elif status == "ambiguous":
                matching = policy.matching_rules(src_pkg, tgt_pkg)
                rule_ids = ", ".join(f"'{r.rule_id}' ({r.policy})" for r in matching)
                violated_rule_id = "AMBIGUOUS"
                violation_reason = (
                    f"Ambiguous package boundary policy for '{src_pkg}' to '{tgt_pkg}': "
                    f"conflicting wildcard rules {rule_ids}"
                )

        cross_deps_raw.append(
            CrossPackageDependency(
                source_package=src_pkg,
                source_file_path=src_path_str,
                source_file_id=src_file.id,
                source_entity_name=src_name,
                source_entity_id=src_sym.id if src_sym else src_file.id,
                target_package=tgt_pkg,
                target_file_path=tgt_path_str,
                target_file_id=tgt_file.id,
                target_entity_name=tgt_name,
                target_entity_id=tgt_sym.id if tgt_sym else tgt_file.id,
                relationship_type=rel_type,
                evidence=evidence,
                direction="source_to_target",
                policy_status=pol_status,
                violated_rule_id=violated_rule_id,
                violation_reason=violation_reason,
            )
        )

    # Sort cross-package dependencies deterministically
    sorted_cross_deps = tuple(
        sorted(
            cross_deps_raw,
            key=lambda d: (
                d.source_package,
                d.target_package,
                d.source_file_path,
                d.target_file_path,
                d.relationship_type,
            ),
        )
    )

    # Aggregate repeated patterns: group by (source_package, target_package, relationship_type)
    pattern_groups: dict[tuple[str, str, str], list[CrossPackageDependency]] = (
        defaultdict(list)
    )
    for cd in sorted_cross_deps:
        pattern_groups[
            (cd.source_package, cd.target_package, cd.relationship_type)
        ].append(cd)

    repeated_patterns_list: list[RepeatedCrossPackagePattern] = []
    for (spkg, tpkg, rtype), deps in sorted(
        pattern_groups.items(), key=lambda kv: kv[0]
    ):
        repeated_patterns_list.append(
            RepeatedCrossPackagePattern(
                source_package=spkg,
                target_package=tpkg,
                relationship_type=rtype,
                count=len(deps),
                dependencies=tuple(deps),
            )
        )

    sorted_unclassified = tuple(
        sorted(
            unclassified_raw,
            key=lambda u: (u.source_file_path, u.target_file_path, u.relationship_type),
        )
    )

    sorted_violations = tuple(
        sorted(
            violations_raw,
            key=lambda v: (
                v.rule_id,
                v.source_package,
                v.target_package,
                v.source_file_path,
                v.target_file_path,
            ),
        )
    )

    limitations: list[str] = [
        "Package detection identifies conventional Python packages containing __init__.py files; namespace packages without __init__.py are not inventoried as packages.",
        "Unresolved imports are evidence records and are not treated as resolved dependency edges.",
    ]

    is_complete_project = (
        is_terminal_complete_status(project.analysis_status) and not project.errors
    )
    if not is_complete_project:
        limitations.append(
            f"Repository analysis status is '{project.analysis_status}'; package boundaries or dependencies may be incomplete."
        )

    diagnostics: list[DiagnosticItem] = []
    for v in sorted_violations:
        diagnostics.append(
            DiagnosticItem.error(
                v.message,
                code="PACKAGE_BOUNDARY_VIOLATION",
                path=v.source_file_path,
                source="package_policy",
            )
        )

    ambiguous_deps = [d for d in cross_deps_raw if d.policy_status == "ambiguous"]
    for amb in ambiguous_deps:
        diagnostics.append(
            DiagnosticItem.warning(
                amb.violation_reason
                or f"Ambiguous package policy for '{amb.source_package}' to '{amb.target_package}'",
                code="AMBIGUOUS_POLICY_EVALUATION",
                path=amb.source_file_path,
                source="package_policy",
            )
        )

    if ambiguous_deps:
        limitations.append(
            f"Ambiguous package policy detected for {len(ambiguous_deps)} cross-package relationship(s); conflicting wildcard rules require resolution."
        )

    if not is_complete_project and policy is not None and policy.rules:
        diagnostics.append(
            DiagnosticItem.warning(
                "Repository analysis is incomplete; some package policy rules could not be exhaustively evaluated.",
                code="INCOMPLETE_POLICY_EVALUATION",
                source="package_policy",
            )
        )

    total_cross = len(sorted_cross_deps)
    truncated = total_cross > limit
    displayed_cross_deps = sorted_cross_deps[:limit] if truncated else sorted_cross_deps

    if truncated:
        limitations.append(
            f"Cross-package dependencies display was truncated to {limit} of {total_cross} items."
        )

    if project.analysis_status == "failed":
        status = OperationStatus.FAILED
        message = "Package boundary analysis failed due to upstream analysis failure"
    elif not is_complete_project or not is_terminal_complete_status(
        project.analysis_status
    ):
        status = OperationStatus.PARTIAL
        message = (
            "Package boundary analysis generated with partial or incomplete analysis"
        )
    elif sorted_violations or ambiguous_deps:
        status = OperationStatus.PARTIAL
        if sorted_violations and ambiguous_deps:
            message = (
                f"Package boundary analysis detected {len(sorted_violations)} policy violation(s) "
                f"and {len(ambiguous_deps)} ambiguous policy evaluation(s)"
            )
        elif sorted_violations:
            message = f"Package boundary analysis detected {len(sorted_violations)} policy violation(s)"
        else:
            message = f"Package boundary analysis detected {len(ambiguous_deps)} ambiguous policy evaluation(s)"
    else:
        status = OperationStatus.SUCCESS
        message = "Package boundary analysis completed successfully"

    outcome = OperationOutcome(
        status=status,
        message=message,
        diagnostics=tuple(diagnostics),
        limitations=tuple(sorted(set(limitations))),
    )

    return PackageBoundaryReport(
        repository_path=repo_path,
        packages=tuple(initializer_directories),
        cross_package_dependencies=displayed_cross_deps,
        repeated_patterns=tuple(repeated_patterns_list),
        unclassified_dependencies=sorted_unclassified,
        internal_dependencies_count=internal_count,
        policy_violations=sorted_violations,
        policy_evaluated=policy is not None,
        total_cross_package_count=total_cross,
        truncated=truncated,
        limit=limit,
        diagnostics=tuple(diagnostics),
        limitations=tuple(sorted(set(limitations))),
        outcome=outcome,
    )
