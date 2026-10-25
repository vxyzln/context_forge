from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol
from context_forge.query.impact import (
    DEFAULT_IMPACT_RELATIONSHIP_TYPES,
    ResolvedTarget,
    TargetResolution,
    _relationship_type_value,
    resolve_impact_target,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)

DEFAULT_PATH_MAX_DEPTH: int = 10
DEFAULT_PATH_MAX_EXPANSIONS: int = 1000


@dataclass(frozen=True)
class RelationshipPathStep:
    relationship_id: UUID
    relationship_type: str
    stored_source_id: UUID
    stored_target_id: UUID
    traversal_direction: str
    from_id: UUID
    to_id: UUID
    from_name: str
    to_name: str
    from_path: str | None = None
    to_path: str | None = None
    from_kind: str | None = None
    to_kind: str | None = None
    source_line: int | None = None
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "from_id": str(self.from_id),
            "from_kind": self.from_kind,
            "from_name": self.from_name,
            "from_path": self.from_path,
            "metadata": dict(sorted(self.metadata.items())),
            "relationship_id": str(self.relationship_id),
            "relationship_type": self.relationship_type,
            "source_line": self.source_line,
            "stored_source_id": str(self.stored_source_id),
            "stored_target_id": str(self.stored_target_id),
            "to_id": str(self.to_id),
            "to_kind": self.to_kind,
            "to_name": self.to_name,
            "to_path": self.to_path,
            "traversal_direction": self.traversal_direction,
        }


@dataclass(frozen=True)
class RelationshipPathResult:
    status: str
    path_found: bool
    is_exhaustive: bool
    start_target: ResolvedTarget | None
    end_target: ResolvedTarget | None
    start_resolution: TargetResolution | None = None
    end_resolution: TargetResolution | None = None
    direction: str = "both"
    relationship_types: tuple[str, ...] = ()
    steps: tuple[RelationshipPathStep, ...] = ()
    length: int = 0
    max_depth: int = DEFAULT_PATH_MAX_DEPTH
    max_expansions: int | None = DEFAULT_PATH_MAX_EXPANSIONS
    expansions_used: int = 0
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()
    message: str = ""
    outcome: OperationOutcome = field(
        default_factory=lambda: OperationOutcome.success()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "direction": self.direction,
            "end_resolution": (
                self.end_resolution.to_dict() if self.end_resolution else None
            ),
            "end_target": self.end_target.to_dict() if self.end_target else None,
            "expansions_used": self.expansions_used,
            "is_exhaustive": self.is_exhaustive,
            "length": self.length,
            "limitations": list(self.limitations),
            "max_depth": self.max_depth,
            "max_expansions": self.max_expansions,
            "message": self.message,
            "outcome": self.outcome.to_dict(),
            "path_found": self.path_found,
            "relationship_types": list(self.relationship_types),
            "start_resolution": (
                self.start_resolution.to_dict() if self.start_resolution else None
            ),
            "start_target": self.start_target.to_dict() if self.start_target else None,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
        }


def _extract_source_line(metadata: dict[str, str]) -> int | None:
    line_raw = metadata.get("line")
    if line_raw is not None:
        try:
            val = int(line_raw)
            return val if val > 0 else None
        except (ValueError, TypeError):
            return None
    return None


def find_relationship_path(
    project: Project,
    start: str | File | Symbol,
    end: str | File | Symbol,
    *,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    max_depth: int = DEFAULT_PATH_MAX_DEPTH,
    max_expansions: int | None = DEFAULT_PATH_MAX_EXPANSIONS,
) -> RelationshipPathResult:
    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError("Direction must be 'incoming', 'outgoing', or 'both'")

    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError("Depth must be a positive integer")

    if max_expansions is not None and (
        isinstance(max_expansions, bool)
        or not isinstance(max_expansions, int)
        or max_expansions < 1
    ):
        raise ValueError("Expansion limit must be a positive integer")

    types_filter = (
        frozenset(str(t).lower() for t in relationship_types)
        if relationship_types is not None
        else DEFAULT_IMPACT_RELATIONSHIP_TYPES
    )

    limitations: list[str] = [
        (
            "Relationship path query describes observed structural connections "
            "in indexed repository files; it does not guarantee runtime execution paths."
        ),
        (
            "Analysis is limited to statically resolved relationships; dynamic calls, "
            "runtime reflection, and unresolved imports are not represented as path edges."
        ),
    ]
    diagnostics: list[DiagnosticItem] = []

    start_resolution = resolve_impact_target(project, start)
    end_resolution = resolve_impact_target(project, end)

    endpoint_failed = False
    if not start_resolution.is_resolved:
        endpoint_failed = True
        diag = DiagnosticItem.blocker(
            f"Start endpoint could not be resolved: {start_resolution.message}",
            code="UNRESOLVED_START_ENDPOINT",
            source="path_query",
            details={"status": start_resolution.status},
        )
        diagnostics.append(diag)
        limitations.append(f"Start endpoint query '{start}' could not be resolved")

    if not end_resolution.is_resolved:
        endpoint_failed = True
        diag = DiagnosticItem.blocker(
            f"End endpoint could not be resolved: {end_resolution.message}",
            code="UNRESOLVED_END_ENDPOINT",
            source="path_query",
            details={"status": end_resolution.status},
        )
        diagnostics.append(diag)
        limitations.append(f"End endpoint query '{end}' could not be resolved")

    if endpoint_failed:
        outcome = OperationOutcome.blocked(
            message="Endpoint resolution failed for relationship path query",
            diagnostics=tuple(diagnostics),
            limitations=tuple(sorted(limitations)),
        )
        return RelationshipPathResult(
            status="endpoint_unresolved",
            path_found=False,
            is_exhaustive=False,
            start_target=start_resolution.target,
            end_target=end_resolution.target,
            start_resolution=start_resolution,
            end_resolution=end_resolution,
            direction=direction,
            relationship_types=tuple(sorted(types_filter)),
            steps=(),
            length=0,
            max_depth=max_depth,
            max_expansions=max_expansions,
            expansions_used=0,
            diagnostics=tuple(diagnostics),
            limitations=tuple(sorted(limitations)),
            message="Endpoint resolution failed for relationship path query",
            outcome=outcome,
        )

    start_target = start_resolution.target
    end_target = end_resolution.target
    assert start_target is not None
    assert end_target is not None

    start_id = start_target.id
    end_id = end_target.id

    is_complete_project = project.analysis_status == "analyzed" and not project.errors
    if not is_complete_project:
        limitations.append(
            f"Repository analysis status is {project.analysis_status!r}; path query results may be incomplete"
        )
        if project.errors:
            limitations.append("Repository analysis contains recorded errors")

    if start_id == end_id:
        msg = f"Start and end endpoints are identical ('{start_target.name}'); zero-edge path."
        outcome = (
            OperationOutcome.success(
                message=msg,
                diagnostics=tuple(diagnostics),
                limitations=tuple(sorted(limitations)),
            )
            if is_complete_project
            else OperationOutcome.incomplete(
                message=msg,
                diagnostics=tuple(diagnostics),
                limitations=tuple(sorted(limitations)),
            )
        )
        return RelationshipPathResult(
            status="resolved",
            path_found=True,
            is_exhaustive=True,
            start_target=start_target,
            end_target=end_target,
            start_resolution=start_resolution,
            end_resolution=end_resolution,
            direction=direction,
            relationship_types=tuple(sorted(types_filter)),
            steps=(),
            length=0,
            max_depth=max_depth,
            max_expansions=max_expansions,
            expansions_used=0,
            diagnostics=tuple(diagnostics),
            limitations=tuple(sorted(limitations)),
            message=msg,
            outcome=outcome,
        )

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

    queue: deque[tuple[UUID, tuple[RelationshipPathStep, ...], int]] = deque()
    queue.append((start_id, (), 0))
    visited: set[UUID] = {start_id}

    expansions_used = 0
    stopped_by_depth = False
    stopped_by_expansions = False
    found_path: tuple[RelationshipPathStep, ...] | None = None

    while queue:
        if max_expansions is not None and expansions_used >= max_expansions:
            stopped_by_expansions = True
            break

        u_id, u_path, u_depth = queue.popleft()
        expansions_used += 1

        if u_depth >= max_depth:
            has_unvisited_neighbors = False
            if direction in ("outgoing", "both"):
                for rel in outgoing_by_id.get(u_id, []):
                    if rel.target_id not in visited:
                        has_unvisited_neighbors = True
                        break
            if not has_unvisited_neighbors and direction in ("incoming", "both"):
                for rel in incoming_by_id.get(u_id, []):
                    if rel.source_id not in visited:
                        has_unvisited_neighbors = True
                        break
            if has_unvisited_neighbors:
                stopped_by_depth = True
            continue

        _u_type, u_name, u_path_str, u_kind, _ = _entity_info(u_id)

        neighbor_steps: list[tuple[UUID, RelationshipPathStep]] = []

        if direction in ("outgoing", "both"):
            for rel in outgoing_by_id.get(u_id, []):
                v_id = rel.target_id
                _v_type, v_name, v_path_str, v_kind, _ = _entity_info(v_id)
                step = RelationshipPathStep(
                    relationship_id=rel.id,
                    relationship_type=_relationship_type_value(rel),
                    stored_source_id=rel.source_id,
                    stored_target_id=rel.target_id,
                    traversal_direction="outgoing",
                    from_id=u_id,
                    to_id=v_id,
                    from_name=u_name,
                    to_name=v_name,
                    from_path=u_path_str,
                    to_path=v_path_str,
                    from_kind=u_kind,
                    to_kind=v_kind,
                    source_line=_extract_source_line(rel.metadata),
                    confidence=rel.confidence,
                    metadata=dict(rel.metadata),
                )
                neighbor_steps.append((v_id, step))

        if direction in ("incoming", "both"):
            for rel in incoming_by_id.get(u_id, []):
                v_id = rel.source_id
                _v_type, v_name, v_path_str, v_kind, _ = _entity_info(v_id)
                step = RelationshipPathStep(
                    relationship_id=rel.id,
                    relationship_type=_relationship_type_value(rel),
                    stored_source_id=rel.source_id,
                    stored_target_id=rel.target_id,
                    traversal_direction="incoming",
                    from_id=u_id,
                    to_id=v_id,
                    from_name=u_name,
                    to_name=v_name,
                    from_path=u_path_str,
                    to_path=v_path_str,
                    from_kind=u_kind,
                    to_kind=v_kind,
                    source_line=_extract_source_line(rel.metadata),
                    confidence=rel.confidence,
                    metadata=dict(rel.metadata),
                )
                neighbor_steps.append((v_id, step))

        neighbor_steps.sort(
            key=lambda item: (
                0 if item[1].traversal_direction == "outgoing" else 1,
                item[1].relationship_type,
                item[1].to_path or "",
                item[1].to_name,
                item[1].to_id.hex,
                item[1].relationship_id.hex,
            )
        )

        reached_target = False
        for v_id, step in neighbor_steps:
            if v_id == end_id:
                found_path = u_path + (step,)
                reached_target = True
                break

            if v_id not in visited:
                visited.add(v_id)
                queue.append((v_id, u_path + (step,), u_depth + 1))

        if reached_target:
            break

    if not found_path and queue and any(d >= max_depth for _, _, d in queue):
        stopped_by_depth = True

    if found_path is not None:
        path_length = len(found_path)
        msg = (
            f"Found relationship path of length {path_length} from "
            f"'{start_target.name}' to '{end_target.name}'"
        )
        outcome_status = (
            OperationStatus.SUCCESS
            if is_complete_project
            else OperationStatus.INCOMPLETE
        )
        final_outcome = OperationOutcome(
            status=outcome_status,
            message=msg,
            diagnostics=tuple(diagnostics),
            limitations=tuple(sorted(set(limitations))),
        )
        return RelationshipPathResult(
            status="resolved",
            path_found=True,
            is_exhaustive=True,
            start_target=start_target,
            end_target=end_target,
            start_resolution=start_resolution,
            end_resolution=end_resolution,
            direction=direction,
            relationship_types=tuple(sorted(types_filter)),
            steps=found_path,
            length=path_length,
            max_depth=max_depth,
            max_expansions=max_expansions,
            expansions_used=expansions_used,
            diagnostics=final_outcome.diagnostics,
            limitations=final_outcome.limitations,
            message=msg,
            outcome=final_outcome,
        )

    if stopped_by_expansions:
        status_label = "expansion_limited"
        msg = (
            f"Relationship path search stopped at expansion limit ({max_expansions} entities); "
            f"could not definitively establish whether a path exists between '{start_target.name}' and '{end_target.name}'"
        )
        diag = DiagnosticItem.warning(
            f"Search stopped at expansion limit of {max_expansions} entities without finding target",
            code="EXPANSION_LIMIT_REACHED",
            source="path_query",
            details={
                "expansions_used": expansions_used,
                "max_expansions": max_expansions,
            },
        )
        diagnostics.append(diag)
        limitations.append(
            f"Search was truncated at expansion limit of {max_expansions} entities"
        )
        outcome_status = OperationStatus.PARTIAL
    elif stopped_by_depth:
        status_label = "depth_limited"
        msg = (
            f"Relationship path search stopped at maximum depth limit ({max_depth} hops); "
            f"could not definitively establish whether a path exists between '{start_target.name}' and '{end_target.name}'"
        )
        diag = DiagnosticItem.warning(
            f"Search stopped at depth limit of {max_depth} hops without finding target",
            code="DEPTH_LIMIT_REACHED",
            source="path_query",
            details={"depth_limit": max_depth},
        )
        diagnostics.append(diag)
        limitations.append(
            f"Search was limited to depth {max_depth}; deeper paths were not explored"
        )
        outcome_status = OperationStatus.PARTIAL
    else:
        status_label = "no_path_found"
        msg = (
            f"Exhaustive search completed: no relationship path exists between "
            f"'{start_target.name}' and '{end_target.name}' under the configured direction ('{direction}') "
            f"and relationship filters."
        )
        outcome_status = (
            OperationStatus.SUCCESS
            if is_complete_project
            else OperationStatus.INCOMPLETE
        )

    final_outcome = OperationOutcome(
        status=outcome_status,
        message=msg,
        diagnostics=tuple(diagnostics),
        limitations=tuple(sorted(set(limitations))),
    )

    return RelationshipPathResult(
        status=status_label,
        path_found=False,
        is_exhaustive=status_label == "no_path_found",
        start_target=start_target,
        end_target=end_target,
        start_resolution=start_resolution,
        end_resolution=end_resolution,
        direction=direction,
        relationship_types=tuple(sorted(types_filter)),
        steps=(),
        length=0,
        max_depth=max_depth,
        max_expansions=max_expansions,
        expansions_used=expansions_used,
        diagnostics=final_outcome.diagnostics,
        limitations=final_outcome.limitations,
        message=msg,
        outcome=final_outcome,
    )
