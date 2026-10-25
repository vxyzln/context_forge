from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from context_forge.comparison.models import (
    AffectedComponent,
    AmbiguousMatch,
    ComparisonState,
    FileDiff,
    RelationshipDiff,
    StateValidationResult,
    StructuralComparisonResult,
    SymbolDiff,
)
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship
from context_forge.models.symbol import Symbol
from context_forge.pipeline.freshness import FreshnessState, WorkflowFreshness
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
    OperationStatus,
)
from context_forge.storage.cache import FileFingerprint


def _normalize_rel_path(root: Path, path: Path | str) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def _get_fingerprint_hash(fp: FileFingerprint | Any) -> str | None:
    if fp is None:
        return None
    if hasattr(fp, "content_hash") and fp.content_hash:
        return str(fp.content_hash)
    if isinstance(fp, dict) and fp.get("content_hash"):
        return str(fp["content_hash"])
    return None


def _resolve_endpoint_key(
    entity_id: UUID,
    project: Project,
    file_paths_by_id: dict[UUID, str],
    symbols_by_id: dict[UUID, Symbol],
) -> str | None:
    if entity_id in file_paths_by_id:
        return f"file:{file_paths_by_id[entity_id]}"
    if entity_id in symbols_by_id:
        sym = symbols_by_id[entity_id]
        file_path = file_paths_by_id.get(sym.file_id, "unknown")
        sym_name = sym.qualified_name or sym.name
        return f"symbol:{file_path}:{sym.kind}:{sym_name}"
    return None


def validate_comparison_states(
    before: ComparisonState | Project | None,
    after: ComparisonState | Project | None,
) -> StateValidationResult:
    before_state = (
        ComparisonState.from_project(before) if isinstance(before, Project) else before
    )
    after_state = (
        ComparisonState.from_project(after) if isinstance(after, Project) else after
    )

    diagnostics: list[DiagnosticItem] = []
    limitations: list[str] = []

    if before_state is None or not before_state.is_supplied:
        diag = DiagnosticItem.blocker(
            "Missing before comparison state; a valid before-state must be supplied",
            code="MISSING_BEFORE_STATE",
            source="comparison",
        )
        outcome = OperationOutcome.blocked(
            message="Missing before comparison state",
            diagnostics=(diag,),
            limitations=("Comparison cannot proceed: missing before-state",),
        )
        return StateValidationResult(
            is_valid=False,
            outcome=outcome,
            before_state=before_state,
            after_state=after_state,
            is_complete=False,
            reason="missing_before_state",
        )

    if after_state is None or not after_state.is_supplied:
        diag = DiagnosticItem.blocker(
            "Missing after comparison state; a valid after-state must be supplied",
            code="MISSING_AFTER_STATE",
            source="comparison",
        )
        outcome = OperationOutcome.blocked(
            message="Missing after comparison state",
            diagnostics=(diag,),
            limitations=("Comparison cannot proceed: missing after-state",),
        )
        return StateValidationResult(
            is_valid=False,
            outcome=outcome,
            before_state=before_state,
            after_state=after_state,
            is_complete=False,
            reason="missing_after_state",
        )

    before_key = before_state.repository_key
    after_key = after_state.repository_key
    if before_key and after_key and before_key != after_key:
        diag = DiagnosticItem.blocker(
            f"Repository identity mismatch: before state represents '{before_key}', "
            f"while after state represents '{after_key}'",
            code="REPOSITORY_MISMATCH",
            source="comparison",
            details={"after_key": after_key, "before_key": before_key},
        )
        outcome = OperationOutcome.blocked(
            message="Repository identity mismatch between comparison states",
            diagnostics=(diag,),
            limitations=(
                "Comparison cannot proceed: states belong to different repositories",
            ),
        )
        return StateValidationResult(
            is_valid=False,
            outcome=outcome,
            before_state=before_state,
            after_state=after_state,
            is_complete=False,
            reason="repository_mismatch",
        )

    is_complete = True

    if not before_state.is_complete:
        is_complete = False
        limitations.append("Before-state analysis is incomplete or has errors")
        diagnostics.append(
            DiagnosticItem.warning(
                f"Before-state analysis is incomplete (status='{before_state.analysis_status}', "
                f"errors={len(before_state.analysis_errors)})",
                code="INCOMPLETE_BEFORE_STATE",
                source="comparison",
            )
        )

    if not after_state.is_complete:
        is_complete = False
        limitations.append("After-state analysis is incomplete or has errors")
        diagnostics.append(
            DiagnosticItem.warning(
                f"After-state analysis is incomplete (status='{after_state.analysis_status}', "
                f"errors={len(after_state.analysis_errors)})",
                code="INCOMPLETE_AFTER_STATE",
                source="comparison",
            )
        )

    for state, label in ((before_state, "before"), (after_state, "after")):
        if state.freshness is not None:
            state_freshness = (
                state.freshness.state
                if isinstance(state.freshness, WorkflowFreshness)
                else state.freshness
            )
            if state_freshness == FreshnessState.INCOMPLETE:
                diagnostics.append(
                    DiagnosticItem.warning(
                        f"The {label}-state analysis freshness is marked incomplete",
                        code="INCOMPLETE_FRESHNESS",
                        source="comparison",
                    )
                )
                limitations.append(
                    f"{label.capitalize()}-state freshness is incomplete"
                )
            elif state_freshness == FreshnessState.INDETERMINATE:
                diagnostics.append(
                    DiagnosticItem.warning(
                        f"The freshness of the {label}-state could not be definitively determined",
                        code="INDETERMINATE_FRESHNESS",
                        source="comparison",
                    )
                )
                limitations.append(
                    f"{label.capitalize()}-state freshness is indeterminate"
                )
            elif state_freshness == FreshnessState.STALE:
                if not state.is_historical:
                    diagnostics.append(
                        DiagnosticItem.warning(
                            f"The {label}-state analysis is stale with respect to current repository evidence",
                            code="STALE_STATE",
                            source="comparison",
                        )
                    )
                    limitations.append(f"{label.capitalize()}-state is stale")

    if not is_complete:
        outcome = OperationOutcome.incomplete(
            message="Comparison states validated with incomplete analysis warnings",
            diagnostics=tuple(diagnostics),
            limitations=tuple(sorted(limitations)),
        )
    elif limitations:
        outcome = OperationOutcome.partial(
            message="Comparison states validated with limitations",
            diagnostics=tuple(diagnostics),
            limitations=tuple(sorted(limitations)),
        )
    else:
        outcome = OperationOutcome.success(
            message="Comparison states validated successfully",
            diagnostics=tuple(diagnostics),
        )

    return StateValidationResult(
        is_valid=True,
        outcome=outcome,
        before_state=before_state,
        after_state=after_state,
        is_complete=is_complete,
        reason="valid",
    )


def compare_states(
    before: ComparisonState | Project | None,
    after: ComparisonState | Project | None,
) -> StructuralComparisonResult:
    validation = validate_comparison_states(before, after)

    before_state = validation.before_state
    after_state = validation.after_state

    before_state_id = before_state.state_id if before_state else None
    after_state_id = after_state.state_id if after_state else None
    repository_key = (
        before_state.repository_key
        if before_state and before_state.repository_key
        else (after_state.repository_key if after_state else "")
    )

    if not validation.is_valid:
        return StructuralComparisonResult(
            before_state_id=before_state_id,
            after_state_id=after_state_id,
            repository_key=repository_key,
            outcome=validation.outcome,
            is_complete=False,
            diagnostics=validation.outcome.diagnostics,
            limitations=validation.outcome.limitations,
        )

    assert before_state is not None and before_state.project is not None
    assert after_state is not None and after_state.project is not None

    before_project = before_state.project
    after_project = after_state.project

    diagnostics: list[DiagnosticItem] = list(validation.outcome.diagnostics)
    limitations: list[str] = list(validation.outcome.limitations)
    is_complete = validation.is_complete

    before_file_paths: dict[UUID, str] = {
        f.id: _normalize_rel_path(before_project.root_path, f.path)
        for f in before_project.files
    }
    after_file_paths: dict[UUID, str] = {
        f.id: _normalize_rel_path(after_project.root_path, f.path)
        for f in after_project.files
    }

    before_files_by_path: dict[str, File] = {
        _normalize_rel_path(before_project.root_path, f.path): f
        for f in before_project.files
    }
    after_files_by_path: dict[str, File] = {
        _normalize_rel_path(after_project.root_path, f.path): f
        for f in after_project.files
    }

    before_fps: dict[str, str] = {}
    if before_state.fingerprints:
        for p, fp in before_state.fingerprints.items():
            norm_p = _normalize_rel_path(before_project.root_path, p)
            h = _get_fingerprint_hash(fp)
            if h:
                before_fps[norm_p] = h

    after_fps: dict[str, str] = {}
    if after_state.fingerprints:
        for p, fp in after_state.fingerprints.items():
            norm_p = _normalize_rel_path(after_project.root_path, p)
            h = _get_fingerprint_hash(fp)
            if h:
                after_fps[norm_p] = h

    added_files: list[FileDiff] = []
    removed_files: list[FileDiff] = []
    modified_files: list[FileDiff] = []
    moved_files: list[FileDiff] = []
    ambiguous_matches: list[AmbiguousMatch] = []

    shared_paths = set(before_files_by_path.keys()) & set(after_files_by_path.keys())
    only_before_paths = set(before_files_by_path.keys()) - set(
        after_files_by_path.keys()
    )
    only_after_paths = set(after_files_by_path.keys()) - set(
        before_files_by_path.keys()
    )

    for path in sorted(shared_paths):
        b_file = before_files_by_path[path]
        a_file = after_files_by_path[path]
        b_hash = before_fps.get(path)
        a_hash = after_fps.get(path)

        if b_hash and a_hash:
            if b_hash != a_hash:
                details: dict[str, Any] = {"reason": "content_hash_changed"}
                if not before_state.is_complete or not after_state.is_complete:
                    details["qualification"] = (
                        "unconfirmed_modification_due_to_incomplete_analysis"
                    )
                modified_files.append(
                    FileDiff(
                        path=path,
                        change_type="modified",
                        before_path=path,
                        after_path=path,
                        before_fingerprint=b_hash,
                        after_fingerprint=a_hash,
                        details=details,
                    )
                )
        elif b_file.size != a_file.size:
            details = {
                "before_size": b_file.size,
                "after_size": a_file.size,
                "reason": "size_changed",
            }
            if not before_state.is_complete or not after_state.is_complete:
                details["qualification"] = (
                    "unconfirmed_modification_due_to_incomplete_analysis"
                )
            modified_files.append(
                FileDiff(
                    path=path,
                    change_type="modified",
                    before_path=path,
                    after_path=path,
                    details=details,
                )
            )

    matched_before_moves: set[str] = set()
    matched_after_moves: set[str] = set()

    if before_fps and after_fps:
        rem_by_hash: dict[str, list[str]] = {}
        for p in only_before_paths:
            h = before_fps.get(p)
            if h:
                rem_by_hash.setdefault(h, []).append(p)

        add_by_hash: dict[str, list[str]] = {}
        for p in only_after_paths:
            h = after_fps.get(p)
            if h:
                add_by_hash.setdefault(h, []).append(p)

        for h, rem_candidates in sorted(rem_by_hash.items()):
            add_candidates = add_by_hash.get(h, [])
            if not add_candidates:
                continue

            if len(rem_candidates) == 1 and len(add_candidates) == 1:
                old_p = rem_candidates[0]
                new_p = add_candidates[0]
                moved_files.append(
                    FileDiff(
                        path=new_p,
                        change_type="moved",
                        before_path=old_p,
                        after_path=new_p,
                        before_fingerprint=h,
                        after_fingerprint=h,
                        details={"reason": "content_hash_match"},
                    )
                )
                matched_before_moves.add(old_p)
                matched_after_moves.add(new_p)
            else:
                ambiguous_matches.append(
                    AmbiguousMatch(
                        category="file",
                        before_candidates=tuple(sorted(rem_candidates)),
                        after_candidates=tuple(sorted(add_candidates)),
                        reason=f"Multiple files share identical content hash '{h}' across states",
                    )
                )

    for p in sorted(only_after_paths - matched_after_moves):
        details = {}
        if not before_state.is_complete:
            details["qualification"] = "unconfirmed_addition_due_to_incomplete_analysis"
        added_files.append(
            FileDiff(
                path=p,
                change_type="added",
                after_path=p,
                after_fingerprint=after_fps.get(p),
                details=details,
            )
        )

    for p in sorted(only_before_paths - matched_before_moves):
        details = {}
        if not after_state.is_complete:
            details["qualification"] = "unconfirmed_removal_due_to_incomplete_analysis"
        removed_files.append(
            FileDiff(
                path=p,
                change_type="removed",
                before_path=p,
                before_fingerprint=before_fps.get(p),
                details=details,
            )
        )

    before_symbols_by_id = {s.id: s for s in before_project.symbols}
    after_symbols_by_id = {s.id: s for s in after_project.symbols}

    def _group_symbols_by_key(
        symbols: list[Symbol],
        file_paths: dict[UUID, str],
        state_label: str,
    ) -> dict[tuple[str, str, str], list[Symbol]]:
        grouped: dict[tuple[str, str, str], list[Symbol]] = {}
        for s in symbols:
            f_path = file_paths.get(s.file_id, "unknown")
            qname = s.qualified_name or s.name
            grouped.setdefault((f_path, s.kind, qname), []).append(s)

        for key, sym_list in sorted(grouped.items()):
            if len(sym_list) > 1:
                f_path, kind, qname = key
                diagnostics.append(
                    DiagnosticItem.warning(
                        f"Multiple symbols share identical key '{f_path}:{kind}:{qname}' in {state_label} state",
                        code="SYMBOL_COLLISION",
                        source="comparison",
                        details={
                            "count": len(sym_list),
                            "file_path": f_path,
                            "kind": kind,
                            "name": qname,
                        },
                    )
                )
                limitations.append(
                    f"Symbol key collision detected in {state_label}-state for '{qname}' in '{f_path}'"
                )
        return grouped

    before_symbols_by_key = _group_symbols_by_key(
        before_project.symbols, before_file_paths, "before"
    )
    after_symbols_by_key = _group_symbols_by_key(
        after_project.symbols, after_file_paths, "after"
    )

    added_symbols: list[SymbolDiff] = []
    removed_symbols: list[SymbolDiff] = []
    modified_symbols: list[SymbolDiff] = []
    moved_symbols: list[SymbolDiff] = []

    shared_sym_keys = set(before_symbols_by_key.keys()) & set(
        after_symbols_by_key.keys()
    )
    only_before_sym_keys = set(before_symbols_by_key.keys()) - set(
        after_symbols_by_key.keys()
    )
    only_after_sym_keys = set(after_symbols_by_key.keys()) - set(
        before_symbols_by_key.keys()
    )

    for key in sorted(shared_sym_keys):
        b_syms = before_symbols_by_key[key]
        a_syms = after_symbols_by_key[key]
        f_path, kind, qname = key

        if len(b_syms) == 1 and len(a_syms) == 1:
            b_sym = b_syms[0]
            a_sym = a_syms[0]

            sig_changed = (
                b_sym.signature is not None
                and a_sym.signature is not None
                and b_sym.signature != a_sym.signature
            ) or ((b_sym.signature is None) != (a_sym.signature is None))

            if sig_changed:
                details = {"reason": "signature_changed"}
                if not before_state.is_complete or not after_state.is_complete:
                    details["qualification"] = (
                        "unconfirmed_modification_due_to_incomplete_analysis"
                    )
                modified_symbols.append(
                    SymbolDiff(
                        name=a_sym.name,
                        kind=kind,
                        file_path=f_path,
                        change_type="modified",
                        qualified_name=a_sym.qualified_name,
                        before_signature=b_sym.signature,
                        after_signature=a_sym.signature,
                        before_lines=(b_sym.start_line, b_sym.end_line),
                        after_lines=(a_sym.start_line, a_sym.end_line),
                        is_line_shift_only=False,
                        details=details,
                    )
                )
        else:
            ambiguous_matches.append(
                AmbiguousMatch(
                    category="symbol",
                    before_candidates=tuple(
                        sorted(
                            f"{f_path}:{s.kind}:{qname}:{s.start_line}-{s.end_line}"
                            for s in b_syms
                        )
                    ),
                    after_candidates=tuple(
                        sorted(
                            f"{f_path}:{s.kind}:{qname}:{s.start_line}-{s.end_line}"
                            for s in a_syms
                        )
                    ),
                    reason=f"Symbol collision: multiple candidates share identical key '{f_path}:{kind}:{qname}' across states",
                )
            )

    matched_before_sym_keys: set[tuple[str, str, str]] = set()
    matched_after_sym_keys: set[tuple[str, str, str]] = set()

    unmatched_before_by_name: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for key in only_before_sym_keys:
        f_path, kind, qname = key
        unmatched_before_by_name.setdefault((kind, qname), []).append(key)

    unmatched_after_by_name: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for key in only_after_sym_keys:
        f_path, kind, qname = key
        unmatched_after_by_name.setdefault((kind, qname), []).append(key)

    for name_key, b_keys in sorted(unmatched_before_by_name.items()):
        a_keys = unmatched_after_by_name.get(name_key, [])
        if not a_keys:
            continue

        if (
            len(b_keys) == 1
            and len(a_keys) == 1
            and len(before_symbols_by_key[b_keys[0]]) == 1
            and len(after_symbols_by_key[a_keys[0]]) == 1
        ):
            b_key = b_keys[0]
            a_key = a_keys[0]
            b_sym = before_symbols_by_key[b_key][0]
            a_sym = after_symbols_by_key[a_key][0]

            sigs_compatible = (
                b_sym.signature == a_sym.signature
                or b_sym.signature is None
                or a_sym.signature is None
            )

            if sigs_compatible:
                moved_symbols.append(
                    SymbolDiff(
                        name=a_sym.name,
                        kind=a_sym.kind,
                        file_path=a_key[0],
                        change_type="moved",
                        qualified_name=a_sym.qualified_name,
                        before_file_path=b_key[0],
                        after_file_path=a_key[0],
                        before_signature=b_sym.signature,
                        after_signature=a_sym.signature,
                        before_lines=(b_sym.start_line, b_sym.end_line),
                        after_lines=(a_sym.start_line, a_sym.end_line),
                        details={"reason": "name_and_kind_match_across_files"},
                    )
                )
                matched_before_sym_keys.add(b_key)
                matched_after_sym_keys.add(a_key)
        else:
            b_cands = tuple(sorted(f"{k[0]}:{k[1]}:{k[2]}" for k in b_keys))
            a_cands = tuple(sorted(f"{k[0]}:{k[1]}:{k[2]}" for k in a_keys))
            ambiguous_matches.append(
                AmbiguousMatch(
                    category="symbol",
                    before_candidates=b_cands,
                    after_candidates=a_cands,
                    reason=f"Multiple symbol candidates match name '{name_key[1]}' and kind '{name_key[0]}' across files",
                )
            )

    for key in sorted(only_after_sym_keys - matched_after_sym_keys):
        details = {}
        if not before_state.is_complete:
            details["qualification"] = "unconfirmed_addition_due_to_incomplete_analysis"
        for s in after_symbols_by_key[key]:
            added_symbols.append(
                SymbolDiff(
                    name=s.name,
                    kind=s.kind,
                    file_path=key[0],
                    change_type="added",
                    qualified_name=s.qualified_name,
                    after_signature=s.signature,
                    after_lines=(s.start_line, s.end_line),
                    details=details,
                )
            )

    for key in sorted(only_before_sym_keys - matched_before_sym_keys):
        details = {}
        if not after_state.is_complete:
            details["qualification"] = "unconfirmed_removal_due_to_incomplete_analysis"
        for s in before_symbols_by_key[key]:
            removed_symbols.append(
                SymbolDiff(
                    name=s.name,
                    kind=s.kind,
                    file_path=key[0],
                    change_type="removed",
                    qualified_name=s.qualified_name,
                    before_signature=s.signature,
                    before_lines=(s.start_line, s.end_line),
                    details=details,
                )
            )

    added_relationships: list[RelationshipDiff] = []
    removed_relationships: list[RelationshipDiff] = []
    modified_relationships: list[RelationshipDiff] = []

    def _index_relationships(
        rels: list[Relationship],
        project: Project,
        file_paths: dict[UUID, str],
        symbols_by_id: dict[UUID, Symbol],
        state_label: str,
    ) -> dict[tuple[str, str, str], list[Relationship]]:
        indexed: dict[tuple[str, str, str], list[Relationship]] = {}
        for r in rels:
            src_key = _resolve_endpoint_key(
                r.source_id, project, file_paths, symbols_by_id
            )
            tgt_key = _resolve_endpoint_key(
                r.target_id, project, file_paths, symbols_by_id
            )

            if src_key is None or tgt_key is None:
                unresolved_id = r.source_id if src_key is None else r.target_id
                diagnostics.append(
                    DiagnosticItem.warning(
                        f"Relationship endpoint '{unresolved_id}' could not be matched reliably in {state_label} state",
                        code="UNRESOLVED_RELATIONSHIP_ENDPOINT",
                        source="comparison",
                        details={
                            "relationship_type": str(r.relationship_type),
                            "source_id": str(r.source_id),
                            "target_id": str(r.target_id),
                        },
                    )
                )
                limitations.append(
                    f"Relationship with unresolved endpoint in {state_label}-state was excluded from difference calculation"
                )
                continue

            rel_type = (
                r.relationship_type.value
                if hasattr(r.relationship_type, "value")
                else str(r.relationship_type)
            )
            indexed.setdefault((src_key, tgt_key, rel_type), []).append(r)

        for key, r_list in sorted(indexed.items()):
            if len(r_list) > 1:
                src_key, tgt_key, rel_type = key
                diagnostics.append(
                    DiagnosticItem.warning(
                        f"Multiple relationships share identical key '({src_key} -> {tgt_key}, {rel_type})' in {state_label} state",
                        code="RELATIONSHIP_COLLISION",
                        source="comparison",
                        details={
                            "count": len(r_list),
                            "relationship_type": rel_type,
                            "source_key": src_key,
                            "target_key": tgt_key,
                        },
                    )
                )
                limitations.append(
                    f"Relationship collision detected in {state_label}-state for '{src_key} -> {tgt_key}'"
                )
        return indexed

    before_indexed_rels = _index_relationships(
        before_project.relationships,
        before_project,
        before_file_paths,
        before_symbols_by_id,
        "before",
    )
    after_indexed_rels = _index_relationships(
        after_project.relationships,
        after_project,
        after_file_paths,
        after_symbols_by_id,
        "after",
    )

    shared_rel_keys = set(before_indexed_rels.keys()) & set(after_indexed_rels.keys())
    only_before_rel_keys = set(before_indexed_rels.keys()) - set(
        after_indexed_rels.keys()
    )
    only_after_rel_keys = set(after_indexed_rels.keys()) - set(
        before_indexed_rels.keys()
    )

    for key in sorted(shared_rel_keys):
        b_rels = before_indexed_rels[key]
        a_rels = after_indexed_rels[key]

        if len(b_rels) == 1 and len(a_rels) == 1:
            b_rel = b_rels[0]
            a_rel = a_rels[0]

            conf_changed = abs(b_rel.confidence - a_rel.confidence) > 1e-6
            meta_changed = b_rel.metadata != a_rel.metadata

            if conf_changed or meta_changed:
                details = {}
                if not before_state.is_complete or not after_state.is_complete:
                    details["qualification"] = (
                        "unconfirmed_modification_due_to_incomplete_analysis"
                    )
                modified_relationships.append(
                    RelationshipDiff(
                        source_key=key[0],
                        target_key=key[1],
                        relationship_type=key[2],
                        change_type="modified",
                        before_confidence=b_rel.confidence,
                        after_confidence=a_rel.confidence,
                        metadata_changes={
                            "before": b_rel.metadata,
                            "after": a_rel.metadata,
                        },
                        details=details,
                    )
                )
        else:
            ambiguous_matches.append(
                AmbiguousMatch(
                    category="relationship",
                    before_candidates=tuple(
                        sorted(f"{key[0]}->{key[1]}:{key[2]}:{r.id}" for r in b_rels)
                    ),
                    after_candidates=tuple(
                        sorted(f"{key[0]}->{key[1]}:{key[2]}:{r.id}" for r in a_rels)
                    ),
                    reason=f"Relationship collision: multiple edges share key '{key[0]} -> {key[1]}' of type '{key[2]}'",
                )
            )

    for key in sorted(only_after_rel_keys):
        details = {}
        if not before_state.is_complete:
            details["qualification"] = "unconfirmed_addition_due_to_incomplete_analysis"
        for r in after_indexed_rels[key]:
            added_relationships.append(
                RelationshipDiff(
                    source_key=key[0],
                    target_key=key[1],
                    relationship_type=key[2],
                    change_type="added",
                    after_confidence=r.confidence,
                    metadata_changes={"after": r.metadata},
                    details=details,
                )
            )

    for key in sorted(only_before_rel_keys):
        details = {}
        if not after_state.is_complete:
            details["qualification"] = "unconfirmed_removal_due_to_incomplete_analysis"
        for r in before_indexed_rels[key]:
            removed_relationships.append(
                RelationshipDiff(
                    source_key=key[0],
                    target_key=key[1],
                    relationship_type=key[2],
                    change_type="removed",
                    before_confidence=r.confidence,
                    metadata_changes={"before": r.metadata},
                    details=details,
                )
            )

    changed_entity_keys: set[str] = set()
    for f in modified_files:
        changed_entity_keys.add(f"file:{f.path}")
    for f in added_files:
        changed_entity_keys.add(f"file:{f.path}")
    for f in removed_files:
        changed_entity_keys.add(f"file:{f.path}")
    for f in moved_files:
        changed_entity_keys.add(f"file:{f.path}")
        if f.before_path:
            changed_entity_keys.add(f"file:{f.before_path}")

    for s in modified_symbols:
        changed_entity_keys.add(
            f"symbol:{s.file_path}:{s.kind}:{s.qualified_name or s.name}"
        )
    for s in added_symbols:
        changed_entity_keys.add(
            f"symbol:{s.file_path}:{s.kind}:{s.qualified_name or s.name}"
        )
    for s in removed_symbols:
        changed_entity_keys.add(
            f"symbol:{s.file_path}:{s.kind}:{s.qualified_name or s.name}"
        )
    for s in moved_symbols:
        changed_entity_keys.add(
            f"symbol:{s.file_path}:{s.kind}:{s.qualified_name or s.name}"
        )
        if s.before_file_path:
            changed_entity_keys.add(
                f"symbol:{s.before_file_path}:{s.kind}:{s.qualified_name or s.name}"
            )

    affected_components_map: dict[str, AffectedComponent] = {}

    for src_key, tgt_key, rel_type in after_indexed_rels:
        if tgt_key in changed_entity_keys and src_key not in changed_entity_keys:
            entity_type = "file" if src_key.startswith("file:") else "symbol"
            path = (
                src_key[len("file:") :]
                if src_key.startswith("file:")
                else src_key.split(":")[1]
            )
            reason = f"Depends on changed {tgt_key} via {rel_type}"
            affected_components_map[src_key] = AffectedComponent(
                entity_key=src_key,
                entity_type=entity_type,
                path=path,
                reason=reason,
            )

    affected_components = tuple(
        sorted(
            affected_components_map.values(),
            key=lambda a: (a.path, a.entity_key, a.reason),
        )
    )

    if not is_complete:
        outcome_status = OperationStatus.INCOMPLETE
        outcome_msg = "Comparison completed with incomplete analysis limitations"
    elif limitations:
        outcome_status = OperationStatus.PARTIAL
        outcome_msg = "Comparison completed with limitations"
    else:
        outcome_status = OperationStatus.SUCCESS
        outcome_msg = "Comparison completed successfully"

    final_outcome = OperationOutcome(
        status=outcome_status,
        message=outcome_msg,
        diagnostics=tuple(
            sorted(
                diagnostics,
                key=lambda d: (
                    d.severity.value,
                    d.code or "",
                    d.path or "",
                    d.line or 0,
                    d.message,
                ),
            )
        ),
        limitations=tuple(sorted(set(limitations))),
    )

    return StructuralComparisonResult(
        before_state_id=before_state_id,
        after_state_id=after_state_id,
        repository_key=repository_key,
        outcome=final_outcome,
        is_complete=is_complete,
        added_files=tuple(sorted(added_files, key=lambda f: f.path)),
        removed_files=tuple(sorted(removed_files, key=lambda f: f.path)),
        modified_files=tuple(sorted(modified_files, key=lambda f: f.path)),
        moved_files=tuple(
            sorted(
                moved_files,
                key=lambda f: (f.before_path or "", f.after_path or ""),
            )
        ),
        added_symbols=tuple(
            sorted(added_symbols, key=lambda s: (s.file_path, s.kind, s.name))
        ),
        removed_symbols=tuple(
            sorted(removed_symbols, key=lambda s: (s.file_path, s.kind, s.name))
        ),
        modified_symbols=tuple(
            sorted(modified_symbols, key=lambda s: (s.file_path, s.kind, s.name))
        ),
        moved_symbols=tuple(
            sorted(
                moved_symbols,
                key=lambda s: (
                    s.before_file_path or "",
                    s.after_file_path or "",
                    s.kind,
                    s.name,
                ),
            )
        ),
        added_relationships=tuple(
            sorted(
                added_relationships,
                key=lambda r: (r.source_key, r.target_key, r.relationship_type),
            )
        ),
        removed_relationships=tuple(
            sorted(
                removed_relationships,
                key=lambda r: (r.source_key, r.target_key, r.relationship_type),
            )
        ),
        modified_relationships=tuple(
            sorted(
                modified_relationships,
                key=lambda r: (r.source_key, r.target_key, r.relationship_type),
            )
        ),
        ambiguous_matches=tuple(
            sorted(
                ambiguous_matches,
                key=lambda m: (m.category, m.reason, str(m.before_candidates)),
            )
        ),
        affected_components=affected_components,
        diagnostics=final_outcome.diagnostics,
        limitations=final_outcome.limitations,
    )
