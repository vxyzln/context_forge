from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)

DEFAULT_IMPACT_LIMIT: int = 50
DEFAULT_IMPACT_MAX_DEPTH: int = 3

DEFAULT_IMPACT_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        RelationshipType.IMPORTS.value,
        RelationshipType.REFERENCES.value,
        RelationshipType.INHERITS.value,
        RelationshipType.CALLS.value,
        RelationshipType.DEPENDS_ON.value,
    }
)


@dataclass(frozen=True)
class TargetCandidate:
    id: UUID
    name: str
    kind: str
    qualified_name: str | None = None
    path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "kind": self.kind,
            "qualified_name": self.qualified_name,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class ResolvedTarget:
    id: UUID
    target_type: str
    name: str
    path: str
    kind: str
    qualified_name: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "target_type": self.target_type,
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "qualified_name": self.qualified_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class TargetResolution:
    status: str
    target: ResolvedTarget | None = None
    candidates: tuple[TargetCandidate, ...] = ()
    message: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.status == "resolved" and self.target is not None

    @property
    def is_ambiguous(self) -> bool:
        return self.status == "ambiguous"

    @property
    def is_not_found(self) -> bool:
        return self.status == "not_found"

    @property
    def is_invalid(self) -> bool:
        return self.status == "invalid"

    @property
    def outcome(self) -> OperationOutcome:
        if self.status == "not_found":
            return OperationOutcome.blocked(
                self.message or "Target query not found",
                diagnostics=[
                    DiagnosticItem.blocker(
                        self.message or "Target query not found",
                        code="TARGET_NOT_FOUND",
                        source="impact",
                    )
                ],
            )
        if self.status == "ambiguous":
            return OperationOutcome.blocked(
                self.message or "Ambiguous target query",
                diagnostics=[
                    DiagnosticItem.blocker(
                        self.message or "Ambiguous target query",
                        code="TARGET_AMBIGUOUS",
                        source="impact",
                        details={"candidate_count": len(self.candidates)},
                    )
                ],
            )
        if self.status == "invalid":
            return OperationOutcome.blocked(
                self.message or "Invalid target query",
                diagnostics=[
                    DiagnosticItem.blocker(
                        self.message or "Invalid target query",
                        code="TARGET_INVALID",
                        source="impact",
                    )
                ],
            )
        if self.status == "insufficient_metadata":
            return OperationOutcome.blocked(
                self.message or "Insufficient repository metadata",
                diagnostics=[
                    DiagnosticItem.blocker(
                        self.message or "Insufficient repository metadata",
                        code="INSUFFICIENT_METADATA",
                        source="impact",
                    )
                ],
            )
        return OperationOutcome.success(
            self.message or "Target resolved successfully",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target": self.target.to_dict() if self.target is not None else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "message": self.message,
            "outcome": self.outcome.to_dict(),
        }


@dataclass(frozen=True)
class ImpactPathStep:
    relationship_id: UUID
    relationship_type: str
    direction: str
    source_id: UUID
    target_id: UUID
    from_id: UUID
    to_id: UUID
    from_name: str
    to_name: str
    from_path: str | None = None
    to_path: str | None = None
    from_kind: str | None = None
    to_kind: str | None = None
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": str(self.relationship_id),
            "relationship_type": self.relationship_type,
            "direction": self.direction,
            "source_id": str(self.source_id),
            "target_id": str(self.target_id),
            "from_id": str(self.from_id),
            "to_id": str(self.to_id),
            "from_name": self.from_name,
            "to_name": self.to_name,
            "from_path": self.from_path,
            "to_path": self.to_path,
            "from_kind": self.from_kind,
            "to_kind": self.to_kind,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ImpactItem:
    relationship_id: UUID
    relationship_type: str
    direction: str
    source_id: UUID
    target_id: UUID
    related_id: UUID
    related_type: str
    related_name: str
    related_path: str | None = None
    related_kind: str | None = None
    related_qualified_name: str | None = None
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)
    depth: int = 1
    classification: str = "direct"
    path: tuple[ImpactPathStep, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": str(self.relationship_id),
            "relationship_type": self.relationship_type,
            "direction": self.direction,
            "source_id": str(self.source_id),
            "target_id": str(self.target_id),
            "related_id": str(self.related_id),
            "related_type": self.related_type,
            "related_name": self.related_name,
            "related_path": self.related_path,
            "related_kind": self.related_kind,
            "related_qualified_name": self.related_qualified_name,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
            "depth": self.depth,
            "classification": self.classification,
            "path": [step.to_dict() for step in self.path],
        }


DirectImpactItem = ImpactItem


@dataclass(frozen=True)
class ImpactResult:
    status: str
    target: ResolvedTarget | None
    direction: str
    items: tuple[ImpactItem, ...]
    total: int
    truncated: bool
    limit: int | None
    relationship_types: tuple[str, ...]
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH
    depth_reached: int = 0
    direct_count: int = 0
    indirect_count: int = 0
    candidates: tuple[TargetCandidate, ...] = ()
    limitations: tuple[str, ...] = ()
    message: str = ""

    @property
    def outcome(self) -> OperationOutcome:
        diagnostics: list[DiagnosticItem] = []

        if self.status == "not_found":
            status = OperationStatus.BLOCKED
            diagnostics.append(
                DiagnosticItem.blocker(
                    self.message or "Target query not found",
                    code="TARGET_NOT_FOUND",
                    source="impact",
                )
            )
        elif self.status == "ambiguous":
            status = OperationStatus.BLOCKED
            diagnostics.append(
                DiagnosticItem.blocker(
                    self.message or "Ambiguous target query",
                    code="TARGET_AMBIGUOUS",
                    source="impact",
                    details={"candidate_count": len(self.candidates)},
                )
            )
        elif self.truncated:
            status = OperationStatus.PARTIAL
            diagnostics.append(
                DiagnosticItem.warning(
                    f"Impact results truncated to limit {self.limit}",
                    code="RESULTS_TRUNCATED",
                    source="impact",
                    details={"limit": self.limit, "total": self.total},
                )
            )
        else:
            status = OperationStatus.SUCCESS

        return OperationOutcome(
            status=status,
            message=self.message,
            diagnostics=tuple(diagnostics),
            limitations=self.limitations,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target": self.target.to_dict() if self.target is not None else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "direction": self.direction,
            "relationship_types": list(self.relationship_types),
            "total": self.total,
            "direct_count": self.direct_count,
            "indirect_count": self.indirect_count,
            "limit": self.limit,
            "max_depth": self.max_depth,
            "depth_reached": self.depth_reached,
            "truncated": self.truncated,
            "items": [item.to_dict() for item in self.items],
            "limitations": list(self.limitations),
            "message": self.message,
            "outcome": self.outcome.to_dict(),
        }


DirectImpactResult = ImpactResult


def _module_parts(file: File) -> list[str]:
    parts = list(file.path.parts)
    if not parts:
        return []
    filename = parts.pop()
    if filename != "__init__.py" and filename.endswith(".py"):
        parts.append(filename[:-3])

    package_start = None
    for index, part in enumerate(parts):
        if part == "src":
            package_start = index + 1
            break
    if package_start is not None:
        parts = parts[package_start:]
    return parts


def _build_module_index(project: Project) -> dict[str, File]:
    index: dict[str, File] = {}
    for file in project.files:
        if file.extension != ".py":
            continue
        parts = _module_parts(file)
        if parts:
            index[".".join(parts)] = file

        raw_parts = list(file.path.parts)
        if raw_parts:
            raw_filename = raw_parts.pop()
            if raw_filename != "__init__.py" and raw_filename.endswith(".py"):
                raw_parts.append(raw_filename[:-3])
            if raw_parts:
                index[".".join(raw_parts)] = file
    return index


def resolve_impact_target(
    project: Project,
    target: str | File | Symbol,
) -> TargetResolution:
    files_by_id = {file.id: file for file in project.files}
    symbols_by_id = {symbol.id: symbol for symbol in project.symbols}

    if isinstance(target, File):
        if target.id not in files_by_id:
            return TargetResolution(
                status="not_found",
                message=f"File '{target.path}' does not belong to the project.",
            )
        return TargetResolution(
            status="resolved",
            target=ResolvedTarget(
                id=target.id,
                target_type="file",
                name=target.name,
                path=target.path.as_posix(),
                kind="file",
            ),
        )

    if isinstance(target, Symbol):
        if target.id not in symbols_by_id:
            return TargetResolution(
                status="not_found",
                message=f"Symbol '{target.name}' does not belong to the project.",
            )
        file = files_by_id.get(target.file_id)
        return TargetResolution(
            status="resolved",
            target=ResolvedTarget(
                id=target.id,
                target_type="symbol",
                name=target.name,
                path=file.path.as_posix() if file is not None else "",
                kind=target.kind,
                qualified_name=target.qualified_name,
                start_line=target.start_line,
                end_line=target.end_line,
                signature=target.signature,
            ),
        )

    if not isinstance(target, str):
        raise TypeError(
            f"Target must be a str, File, or Symbol; got {type(target).__name__}"
        )

    query = target.strip()
    if not query:
        raise ValueError("Target cannot be empty")

    normalized_path = query.replace("\\", "/").removeprefix("./")

    if project.root_path is not None:
        as_path = Path(query)
        if as_path.is_absolute():
            try:
                normalized_path = as_path.relative_to(project.root_path).as_posix()
            except ValueError:
                pass

    for file in project.files:
        if file.path.as_posix() == normalized_path:
            return TargetResolution(
                status="resolved",
                target=ResolvedTarget(
                    id=file.id,
                    target_type="file",
                    name=file.name,
                    path=file.path.as_posix(),
                    kind="file",
                ),
            )

    matching_symbols: list[Symbol] = []

    if "." in query:
        qualified_matches = [s for s in project.symbols if s.qualified_name == query]
        if qualified_matches:
            matching_symbols = qualified_matches
        else:
            module_index = _build_module_index(project)
            if query in module_index:
                mod_file = module_index[query]
                return TargetResolution(
                    status="resolved",
                    target=ResolvedTarget(
                        id=mod_file.id,
                        target_type="file",
                        name=mod_file.name,
                        path=mod_file.path.as_posix(),
                        kind="file",
                    ),
                )

            matching_symbols = [s for s in project.symbols if s.name == query]
    else:
        matching_symbols = [s for s in project.symbols if s.name == query]
        if not matching_symbols:
            module_index = _build_module_index(project)
            if query in module_index:
                mod_file = module_index[query]
                return TargetResolution(
                    status="resolved",
                    target=ResolvedTarget(
                        id=mod_file.id,
                        target_type="file",
                        name=mod_file.name,
                        path=mod_file.path.as_posix(),
                        kind="file",
                    ),
                )

    if not matching_symbols:
        return TargetResolution(
            status="not_found",
            message=f"Target '{query}' not found in repository.",
        )

    if len(matching_symbols) == 1:
        symbol = matching_symbols[0]
        file = files_by_id.get(symbol.file_id)
        return TargetResolution(
            status="resolved",
            target=ResolvedTarget(
                id=symbol.id,
                target_type="symbol",
                name=symbol.name,
                path=file.path.as_posix() if file is not None else "",
                kind=symbol.kind,
                qualified_name=symbol.qualified_name,
                start_line=symbol.start_line,
                end_line=symbol.end_line,
                signature=symbol.signature,
            ),
        )

    candidates = sorted(
        [
            TargetCandidate(
                id=s.id,
                name=s.name,
                kind=s.kind,
                qualified_name=s.qualified_name,
                path=files_by_id[s.file_id].path.as_posix()
                if s.file_id in files_by_id
                else None,
                start_line=s.start_line,
                end_line=s.end_line,
                signature=s.signature,
            )
            for s in matching_symbols
        ],
        key=lambda c: (
            c.path or "",
            c.start_line or 0,
            c.name,
            c.qualified_name or "",
            c.id.hex,
        ),
    )

    return TargetResolution(
        status="ambiguous",
        candidates=tuple(candidates),
        message=(
            f"Multiple symbols match '{query}'; specify a qualified name "
            "or file path to disambiguate."
        ),
    )


def _build_limitations(
    project: Project,
    depth_limited: bool = False,
    max_depth: int | None = None,
    truncated: bool = False,
    limit: int | None = None,
    total: int = 0,
) -> tuple[str, ...]:
    limits = [
        (
            "Impact analysis describes observed structural connections in indexed "
            "repository files; it does not establish or guarantee runtime behavior "
            "or execution failure."
        ),
        (
            "Analysis is limited to statically resolved relationships; dynamic calls, "
            "runtime reflection, and unresolved imports are not represented as impact edges."
        ),
    ]
    if project.analysis_status != "analyzed":
        limits.append(
            f"Repository analysis status is {project.analysis_status!r}; impact data "
            "may be incomplete."
        )
    if project.errors:
        limits.append(
            "The persisted analysis contains errors; some relationships may be missing."
        )
    if depth_limited and max_depth is not None:
        limits.append(
            f"Traversal depth was limited to {max_depth} hop(s); components beyond "
            "this depth were not explored."
        )
    if truncated and limit is not None:
        limits.append(
            f"Display was limited to {limit} of {total} reachable components."
        )
    return tuple(limits)


def _relationship_type_value(relationship: Relationship) -> str:
    rel_type = relationship.relationship_type
    if hasattr(rel_type, "value"):
        return str(rel_type.value).lower()
    return str(rel_type).lower()


def _step_sort_key(step: ImpactPathStep) -> tuple[Any, ...]:
    return (
        0 if step.direction == "incoming" else 1,
        step.relationship_type,
        step.to_path or "",
        step.to_name,
        step.to_kind or "",
        step.to_id.hex,
        tuple(sorted(step.metadata.items())),
        step.relationship_id.hex,
    )


def _path_sort_key(path: tuple[ImpactPathStep, ...]) -> tuple[tuple[Any, ...], ...]:
    return tuple(_step_sort_key(step) for step in path)


def find_direct_impact(
    project: Project,
    target: str | File | Symbol,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    target_types: set[str] | None = None,
    limit: int | None = None,
) -> DirectImpactResult:
    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError("Direction must be 'incoming', 'outgoing', or 'both'")

    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError("Limit must be a positive integer")

    if relationship_types is None:
        types_filter = DEFAULT_IMPACT_RELATIONSHIP_TYPES
    else:
        types_filter = frozenset(str(t).lower() for t in relationship_types)

    allowed_target_types = (
        frozenset(str(t).lower() for t in target_types)
        if target_types is not None
        else None
    )

    resolution = resolve_impact_target(project, target)
    if not resolution.is_resolved:
        return DirectImpactResult(
            status=resolution.status,
            target=None,
            direction=direction,
            items=(),
            total=0,
            truncated=False,
            limit=limit,
            relationship_types=tuple(sorted(types_filter)),
            max_depth=1,
            depth_reached=0,
            direct_count=0,
            indirect_count=0,
            candidates=resolution.candidates,
            limitations=_build_limitations(project),
            message=resolution.message,
        )

    resolved_target = resolution.target
    assert resolved_target is not None
    target_id = resolved_target.id

    files_by_id = {f.id: f for f in project.files}
    symbols_by_id = {s.id: s for s in project.symbols}

    raw_items: list[DirectImpactItem] = []

    for rel in project.relationships:
        rel_type = _relationship_type_value(rel)
        if rel_type not in types_filter:
            continue

        if direction in ("incoming", "both") and rel.target_id == target_id:
            related_id = rel.source_id
            if related_id in files_by_id:
                file = files_by_id[related_id]
                rel_type_name = "file"
                rel_name = file.name
                rel_path = file.path.as_posix()
                rel_kind = "file"
                rel_qual = None
            elif related_id in symbols_by_id:
                sym = symbols_by_id[related_id]
                rel_type_name = "symbol"
                rel_name = sym.name
                sym_file = files_by_id.get(sym.file_id)
                rel_path = sym_file.path.as_posix() if sym_file else None
                rel_kind = sym.kind
                rel_qual = sym.qualified_name
            else:
                rel_type_name = "unknown"
                rel_name = str(related_id)
                rel_path = None
                rel_kind = None
                rel_qual = None

            if allowed_target_types is None or rel_type_name in allowed_target_types:
                step = ImpactPathStep(
                    relationship_id=rel.id,
                    relationship_type=rel_type,
                    direction="incoming",
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    from_id=target_id,
                    to_id=related_id,
                    from_name=resolved_target.name,
                    to_name=rel_name,
                    from_path=resolved_target.path,
                    to_path=rel_path,
                    from_kind=resolved_target.kind,
                    to_kind=rel_kind,
                    confidence=rel.confidence,
                    metadata=dict(rel.metadata),
                )
                raw_items.append(
                    DirectImpactItem(
                        relationship_id=rel.id,
                        relationship_type=rel_type,
                        direction="incoming",
                        source_id=rel.source_id,
                        target_id=rel.target_id,
                        related_id=related_id,
                        related_type=rel_type_name,
                        related_name=rel_name,
                        related_path=rel_path,
                        related_kind=rel_kind,
                        related_qualified_name=rel_qual,
                        confidence=rel.confidence,
                        metadata=dict(rel.metadata),
                        depth=1,
                        classification="direct",
                        path=(step,),
                    )
                )

        if direction in ("outgoing", "both") and rel.source_id == target_id:
            related_id = rel.target_id
            if related_id in files_by_id:
                file = files_by_id[related_id]
                rel_type_name = "file"
                rel_name = file.name
                rel_path = file.path.as_posix()
                rel_kind = "file"
                rel_qual = None
            elif related_id in symbols_by_id:
                sym = symbols_by_id[related_id]
                rel_type_name = "symbol"
                rel_name = sym.name
                sym_file = files_by_id.get(sym.file_id)
                rel_path = sym_file.path.as_posix() if sym_file else None
                rel_kind = sym.kind
                rel_qual = sym.qualified_name
            else:
                rel_type_name = "unknown"
                rel_name = str(related_id)
                rel_path = None
                rel_kind = None
                rel_qual = None

            if allowed_target_types is None or rel_type_name in allowed_target_types:
                step = ImpactPathStep(
                    relationship_id=rel.id,
                    relationship_type=rel_type,
                    direction="outgoing",
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    from_id=target_id,
                    to_id=related_id,
                    from_name=resolved_target.name,
                    to_name=rel_name,
                    from_path=resolved_target.path,
                    to_path=rel_path,
                    from_kind=resolved_target.kind,
                    to_kind=rel_kind,
                    confidence=rel.confidence,
                    metadata=dict(rel.metadata),
                )
                raw_items.append(
                    DirectImpactItem(
                        relationship_id=rel.id,
                        relationship_type=rel_type,
                        direction="outgoing",
                        source_id=rel.source_id,
                        target_id=rel.target_id,
                        related_id=related_id,
                        related_type=rel_type_name,
                        related_name=rel_name,
                        related_path=rel_path,
                        related_kind=rel_kind,
                        related_qualified_name=rel_qual,
                        confidence=rel.confidence,
                        metadata=dict(rel.metadata),
                        depth=1,
                        classification="direct",
                        path=(step,),
                    )
                )

    sorted_items = sorted(
        raw_items,
        key=lambda item: (
            item.direction,
            item.relationship_type,
            item.related_path or "",
            item.related_name,
            item.related_kind or "",
            item.related_id.hex,
            tuple(sorted(item.metadata.items())),
            item.relationship_id.hex,
        ),
    )

    total = len(sorted_items)
    if limit is not None:
        displayed_items = sorted_items[:limit]
        truncated = total > limit
    else:
        displayed_items = sorted_items
        truncated = False

    return DirectImpactResult(
        status="resolved",
        target=resolved_target,
        direction=direction,
        items=tuple(displayed_items),
        total=total,
        truncated=truncated,
        limit=limit,
        relationship_types=tuple(sorted(types_filter)),
        max_depth=1,
        depth_reached=1 if displayed_items else 0,
        direct_count=total,
        indirect_count=0,
        candidates=(),
        limitations=_build_limitations(
            project,
            truncated=truncated,
            limit=limit,
            total=total,
        ),
        message="",
    )


def find_impact(
    project: Project,
    target: str | File | Symbol,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    target_types: set[str] | None = None,
    max_depth: int = DEFAULT_IMPACT_MAX_DEPTH,
    limit: int | None = DEFAULT_IMPACT_LIMIT,
) -> ImpactResult:
    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError("Direction must be 'incoming', 'outgoing', or 'both'")

    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError("Depth must be a positive integer")

    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError("Limit must be a positive integer")

    if relationship_types is None:
        types_filter = DEFAULT_IMPACT_RELATIONSHIP_TYPES
    else:
        types_filter = frozenset(str(t).lower() for t in relationship_types)

    allowed_target_types = (
        frozenset(str(t).lower() for t in target_types)
        if target_types is not None
        else None
    )

    resolution = resolve_impact_target(project, target)
    if not resolution.is_resolved:
        return ImpactResult(
            status=resolution.status,
            target=None,
            direction=direction,
            items=(),
            total=0,
            truncated=False,
            limit=limit,
            relationship_types=tuple(sorted(types_filter)),
            max_depth=max_depth,
            depth_reached=0,
            direct_count=0,
            indirect_count=0,
            candidates=resolution.candidates,
            limitations=_build_limitations(project),
            message=resolution.message,
        )

    resolved_target = resolution.target
    assert resolved_target is not None
    target_id = resolved_target.id

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

    visited: set[UUID] = {target_id}
    best_path_to: dict[UUID, tuple[ImpactPathStep, ...]] = {target_id: ()}
    current_frontier: list[UUID] = [target_id]
    discovered_items: list[ImpactItem] = []
    depth_limited = False

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
                    if v_id in visited:
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
                    if v_id in visited:
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
            visited.add(v_id)
            next_frontier.append(v_id)

            v_type, v_name, v_path, v_kind, v_qual = _entity_info(v_id)
            last_step = winning_path[-1]

            if allowed_target_types is None or v_type in allowed_target_types:
                discovered_items.append(
                    ImpactItem(
                        relationship_id=last_step.relationship_id,
                        relationship_type=last_step.relationship_type,
                        direction=last_step.direction,
                        source_id=last_step.source_id,
                        target_id=last_step.target_id,
                        related_id=v_id,
                        related_type=v_type,
                        related_name=v_name,
                        related_path=v_path,
                        related_kind=v_kind,
                        related_qualified_name=v_qual,
                        confidence=last_step.confidence,
                        metadata=dict(last_step.metadata),
                        depth=current_depth,
                        classification="direct" if current_depth == 1 else "indirect",
                        path=winning_path,
                    )
                )

        if current_depth == max_depth:
            for v_id in next_frontier:
                if direction in ("outgoing", "both") and any(
                    rel.target_id not in visited for rel in outgoing_by_id.get(v_id, [])
                ):
                    depth_limited = True
                    break
                if direction in ("incoming", "both") and any(
                    rel.source_id not in visited for rel in incoming_by_id.get(v_id, [])
                ):
                    depth_limited = True
                    break

        current_frontier = next_frontier

    sorted_items = sorted(
        discovered_items,
        key=lambda item: (
            item.depth,
            0 if item.classification == "direct" else 1,
            0 if item.direction == "incoming" else 1,
            item.related_path or "",
            item.related_name,
            item.related_kind or "",
            item.related_id.hex,
            _path_sort_key(item.path),
        ),
    )

    total = len(sorted_items)
    if limit is not None:
        displayed_items = sorted_items[:limit]
        truncated = total > limit
    else:
        displayed_items = sorted_items
        truncated = False

    direct_count = sum(1 for it in sorted_items if it.depth == 1)
    indirect_count = sum(1 for it in sorted_items if it.depth > 1)
    depth_reached = max((it.depth for it in sorted_items), default=0)

    limitations = _build_limitations(
        project,
        depth_limited=depth_limited,
        max_depth=max_depth,
        truncated=truncated,
        limit=limit,
        total=total,
    )

    return ImpactResult(
        status="resolved",
        target=resolved_target,
        direction=direction,
        items=tuple(displayed_items),
        total=total,
        truncated=truncated,
        limit=limit,
        relationship_types=tuple(sorted(types_filter)),
        max_depth=max_depth,
        depth_reached=depth_reached,
        direct_count=direct_count,
        indirect_count=indirect_count,
        candidates=(),
        limitations=limitations,
        message="",
    )


find_transitive_impact = find_impact
