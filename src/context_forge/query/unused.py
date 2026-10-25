"""Unused-entity candidate reporting.

Identifies entities (functions, methods, classes, variables, files) that have no
detected incoming references or usage evidence in the analyzed project, distinguishing
likely candidates from entities that cannot be assessed reliably, and reporting
evidence and limitations with strict non-presumptive honesty.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
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

DEFAULT_UNUSED_LIMIT: int = 50

UNUSED_REPORT_LIMITATIONS: tuple[str, ...] = (
    "Candidates are identified strictly from static AST-level relationships and imports.",
    "Dynamic imports, runtime getattr/setattr reflection, and dynamic dispatch are not detected.",
    "Framework entry points, pytest fixtures/hooks, and external consumer APIs cannot be fully verified.",
    "Unused candidate reporting does not guarantee safety to delete; manual verification is required.",
)

STANDARD_ENTRY_POINT_FILENAMES: frozenset[str] = frozenset(
    {
        "__init__.py",
        "__main__.py",
        "main.py",
        "conftest.py",
        "setup.py",
        "manage.py",
        "wsgi.py",
        "asgi.py",
    }
)

# Standard Python data model protocol methods recognized by runtime language syntax
PYTHON_DATA_MODEL_METHODS: frozenset[str] = frozenset(
    {
        # Object creation & destruction
        "__new__",
        "__init__",
        "__del__",
        # String / representation
        "__repr__",
        "__str__",
        "__bytes__",
        "__format__",
        # Comparisons & hashing
        "__lt__",
        "__le__",
        "__eq__",
        "__ne__",
        "__gt__",
        "__ge__",
        "__hash__",
        "__bool__",
        # Attribute access
        "__getattr__",
        "__getattribute__",
        "__setattr__",
        "__delattr__",
        "__dir__",
        # Descriptors
        "__get__",
        "__set__",
        "__delete__",
        "__set_name__",
        # Class customization
        "__init_subclass__",
        "__class_getitem__",
        "__mro_entries__",
        # Containers & sequences
        "__len__",
        "__length_hint__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__missing__",
        "__iter__",
        "__next__",
        "__reversed__",
        "__contains__",
        # Callables
        "__call__",
        # Context managers
        "__enter__",
        "__exit__",
        "__aenter__",
        "__aexit__",
        # Async iterators
        "__aiter__",
        "__anext__",
        # Numeric / arithmetic operations
        "__add__",
        "__sub__",
        "__mul__",
        "__matmul__",
        "__truediv__",
        "__floordiv__",
        "__mod__",
        "__divmod__",
        "__pow__",
        "__lshift__",
        "__rshift__",
        "__and__",
        "__xor__",
        "__or__",
        "__radd__",
        "__rsub__",
        "__rmul__",
        "__rmatmul__",
        "__rtruediv__",
        "__rfloordiv__",
        "__rmod__",
        "__rdivmod__",
        "__rpow__",
        "__rlshift__",
        "__rrshift__",
        "__rand__",
        "__rxor__",
        "__ror__",
        "__iadd__",
        "__isub__",
        "__imul__",
        "__imatmul__",
        "__itruediv__",
        "__ifloordiv__",
        "__imod__",
        "__ipow__",
        "__ilshift__",
        "__irshift__",
        "__iand__",
        "__ixor__",
        "__ior__",
        "__neg__",
        "__pos__",
        "__abs__",
        "__invert__",
        "__complex__",
        "__int__",
        "__float__",
        "__index__",
        "__round__",
        "__trunc__",
        "__floor__",
        "__ceil__",
        # Dataclasses & copy/pickle
        "__post_init__",
        "__copy__",
        "__deepcopy__",
        "__getstate__",
        "__setstate__",
        "__reduce__",
        "__reduce_ex__",
    }
)


class UnusedClassification(str, Enum):
    APPARENT_UNUSED_CANDIDATE = "apparent_unused_candidate"
    CANNOT_ASSESS_RELIABLY = "cannot_assess_reliably"
    NOT_CANDIDATE = "not_candidate"


@dataclass(frozen=True)
class UnusedCandidateItem:
    entity_id: str
    name: str
    kind: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    qualified_name: str | None = None
    classification: str = UnusedClassification.APPARENT_UNUSED_CANDIDATE.value
    reason: str = ""
    evidence: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "entity_id": self.entity_id,
            "name": self.name,
            "kind": self.kind,
            "path": self.path,
            "classification": self.classification,
            "reason": self.reason,
            "evidence": list(self.evidence),
        }
        if self.start_line is not None:
            result["start_line"] = self.start_line
        if self.end_line is not None:
            result["end_line"] = self.end_line
        if self.qualified_name is not None:
            result["qualified_name"] = self.qualified_name
        if self.limitations:
            result["limitations"] = list(self.limitations)
        return result


@dataclass(frozen=True)
class UnusedEntitiesSummary:
    total_entities_analyzed: int
    candidates_count: int
    unassessable_count: int
    by_kind: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entities_analyzed": self.total_entities_analyzed,
            "candidates_count": self.candidates_count,
            "unassessable_count": self.unassessable_count,
            "by_kind": dict(sorted(self.by_kind.items())),
        }


@dataclass(frozen=True)
class UnusedEntitiesReport:
    """Report describing apparent unused entity candidates and unassessable entities.

    Attributes:
        repository_path: Target repository path.
        analysis_status: Analysis status of the scanned project.
        candidates: Apparent unused candidates, capped per section by limit.
        unassessable: Unassessable entities, capped per section by limit.
        summary: True repository-wide summary counts independent of displayed item limits.
        truncated: True if either candidates or unassessable sections exceeded limit.
        limit: Display limit applied per section, or None if unlimited.
        diagnostics: Collection of diagnostic notices.
        limitations: Explicit caveats and limitations of static analysis.
        outcome: Operation outcome status and summary.
    """

    repository_path: str
    analysis_status: str
    candidates: tuple[UnusedCandidateItem, ...] = ()
    unassessable: tuple[UnusedCandidateItem, ...] = ()
    summary: UnusedEntitiesSummary = field(
        default_factory=lambda: UnusedEntitiesSummary(0, 0, 0, {})
    )
    truncated: bool = False
    limit: int | None = None
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = UNUSED_REPORT_LIMITATIONS
    outcome: OperationOutcome = field(default_factory=OperationOutcome.success)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_path": self.repository_path,
            "analysis_status": self.analysis_status,
            "summary": self.summary.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "unassessable": [u.to_dict() for u in self.unassessable],
            "truncated": self.truncated,
            "limit": self.limit,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "limitations": list(self.limitations),
            "outcome": self.outcome.to_dict(),
        }


def _to_repo_relative_path(path: Path | str, root_path: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.relative_to(root_path).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def _is_test_path(path_str: str) -> bool:
    norm = path_str.replace("\\", "/").lower()
    parts = norm.split("/")
    filename = parts[-1]
    return (
        "tests" in parts
        or "test" in parts
        or filename.startswith("test_")
        or filename.endswith("_test.py")
    )


def _is_test_runner_file(file_name: str) -> bool:
    lower = file_name.lower()
    return lower.startswith("test_") or lower.endswith("_test.py")


def _is_convention_uncertainty(
    symbol: Symbol,
    file: File | None,
    file_path: str,
) -> tuple[bool, str]:
    # 1. Standard Python data-model methods on classes
    if symbol.kind == "method" and symbol.name in PYTHON_DATA_MODEL_METHODS:
        return (
            True,
            "Python data-model protocol method; may be invoked implicitly by runtime syntax without static call references.",
        )

    # 2. Test functions and test classes in test files
    if _is_test_path(file_path):
        if symbol.kind in ("function", "method") and symbol.name.startswith("test_"):
            return (
                True,
                "Potential test runner discovery target; may be invoked dynamically by test framework without static call references.",
            )
        if symbol.kind == "class" and symbol.name.startswith("Test"):
            return (
                True,
                "Potential test suite class; may be discovered dynamically by test framework without static call references.",
            )

    # 3. 'main' functions in recognized entry-point files
    if (
        symbol.name == "main"
        and file is not None
        and file.name in ("__main__.py", "main.py", "app.py", "manage.py", "cli.py")
    ):
        return (
            True,
            "Potential application entry point function; may be invoked externally by runtime execution without static call references.",
        )

    return False, ""


SUPPORTED_KINDS: dict[str, str] = {
    "all": "all",
    "*": "all",
    "function": "function",
    "functions": "function",
    "method": "method",
    "methods": "method",
    "class": "class",
    "classes": "class",
    "variable": "variable",
    "variables": "variable",
    "file": "file",
    "files": "file",
    "symbol": "symbol",
    "symbols": "symbol",
}


def _normalize_kind_filter(kind: str | None) -> set[str]:
    """Normalize and validate entity kind filter.

    Supports 'all', '*', singular and plural entity kinds, or None.
    Raises ValueError for unsupported kind filters.
    """
    if kind is None or not kind.strip() or kind.strip().lower() in ("all", "*"):
        return {"all"}

    raw = kind.strip().lower()
    if raw not in SUPPORTED_KINDS:
        supported_list = ", ".join(sorted(set(SUPPORTED_KINDS.values())))
        raise ValueError(
            f"Unsupported kind filter: '{kind}'. Supported kinds: {supported_list}."
        )

    return {SUPPORTED_KINDS[raw]}


PATH_DELIMITERS: frozenset[str] = frozenset(
    {
        " ",
        "\t",
        "\n",
        "\r",
        '"',
        "'",
        "`",
        ":",
        ";",
        ",",
        "(",
        ")",
        "[",
        "]",
        "{",
        "}",
        "<",
        ">",
        "=",
        "!",
    }
)


def _contains_path_token(text: str, path_str: str) -> bool:
    """Check if path_str appears in text bounded by path delimiters.

    Prevents false substring matches where path_str is part of a longer path
    component or different filename (e.g. 'src/a.py' in 'sub/src/a.py' or 'src/a.py.bak').
    """
    if not path_str or not text:
        return False
    start = 0
    p_len = len(path_str)
    while True:
        idx = text.find(path_str, start)
        if idx == -1:
            return False
        valid_before = (idx == 0) or (text[idx - 1] in PATH_DELIMITERS)
        end_idx = idx + p_len
        valid_after = (end_idx == len(text)) or (text[end_idx] in PATH_DELIMITERS)
        if valid_before and valid_after:
            return True
        start = idx + 1


def _is_error_location(err_norm: str, rel_path: str, abs_path: str | None) -> bool:
    """Check if a file path appears at the primary error location prefix."""
    variants = [rel_path, "./" + rel_path]
    if abs_path:
        variants.append(abs_path)

    for line in err_norm.splitlines():
        line = line.strip()
        stripped_line = line
        for tag in ("[error]", "[warning]", "[fatal]", "error:", "warning:", "fatal:"):
            if stripped_line.lower().startswith(tag):
                stripped_line = stripped_line[len(tag) :].strip()

        for var in variants:
            # Standard compiler prefix: var(:line)?(:col)?: or var\s
            if stripped_line.startswith(var):
                rest = stripped_line[len(var) :]
                if (
                    not rest
                    or rest.startswith((":", " "))
                    or rest[0] in PATH_DELIMITERS
                ):
                    return True
            lower_line = stripped_line.lower()
            var_lower = var.lower()
            # File "var" or File 'var'
            if lower_line.startswith(
                (
                    f'file "{var_lower}"',
                    f"file '{var_lower}'",
                    f"file {var_lower}:",
                )
            ):
                return True
            # in file var, error in var, etc.
            for prefix in (
                "in file ",
                "in ",
                "error in file ",
                "error in ",
                "syntax error in file ",
                "syntax error in ",
            ):
                if lower_line.startswith(prefix + var_lower):
                    return True

    return False


def _index_file_errors(project: Project) -> tuple[dict[str, list[str]], list[str]]:
    """Attribute analysis errors to files using precise path matching.

    Avoids false positives across files that share the same basename or appear together
    in error messages by prioritizing normalized relative paths and identifiable error locations.
    Returns (file_errors_by_repo_rel_path, ambiguous_errors).
    """
    file_errors: dict[str, list[str]] = defaultdict(list)
    ambiguous_errors: list[str] = []
    if not project.errors:
        return file_errors, ambiguous_errors

    files_by_rel_path: dict[str, File] = {}
    files_by_abs_path: dict[str, File] = {}
    files_by_basename: dict[str, list[File]] = defaultdict(list)

    for f in project.files:
        rel_path = _to_repo_relative_path(f.path, project.root_path)
        files_by_rel_path[rel_path] = f
        unresolved_abs = (
            f.path if Path(f.path).is_absolute() else (project.root_path / rel_path)
        ).as_posix()
        files_by_abs_path[unresolved_abs] = f
        try:
            resolved_abs = Path(unresolved_abs).resolve().as_posix()
            files_by_abs_path[resolved_abs] = f
        except (OSError, RuntimeError, ValueError):
            pass
        files_by_basename[f.name].append(f)

    for err in project.errors:
        err_str = str(err)
        err_norm = err_str.replace("\\", "/").strip()

        # 1. Exact path matches (relative, dot-slash, or absolute)
        matched_rel_paths: set[str] = set()

        for rel_path, f in files_by_rel_path.items():
            if _contains_path_token(err_norm, rel_path) or _contains_path_token(
                err_norm, f"./{rel_path}"
            ):
                matched_rel_paths.add(rel_path)

        for abs_path, f in files_by_abs_path.items():
            if _contains_path_token(err_norm, abs_path):
                matched_rel_paths.add(_to_repo_relative_path(f.path, project.root_path))

        if len(matched_rel_paths) == 1:
            # Unambiguous single file match
            file_errors[next(iter(matched_rel_paths))].append(err_str)
            continue
        elif len(matched_rel_paths) > 1:
            # Multiple distinct repository files matched.
            # Do NOT assign to multiple files unless the primary failing file location is identifiable.
            loc_matched: list[str] = []
            for rel_p in matched_rel_paths:
                f = files_by_rel_path[rel_p]
                abs_p = (
                    f.path
                    if Path(f.path).is_absolute()
                    else (project.root_path / rel_p)
                ).as_posix()
                if _is_error_location(err_norm, rel_p, abs_p):
                    loc_matched.append(rel_p)

            if len(loc_matched) == 1:
                # Exactly one matched file is at the primary error location
                file_errors[loc_matched[0]].append(err_str)
            else:
                # Multiple files mentioned and primary location cannot be established reliably
                ambiguous_errors.append(err_str)
            continue

        # 2. Basename fallback if no exact path matched
        matched_basenames = [
            name for name in files_by_basename if _contains_path_token(err_norm, name)
        ]

        if len(matched_basenames) == 1:
            bname = matched_basenames[0]
            if len(files_by_basename[bname]) == 1:
                unique_file = files_by_basename[bname][0]
                unique_rel_path = _to_repo_relative_path(
                    unique_file.path, project.root_path
                )
                file_errors[unique_rel_path].append(err_str)
            else:
                ambiguous_errors.append(err_str)
        else:
            ambiguous_errors.append(err_str)

    return file_errors, ambiguous_errors


def find_unused_candidates(
    project: Project,
    *,
    kind: str | None = "all",
    limit: int | None = DEFAULT_UNUSED_LIMIT,
) -> UnusedEntitiesReport:
    """Identify entities with no detected incoming references or usage evidence.

    Args:
        project: Analyzed project model containing files, symbols, and relationships.
        kind: Entity kind filter ('all', '*', 'function', 'functions', 'method',
            'methods', 'class', 'classes', 'variable', 'variables', 'file', 'files',
            'symbol', 'symbols'). Unsupported values raise ValueError.
        limit: Maximum number of items displayed per section ('candidates' and
            'unassessable'). If None, all items are retained without section-level truncation.

    Returns:
        UnusedEntitiesReport with capped candidate and unassessable sections,
        full summary counts, and non-presumptive evidence and limitations.
    """
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise ValueError("Report limit must be a positive integer")

    repo_path = str(project.root_path)
    analysis_status = project.analysis_status or "not_analyzed"
    diagnostics: list[DiagnosticItem] = []
    kind_filters = _normalize_kind_filter(kind)

    include_symbols = (
        "all" in kind_filters
        or "symbol" in kind_filters
        or any(k in kind_filters for k in ("function", "method", "class", "variable"))
    )
    include_files = "all" in kind_filters or "file" in kind_filters

    files_by_id: dict[UUID, File] = {f.id: f for f in project.files}

    # Index errors with precise path attribution
    file_errors, ambiguous_errors = _index_file_errors(project)

    # Index incoming relationships by target_id
    incoming_rels: dict[UUID, list[Relationship]] = defaultdict(list)
    for rel in project.relationships:
        incoming_rels[rel.target_id].append(rel)

    usage_rel_types = {
        RelationshipType.REFERENCES,
        RelationshipType.CALLS,
        RelationshipType.INHERITS,
        RelationshipType.DEPENDS_ON,
        "references",
        "calls",
        "inherits",
        "depends_on",
    }

    candidates_list: list[UnusedCandidateItem] = []
    unassessable_list: list[UnusedCandidateItem] = []
    total_entities_analyzed = 0
    any_missing_provenance = False

    # 1. Analyze symbols
    if include_symbols:
        for symbol in project.symbols:
            if symbol.kind == "import":
                continue

            if (
                "all" not in kind_filters
                and "symbol" not in kind_filters
                and symbol.kind not in kind_filters
            ):
                continue

            total_entities_analyzed += 1
            file = files_by_id.get(symbol.file_id)
            file_path = (
                _to_repo_relative_path(file.path, project.root_path)
                if file
                else "<unknown>"
            )

            # Check unassessable conditions: missing file
            if file is None:
                any_missing_provenance = True
                unassessable_list.append(
                    UnusedCandidateItem(
                        entity_id=str(symbol.id),
                        name=symbol.name,
                        kind=symbol.kind,
                        path=file_path,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        qualified_name=symbol.qualified_name,
                        classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                        reason="Associated source file not found in project inventory.",
                        evidence=(),
                        limitations=(
                            "Missing file metadata prevents usage assessment.",
                        ),
                    )
                )
                continue

            # Check unassessable conditions: analysis error in containing file
            if file_path in file_errors:
                unassessable_list.append(
                    UnusedCandidateItem(
                        entity_id=str(symbol.id),
                        name=symbol.name,
                        kind=symbol.kind,
                        path=file_path,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        qualified_name=symbol.qualified_name,
                        classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                        reason=f"Containing file encountered analysis error: {file_errors[file_path][0]}",
                        evidence=(),
                        limitations=(
                            "Parsing/analysis error in file limits assessment reliability.",
                        ),
                    )
                )
                continue

            # Check unassessable conditions: invalid source line bounds
            if symbol.start_line <= 0 or symbol.end_line < symbol.start_line:
                any_missing_provenance = True
                unassessable_list.append(
                    UnusedCandidateItem(
                        entity_id=str(symbol.id),
                        name=symbol.name,
                        kind=symbol.kind,
                        path=file_path,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        qualified_name=symbol.qualified_name,
                        classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                        reason="Symbol has invalid or missing source line boundaries.",
                        evidence=(),
                        limitations=(
                            "Invalid line boundaries prevent spatial reference correlation.",
                        ),
                    )
                )
                continue

            # Evaluate incoming relationships
            incoming = incoming_rels.get(symbol.id, [])
            external_usage: list[Relationship] = []
            self_refs_count = 0
            has_ambiguous_line_metadata = False
            has_ambiguous_same_name_reference = False

            same_file_same_name_symbols = [
                s
                for s in project.symbols
                if s.file_id == symbol.file_id
                and s.name == symbol.name
                and s.kind != "import"
            ]
            has_multiple_same_name_in_file = len(same_file_same_name_symbols) > 1

            for rel in incoming:
                rtype = rel.relationship_type
                if rtype not in usage_rel_types:
                    continue

                # Direct self-reference where source is the symbol itself
                if rel.source_id == symbol.id:
                    self_refs_count += 1
                    continue

                if rel.source_id == symbol.file_id:
                    # Same-file reference.
                    # Verify whether reference line metadata exists and is within symbol boundaries.
                    line_str = rel.metadata.get("line")
                    if not line_str or not str(line_str).isdigit():
                        has_ambiguous_line_metadata = True
                        continue

                    line_num = int(str(line_str))
                    if symbol.start_line <= line_num <= symbol.end_line:
                        # Edge line is inside the symbol (internal recursion / reference).
                        self_refs_count += 1
                        continue
                    else:
                        # Line is outside symbol bounds: caller is a different function in same file!
                        external_usage.append(rel)
                        continue

                # Reference from a different file or symbol
                external_usage.append(rel)

            # Check if graph builder deduplication masked a coexisting same-file caller
            if not external_usage and not has_ambiguous_line_metadata:
                for ref in project.references:
                    if (
                        ref.file_id == symbol.file_id
                        and ref.name == symbol.name
                        and (ref.line < symbol.start_line or ref.line > symbol.end_line)
                    ):
                        if has_multiple_same_name_in_file:
                            if (
                                ref.qualified_name
                                and symbol.qualified_name
                                and ref.qualified_name == symbol.qualified_name
                            ):
                                external_usage.append(
                                    Relationship(
                                        source_id=symbol.file_id,
                                        target_id=symbol.id,
                                        relationship_type=RelationshipType.REFERENCES,
                                        metadata={
                                            "line": str(ref.line),
                                            "source": "project_references",
                                        },
                                    )
                                )
                            elif ref.qualified_name:
                                # Reference explicitly names a different qualified symbol
                                pass
                            else:
                                has_ambiguous_same_name_reference = True
                        else:
                            external_usage.append(
                                Relationship(
                                    source_id=symbol.file_id,
                                    target_id=symbol.id,
                                    relationship_type=RelationshipType.REFERENCES,
                                    metadata={
                                        "line": str(ref.line),
                                        "source": "project_references",
                                    },
                                )
                            )

            if not external_usage:
                # If incoming same-file reference had ambiguous line metadata, classify conservatively
                if has_ambiguous_line_metadata:
                    any_missing_provenance = True
                    unassessable_list.append(
                        UnusedCandidateItem(
                            entity_id=str(symbol.id),
                            name=symbol.name,
                            kind=symbol.kind,
                            path=file_path,
                            start_line=symbol.start_line,
                            end_line=symbol.end_line,
                            qualified_name=symbol.qualified_name,
                            classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                            reason="Incoming reference from containing file lacks valid line metadata; cannot distinguish self-recursion from separate caller.",
                            evidence=(),
                            limitations=(
                                "Missing reference line provenance prevents reliable usage assessment.",
                            ),
                        )
                    )
                    continue

                if has_ambiguous_same_name_reference:
                    any_missing_provenance = True
                    unassessable_list.append(
                        UnusedCandidateItem(
                            entity_id=str(symbol.id),
                            name=symbol.name,
                            kind=symbol.kind,
                            path=file_path,
                            start_line=symbol.start_line,
                            end_line=symbol.end_line,
                            qualified_name=symbol.qualified_name,
                            classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                            reason=f"Multiple same-named symbols ('{symbol.name}') in containing file make incoming reference target ambiguous.",
                            evidence=(),
                            limitations=(
                                "Ambiguous reference resolution among same-named symbols prevents definitive classification.",
                            ),
                        )
                    )
                    continue

                # Check runtime protocol / dynamic discovery / entry-point conventions
                is_uncertain, convention_reason = _is_convention_uncertainty(
                    symbol, file, file_path
                )
                if is_uncertain:
                    unassessable_list.append(
                        UnusedCandidateItem(
                            entity_id=str(symbol.id),
                            name=symbol.name,
                            kind=symbol.kind,
                            path=file_path,
                            start_line=symbol.start_line,
                            end_line=symbol.end_line,
                            qualified_name=symbol.qualified_name,
                            classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                            reason=convention_reason,
                            evidence=(),
                            limitations=(
                                "Dynamic runtime invocation or test runner discovery cannot be verified statically.",
                            ),
                        )
                    )
                    continue

                # Confirmed apparent unused candidate
                evidence_items: list[str] = [
                    "No external incoming references, calls, or inheritance relationships detected in AST."
                ]
                if self_refs_count > 0:
                    evidence_items.append(
                        f"Detected {self_refs_count} self-referential reference(s) within own definition."
                    )

                candidates_list.append(
                    UnusedCandidateItem(
                        entity_id=str(symbol.id),
                        name=symbol.name,
                        kind=symbol.kind,
                        path=file_path,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        qualified_name=symbol.qualified_name,
                        classification=UnusedClassification.APPARENT_UNUSED_CANDIDATE.value,
                        reason="No external incoming references, calls, or inheritance relationships detected.",
                        evidence=tuple(evidence_items),
                        limitations=(),
                    )
                )

    # 2. Analyze files
    if include_files:
        for file in project.files:
            if file.is_ignored or file.is_generated:
                continue

            # Only analyze source files (e.g. Python modules)
            if file.extension not in (".py", ".pyi"):
                continue

            total_entities_analyzed += 1
            file_path = _to_repo_relative_path(file.path, project.root_path)

            if file_path in file_errors:
                unassessable_list.append(
                    UnusedCandidateItem(
                        entity_id=str(file.id),
                        name=file.name,
                        kind="file",
                        path=file_path,
                        classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                        reason=f"File encountered analysis error: {file_errors[file_path][0]}",
                        evidence=(),
                        limitations=(
                            "File analysis error limits assessment reliability.",
                        ),
                    )
                )
                continue

            # Check incoming imports to this file
            incoming_file_rels = incoming_rels.get(file.id, [])
            incoming_imports = [
                r
                for r in incoming_file_rels
                if (
                    r.relationship_type == RelationshipType.IMPORTS
                    or r.relationship_type == "imports"
                )
                and r.source_id != file.id
            ]

            # Check if any symbol in this file has external usage
            symbols_in_file = [
                s
                for s in project.symbols
                if s.file_id == file.id and s.kind != "import"
            ]
            symbol_has_external_usage = False
            for sym in symbols_in_file:
                for r in incoming_rels.get(sym.id, []):
                    if (
                        r.relationship_type in usage_rel_types
                        and r.source_id != file.id
                    ):
                        symbol_has_external_usage = True
                        break
                if symbol_has_external_usage:
                    break

            if not incoming_imports and not symbol_has_external_usage:
                # Check if entry point or test file convention
                if file.name in STANDARD_ENTRY_POINT_FILENAMES:
                    unassessable_list.append(
                        UnusedCandidateItem(
                            entity_id=str(file.id),
                            name=file.name,
                            kind="file",
                            path=file_path,
                            classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                            reason=f"Standard entry-point module convention ('{file.name}'); may be executed directly without static imports.",
                            evidence=(),
                            limitations=(
                                "Direct execution or framework loading conventions cannot be verified statically.",
                            ),
                        )
                    )
                    continue

                if _is_test_runner_file(file.name):
                    unassessable_list.append(
                        UnusedCandidateItem(
                            entity_id=str(file.id),
                            name=file.name,
                            kind="file",
                            path=file_path,
                            classification=UnusedClassification.CANNOT_ASSESS_RELIABLY.value,
                            reason="Test suite file; discovered and executed dynamically by test runner without static imports.",
                            evidence=(),
                            limitations=(
                                "Test runner framework discovery cannot be verified statically.",
                            ),
                        )
                    )
                    continue

                candidates_list.append(
                    UnusedCandidateItem(
                        entity_id=str(file.id),
                        name=file.name,
                        kind="file",
                        path=file_path,
                        classification=UnusedClassification.APPARENT_UNUSED_CANDIDATE.value,
                        reason="No incoming module imports or external symbol references detected.",
                        evidence=(
                            "No incoming import relationships from other files detected in project.",
                            "No contained symbols referenced from external files.",
                        ),
                        limitations=(),
                    )
                )

    # Deterministic sort: (path, start_line or 0, name, kind)
    candidates_list.sort(
        key=lambda item: (
            item.path,
            item.start_line if item.start_line is not None else 0,
            item.name,
            item.kind,
        )
    )
    unassessable_list.sort(
        key=lambda item: (
            item.path,
            item.start_line if item.start_line is not None else 0,
            item.name,
            item.kind,
        )
    )

    # Count by kind
    by_kind: dict[str, int] = defaultdict(int)
    for c in candidates_list:
        by_kind[c.kind] += 1

    total_candidates_found = len(candidates_list)
    total_unassessable_found = len(unassessable_list)
    truncated = False
    if limit is not None:
        candidates_tuple = tuple(candidates_list[:limit])
        unassessable_tuple = tuple(unassessable_list[:limit])
        if total_candidates_found > limit or total_unassessable_found > limit:
            truncated = True
    else:
        candidates_tuple = tuple(candidates_list)
        unassessable_tuple = tuple(unassessable_list)

    summary = UnusedEntitiesSummary(
        total_entities_analyzed=total_entities_analyzed,
        candidates_count=total_candidates_found,
        unassessable_count=total_unassessable_found,
        by_kind=dict(by_kind),
    )

    # Determine diagnostics and outcome status directly without string checks
    outcome_status = OperationStatus.SUCCESS
    outcome_message = f"Found {total_candidates_found} unused candidate(s)"

    if analysis_status == "not_analyzed":
        outcome_status = OperationStatus.INCOMPLETE
        outcome_message = f"Project analysis status is '{analysis_status}'; found {total_candidates_found} candidate(s)"
        diagnostics.append(
            DiagnosticItem.warning(
                f"Project analysis status is '{analysis_status}'. Unused candidate findings may be incomplete.",
                source="unused_query",
            )
        )
    elif (
        analysis_status in ("incomplete", "failed", "partial")
        or bool(file_errors)
        or bool(ambiguous_errors)
        or any_missing_provenance
    ):
        outcome_status = OperationStatus.PARTIAL
        outcome_message = f"Found {total_candidates_found} unused candidate(s) ({len(unassessable_list)} unassessable)"
        if file_errors or ambiguous_errors:
            msg_parts: list[str] = []
            if file_errors:
                msg_parts.append(
                    f"{len(file_errors)} file(s) encountered analysis errors affecting assessment reliability."
                )
            if ambiguous_errors:
                msg_parts.append(
                    f"{len(ambiguous_errors)} error(s) could not be unambiguously attributed to specific files."
                )
            diagnostics.append(
                DiagnosticItem.info(
                    " ".join(msg_parts),
                    source="unused_query",
                )
            )
        elif any_missing_provenance:
            diagnostics.append(
                DiagnosticItem.info(
                    f"{len(unassessable_list)} entity(ies) could not be assessed reliably due to missing provenance or ambiguity.",
                    source="unused_query",
                )
            )

    outcome = OperationOutcome(
        status=outcome_status,
        message=outcome_message,
        diagnostics=tuple(diagnostics),
        limitations=UNUSED_REPORT_LIMITATIONS,
    )

    return UnusedEntitiesReport(
        repository_path=repo_path,
        analysis_status=analysis_status,
        candidates=candidates_tuple,
        unassessable=unassessable_tuple,
        summary=summary,
        truncated=truncated,
        limit=limit,
        diagnostics=tuple(diagnostics),
        limitations=UNUSED_REPORT_LIMITATIONS,
        outcome=outcome,
    )
