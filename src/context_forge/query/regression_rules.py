from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.comparison.models import is_terminal_complete_status
from context_forge.config.project import PackageBoundaryPolicy, StructuralRule
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)


class RuleKind(str, Enum):
    PROHIBITED_DEPENDENCY = "prohibited_dependency"
    PROHIBITED_RELATIONSHIP = "prohibited_relationship"
    ISOLATED_COMPONENT = "isolated_component"
    LAYER_BOUNDARY = "layer_boundary"
    PACKAGE_BOUNDARY = "package_boundary"


class RuleOutcome(str, Enum):
    NO_VIOLATION_DETECTED = "no_violation_detected"
    VIOLATION_DETECTED = "violation_detected"
    UNEVALUABLE = "unevaluable"


SUPPORTED_RULE_KINDS = {kind.value for kind in RuleKind}


@dataclass(frozen=True)
class RuleEvaluationItem:
    rule_id: str
    kind: str
    outcome: str
    message: str
    source: str
    target: str | None = None
    relationship_type: str | None = None
    evidence: tuple[str, ...] = ()
    source_path: str | None = None
    line: int | None = None
    target_path: str | None = None
    diagnostics: tuple[DiagnosticItem, ...] = ()
    affected_entities: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def is_violation(self) -> bool:
        return self.outcome == RuleOutcome.VIOLATION_DETECTED.value

    @property
    def is_no_violation(self) -> bool:
        return self.outcome == RuleOutcome.NO_VIOLATION_DETECTED.value

    @property
    def is_unevaluable(self) -> bool:
        return self.outcome == RuleOutcome.UNEVALUABLE.value

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "affected_entities": list(self.affected_entities),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "evidence": list(self.evidence),
            "kind": self.kind,
            "line": self.line,
            "message": self.message,
            "outcome": self.outcome,
            "relationship_type": self.relationship_type,
            "rule_id": self.rule_id,
            "source": self.source,
            "source_path": self.source_path,
            "target": self.target,
            "target_path": self.target_path,
        }
        if self.details:
            result["details"] = dict(sorted(self.details.items()))
        return result


@dataclass(frozen=True)
class StructuralRulesReport:
    repository_path: str
    rules: tuple[StructuralRule, ...]
    results: tuple[RuleEvaluationItem, ...]
    violations_count: int
    no_violations_count: int
    unevaluable_count: int
    analysis_status: str = "completed"
    truncated: bool = False
    limit: int | None = None
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    outcome: OperationOutcome = field(default_factory=OperationOutcome.success)

    @property
    def violations(self) -> tuple[RuleEvaluationItem, ...]:
        return tuple(r for r in self.results if r.is_violation)

    @property
    def unevaluable_items(self) -> tuple[RuleEvaluationItem, ...]:
        return tuple(r for r in self.results if r.is_unevaluable)

    @property
    def no_violation_items(self) -> tuple[RuleEvaluationItem, ...]:
        return tuple(r for r in self.results if r.is_no_violation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_status": self.analysis_status,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "limit": self.limit,
            "limitations": list(self.limitations),
            "no_violations_count": self.no_violations_count,
            "outcome": self.outcome.to_dict(),
            "repository_path": self.repository_path,
            "results": [r.to_dict() for r in self.results],
            "rules": [r.to_dict() for r in self.rules],
            "truncated": self.truncated,
            "unevaluable_count": self.unevaluable_count,
            "violations_count": self.violations_count,
        }


def _normalize_rel_path(root: Path | None, path: Path | str) -> str:
    p = Path(path)
    if root is not None and p.is_absolute():
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix().replace("\\", "/")


def _matches_pattern(candidate: str, pattern: str) -> bool:
    c_norm = candidate.replace("\\", "/").strip("/")
    p_norm = pattern.replace("\\", "/").strip("/")

    if p_norm == "*" or p_norm == c_norm:
        return True

    c_dotted = c_norm.replace("/", ".")
    p_dotted = p_norm.replace("/", ".")

    if c_dotted == p_dotted or c_dotted.startswith(f"{p_dotted}."):
        return True

    return bool(
        fnmatch.fnmatchcase(c_norm, p_norm) or fnmatch.fnmatchcase(c_dotted, p_dotted)
    )


def _resolve_entities_for_pattern(
    project: Project,
    pattern: str,
    files_by_id: dict[UUID, File],
    file_rel_paths: dict[UUID, str],
    symbols_by_id: dict[UUID, Symbol],
    package_directories: set[str],
) -> tuple[set[UUID], set[str], bool, str | None]:
    if not pattern or not pattern.strip():
        return set(), set(), False, "Pattern cannot be empty"

    p = pattern.strip()
    is_wildcard = "*" in p or "?" in p

    matched_ids: set[UUID] = set()
    matched_pkgs: set[str] = set()

    for pkg_dir in package_directories:
        if _matches_pattern(pkg_dir, p):
            matched_pkgs.add(pkg_dir)
            for f_id, rel_path in file_rel_paths.items():
                if rel_path == pkg_dir or rel_path.startswith(f"{pkg_dir}/"):
                    matched_ids.add(f_id)

    for f_id, rel_path in file_rel_paths.items():
        if _matches_pattern(rel_path, p):
            matched_ids.add(f_id)

    matched_symbol_ids: set[UUID] = set()
    for s_id, sym in symbols_by_id.items():
        file_path = file_rel_paths.get(sym.file_id, "")
        sym_qualified = sym.qualified_name or sym.name
        if (
            _matches_pattern(sym.name, p)
            or _matches_pattern(sym_qualified, p)
            or (file_path and _matches_pattern(f"{file_path}:{sym.name}", p))
        ):
            matched_symbol_ids.add(s_id)
            matched_ids.add(s_id)

    if (
        not is_wildcard
        and not matched_pkgs
        and len(matched_symbol_ids) > 1
        and len({symbols_by_id[s_id].file_id for s_id in matched_symbol_ids}) > 1
    ):
        return (
            set(),
            set(),
            True,
            f"Ambiguous symbol reference '{pattern}': matches multiple symbols across distinct files",
        )

    if not matched_ids and not matched_pkgs:
        if is_wildcard:
            return (
                set(),
                set(),
                False,
                f"Wildcard pattern '{pattern}' matched no entities or packages in the repository",
            )
        return (
            set(),
            set(),
            False,
            f"Referenced entity or package '{pattern}' could not be resolved in the repository",
        )

    return matched_ids, matched_pkgs, False, None


def _get_entity_info(
    entity_id: UUID,
    files_by_id: dict[UUID, File],
    file_rel_paths: dict[UUID, str],
    symbols_by_id: dict[UUID, Symbol],
) -> tuple[str, str | None, int | None]:
    if entity_id in symbols_by_id:
        sym = symbols_by_id[entity_id]
        path = file_rel_paths.get(sym.file_id)
        name = sym.qualified_name or sym.name
        return name, path, sym.start_line

    if entity_id in files_by_id:
        path = file_rel_paths.get(entity_id)
        name = path or str(entity_id)
        return name, path, None

    return str(entity_id), None, None


def evaluate_structural_rules(
    project: Project,
    rules: Sequence[StructuralRule | dict[str, Any]],
    *,
    limit: int | None = None,
    package_policy: PackageBoundaryPolicy | None = None,
) -> StructuralRulesReport:
    root_path = project.root_path or Path(".")
    repo_path = root_path.as_posix()

    files_by_id: dict[UUID, File] = {f.id: f for f in project.files}
    file_rel_paths: dict[UUID, str] = {
        f.id: _normalize_rel_path(project.root_path, f.path) for f in project.files
    }
    symbols_by_id: dict[UUID, Symbol] = {s.id: s for s in project.symbols}

    package_directories: set[str] = set()
    for rel_path in file_rel_paths.values():
        if rel_path.endswith("/__init__.py"):
            package_directories.add(rel_path[: -len("/__init__.py")])
        elif rel_path == "__init__.py":
            package_directories.add(".")

    is_analysis_complete = is_terminal_complete_status(project.analysis_status)
    has_analysis_errors = bool(project.errors)
    analysis_limitation: str | None = None
    if not is_analysis_complete or has_analysis_errors:
        analysis_limitation = (
            f"Repository analysis status is '{project.analysis_status}' "
            f"with {len(project.errors)} error(s); incomplete evidence may conceal violations"
        )

    normalized_rules: list[StructuralRule] = []
    rule_validation_errors: dict[str, str] = {}
    seen_ids: set[str] = set()

    for idx, r in enumerate(rules):
        if isinstance(r, StructuralRule):
            rule_obj = r
        elif isinstance(r, dict):
            rule_id = r.get("rule_id") or r.get("id") or f"rule_{idx + 1}"
            kind = r.get("kind") or r.get("type", "")
            source = r.get("source") or r.get("source_package") or ""
            target = r.get("target") or r.get("target_package")
            rel_type = r.get("relationship_type") or r.get("rel_type")
            desc = r.get("description")
            severity = r.get("severity", "error")
            rule_obj = StructuralRule(
                rule_id=str(rule_id),
                kind=str(kind),
                source=str(source),
                target=str(target) if target else None,
                relationship_type=str(rel_type) if rel_type else None,
                description=str(desc) if desc else None,
                severity=str(severity),
            )
        else:
            rule_id = f"rule_{idx + 1}"
            rule_validation_errors[rule_id] = (
                f"Invalid rule definition format: {type(r)}"
            )
            rule_obj = StructuralRule(
                rule_id=rule_id,
                kind="unknown",
                source="",
            )

        if not rule_obj.kind or rule_obj.kind not in SUPPORTED_RULE_KINDS:
            rule_validation_errors[rule_obj.rule_id] = (
                f"Unsupported or missing rule kind: '{rule_obj.kind}' "
                f"(supported: {sorted(SUPPORTED_RULE_KINDS)})"
            )
        elif not rule_obj.source or not rule_obj.source.strip():
            rule_validation_errors[rule_obj.rule_id] = (
                "Structural rule is missing required 'source'"
            )

        if rule_obj.rule_id in seen_ids:
            rule_validation_errors[rule_obj.rule_id] = (
                f"Duplicate structural rule_id: '{rule_obj.rule_id}'"
            )
        seen_ids.add(rule_obj.rule_id)
        normalized_rules.append(rule_obj)

    results: list[RuleEvaluationItem] = []
    diagnostics: list[DiagnosticItem] = []
    limitations: list[str] = []

    if analysis_limitation:
        limitations.append(analysis_limitation)
        diagnostics.append(
            DiagnosticItem.warning(
                analysis_limitation,
                code="INCOMPLETE_ANALYSIS",
                source="structural_rules",
            )
        )

    for rule in normalized_rules:
        if rule.rule_id in rule_validation_errors:
            err_msg = rule_validation_errors[rule.rule_id]
            diag = DiagnosticItem.warning(
                f"Rule '{rule.rule_id}' is invalid: {err_msg}",
                code="INVALID_RULE",
                source="structural_rules",
            )
            diagnostics.append(diag)
            results.append(
                RuleEvaluationItem(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    outcome=RuleOutcome.UNEVALUABLE.value,
                    message=f"Rule definition invalid: {err_msg}",
                    source=rule.source,
                    target=rule.target,
                    relationship_type=rule.relationship_type,
                    diagnostics=(diag,),
                )
            )
            continue

        src_ids, _src_pkgs, src_ambiguous, src_err = _resolve_entities_for_pattern(
            project,
            rule.source,
            files_by_id,
            file_rel_paths,
            symbols_by_id,
            package_directories,
        )

        if src_err:
            diag_code = (
                "AMBIGUOUS_REFERENCE"
                if src_ambiguous
                else (
                    "UNMATCHED_WILDCARD"
                    if ("*" in rule.source or "?" in rule.source)
                    else "UNKNOWN_REFERENCE"
                )
            )
            diag = DiagnosticItem.warning(
                f"Rule '{rule.rule_id}' source resolution failure: {src_err}",
                code=diag_code,
                source="structural_rules",
            )
            diagnostics.append(diag)
            results.append(
                RuleEvaluationItem(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    outcome=RuleOutcome.UNEVALUABLE.value,
                    message=src_err,
                    source=rule.source,
                    target=rule.target,
                    relationship_type=rule.relationship_type,
                    diagnostics=(diag,),
                )
            )
            continue

        tgt_ids: set[UUID] = set()
        if rule.target is not None:
            (
                tgt_ids,
                _tgt_pkgs,
                tgt_ambiguous,
                tgt_err,
            ) = _resolve_entities_for_pattern(
                project,
                rule.target,
                files_by_id,
                file_rel_paths,
                symbols_by_id,
                package_directories,
            )

            if tgt_err:
                diag_code = (
                    "AMBIGUOUS_REFERENCE"
                    if tgt_ambiguous
                    else (
                        "UNMATCHED_WILDCARD"
                        if ("*" in rule.target or "?" in rule.target)
                        else "UNKNOWN_REFERENCE"
                    )
                )
                diag = DiagnosticItem.warning(
                    f"Rule '{rule.rule_id}' target resolution failure: {tgt_err}",
                    code=diag_code,
                    source="structural_rules",
                )
                diagnostics.append(diag)
                results.append(
                    RuleEvaluationItem(
                        rule_id=rule.rule_id,
                        kind=rule.kind,
                        outcome=RuleOutcome.UNEVALUABLE.value,
                        message=tgt_err,
                        source=rule.source,
                        target=rule.target,
                        relationship_type=rule.relationship_type,
                        diagnostics=(diag,),
                    )
                )
                continue

        violating_relationships: list[Relationship] = []
        evidence_list: list[str] = []
        affected_entities_set: set[str] = set()

        if rule.kind in {
            RuleKind.PROHIBITED_DEPENDENCY.value,
            RuleKind.LAYER_BOUNDARY.value,
            RuleKind.PACKAGE_BOUNDARY.value,
        }:
            if not rule.target:
                diag = DiagnosticItem.warning(
                    f"Rule '{rule.rule_id}' of kind '{rule.kind}' requires a 'target'",
                    code="MISSING_TARGET",
                    source="structural_rules",
                )
                diagnostics.append(diag)
                results.append(
                    RuleEvaluationItem(
                        rule_id=rule.rule_id,
                        kind=rule.kind,
                        outcome=RuleOutcome.UNEVALUABLE.value,
                        message=f"Rule of kind '{rule.kind}' requires a target component",
                        source=rule.source,
                        target=rule.target,
                        diagnostics=(diag,),
                    )
                )
                continue

            for rel in project.relationships:
                rel_type_str = (
                    rel.relationship_type.value
                    if isinstance(rel.relationship_type, RelationshipType)
                    else str(rel.relationship_type)
                )
                if rule.relationship_type and rel_type_str != rule.relationship_type:
                    continue

                source_matched = rel.source_id in src_ids
                target_matched = rel.target_id in tgt_ids

                if not source_matched and rel.source_id in symbols_by_id:
                    source_matched = symbols_by_id[rel.source_id].file_id in src_ids
                if not target_matched and rel.target_id in symbols_by_id:
                    target_matched = symbols_by_id[rel.target_id].file_id in tgt_ids

                if source_matched and target_matched:
                    violating_relationships.append(rel)
                    src_name, src_path, src_line = _get_entity_info(
                        rel.source_id, files_by_id, file_rel_paths, symbols_by_id
                    )
                    tgt_name, tgt_path, _ = _get_entity_info(
                        rel.target_id, files_by_id, file_rel_paths, symbols_by_id
                    )
                    loc_str = (
                        f"{src_path}:{src_line}"
                        if src_line
                        else (src_path or "unknown")
                    )
                    ev = f"{src_name} ({loc_str}) --[{rel_type_str}]--> {tgt_name} ({tgt_path or 'unknown'})"
                    evidence_list.append(ev)
                    affected_entities_set.add(src_name)
                    affected_entities_set.add(tgt_name)

        elif rule.kind == RuleKind.PROHIBITED_RELATIONSHIP.value:
            target_required = rule.target is not None
            expected_type = rule.relationship_type

            for rel in project.relationships:
                rel_type_str = (
                    rel.relationship_type.value
                    if isinstance(rel.relationship_type, RelationshipType)
                    else str(rel.relationship_type)
                )
                if expected_type and rel_type_str != expected_type:
                    continue

                source_matched = rel.source_id in src_ids
                if not source_matched and rel.source_id in symbols_by_id:
                    source_matched = symbols_by_id[rel.source_id].file_id in src_ids

                if not source_matched:
                    continue

                target_matched = True
                if target_required:
                    target_matched = rel.target_id in tgt_ids
                    if not target_matched and rel.target_id in symbols_by_id:
                        target_matched = symbols_by_id[rel.target_id].file_id in tgt_ids

                if source_matched and target_matched:
                    violating_relationships.append(rel)
                    src_name, src_path, src_line = _get_entity_info(
                        rel.source_id, files_by_id, file_rel_paths, symbols_by_id
                    )
                    tgt_name, tgt_path, _ = _get_entity_info(
                        rel.target_id, files_by_id, file_rel_paths, symbols_by_id
                    )
                    loc_str = (
                        f"{src_path}:{src_line}"
                        if src_line
                        else (src_path or "unknown")
                    )
                    ev = f"{src_name} ({loc_str}) --[{rel_type_str}]--> {tgt_name} ({tgt_path or 'unknown'})"
                    evidence_list.append(ev)
                    affected_entities_set.add(src_name)
                    affected_entities_set.add(tgt_name)

        elif rule.kind == RuleKind.ISOLATED_COMPONENT.value:
            for rel in project.relationships:
                rel_type_str = (
                    rel.relationship_type.value
                    if isinstance(rel.relationship_type, RelationshipType)
                    else str(rel.relationship_type)
                )
                is_outgoing = rel.source_id in src_ids or (
                    rel.source_id in symbols_by_id
                    and symbols_by_id[rel.source_id].file_id in src_ids
                )
                is_incoming = rel.target_id in src_ids or (
                    rel.target_id in symbols_by_id
                    and symbols_by_id[rel.target_id].file_id in src_ids
                )

                if is_outgoing or is_incoming:
                    violating_relationships.append(rel)
                    src_name, src_path, src_line = _get_entity_info(
                        rel.source_id, files_by_id, file_rel_paths, symbols_by_id
                    )
                    tgt_name, tgt_path, _ = _get_entity_info(
                        rel.target_id, files_by_id, file_rel_paths, symbols_by_id
                    )
                    loc_str = (
                        f"{src_path}:{src_line}"
                        if src_line
                        else (src_path or "unknown")
                    )
                    ev = (
                        f"Isolated component violated by dependency: {src_name} ({loc_str}) "
                        f"--[{rel_type_str}]--> {tgt_name} ({tgt_path or 'unknown'})"
                    )
                    evidence_list.append(ev)
                    affected_entities_set.add(src_name)
                    affected_entities_set.add(tgt_name)

        evidence_list.sort()
        affected_entities = tuple(sorted(affected_entities_set))

        if violating_relationships:
            first_rel = violating_relationships[0]
            _, first_src_path, first_src_line = _get_entity_info(
                first_rel.source_id, files_by_id, file_rel_paths, symbols_by_id
            )
            _, first_tgt_path, _ = _get_entity_info(
                first_rel.target_id, files_by_id, file_rel_paths, symbols_by_id
            )
            msg = (
                f"Structural violation detected: {len(violating_relationships)} "
                f"prohibited relationship(s) found under rule '{rule.rule_id}'"
            )
            if rule.description:
                msg += f" ({rule.description})"

            diag = DiagnosticItem.error(
                msg,
                code="STRUCTURAL_RULE_VIOLATION",
                path=first_src_path,
                line=first_src_line,
                source="structural_rules",
            )
            diagnostics.append(diag)

            results.append(
                RuleEvaluationItem(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    outcome=RuleOutcome.VIOLATION_DETECTED.value,
                    message=msg,
                    source=rule.source,
                    target=rule.target,
                    relationship_type=rule.relationship_type,
                    evidence=tuple(evidence_list),
                    source_path=first_src_path,
                    line=first_src_line,
                    target_path=first_tgt_path,
                    diagnostics=(diag,),
                    affected_entities=affected_entities,
                    details={"violation_count": len(violating_relationships)},
                )
            )
        elif not is_analysis_complete or has_analysis_errors:
            msg = (
                f"Rule '{rule.rule_id}' could not be reliably evaluated: "
                f"repository analysis is incomplete or reported errors"
            )
            diag = DiagnosticItem.warning(
                msg,
                code="INCOMPLETE_RULE_EVALUATION",
                source="structural_rules",
            )
            diagnostics.append(diag)
            results.append(
                RuleEvaluationItem(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    outcome=RuleOutcome.UNEVALUABLE.value,
                    message=msg,
                    source=rule.source,
                    target=rule.target,
                    relationship_type=rule.relationship_type,
                    diagnostics=(diag,),
                )
            )
        else:
            msg = f"No violation detected for rule '{rule.rule_id}'"
            if rule.description:
                msg += f" ({rule.description})"
            results.append(
                RuleEvaluationItem(
                    rule_id=rule.rule_id,
                    kind=rule.kind,
                    outcome=RuleOutcome.NO_VIOLATION_DETECTED.value,
                    message=msg,
                    source=rule.source,
                    target=rule.target,
                    relationship_type=rule.relationship_type,
                    details={"evaluated_relationships": len(project.relationships)},
                )
            )

    results.sort(key=lambda r: r.rule_id)

    violations_count = sum(1 for r in results if r.is_violation)
    no_violations_count = sum(1 for r in results if r.is_no_violation)
    unevaluable_count = sum(1 for r in results if r.is_unevaluable)

    truncated = False
    displayed_results = tuple(results)
    if limit is not None and len(results) > limit:
        displayed_results = tuple(results[:limit])
        truncated = True

    if not is_analysis_complete:
        outcome_status = OperationStatus.INCOMPLETE
        outcome_msg = (
            f"Structural rule evaluation incomplete: {violations_count} violation(s), "
            f"{unevaluable_count} unevaluable, analysis status '{project.analysis_status}'"
        )
    elif violations_count > 0 or unevaluable_count > 0:
        outcome_status = OperationStatus.PARTIAL
        outcome_msg = (
            f"Structural rule evaluation completed with findings: {violations_count} violation(s), "
            f"{unevaluable_count} unevaluable rule(s)"
        )
    else:
        outcome_status = OperationStatus.SUCCESS
        outcome_msg = f"Structural rule evaluation passed: {no_violations_count} rule(s) evaluated cleanly"

    outcome = OperationOutcome(
        status=outcome_status,
        message=outcome_msg,
        diagnostics=tuple(diagnostics),
        limitations=tuple(sorted(set(limitations))),
    )

    return StructuralRulesReport(
        repository_path=repo_path,
        rules=tuple(normalized_rules),
        results=displayed_results,
        violations_count=violations_count,
        no_violations_count=no_violations_count,
        unevaluable_count=unevaluable_count,
        analysis_status=project.analysis_status,
        truncated=truncated,
        limit=limit,
        diagnostics=tuple(diagnostics),
        limitations=tuple(sorted(set(limitations))),
        outcome=outcome,
    )
