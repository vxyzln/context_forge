"""Verification checklist and test association evidence models.

Provides deterministic, evidence-based test-to-code association discovery
and verification checklist generation for change sets.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from context_forge.comparison.models import is_terminal_complete_status
from context_forge.git.navigation import normalize_relative_path
from context_forge.models.enums import DirectoryType, FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol
from context_forge.pipeline.freshness import (
    FreshnessState,
    WorkflowFreshness,
    WorkflowFreshnessGuard,
)
from context_forge.reporting.contract import DiagnosticItem
from context_forge.scanner.repository import (
    TEST_DIRECTORIES,
    TEST_FILE_PREFIXES,
    TEST_FILE_SUFFIXES,
)

if TYPE_CHECKING:
    from context_forge.query.changeset import (
        ChangeSetImpactResult,
    )

DYNAMIC_COVERAGE_DISCLAIMER: str = (
    "Structural and heuristic test associations indicate potential relevance only and "
    "do not establish runtime execution, test pass/fail status, or behavioral coverage."
)


class TestAssociationClassification(str, Enum):
    __test__ = False
    DIRECT = "direct"
    HEURISTIC = "heuristic"
    UNKNOWN = "unknown"


class ChecklistCategory(str, Enum):
    DETECTED_STRUCTURAL = "detected_structural"
    HEURISTIC_RECOMMENDATION = "heuristic_recommendation"
    ADDITIONAL_VERIFICATION = "additional_verification"
    UNVERIFIED_AREA = "unverified_area"


@dataclass(frozen=True)
class TestAssociationItem:
    __test__ = False
    test_file_path: str
    target_entity_name: str
    classification: str
    rule: str
    evidence: str
    target_entity_id: UUID | None = None
    target_entity_path: str | None = None
    target_kind: str = "root"
    test_file_id: UUID | None = None
    relationship_type: str | None = None
    direction: str | None = None
    confidence: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "direction": self.direction,
            "evidence": self.evidence,
            "relationship_type": self.relationship_type,
            "rule": self.rule,
            "target_entity_id": str(self.target_entity_id)
            if self.target_entity_id
            else None,
            "target_entity_name": self.target_entity_name,
            "target_entity_path": self.target_entity_path,
            "target_kind": self.target_kind,
            "test_file_id": str(self.test_file_id) if self.test_file_id else None,
            "test_file_path": self.test_file_path,
        }


@dataclass(frozen=True)
class ChecklistItem:
    item_id: str
    category: str
    classification: str
    action: str
    rationale: str
    test_file_path: str | None = None
    target_entities: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    suggested_command: str | None = None
    executed: bool = False
    execution_status: str = "unexecuted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "category": self.category,
            "classification": self.classification,
            "executed": self.executed,
            "execution_status": self.execution_status,
            "item_id": self.item_id,
            "rationale": self.rationale,
            "suggested_command": self.suggested_command,
            "supporting_evidence": list(self.supporting_evidence),
            "target_entities": list(self.target_entities),
            "test_file_path": self.test_file_path,
        }


@dataclass(frozen=True)
class VerificationChecklist:
    change_inputs: tuple[str, ...]
    resolved_inputs: tuple[Any, ...]
    items: tuple[ChecklistItem, ...]
    analysis_status: str
    freshness_state: str
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    disclaimer: str = DYNAMIC_COVERAGE_DISCLAIMER

    @property
    def detected_structural_tests(self) -> tuple[ChecklistItem, ...]:
        return tuple(
            it
            for it in self.items
            if it.category == ChecklistCategory.DETECTED_STRUCTURAL.value
        )

    @property
    def heuristic_tests(self) -> tuple[ChecklistItem, ...]:
        return tuple(
            it
            for it in self.items
            if it.category == ChecklistCategory.HEURISTIC_RECOMMENDATION.value
        )

    @property
    def additional_verifications(self) -> tuple[ChecklistItem, ...]:
        return tuple(
            it
            for it in self.items
            if it.category == ChecklistCategory.ADDITIONAL_VERIFICATION.value
        )

    @property
    def unverified_areas(self) -> tuple[ChecklistItem, ...]:
        return tuple(
            it
            for it in self.items
            if it.category == ChecklistCategory.UNVERIFIED_AREA.value
        )

    @property
    def suggested_commands(self) -> tuple[str, ...]:
        seen: set[str] = set()
        cmds: list[str] = []
        for it in self.items:
            if it.suggested_command and it.suggested_command not in seen:
                seen.add(it.suggested_command)
                cmds.append(it.suggested_command)
        return tuple(cmds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "additional_verifications": [
                it.to_dict() for it in self.additional_verifications
            ],
            "analysis_status": self.analysis_status,
            "change_inputs": list(self.change_inputs),
            "detected_structural_tests": [
                it.to_dict() for it in self.detected_structural_tests
            ],
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "disclaimer": self.disclaimer,
            "freshness_state": self.freshness_state,
            "heuristic_tests": [it.to_dict() for it in self.heuristic_tests],
            "items": [it.to_dict() for it in self.items],
            "limitations": list(self.limitations),
            "resolved_inputs": [
                r.to_dict() if hasattr(r, "to_dict") else str(r)
                for r in self.resolved_inputs
            ],
            "suggested_commands": list(self.suggested_commands),
            "unverified_areas": [it.to_dict() for it in self.unverified_areas],
        }


def _is_test_file_entity(file: File, project: Project | None = None) -> bool:
    """Determine if a File is a test file based on type, directory, or filename patterns."""
    if file.file_type == FileType.TEST:
        return True

    if project is not None and file.directory_id:
        for d in project.directories:
            if d.id == file.directory_id and d.directory_type == DirectoryType.TESTS:
                return True

    norm = normalize_relative_path(file.path.as_posix()).lower()
    parts = norm.split("/")
    filename = parts[-1]

    if any(d in TEST_DIRECTORIES for d in parts):
        return True
    if any(filename.startswith(p) for p in TEST_FILE_PREFIXES):
        return True
    return bool(
        any(filename.endswith(s) for s in TEST_FILE_SUFFIXES)
        or filename.endswith("_test")
    )


def _is_test_path_str(path_str: str) -> bool:
    norm = normalize_relative_path(path_str).lower()
    parts = norm.split("/")
    filename = parts[-1]
    if any(d in TEST_DIRECTORIES for d in parts):
        return True
    if any(filename.startswith(p) for p in TEST_FILE_PREFIXES):
        return True
    return bool(
        any(filename.endswith(s) for s in TEST_FILE_SUFFIXES)
        or filename.endswith("_test")
    )


def identify_test_associations(
    project: Project,
    targets: Sequence[
        tuple[UUID, str, str | None, str]
    ],  # (id, name, path, target_kind)
    *,
    relationship_types: set[str] | None = None,
) -> tuple[
    tuple[TestAssociationItem, ...],
    tuple[TestAssociationItem, ...],
    tuple[TestAssociationItem, ...],
]:
    """Identify direct, heuristic, and unknown test-to-code associations for the given targets.

    Returns:
        (direct_associations, heuristic_associations, unknown_associations)
    """
    files_by_id: dict[UUID, File] = {f.id: f for f in project.files}
    symbols_by_id: dict[UUID, Symbol] = {s.id: s for s in project.symbols}
    test_files: list[File] = [
        f for f in project.files if _is_test_file_entity(f, project)
    ]
    test_file_ids: set[UUID] = {f.id for f in test_files}

    # Group symbols by file_id for quick symbol-level lookup
    symbols_by_file: dict[UUID, list[Symbol]] = {}
    for s in project.symbols:
        symbols_by_file.setdefault(s.file_id, []).append(s)

    types_filter = (
        frozenset(str(t).lower() for t in relationship_types)
        if relationship_types is not None
        else None
    )

    target_ids: set[UUID] = {t[0] for t in targets}
    targets_by_id: dict[UUID, tuple[UUID, str, str | None, str]] = {
        t[0]: t for t in targets
    }

    # 1. Direct Structural Associations from project.relationships
    # Group by (test_file_id, target_entity_id) to aggregate multiple/duplicate relationships
    direct_rels_by_pair: dict[tuple[UUID, UUID], list[tuple[str, str, str]]] = {}
    direct_test_files: dict[UUID, File] = {}
    direct_targets_info: dict[UUID, tuple[UUID, str, str | None, str]] = {}

    for rel in project.relationships:
        rel_type = (
            rel.relationship_type.value
            if hasattr(rel.relationship_type, "value")
            else str(rel.relationship_type)
        ).lower()
        if types_filter is not None and rel_type not in types_filter:
            continue

        src_is_test = rel.source_id in test_file_ids
        tgt_is_test = rel.target_id in test_file_ids

        # If source is in test file (symbol or file)
        if not src_is_test:
            src_sym = symbols_by_id.get(rel.source_id)
            if src_sym and src_sym.file_id in test_file_ids:
                src_is_test = True

        # If target is in test file (symbol or file)
        if not tgt_is_test:
            tgt_sym = symbols_by_id.get(rel.target_id)
            if tgt_sym and tgt_sym.file_id in test_file_ids:
                tgt_is_test = True

        # Check if source is a test pointing to an affected target
        if src_is_test and rel.target_id in target_ids:
            tgt_info = targets_by_id[rel.target_id]
            test_f = files_by_id.get(rel.source_id)
            if not test_f:
                s_sym = symbols_by_id.get(rel.source_id)
                test_f = files_by_id.get(s_sym.file_id) if s_sym else None
            if test_f:
                pair = (test_f.id, rel.target_id)
                ev = (
                    f"Confirmed graph relationship '{rel_type}' from test '{test_f.path.as_posix()}' "
                    f"to affected component '{tgt_info[1]}'"
                )
                direct_rels_by_pair.setdefault(pair, []).append(
                    (rel_type, "outgoing_from_test", ev)
                )
                direct_test_files[test_f.id] = test_f
                direct_targets_info[rel.target_id] = tgt_info

        # Check if target is a test receiving a relationship from an affected target
        if tgt_is_test and rel.source_id in target_ids:
            tgt_info = targets_by_id[rel.source_id]
            test_f = files_by_id.get(rel.target_id)
            if not test_f:
                s_sym = symbols_by_id.get(rel.target_id)
                test_f = files_by_id.get(s_sym.file_id) if s_sym else None
            if test_f:
                pair = (test_f.id, rel.source_id)
                ev = (
                    f"Confirmed graph relationship '{rel_type}' from affected component "
                    f"'{tgt_info[1]}' to test '{test_f.path.as_posix()}'"
                )
                direct_rels_by_pair.setdefault(pair, []).append(
                    (rel_type, "incoming_to_test", ev)
                )
                direct_test_files[test_f.id] = test_f
                direct_targets_info[rel.source_id] = tgt_info

    direct_associations: list[TestAssociationItem] = []
    direct_keys: set[tuple[str, UUID]] = set()

    # Sort pairs deterministically: test_file_path, target_name, target_id.hex
    sorted_pairs = sorted(
        direct_rels_by_pair.keys(),
        key=lambda pair: (
            direct_test_files[pair[0]].path.as_posix(),
            direct_targets_info[pair[1]][1],
            pair[1].hex,
        ),
    )

    for test_f_id, tgt_id in sorted_pairs:
        raw_rels = direct_rels_by_pair[(test_f_id, tgt_id)]
        # Deduplicate exact duplicate relationship tuples while preserving insertion order
        unique_rels = list(dict.fromkeys(raw_rels))

        test_f = direct_test_files[test_f_id]
        tgt_info = direct_targets_info[tgt_id]
        tf_path = test_f.path.as_posix()

        # Suppress heuristic matching for this test and target
        direct_keys.add((tf_path, tgt_id))

        distinct_rel_types = sorted({r[0] for r in unique_rels})
        distinct_directions = sorted({r[1] for r in unique_rels})
        distinct_evidences = sorted({r[2] for r in unique_rels})

        rel_type_str = ", ".join(distinct_rel_types)
        dir_str = ", ".join(distinct_directions)
        evidence_str = "; ".join(distinct_evidences)
        rule_str = (
            f"structural_{distinct_rel_types[0]}"
            if len(distinct_rel_types) == 1
            else f"structural_{'_'.join(distinct_rel_types)}"
        )

        direct_associations.append(
            TestAssociationItem(
                test_file_path=tf_path,
                test_file_id=test_f.id,
                target_entity_id=tgt_info[0],
                target_entity_name=tgt_info[1],
                target_entity_path=tgt_info[2],
                target_kind=tgt_info[3],
                classification=TestAssociationClassification.DIRECT.value,
                rule=rule_str,
                relationship_type=rel_type_str,
                direction=dir_str,
                evidence=evidence_str,
                confidence="high",
            )
        )

    # 2. Heuristic Associations
    # Rules:
    # A) naming_convention: Test file stem matches target file stem (e.g. test_foo.py / foo_test.py for foo.py)
    # B) symbol_name_match: Test symbol in test file matches target symbol (e.g. test_bar for bar)
    heuristic_associations: list[TestAssociationItem] = []
    heuristic_keys: set[tuple[str, UUID]] = set()

    for tgt_id, tgt_name, tgt_path, tgt_kind in targets:
        target_stem: str | None = None
        target_sym_names: set[str] = set()

        if tgt_path:
            p = Path(tgt_path)
            target_stem = p.stem.lower()

        # Check if target itself is a symbol
        sym = symbols_by_id.get(tgt_id)
        if sym:
            target_sym_names.add(sym.name.lower())
            if not target_stem and sym.file_id in files_by_id:
                target_stem = files_by_id[sym.file_id].path.stem.lower()
        elif tgt_id in files_by_id:
            # File target: gather all symbol names in this file
            file_syms = symbols_by_file.get(tgt_id, [])
            for fs in file_syms:
                target_sym_names.add(fs.name.lower())

        for tf in test_files:
            tf_path = tf.path.as_posix()
            key = (tf_path, tgt_id)
            if key in direct_keys or key in heuristic_keys:
                continue

            tf_stem = tf.path.stem.lower()
            matched_rule: str | None = None
            evidence_str: str | None = None

            # Heuristic Rule 1: Naming convention match
            if target_stem:
                candidate_test_stems = {
                    f"test_{target_stem}",
                    f"{target_stem}_test",
                }
                if tf_stem in candidate_test_stems or tf_stem == target_stem:
                    matched_rule = "naming_convention"
                    evidence_str = (
                        f"Test file '{tf_path}' matches naming convention for "
                        f"target '{tgt_name}' (rule: naming_convention)"
                    )

            # Heuristic Rule 2: Symbol name match (if naming convention didn't match)
            if not matched_rule and target_sym_names:
                tf_symbols = symbols_by_file.get(tf.id, [])
                for tfs in tf_symbols:
                    tfs_lower = tfs.name.lower()
                    for sn in target_sym_names:
                        if (
                            tfs_lower == f"test_{sn}"
                            or tfs_lower == f"{sn}_test"
                            or tfs_lower.startswith(f"test_{sn}_")
                        ):
                            matched_rule = "symbol_name_match"
                            evidence_str = (
                                f"Test symbol '{tfs.name}' in '{tf_path}' matches target "
                                f"symbol '{sn}' (rule: symbol_name_match)"
                            )
                            break
                    if matched_rule:
                        break

            if matched_rule and evidence_str:
                heuristic_keys.add(key)
                heuristic_associations.append(
                    TestAssociationItem(
                        test_file_path=tf_path,
                        test_file_id=tf.id,
                        target_entity_id=tgt_id,
                        target_entity_name=tgt_name,
                        target_entity_path=tgt_path,
                        target_kind=tgt_kind,
                        classification=TestAssociationClassification.HEURISTIC.value,
                        rule=matched_rule,
                        evidence=evidence_str,
                        confidence="medium",
                    )
                )

    # 3. Unknown / Unassociated Targets
    unknown_associations: list[TestAssociationItem] = []
    associated_target_ids = {k[1] for k in direct_keys} | {k[1] for k in heuristic_keys}

    for tgt_id, tgt_name, tgt_path, tgt_kind in targets:
        if tgt_id not in associated_target_ids:
            unknown_associations.append(
                TestAssociationItem(
                    test_file_path="",
                    test_file_id=None,
                    target_entity_id=tgt_id,
                    target_entity_name=tgt_name,
                    target_entity_path=tgt_path,
                    target_kind=tgt_kind,
                    classification=TestAssociationClassification.UNKNOWN.value,
                    rule="unassociated",
                    evidence=(
                        f"Available structural and heuristic evidence did not identify test "
                        f"associations for target '{tgt_name}'"
                    ),
                    confidence="none",
                )
            )

    # Sort deterministically
    sorted_direct = tuple(
        sorted(
            direct_associations,
            key=lambda a: (a.test_file_path, a.target_entity_name, a.rule),
        )
    )
    sorted_heuristic = tuple(
        sorted(
            heuristic_associations,
            key=lambda a: (a.test_file_path, a.target_entity_name, a.rule),
        )
    )
    sorted_unknown = tuple(
        sorted(
            unknown_associations,
            key=lambda a: (a.target_entity_name, a.target_entity_path or ""),
        )
    )

    return sorted_direct, sorted_heuristic, sorted_unknown


def generate_verification_checklist(
    project: Project,
    paths: Sequence[str | Path],
    *,
    impact_result: ChangeSetImpactResult | None = None,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    max_depth: int = 2,
    limit: int | None = 100,
) -> VerificationChecklist:
    """Generate a deterministic verification checklist for the given changed paths."""
    from context_forge.query.changeset import analyze_changeset

    supplied_paths = tuple(str(p) for p in paths)

    # If impact_result is not passed, compute it via analyze_changeset with include_checklist=False
    if impact_result is None:
        impact = analyze_changeset(
            project,
            paths,
            direction=direction,
            relationship_types=relationship_types,
            max_depth=max_depth,
            limit=limit,
            include_checklist=False,
        )
    else:
        impact = impact_result

    # Freshness assessment
    freshness_state = FreshnessState.INDETERMINATE.value
    freshness_diagnostics: list[DiagnosticItem] = []
    freshness_limitations: list[str] = []
    wf: WorkflowFreshness | None = None

    if not project.root_path or not project.root_path.exists():
        freshness_state = FreshnessState.INDETERMINATE.value
        freshness_limitations.append(
            "Project has no accessible root_path; repository freshness cannot be assessed."
        )
    else:
        try:
            guard = WorkflowFreshnessGuard(project.root_path)
            wf = guard.assess_freshness(project=project)
            freshness_state = wf.state.value
            if wf.diagnostics:
                freshness_diagnostics.extend(wf.diagnostics)
            if wf.limitations:
                freshness_limitations.extend(wf.limitations)
        except (
            sqlite3.Error,
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            AttributeError,
        ) as exc:
            freshness_state = FreshnessState.INDETERMINATE.value
            diag = DiagnosticItem.warning(
                f"Freshness assessment failed: {exc}",
                code="FRESHNESS_CHECK_FAILED",
                source="freshness",
            )
            freshness_diagnostics.append(diag)
            freshness_limitations.append(
                f"Freshness assessment encountered an error: {exc}; freshness is indeterminate."
            )

    is_complete_project = (
        is_terminal_complete_status(project.analysis_status) and not project.errors
    )
    analysis_status = project.analysis_status if is_complete_project else "incomplete"

    # Gather targets: direct roots and downstream impacted items
    targets: list[tuple[UUID, str, str | None, str]] = []
    seen_target_ids: set[UUID] = set()

    for r in impact.resolved_inputs:
        if (
            r.is_resolved
            and r.target is not None
            and r.target.id not in seen_target_ids
        ):
            seen_target_ids.add(r.target.id)
            targets.append((r.target.id, r.target.name, r.target.path, "root"))

    # Reuse full computed affected items if available (Defect C: Truncation guarantee)
    all_downstream_items = (
        impact._all_items
        if hasattr(impact, "_all_items") and impact._all_items is not None
        else impact.items
    )
    for it in all_downstream_items:
        if it.classification == "downstream" and it.entity_id not in seen_target_ids:
            seen_target_ids.add(it.entity_id)
            targets.append((it.entity_id, it.name, it.path, "downstream"))

    direct_assocs, heuristic_assocs, unknown_assocs = identify_test_associations(
        project,
        targets,
        relationship_types=relationship_types,
    )

    checklist_items: list[ChecklistItem] = []

    # Category A: Detected Structural Relationships
    # Deduplicate by test_file_path across all targets
    direct_by_test: dict[str, list[TestAssociationItem]] = {}
    for da in direct_assocs:
        direct_by_test.setdefault(da.test_file_path, []).append(da)

    for tf_path, assocs in sorted(direct_by_test.items(), key=lambda kv: kv[0]):
        affected_targets = tuple(sorted({a.target_entity_name for a in assocs}))
        evidence_list = tuple(sorted({a.evidence for a in assocs}))
        targets_str = ", ".join(affected_targets)
        checklist_items.append(
            ChecklistItem(
                item_id=f"structural:{tf_path}",
                category=ChecklistCategory.DETECTED_STRUCTURAL.value,
                classification="direct",
                test_file_path=tf_path,
                target_entities=affected_targets,
                action=f"Run structural test suite: {tf_path} (verifies {targets_str})",
                rationale=(
                    f"Structural relationship confirmed in repository graph connecting test "
                    f"to {len(affected_targets)} affected component(s)."
                ),
                supporting_evidence=evidence_list,
                suggested_command=f"pytest {tf_path}",
                executed=False,
                execution_status="unexecuted",
            )
        )

    # Category B: Heuristic Recommendations
    # Deduplicate by test_file_path, excluding tests already in Category A
    heuristic_by_test: dict[str, list[TestAssociationItem]] = {}
    for ha in heuristic_assocs:
        if ha.test_file_path not in direct_by_test:
            heuristic_by_test.setdefault(ha.test_file_path, []).append(ha)

    for tf_path, assocs in sorted(heuristic_by_test.items(), key=lambda kv: kv[0]):
        affected_targets = tuple(sorted({a.target_entity_name for a in assocs}))
        rules = tuple(sorted({a.rule for a in assocs}))
        evidence_list = tuple(sorted({a.evidence for a in assocs}))
        targets_str = ", ".join(affected_targets)
        rules_str = ", ".join(rules)
        checklist_items.append(
            ChecklistItem(
                item_id=f"heuristic:{tf_path}",
                category=ChecklistCategory.HEURISTIC_RECOMMENDATION.value,
                classification="heuristic",
                test_file_path=tf_path,
                target_entities=affected_targets,
                action=f"Run heuristic test suite: {tf_path} (inferred for {targets_str})",
                rationale=(
                    f"Heuristic association inferred via {rules_str} without explicit "
                    f"graph relationship."
                ),
                supporting_evidence=evidence_list,
                suggested_command=f"pytest {tf_path}",
                executed=False,
                execution_status="unexecuted",
            )
        )

    # Category C: Additional Verification
    # 1. Author tests for modified root components lacking any test associations
    unassociated_roots = [ua for ua in unknown_assocs if ua.target_kind == "root"]
    for ua in sorted(unassociated_roots, key=lambda u: u.target_entity_name):
        checklist_items.append(
            ChecklistItem(
                item_id=f"missing_test:{ua.target_entity_name}",
                category=ChecklistCategory.ADDITIONAL_VERIFICATION.value,
                classification="suggested",
                test_file_path=None,
                target_entities=(ua.target_entity_name,),
                action=f"Author or expand automated test coverage for '{ua.target_entity_name}'",
                rationale=(
                    f"Target '{ua.target_entity_name}' was modified or impacted but available "
                    f"structural and heuristic evidence did not identify associated tests."
                ),
                supporting_evidence=(ua.evidence,),
                suggested_command=None,
                executed=False,
                execution_status="unexecuted",
            )
        )

    # 2. Consolidated test suite command if 2 or more distinct test files exist
    all_test_files = sorted(set(direct_by_test.keys()) | set(heuristic_by_test.keys()))
    if len(all_test_files) >= 2:
        checklist_items.append(
            ChecklistItem(
                item_id="consolidated_test_run",
                category=ChecklistCategory.ADDITIONAL_VERIFICATION.value,
                classification="suggested",
                test_file_path=None,
                target_entities=tuple(
                    sorted(
                        {a.target_entity_name for a in direct_assocs + heuristic_assocs}
                    )
                ),
                action=(
                    f"Run consolidated verification suite covering all associated tests "
                    f"({len(all_test_files)} test files)"
                ),
                rationale="Execute all associated structural and heuristic test suites together.",
                supporting_evidence=(),
                suggested_command=f"pytest {' '.join(all_test_files)}",
                executed=False,
                execution_status="unexecuted",
            )
        )

    # Category D: Unverified Areas & Diagnostics
    # 1. Unresolved input paths
    for r in impact.resolved_inputs:
        if not r.is_resolved:
            checklist_items.append(
                ChecklistItem(
                    item_id=f"unresolved_path:{r.original_input}",
                    category=ChecklistCategory.UNVERIFIED_AREA.value,
                    classification="unknown",
                    test_file_path=None,
                    target_entities=(r.original_input,),
                    action=f"Verify unresolved change-set path: '{r.original_input}' ({r.reason})",
                    rationale=f"Input could not be resolved against repository inventory (status: {r.status}).",
                    supporting_evidence=tuple(r.limitations),
                    suggested_command=None,
                    executed=False,
                    execution_status="unexecuted",
                )
            )

    # 2. Incomplete analysis state
    if not is_complete_project:
        error_count = len(project.errors)
        checklist_items.append(
            ChecklistItem(
                item_id="incomplete_analysis",
                category=ChecklistCategory.UNVERIFIED_AREA.value,
                classification="unknown",
                test_file_path=None,
                target_entities=(),
                action="Re-analyze repository to establish complete dependency graph and test associations",
                rationale=(
                    f"Repository analysis status is '{project.analysis_status}' (errors: {error_count}); "
                    f"missing symbols, relationships, or recorded errors may affect test associations."
                ),
                supporting_evidence=tuple(project.errors) if project.errors else (),
                suggested_command=None,
                executed=False,
                execution_status="unexecuted",
            )
        )

    # 3. Freshness state handling for non-current states (Defect A)
    if freshness_state == FreshnessState.STALE.value:
        stale_reason = wf.reason if wf else "source changes detected"
        checklist_items.append(
            ChecklistItem(
                item_id="stale_freshness",
                category=ChecklistCategory.UNVERIFIED_AREA.value,
                classification="unknown",
                test_file_path=None,
                target_entities=(),
                action="Refresh repository analysis before relying on verification checklist",
                rationale=(
                    f"Repository analysis is stale ({stale_reason}); source changes may not be "
                    f"reflected in cached analysis and structural test associations may be outdated."
                ),
                supporting_evidence=tuple(freshness_limitations),
                suggested_command=None,
                executed=False,
                execution_status="unexecuted",
            )
        )
    elif freshness_state == FreshnessState.INCOMPLETE.value:
        inc_reason = wf.reason if wf else "analysis incomplete"
        checklist_items.append(
            ChecklistItem(
                item_id="incomplete_freshness",
                category=ChecklistCategory.UNVERIFIED_AREA.value,
                classification="unknown",
                test_file_path=None,
                target_entities=(),
                action="Re-analyze repository to resolve incomplete analysis state",
                rationale=(
                    f"Repository analysis is incomplete ({inc_reason}); missing symbols, "
                    f"relationships, or recorded errors may affect test associations."
                ),
                supporting_evidence=tuple(freshness_limitations),
                suggested_command=None,
                executed=False,
                execution_status="unexecuted",
            )
        )
    elif freshness_state == FreshnessState.INDETERMINATE.value:
        ind_reason = wf.reason if wf else "freshness could not be verified"
        checklist_items.append(
            ChecklistItem(
                item_id="indeterminate_freshness",
                category=ChecklistCategory.UNVERIFIED_AREA.value,
                classification="unknown",
                test_file_path=None,
                target_entities=(),
                action="Verify repository analysis state and index before relying on checklist",
                rationale=(
                    f"Repository freshness could not be established reliably ({ind_reason}); "
                    f"checklist test associations should be treated as unverified."
                ),
                supporting_evidence=tuple(freshness_limitations),
                suggested_command=None,
                executed=False,
                execution_status="unexecuted",
            )
        )

    # 4. Truncated impact coverage handling (Defect C)
    if impact.truncated:
        if hasattr(impact, "_all_items") and impact._all_items is not None:
            freshness_limitations.append(
                f"Impact display was limited to {impact.limit} of {impact.total} affected components; "
                f"verification checklist accounts for all {impact.total} computed affected components."
            )
        else:
            freshness_limitations.append(
                f"Checklist coverage is partial: impact display was truncated to {impact.limit} "
                f"of {impact.total} components and complete downstream entities were not available."
            )
            checklist_items.append(
                ChecklistItem(
                    item_id="truncated_impact_coverage",
                    category=ChecklistCategory.UNVERIFIED_AREA.value,
                    classification="unknown",
                    test_file_path=None,
                    target_entities=(),
                    action="Re-run analysis with higher limit to verify omitted downstream components",
                    rationale=(
                        f"Impact display was truncated to {impact.limit} of {impact.total} components; "
                        f"some downstream components could not be evaluated for test associations."
                    ),
                    supporting_evidence=(),
                    suggested_command=None,
                    executed=False,
                    execution_status="unexecuted",
                )
            )

    # 5. Unassociated targets note
    if unknown_assocs:
        unassoc_names = sorted({ua.target_entity_name for ua in unknown_assocs})
        checklist_items.append(
            ChecklistItem(
                item_id="unassociated_targets",
                category=ChecklistCategory.UNVERIFIED_AREA.value,
                classification="unknown",
                test_file_path=None,
                target_entities=tuple(unassoc_names),
                action=(
                    f"Perform manual verification for {len(unassoc_names)} component(s) "
                    f"lacking automated test associations"
                ),
                rationale=(
                    f"Available structural and heuristic evidence did not identify test associations for: "
                    f"{', '.join(unassoc_names)}"
                ),
                supporting_evidence=(),
                suggested_command=None,
                executed=False,
                execution_status="unexecuted",
            )
        )

    # Category ordering for deterministic sorting:
    category_rank = {
        ChecklistCategory.DETECTED_STRUCTURAL.value: 1,
        ChecklistCategory.HEURISTIC_RECOMMENDATION.value: 2,
        ChecklistCategory.ADDITIONAL_VERIFICATION.value: 3,
        ChecklistCategory.UNVERIFIED_AREA.value: 4,
    }

    sorted_items = tuple(
        sorted(
            checklist_items,
            key=lambda it: (category_rank.get(it.category, 99), it.item_id),
        )
    )

    # Aggregate limitations
    limitations_list: list[str] = list(impact.limitations)
    limitations_list.extend(freshness_limitations)
    limitations_list.append(DYNAMIC_COVERAGE_DISCLAIMER)
    if not is_complete_project:
        limitations_list.append(
            "Verification checklist generated with incomplete repository analysis; "
            "test associations may be partial."
        )
    if unknown_assocs:
        limitations_list.append(
            f"{len(unknown_assocs)} changed/impacted component(s) lack confirmed "
            f"or heuristic test associations."
        )

    # Combine diagnostics without putting DiagnosticItem in a set (details is a dict)
    all_diagnostics = list(impact.diagnostics) + freshness_diagnostics
    seen_diag: set[tuple[str, str, str, str]] = set()
    unique_diagnostics: list[DiagnosticItem] = []
    for d in all_diagnostics:
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

    return VerificationChecklist(
        change_inputs=supplied_paths,
        resolved_inputs=impact.resolved_inputs,
        items=sorted_items,
        analysis_status=analysis_status,
        freshness_state=freshness_state,
        diagnostics=sorted_diagnostics,
        limitations=tuple(sorted(set(limitations_list))),
        disclaimer=DYNAMIC_COVERAGE_DISCLAIMER,
    )
