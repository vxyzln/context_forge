from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol
from context_forge.query.impact import (
    ResolvedTarget,
    TargetCandidate,
    TargetResolution,
)
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)

DEFAULT_EXCERPT_MAX_LINES: int = 50


@dataclass(frozen=True)
class SourceExcerpt:
    target_id: UUID
    target_name: str
    path: str
    start_line: int
    end_line: int
    content: str
    total_lines: int
    symbol_start_line: int | None = None
    symbol_end_line: int | None = None
    is_truncated: bool = False
    status: str = "success"
    message: str = ""
    limitations: tuple[str, ...] = ()

    @property
    def is_success(self) -> bool:
        return self.status in ("success", "stale_location")

    @property
    def outcome(self) -> OperationOutcome:
        diagnostics: list[DiagnosticItem] = []

        if self.status == "success":
            op_status = OperationStatus.SUCCESS
        elif self.status == "stale_location":
            op_status = OperationStatus.PARTIAL
            diagnostics.append(
                DiagnosticItem.warning(
                    self.message
                    or f"Cached location for symbol '{self.target_name}' may be stale in {self.path}",
                    code="STALE_SOURCE_LOCATION",
                    path=self.path,
                    line=self.start_line,
                    source="evidence",
                )
            )
        else:
            op_status = OperationStatus.BLOCKED
            diagnostics.append(
                DiagnosticItem.blocker(
                    self.message
                    or f"Failed to retrieve source evidence for '{self.target_name}'",
                    code=self.status.upper(),
                    path=self.path,
                    line=self.start_line if self.start_line > 0 else None,
                    source="evidence",
                )
            )

        return OperationOutcome(
            status=op_status,
            message=self.message
            or (
                f"Source evidence retrieved for '{self.target_name}'"
                if self.is_success
                else f"Source evidence unavailable for '{self.target_name}'"
            ),
            diagnostics=tuple(diagnostics),
            limitations=self.limitations,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": str(self.target_id),
            "target_name": self.target_name,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "content": self.content,
            "total_lines": self.total_lines,
            "symbol_start_line": self.symbol_start_line,
            "symbol_end_line": self.symbol_end_line,
            "is_truncated": self.is_truncated,
            "is_success": self.is_success,
            "status": self.status,
            "message": self.message,
            "limitations": list(self.limitations),
            "outcome": self.outcome.to_dict(),
        }


def locate_symbol(
    project: Project,
    name: str,
    *,
    file_path: str | Path | None = None,
    symbol_type: str | None = None,
    qualified_name: str | None = None,
) -> TargetResolution:
    if not isinstance(name, str):
        return TargetResolution(
            status="invalid",
            message=f"Symbol name must be a string, got {type(name).__name__}",
        )

    query = name.strip()
    if not query:
        return TargetResolution(
            status="invalid",
            message="Symbol query name cannot be empty",
        )

    files_by_id: dict[UUID, File] = {f.id: f for f in project.files}

    candidate_symbols: list[Symbol]
    if qualified_name is not None:
        q_target = qualified_name.strip()
        candidate_symbols = [s for s in project.symbols if s.qualified_name == q_target]
    elif "." in query:
        q_matches = [s for s in project.symbols if s.qualified_name == query]
        if q_matches:
            candidate_symbols = q_matches
        else:
            candidate_symbols = [s for s in project.symbols if s.name == query]
    else:
        candidate_symbols = [s for s in project.symbols if s.name == query]

    if file_path is not None:
        raw_fp = str(file_path).strip().replace("\\", "/").removeprefix("./")
        if not raw_fp:
            return TargetResolution(
                status="invalid",
                message="File path filter cannot be empty",
            )

        if project.root_path is not None:
            as_path = Path(raw_fp)
            if as_path.is_absolute():
                try:
                    raw_fp = as_path.relative_to(project.root_path).as_posix()
                except ValueError:
                    pass

        filtered: list[Symbol] = []
        is_basename_query = "/" not in raw_fp
        for sym in candidate_symbols:
            f = files_by_id.get(sym.file_id)
            if f is None:
                continue
            f_path_str = f.path.as_posix()
            if f_path_str == raw_fp or is_basename_query and f.name == raw_fp:
                filtered.append(sym)
        candidate_symbols = filtered

    if symbol_type is not None:
        target_type = symbol_type.strip().lower()
        if not target_type:
            return TargetResolution(
                status="invalid",
                message="Symbol type filter cannot be empty",
            )
        candidate_symbols = [
            s for s in candidate_symbols if s.kind.lower() == target_type
        ]

    if not candidate_symbols:
        filter_details: list[str] = []
        if file_path:
            filter_details.append(f"file '{file_path}'")
        if symbol_type:
            filter_details.append(f"type '{symbol_type}'")
        if qualified_name:
            filter_details.append(f"qualified '{qualified_name}'")

        filter_suffix = f" with {', '.join(filter_details)}" if filter_details else ""
        return TargetResolution(
            status="not_found",
            message=f"Symbol '{query}' not found in repository{filter_suffix}.",
        )

    if len(candidate_symbols) == 1:
        sym = candidate_symbols[0]
        sym_file = files_by_id.get(sym.file_id)
        return TargetResolution(
            status="resolved",
            target=ResolvedTarget(
                id=sym.id,
                target_type="symbol",
                name=sym.name,
                path=sym_file.path.as_posix() if sym_file is not None else "",
                kind=sym.kind,
                qualified_name=sym.qualified_name,
                start_line=sym.start_line,
                end_line=sym.end_line,
                signature=sym.signature,
            ),
            message=f"Resolved symbol '{sym.name}' in {sym_file.path.as_posix() if sym_file else 'unknown'}",
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
            for s in candidate_symbols
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
            f"Multiple symbols ({len(candidate_symbols)}) match '{query}'; "
            "specify a qualified name, file path, or symbol type to disambiguate."
        ),
    )


def _validate_definition_header(
    excerpt_lines: list[str],
    target_name: str,
    target_kind: str | None = None,
) -> tuple[str, str | None]:
    if not excerpt_lines or not target_name:
        return "stale", None

    bare_name = target_name.rsplit(".", 1)[-1]
    kind = target_kind.strip().lower() if target_kind else None

    supported_kinds = {"class", "function", "method", "constant", "variable", "import"}
    if kind is not None and kind not in supported_kinds:
        return (
            "unsupported",
            (
                f"Definition header validation is not supported for symbol kind '{kind}'; "
                "source location could not be independently verified."
            ),
        )

    class_pattern = re.compile(
        r"^class\s+" + re.escape(bare_name) + r"(?:[\s\(\:\[]|$)"
    )
    func_pattern = re.compile(
        r"^(?:async\s+)?def\s+" + re.escape(bare_name) + r"(?:[\s\(\:\[]|$)"
    )
    assign_pattern = re.compile(
        r"^(?:[a-zA-Z_][a-zA-Z0-9_]*\s*(?::[^=]+)?=\s*)*"
        + re.escape(bare_name)
        + r"(?:\s*:\s*(?!:)|\s*=\s*(?!=))"
    )

    if kind == "class":
        patterns = [class_pattern]
    elif kind in ("function", "method"):
        patterns = [func_pattern]
    elif kind in ("constant", "variable"):
        patterns = [assign_pattern]
    elif kind == "import":
        patterns = []
    else:
        patterns = [class_pattern, func_pattern, assign_pattern]

    max_scan = min(15, len(excerpt_lines))
    idx = 0
    in_multiline_decorator = False
    in_multiline_import = False
    open_parens = 0
    open_brackets = 0

    while idx < max_scan:
        raw_line = excerpt_lines[idx]
        stripped = raw_line.strip()

        if not stripped:
            idx += 1
            continue

        if stripped.startswith("#"):
            return "stale", None

        if any(p.match(stripped) for p in patterns):
            return "valid", None

        if kind in ("import", None):
            if stripped.startswith(("import ", "from ")):
                simple_import = re.compile(r"\b" + re.escape(bare_name) + r"\b")

                open_parens = stripped.count("(") - stripped.count(")")
                if open_parens > 0:
                    in_multiline_import = True

                if "import" in stripped:
                    after_import = stripped.split("import", 1)[1]
                    if simple_import.search(after_import):
                        return "valid", None
                elif simple_import.search(stripped):
                    return "valid", None

                idx += 1
                continue

            if in_multiline_import:
                simple_import = re.compile(r"\b" + re.escape(bare_name) + r"\b")
                if simple_import.search(stripped):
                    return "valid", None
                open_parens += stripped.count("(") - stripped.count(")")
                if open_parens <= 0:
                    in_multiline_import = False
                idx += 1
                continue

        if stripped.startswith("@") and (kind in ("class", "function", "method", None)):
            open_parens = stripped.count("(") - stripped.count(")")
            open_brackets = stripped.count("[") - stripped.count("]")
            if open_parens > 0 or open_brackets > 0:
                in_multiline_decorator = True
            idx += 1
            continue

        if in_multiline_decorator:
            open_parens += stripped.count("(") - stripped.count(")")
            open_brackets += stripped.count("[") - stripped.count("]")
            if open_parens <= 0 and open_brackets <= 0:
                in_multiline_decorator = False
            idx += 1
            continue

        return "stale", None

    return "stale", None


def get_source_evidence(
    project: Project,
    target: ResolvedTarget | Symbol,
    *,
    root_path: Path | None = None,
    max_lines: int = DEFAULT_EXCERPT_MAX_LINES,
) -> SourceExcerpt:
    if max_lines < 1:
        raise ValueError("max_lines must be a positive integer")

    target_id = target.id
    target_name = target.name
    start_line = target.start_line
    end_line = target.end_line

    target_kind = getattr(target, "kind", None)
    if hasattr(target_kind, "value"):
        target_kind = target_kind.value
    elif target_kind is not None:
        target_kind = str(target_kind)

    if isinstance(target, ResolvedTarget):
        rel_path_str = target.path
    else:
        file_match = next((f for f in project.files if f.id == target.file_id), None)
        rel_path_str = file_match.path.as_posix() if file_match is not None else ""

    if start_line is None or start_line < 1:
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=0,
            end_line=0,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="invalid_location",
            message=f"Invalid start line ({start_line}) for symbol '{target_name}'",
        )

    if end_line is not None and end_line < start_line:
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="invalid_location",
            message=f"End line ({end_line}) precedes start line ({start_line}) for symbol '{target_name}'",
        )

    root = root_path if root_path is not None else project.root_path
    if root is None or not rel_path_str:
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="missing_file",
            message=f"Source file path is unavailable or empty for symbol '{target_name}'",
        )

    canonical_root = Path(root).resolve()
    target_path_obj = Path(rel_path_str)

    if target_path_obj.is_absolute():
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="path_outside_root",
            message=(
                f"Source path must be repository-relative; absolute paths are not permitted: {rel_path_str}"
            ),
        )

    try:
        full_path = (canonical_root / target_path_obj).resolve()
    except (OSError, RuntimeError) as exc:
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="invalid_path",
            message=f"Failed to resolve source path '{rel_path_str}': {exc}",
        )

    # Verify the target path stays within the repository root.
    if not full_path.is_relative_to(canonical_root):
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="path_outside_root",
            message=f"Resolved source path escapes repository root: {rel_path_str}",
        )

    if not full_path.exists():
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="missing_file",
            message=f"Referenced source file does not exist: {rel_path_str}",
        )

    if not full_path.is_file():
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="invalid_file_type",
            message=f"Source path is not a regular file: {rel_path_str}",
        )

    try:
        raw_text = full_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw_text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return SourceExcerpt(
                target_id=target_id,
                target_name=target_name,
                path=rel_path_str,
                start_line=start_line,
                end_line=end_line or start_line,
                content="",
                total_lines=0,
                symbol_start_line=start_line,
                symbol_end_line=end_line,
                status="unreadable_file",
                message=f"Failed to read source file '{rel_path_str}': {exc}",
            )
    except OSError as exc:
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="unreadable_file",
            message=f"Failed to read source file '{rel_path_str}': {exc}",
        )

    file_lines = raw_text.splitlines()
    total_file_lines = len(file_lines)

    if start_line > total_file_lines:
        return SourceExcerpt(
            target_id=target_id,
            target_name=target_name,
            path=rel_path_str,
            start_line=start_line,
            end_line=end_line or start_line,
            content="",
            total_lines=0,
            symbol_start_line=start_line,
            symbol_end_line=end_line,
            status="location_out_of_range",
            message=(
                f"Recorded start line {start_line} exceeds current file line count "
                f"({total_file_lines}) in {rel_path_str}"
            ),
        )

    target_end = end_line if end_line is not None else start_line
    target_end = min(target_end, total_file_lines)

    requested_lines = target_end - start_line + 1
    is_truncated = False
    limitations: list[str] = []

    if requested_lines > max_lines:
        excerpt_end = start_line + max_lines - 1
        is_truncated = True
        limitations.append(
            f"Source excerpt truncated to {max_lines} lines (symbol spans {requested_lines} lines)."
        )
    else:
        excerpt_end = target_end

    slice_start = start_line - 1
    slice_end = excerpt_end
    excerpt_lines = file_lines[slice_start:slice_end]
    content = "\n".join(excerpt_lines)

    status = "success"
    validation_status, validation_limitation = _validate_definition_header(
        excerpt_lines,
        target_name=target_name,
        target_kind=target_kind,
    )

    if validation_status == "stale":
        status = "stale_location"
        msg = (
            f"Source content at lines {start_line}-{excerpt_end} in {rel_path_str} does not "
            f"contain symbol '{target_name}' definition header; cached location metadata may be stale."
        )
        limitations.append(msg)
    elif validation_status == "unsupported":
        msg = f"Excerpt retrieved for '{target_name}' ({start_line}-{excerpt_end})"
        if validation_limitation:
            limitations.append(validation_limitation)
    else:
        msg = f"Excerpt retrieved for '{target_name}' ({start_line}-{excerpt_end})"

    return SourceExcerpt(
        target_id=target_id,
        target_name=target_name,
        path=rel_path_str,
        start_line=start_line,
        end_line=excerpt_end,
        content=content,
        total_lines=len(excerpt_lines),
        symbol_start_line=start_line,
        symbol_end_line=end_line,
        is_truncated=is_truncated,
        status=status,
        message=msg,
        limitations=tuple(limitations),
    )


def locate_and_get_evidence(
    project: Project,
    name: str,
    *,
    file_path: str | Path | None = None,
    symbol_type: str | None = None,
    qualified_name: str | None = None,
    root_path: Path | None = None,
    max_lines: int = DEFAULT_EXCERPT_MAX_LINES,
) -> tuple[TargetResolution, SourceExcerpt | None]:
    resolution = locate_symbol(
        project,
        name,
        file_path=file_path,
        symbol_type=symbol_type,
        qualified_name=qualified_name,
    )

    if resolution.is_resolved and resolution.target is not None:
        evidence = get_source_evidence(
            project,
            resolution.target,
            root_path=root_path,
            max_lines=max_lines,
        )
        return resolution, evidence

    return resolution, None
