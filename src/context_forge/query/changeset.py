from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.comparison.models import is_terminal_complete_status
from context_forge.git.navigation import normalize_relative_path
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.query.impact import (
    DEFAULT_IMPACT_LIMIT,
    DEFAULT_IMPACT_MAX_DEPTH,
    DEFAULT_IMPACT_RELATIONSHIP_TYPES,
    ImpactPathStep,
    ResolvedTarget,
    TargetCandidate,
    _path_sort_key,
    _relationship_type_value,
    resolve_impact_target,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)


@dataclass(frozen=True)
class ChangeSetInputResolution:
    original_input: str
    status: str
    normalized_path: str | None = None
    target: ResolvedTarget | None = None
    candidates: tuple[TargetCandidate, ...] = ()
    reason: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved" and self.target is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "limitations": list(self.limitations),
            "normalized_path": self.normalized_path,
            "original_input": self.original_input,
            "reason": self.reason,
            "status": self.status,
            "target": self.target.to_dict() if self.target is not None else None,
        }


@dataclass(frozen=True)
class ChangeSetProvenance:
    root_path: str
    root_id: UUID
    depth: int
    classification: str
    path: tuple[ImpactPathStep, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "depth": self.depth,
            "path": [p.to_dict() for p in self.path],
            "root_id": str(self.root_id),
            "root_path": self.root_path,
        }


@dataclass(frozen=True)
class ChangeSetImpactItem:
    entity_id: UUID
    entity_type: str
    name: str
    path: str | None
    kind: str | None
    qualified_name: str | None
    classification: str
    min_depth: int
    roots: tuple[str, ...]
    provenance: tuple[ChangeSetProvenance, ...]
    shortest_path: tuple[ImpactPathStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "entity_id": str(self.entity_id),
            "entity_type": self.entity_type,
            "kind": self.kind,
            "min_depth": self.min_depth,
            "name": self.name,
            "path": self.path,
            "provenance": [p.to_dict() for p in self.provenance],
            "qualified_name": self.qualified_name,
            "roots": list(self.roots),
            "shortest_path": [step.to_dict() for step in self.shortest_path],
        }


@dataclass(frozen=True)
class RelevantTestItem:
    test_file_path: str
    test_file_id: UUID
    relationship_type: str
    target_entity_id: UUID
    target_entity_name: str
    target_entity_path: str | None
    direction: str
    evidence: str
    classification: str = "direct"
    rule: str | None = None
    target_kind: str = "direct_root"

    def to_dict(self) -> dict[str, Any]:
        result = {
            "direction": self.direction,
            "evidence": self.evidence,
            "relationship_type": self.relationship_type,
            "target_entity_id": str(self.target_entity_id),
            "target_entity_name": self.target_entity_name,
            "target_entity_path": self.target_entity_path,
            "test_file_id": str(self.test_file_id),
            "test_file_path": self.test_file_path,
        }
        if self.classification is not None:
            result["classification"] = self.classification
        if self.rule is not None:
            result["rule"] = self.rule
        if self.target_kind is not None:
            result["target_kind"] = self.target_kind
        return result


@dataclass(frozen=True)
class ChangeSetImpactResult:
    status: str
    supplied_paths: tuple[str, ...]
    resolved_inputs: tuple[ChangeSetInputResolution, ...]
    items: tuple[ChangeSetImpactItem, ...]
    total: int
    direct_count: int
    downstream_count: int
    truncated: bool
    limit: int | None
    max_depth: int
    depth_reached: int
    direction: str
    relationship_types: tuple[str, ...]
    relevant_tests: tuple[RelevantTestItem, ...] = ()
    verification_checklist: Any | None = None
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    message: str = ""
    outcome: OperationOutcome = field(
        default_factory=lambda: OperationOutcome.success()
    )
    _all_items: tuple[ChangeSetImpactItem, ...] | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def direct_items(self) -> tuple[ChangeSetImpactItem, ...]:
        return tuple(it for it in self.items if it.classification == "direct")

    @property
    def downstream_items(self) -> tuple[ChangeSetImpactItem, ...]:
        return tuple(it for it in self.items if it.classification == "downstream")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "depth_reached": self.depth_reached,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "direct_count": self.direct_count,
            "direction": self.direction,
            "downstream_count": self.downstream_count,
            "items": [it.to_dict() for it in self.items],
            "limit": self.limit,
            "limitations": list(self.limitations),
            "max_depth": self.max_depth,
            "message": self.message,
            "outcome": self.outcome.to_dict(),
            "relationship_types": list(self.relationship_types),
            "relevant_tests": [t.to_dict() for t in self.relevant_tests],
            "resolved_inputs": [r.to_dict() for r in self.resolved_inputs],
            "status": self.status,
            "supplied_paths": list(self.supplied_paths),
            "total": self.total,
            "truncated": self.truncated,
        }
        if self.verification_checklist is not None:
            result["verification_checklist"] = (
                self.verification_checklist.to_dict()
                if hasattr(self.verification_checklist, "to_dict")
                else self.verification_checklist
            )
        return result


def resolve_changeset_path(
    project: Project,
    path_str: str,
) -> ChangeSetInputResolution:
    raw = path_str.strip()
    if not raw:
        return ChangeSetInputResolution(
            original_input=path_str,
            status="invalid",
            reason="Path input cannot be empty",
            limitations=("Empty path supplied in change set",),
        )

    root_path = project.root_path.resolve() if project.root_path else Path.cwd()
    norm = normalize_relative_path(raw)
    segments = norm.split("/")

    is_windows_abs = len(norm) >= 2 and norm[1] == ":" and norm[0].isalpha()
    if norm.startswith("/") or is_windows_abs or ".." in segments:
        p = Path(raw)
        if p.is_absolute():
            try:
                rel = p.resolve().relative_to(root_path).as_posix()
                norm = normalize_relative_path(rel)
            except ValueError:
                return ChangeSetInputResolution(
                    original_input=path_str,
                    status="outside_root",
                    reason=f"Path '{path_str}' escapes repository root",
                    limitations=(
                        f"Path '{path_str}' is outside permitted project root",
                    ),
                )
        else:
            return ChangeSetInputResolution(
                original_input=path_str,
                status="outside_root",
                reason=f"Path '{path_str}' escapes repository root",
                limitations=(
                    f"Path '{path_str}' escapes repository root via relative segments",
                ),
            )

    matching_files = [
        f for f in project.files if normalize_relative_path(f.path.as_posix()) == norm
    ]

    if len(matching_files) == 1:
        f = matching_files[0]
        exists_on_disk = (root_path / f.path).is_file()
        limitations: list[str] = []
        if not exists_on_disk:
            limitations.append(
                f"File '{f.path.as_posix()}' exists in project inventory, but is absent on disk"
            )
        return ChangeSetInputResolution(
            original_input=path_str,
            status="resolved",
            normalized_path=f.path.as_posix(),
            target=ResolvedTarget(
                id=f.id,
                target_type="file",
                name=f.name,
                path=f.path.as_posix(),
                kind="file",
            ),
            reason="Matched known repository file",
            limitations=tuple(limitations),
        )

    if len(matching_files) > 1:
        candidates = tuple(
            TargetCandidate(
                id=f.id,
                name=f.name,
                kind="file",
                path=f.path.as_posix(),
            )
            for f in matching_files
        )
        return ChangeSetInputResolution(
            original_input=path_str,
            status="ambiguous",
            normalized_path=norm,
            candidates=candidates,
            reason=f"Multiple files match path '{norm}' in project inventory",
            limitations=(f"Ambiguous path mapping for '{norm}'",),
        )

    res = resolve_impact_target(project, raw)
    if res.is_resolved and res.target is not None:
        return ChangeSetInputResolution(
            original_input=path_str,
            status="resolved",
            normalized_path=res.target.path,
            target=res.target,
            reason=f"Resolved to {res.target.target_type} '{res.target.name}'",
        )

    if res.is_ambiguous:
        return ChangeSetInputResolution(
            original_input=path_str,
            status="ambiguous",
            normalized_path=norm,
            candidates=res.candidates,
            reason=f"Ambiguous target for path '{raw}'",
            limitations=(f"Target query '{raw}' resolved to multiple entities",),
        )

    exists_on_disk = (root_path / norm).exists()
    reason = (
        f"Path '{norm}' exists on disk but is not part of the analyzed inventory (unsupported or unindexed)"
        if exists_on_disk
        else f"Path '{norm}' not found in project inventory or filesystem"
    )
    status_label = "unindexed" if exists_on_disk else "not_found"
    return ChangeSetInputResolution(
        original_input=path_str,
        status=status_label,
        normalized_path=norm,
        reason=reason,
        limitations=(f"Path '{norm}' cannot be analyzed: {reason}",),
    )


def _is_test_file(path_str: str) -> bool:
    norm = normalize_relative_path(path_str).lower()
    parts = norm.split("/")
    filename = parts[-1]
    return (
        "tests" in parts
        or "test" in parts
        or filename.startswith("test_")
        or filename.endswith("_test.py")
    )


def analyze_changeset(
    project: Project,
    paths: Sequence[str | Path],
    *,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    limit: int | None = DEFAULT_IMPACT_LIMIT,
    include_checklist: bool = False,
    _include_checklist: bool | None = None,
) -> ChangeSetImpactResult:
    if _include_checklist is not None:
        include_checklist = _include_checklist
    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError("Direction must be 'incoming', 'outgoing', or 'both'")

    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError("Depth must be a positive integer")

    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError("Limit must be a positive integer")

    types_filter = (
        frozenset(str(t).lower() for t in relationship_types)
        if relationship_types is not None
        else DEFAULT_IMPACT_RELATIONSHIP_TYPES
    )

    supplied_paths = tuple(str(p) for p in paths)
    diagnostics: list[DiagnosticItem] = []
    limitations: list[str] = [
        (
            "Change-set impact analysis describes observed structural connections "
            "in indexed repository files; it does not guarantee runtime execution behavior."
        ),
        (
            "Analysis is limited to statically resolved relationships; dynamic calls, "
            "runtime reflection, and unresolved imports are not represented as impact edges."
        ),
    ]

    if not supplied_paths:
        diag = DiagnosticItem.blocker(
            "Empty change set provided; at least one path must be supplied",
            code="EMPTY_CHANGESET",
            source="changeset",
        )
        outcome = OperationOutcome.blocked(
            message="Empty change set provided",
            diagnostics=(diag,),
            limitations=("No paths provided in change set",),
        )
        return ChangeSetImpactResult(
            status="blocked",
            supplied_paths=(),
            resolved_inputs=(),
            items=(),
            total=0,
            direct_count=0,
            downstream_count=0,
            truncated=False,
            limit=limit,
            max_depth=max_depth,
            depth_reached=0,
            direction=direction,
            relationship_types=tuple(sorted(types_filter)),
            diagnostics=(diag,),
            limitations=("No paths provided in change set",),
            message="Empty change set provided",
            outcome=outcome,
        )

    resolved_inputs: list[ChangeSetInputResolution] = []
    analyzable_targets: dict[UUID, ResolvedTarget] = {}
    target_to_input_paths: dict[UUID, list[str]] = {}

    for p_str in supplied_paths:
        resolution = resolve_changeset_path(project, p_str)
        resolved_inputs.append(resolution)
        if resolution.is_resolved and resolution.target is not None:
            t = resolution.target
            analyzable_targets[t.id] = t
            target_to_input_paths.setdefault(t.id, []).append(t.path)
        else:
            diagnostics.append(
                DiagnosticItem.warning(
                    f"Path '{p_str}' could not be analyzed: {resolution.reason}",
                    code="UNANALYZABLE_PATH",
                    source="changeset",
                    path=p_str,
                    details={"status": resolution.status},
                )
            )
            limitations.append(
                f"Input path '{p_str}' could not be resolved or analyzed"
            )

    is_complete_project = (
        is_terminal_complete_status(project.analysis_status) and not project.errors
    )
    if not is_complete_project:
        limitations.append(
            f"Repository analysis status is {project.analysis_status!r}; results may be incomplete"
        )
        if project.errors:
            limitations.append("Repository analysis contains recorded errors")

    files_by_id = {f.id: f for f in project.files}
    symbols_by_id = {s.id: s for s in project.symbols}

    outgoing_by_id: dict[UUID, list[Relationship]] = {}
    incoming_by_id: dict[UUID, list[Relationship]] = {}

    for rel in project.relationships:
        rel_type = _relationship_type_value(rel)
        if rel_type not in types_filter:
            continue
        outgoing_by_id.setdefault(rel.source_id, []).append(rel)
        incoming_by_id.setdefault(rel.target_id, []).append(rel)

    def _entity_info(eid: UUID) -> tuple[str, str, str | None, str | None, str | None]:
        if eid in files_by_id:
            f = files_by_id[eid]
            return ("file", f.name, f.path.as_posix(), "file", None)
        if eid in symbols_by_id:
            sym = symbols_by_id[eid]
            sf = files_by_id.get(sym.file_id)
            return (
                "symbol",
                sym.name,
                sf.path.as_posix() if sf else None,
                sym.kind,
                sym.qualified_name,
            )
        return ("unknown", str(eid), None, None, None)

    root_ids: set[UUID] = set(analyzable_targets.keys())
    entity_provenance: dict[UUID, list[ChangeSetProvenance]] = {}
    entity_best_paths: dict[UUID, list[tuple[ImpactPathStep, ...]]] = {}
    depth_limited = False
    max_depth_reached = 0

    for root_id, root_target in sorted(
        analyzable_targets.items(), key=lambda t: t[1].path
    ):
        root_path_label = root_target.path
        visited_for_root: set[UUID] = {root_id}
        best_path_to: dict[UUID, tuple[ImpactPathStep, ...]] = {root_id: ()}
        current_frontier: list[UUID] = [root_id]

        for current_depth in range(1, max_depth + 1):
            next_candidates: dict[UUID, list[tuple[ImpactPathStep, ...]]] = {}
            sorted_frontier = sorted(
                current_frontier,
                key=lambda uid: (_path_sort_key(best_path_to[uid]), uid.hex),
            )

            for u_id in sorted_frontier:
                u_path = best_path_to[u_id]
                _, from_name, from_path, from_kind, _ = _entity_info(u_id)

                if direction in ("outgoing", "both"):
                    for rel in outgoing_by_id.get(u_id, []):
                        v_id = rel.target_id
                        if v_id in visited_for_root:
                            continue
                        _, to_name, to_path, to_kind, _ = _entity_info(v_id)
                        step = ImpactPathStep(
                            relationship_id=rel.id,
                            relationship_type=_relationship_type_value(rel),
                            direction="outgoing",
                            source_id=rel.source_id,
                            target_id=rel.target_id,
                            from_id=u_id,
                            to_id=v_id,
                            from_name=from_name,
                            to_name=to_name,
                            from_path=from_path,
                            to_path=to_path,
                            from_kind=from_kind,
                            to_kind=to_kind,
                            confidence=rel.confidence,
                            metadata=dict(rel.metadata),
                        )
                        next_candidates.setdefault(v_id, []).append(u_path + (step,))

                if direction in ("incoming", "both"):
                    for rel in incoming_by_id.get(u_id, []):
                        v_id = rel.source_id
                        if v_id in visited_for_root:
                            continue
                        _, to_name, to_path, to_kind, _ = _entity_info(v_id)
                        step = ImpactPathStep(
                            relationship_id=rel.id,
                            relationship_type=_relationship_type_value(rel),
                            direction="incoming",
                            source_id=rel.source_id,
                            target_id=rel.target_id,
                            from_id=u_id,
                            to_id=v_id,
                            from_name=from_name,
                            to_name=to_name,
                            from_path=from_path,
                            to_path=to_path,
                            from_kind=from_kind,
                            to_kind=to_kind,
                            confidence=rel.confidence,
                            metadata=dict(rel.metadata),
                        )
                        next_candidates.setdefault(v_id, []).append(u_path + (step,))

            if not next_candidates:
                break

            max_depth_reached = max(max_depth_reached, current_depth)
            next_frontier: list[UUID] = []

            for v_id in sorted(
                next_candidates.keys(),
                key=lambda vid: (
                    min(_path_sort_key(p) for p in next_candidates[vid]),
                    vid.hex,
                ),
            ):
                paths = next_candidates[v_id]
                winning_path = min(paths, key=_path_sort_key)
                best_path_to[v_id] = winning_path
                visited_for_root.add(v_id)
                next_frontier.append(v_id)

                classification = "direct" if current_depth == 1 else "downstream"
                prov = ChangeSetProvenance(
                    root_path=root_path_label,
                    root_id=root_id,
                    depth=current_depth,
                    classification=classification,
                    path=winning_path,
                )
                entity_provenance.setdefault(v_id, []).append(prov)
                entity_best_paths.setdefault(v_id, []).append(winning_path)

            if current_depth == max_depth:
                for v_id in next_frontier:
                    if direction in ("outgoing", "both") and any(
                        rel.target_id not in visited_for_root
                        for rel in outgoing_by_id.get(v_id, [])
                    ):
                        depth_limited = True
                        break
                    if direction in ("incoming", "both") and any(
                        rel.source_id not in visited_for_root
                        for rel in incoming_by_id.get(v_id, [])
                    ):
                        depth_limited = True
                        break

            current_frontier = next_frontier

    if depth_limited:
        limitations.append(
            f"Traversal depth was limited to {max_depth} hop(s); deeper components were not explored"
        )

    consolidated_items: list[ChangeSetImpactItem] = []

    for entity_id in sorted(entity_provenance.keys(), key=lambda eid: eid.hex):
        v_type, v_name, v_path, v_kind, v_qual = _entity_info(entity_id)
        provs = tuple(
            sorted(
                entity_provenance[entity_id],
                key=lambda p: (p.depth, p.root_path),
            )
        )
        min_depth = min(p.depth for p in provs)
        roots_tuple = tuple(sorted({p.root_path for p in provs}))

        if entity_id in root_ids:
            overall_classification = "root"
        elif any(p.depth == 1 for p in provs):
            overall_classification = "direct"
        else:
            overall_classification = "downstream"

        canonical_path = min(entity_best_paths[entity_id], key=_path_sort_key)

        consolidated_items.append(
            ChangeSetImpactItem(
                entity_id=entity_id,
                entity_type=v_type,
                name=v_name,
                path=v_path,
                kind=v_kind,
                qualified_name=v_qual,
                classification=overall_classification,
                min_depth=min_depth,
                roots=roots_tuple,
                provenance=provs,
                shortest_path=canonical_path,
            )
        )

    sorted_items = sorted(
        consolidated_items,
        key=lambda it: (
            it.min_depth,
            0
            if it.classification == "direct"
            else (1 if it.classification == "downstream" else 2),
            it.path or "",
            it.name,
            it.entity_id.hex,
        ),
    )

    total_affected = len(sorted_items)
    truncated = False
    if limit is not None and total_affected > limit:
        displayed_items = sorted_items[:limit]
        truncated = True
        limitations.append(
            f"Display was limited to {limit} of {total_affected} affected components"
        )
    else:
        displayed_items = sorted_items

    direct_count = sum(1 for it in sorted_items if it.classification == "direct")
    downstream_count = sum(
        1 for it in sorted_items if it.classification == "downstream"
    )

    relevant_tests_map: dict[tuple[UUID, UUID, str], RelevantTestItem] = {}

    target_entity_ids = root_ids | set(entity_provenance.keys())
    for rel in project.relationships:
        rel_type = _relationship_type_value(rel)
        if rel_type not in types_filter:
            continue

        src_is_test = False
        tgt_is_test = False
        src_file = files_by_id.get(rel.source_id)
        tgt_file = files_by_id.get(rel.target_id)

        if src_file and _is_test_file(src_file.path.as_posix()):
            src_is_test = True
        if tgt_file and _is_test_file(tgt_file.path.as_posix()):
            tgt_is_test = True

        if src_is_test and rel.target_id in target_entity_ids:
            tgt_info = _entity_info(rel.target_id)
            key = (src_file.id, rel.target_id, rel_type)
            relevant_tests_map[key] = RelevantTestItem(
                test_file_path=src_file.path.as_posix(),
                test_file_id=src_file.id,
                relationship_type=rel_type,
                target_entity_id=rel.target_id,
                target_entity_name=tgt_info[1],
                target_entity_path=tgt_info[2],
                direction="outgoing_from_test",
                evidence=f"Confirmed graph relationship '{rel_type}' from test to affected entity '{tgt_info[1]}'",
                classification="direct",
                rule=f"structural_{rel_type}",
                target_kind="direct_root"
                if rel.target_id in root_ids
                else "downstream_affected",
            )

        if tgt_is_test and rel.source_id in target_entity_ids:
            src_info = _entity_info(rel.source_id)
            key = (tgt_file.id, rel.source_id, rel_type)
            relevant_tests_map[key] = RelevantTestItem(
                test_file_path=tgt_file.path.as_posix(),
                test_file_id=tgt_file.id,
                relationship_type=rel_type,
                target_entity_id=rel.source_id,
                target_entity_name=src_info[1],
                target_entity_path=src_info[2],
                direction="incoming_to_test",
                evidence=f"Confirmed graph relationship '{rel_type}' from affected entity '{src_info[1]}' to test",
                classification="direct",
                rule=f"structural_{rel_type}",
                target_kind="direct_root"
                if rel.source_id in root_ids
                else "downstream_affected",
            )

    relevant_tests = tuple(
        sorted(
            relevant_tests_map.values(),
            key=lambda t: (t.test_file_path, t.relationship_type, t.target_entity_name),
        )
    )

    if not relevant_tests:
        limitations.append(
            "Test relevance could not be established from available repository relationship evidence"
        )

    resolved_count = len(analyzable_targets)
    all_resolved = len(analyzable_targets) == len(supplied_paths)

    if not is_complete_project:
        status = "incomplete"
        outcome_status = OperationStatus.INCOMPLETE
        msg = "Change-set analysis completed with incomplete repository analysis"
    elif not all_resolved:
        if resolved_count > 0:
            status = "partial"
            outcome_status = OperationStatus.PARTIAL
            msg = f"Change-set analysis completed partially ({resolved_count}/{len(supplied_paths)} paths analyzable)"
        else:
            status = "blocked"
            outcome_status = OperationStatus.BLOCKED
            msg = "None of the supplied change-set paths could be resolved or analyzed"
    elif truncated:
        status = "partial"
        outcome_status = OperationStatus.PARTIAL
        msg = f"Change-set analysis completed; results truncated to {limit}"
    else:
        status = "success"
        outcome_status = OperationStatus.SUCCESS
        msg = "Change-set analysis completed successfully"

    final_outcome = OperationOutcome(
        status=outcome_status,
        message=msg,
        diagnostics=tuple(
            sorted(
                diagnostics,
                key=lambda d: (
                    d.severity.value,
                    d.code or "",
                    d.path or "",
                    d.message,
                ),
            )
        ),
        limitations=tuple(sorted(set(limitations))),
    )

    res = ChangeSetImpactResult(
        status=status,
        supplied_paths=supplied_paths,
        resolved_inputs=tuple(resolved_inputs),
        items=tuple(displayed_items),
        total=total_affected,
        direct_count=direct_count,
        downstream_count=downstream_count,
        truncated=truncated,
        limit=limit,
        max_depth=max_depth,
        depth_reached=max_depth_reached,
        direction=direction,
        relationship_types=tuple(sorted(types_filter)),
        relevant_tests=relevant_tests,
        verification_checklist=None,
        diagnostics=final_outcome.diagnostics,
        limitations=final_outcome.limitations,
        message=msg,
        outcome=final_outcome,
        _all_items=tuple(sorted_items),
    )

    if include_checklist:
        from context_forge.query.verification import generate_verification_checklist

        chk = generate_verification_checklist(
            project,
            paths,
            impact_result=res,
            direction=direction,
            relationship_types=types_filter,
            max_depth=max_depth,
            limit=limit,
        )
        res = replace(res, verification_checklist=chk)

    return res
