from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol

DEFAULT_IMPACT_LIMIT: int = 50

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
    """A candidate symbol when an unqualified target query is ambiguous."""

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
    """An unambiguously resolved file or symbol impact target."""

    id: UUID
    target_type: str  # "file" or "symbol"
    name: str
    path: str
    kind: str  # "file" for files, or symbol.kind ("class", "function", "method", etc.)
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
    """Outcome of resolving a target query against a project."""

    status: str  # "resolved", "not_found", "ambiguous"
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target": self.target.to_dict() if self.target is not None else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "message": self.message,
        }


@dataclass(frozen=True)
class DirectImpactItem:
    """A directly connected entity with its supporting relationship evidence."""

    relationship_id: UUID
    relationship_type: str
    direction: str  # "incoming" or "outgoing"
    source_id: UUID
    target_id: UUID
    related_id: UUID
    related_type: str  # "file" or "symbol"
    related_name: str
    related_path: str | None = None
    related_kind: str | None = None
    related_qualified_name: str | None = None
    confidence: float = 1.0
    metadata: dict[str, str] = field(default_factory=dict)

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
        }


@dataclass(frozen=True)
class DirectImpactResult:
    """Complete result of a direct-impact analysis operation."""

    status: str  # "resolved", "not_found", "ambiguous"
    target: ResolvedTarget | None
    direction: str  # "incoming", "outgoing", "both"
    items: tuple[DirectImpactItem, ...]
    total: int
    truncated: bool
    limit: int | None
    relationship_types: tuple[str, ...]
    candidates: tuple[TargetCandidate, ...] = ()
    limitations: tuple[str, ...] = ()
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target": self.target.to_dict() if self.target is not None else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "direction": self.direction,
            "relationship_types": list(self.relationship_types),
            "total": self.total,
            "limit": self.limit,
            "truncated": self.truncated,
            "items": [item.to_dict() for item in self.items],
            "limitations": list(self.limitations),
            "message": self.message,
        }


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
        # Also index raw path parts with dots (e.g. src.pkg)
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
    """Resolve a file path, symbol name, or entity instance to a TargetResolution."""
    files_by_id = {file.id: file for file in project.files}
    symbols_by_id = {symbol.id: symbol for symbol in project.symbols}

    # 1. Direct File instance
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

    # 2. Direct Symbol instance
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

    # 3. String query
    if not isinstance(target, str):
        raise TypeError(
            f"Target must be a str, File, or Symbol; got {type(target).__name__}"
        )

    query = target.strip()
    if not query:
        raise ValueError("Target cannot be empty")

    # Path normalization for file lookup
    normalized_path = query.replace("\\", "/").removeprefix("./")

    # Handle absolute paths within project root
    if project.root_path is not None:
        as_path = Path(query)
        if as_path.is_absolute():
            try:
                normalized_path = as_path.relative_to(project.root_path).as_posix()
            except ValueError:
                pass

    # Exact repository-relative file match takes precedence
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

    # Symbol lookup
    matching_symbols: list[Symbol] = []

    if "." in query:
        # Check exact qualified name first
        qualified_matches = [s for s in project.symbols if s.qualified_name == query]
        if qualified_matches:
            matching_symbols = qualified_matches
        else:
            # Check module index (e.g. package.module)
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
            # Also check if symbol name literally contains dot
            matching_symbols = [s for s in project.symbols if s.name == query]
    else:
        # Unqualified symbol lookup
        matching_symbols = [s for s in project.symbols if s.name == query]
        if not matching_symbols:
            # Check module index for single-component module name
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

    # Ambiguous matches: sort deterministically
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


def _build_limitations(project: Project) -> tuple[str, ...]:
    limits = [
        (
            "Direct impact describes observed structural connections in indexed "
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
    return tuple(limits)


def _relationship_type_value(relationship: Relationship) -> str:
    rel_type = relationship.relationship_type
    if hasattr(rel_type, "value"):
        return str(rel_type.value).lower()
    return str(rel_type).lower()


def find_direct_impact(
    project: Project,
    target: str | File | Symbol,
    direction: str = "both",
    relationship_types: set[str] | None = None,
    target_types: set[str] | None = None,
    limit: int | None = None,
) -> DirectImpactResult:
    """Identify directly connected entities and evidence for a target entity."""
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

        # 1. Incoming: relationship.target_id == target_id
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
                    )
                )

        # 2. Outgoing: relationship.source_id == target_id
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
                    )
                )

    # Sort deterministically
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
        candidates=(),
        limitations=_build_limitations(project),
        message="",
    )
