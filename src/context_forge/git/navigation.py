from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from context_forge.git.models import GitStatusEntry, GitStatusResult
from context_forge.reporting.contract import (
    DiagnosticItem,
    OperationOutcome,
)

if TYPE_CHECKING:
    from context_forge.models.project import Project


class EntityMappingStatus(str, Enum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"

    @property
    def is_matched(self) -> bool:
        return self is EntityMappingStatus.MATCHED

    @property
    def is_unmatched(self) -> bool:
        return self is EntityMappingStatus.UNMATCHED

    @property
    def is_ambiguous(self) -> bool:
        return self is EntityMappingStatus.AMBIGUOUS

    @property
    def is_unavailable(self) -> bool:
        return self is EntityMappingStatus.UNAVAILABLE


@dataclass(frozen=True)
class MappedEntity:
    entity_id: UUID
    entity_type: str
    path: str
    name: str
    exists_in_source: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id.hex,
            "entity_type": self.entity_type,
            "path": self.path,
            "name": self.name,
            "exists_in_source": self.exists_in_source,
        }


@dataclass(frozen=True)
class PathEntityMapping:
    git_path: str
    project_path: str | None
    status: EntityMappingStatus
    git_status_entry: GitStatusEntry | None = None
    matched_entity: MappedEntity | None = None
    candidate_entities: tuple[MappedEntity, ...] = ()
    reason: str = ""
    limitations: tuple[str, ...] = ()
    is_rename: bool = False
    orig_git_path: str | None = None
    orig_project_path: str | None = None
    orig_status: EntityMappingStatus | None = None
    orig_matched_entity: MappedEntity | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "git_path": self.git_path,
            "project_path": self.project_path,
            "status": self.status.value,
            "reason": self.reason,
            "limitations": list(self.limitations),
            "matched_entity": (
                self.matched_entity.to_dict() if self.matched_entity else None
            ),
            "candidate_entities": [c.to_dict() for c in self.candidate_entities],
            "git_status_entry": (
                self.git_status_entry.to_dict() if self.git_status_entry else None
            ),
        }
        if self.is_rename:
            data.update(
                {
                    "is_rename": True,
                    "orig_git_path": self.orig_git_path,
                    "orig_project_path": self.orig_project_path,
                    "orig_status": (
                        self.orig_status.value if self.orig_status else None
                    ),
                    "orig_matched_entity": (
                        self.orig_matched_entity.to_dict()
                        if self.orig_matched_entity
                        else None
                    ),
                }
            )
        return data


@dataclass(frozen=True)
class GitNavigationContext:
    git_root: Path | None
    project_root: Path
    is_git_repository: bool
    git_status: GitStatusResult
    mappings: tuple[PathEntityMapping, ...] = ()
    matched_count: int = 0
    unmatched_count: int = 0
    ambiguous_count: int = 0
    unavailable_count: int = 0
    outcome: OperationOutcome = field(
        default_factory=lambda: OperationOutcome.success()
    )
    diagnostics: tuple[DiagnosticItem, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def has_changes(self) -> bool:
        return len(self.mappings) > 0

    @property
    def is_clean(self) -> bool:
        return self.outcome.is_success and len(self.mappings) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "git_root": self.git_root.as_posix() if self.git_root else None,
            "project_root": self.project_root.as_posix(),
            "is_git_repository": self.is_git_repository,
            "has_changes": self.has_changes,
            "is_clean": self.is_clean,
            "counts": {
                "total": len(self.mappings),
                "matched": self.matched_count,
                "unmatched": self.unmatched_count,
                "ambiguous": self.ambiguous_count,
                "unavailable": self.unavailable_count,
            },
            "mappings": [m.to_dict() for m in self.mappings],
            "git_status": self.git_status.to_dict(),
            "limitations": list(self.limitations),
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "outcome": self.outcome.to_dict(),
        }


def normalize_relative_path(path_str: str) -> str:
    p = path_str.replace("\\", "/").removeprefix("./")
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p


def reconcile_git_path_to_project(
    git_path: str,
    git_root: Path,
    project_root: Path,
) -> tuple[str | None, str | None]:
    git_root_res = git_root.resolve()
    project_root_res = project_root.resolve()

    norm_git_path = normalize_relative_path(git_path)
    segments = norm_git_path.split("/")

    is_windows_abs = (
        len(norm_git_path) >= 2
        and norm_git_path[1] == ":"
        and norm_git_path[0].isalpha()
    )
    if (
        Path(norm_git_path).is_absolute()
        or norm_git_path.startswith("/")
        or is_windows_abs
        or ".." in segments
    ):
        return (
            None,
            f"Git path '{git_path}' is an absolute path or escapes the repository root.",
        )

    if git_root_res == project_root_res:
        return norm_git_path, None

    try:
        rel_root = project_root_res.relative_to(git_root_res).as_posix()
    except ValueError:
        return (
            None,
            f"Git root '{git_root_res}' and project root '{project_root_res}' cannot be reconciled.",
        )

    if norm_git_path == rel_root:
        return "", None

    if norm_git_path.startswith(rel_root + "/"):
        rel_proj_path = norm_git_path[len(rel_root) + 1 :]
        return rel_proj_path, None

    return (
        None,
        f"Git changed path '{git_path}' is outside the project root '{project_root_res.name}'.",
    )


def _match_project_entity(
    proj_path: str,
    project: Project,
    git_status_entry: GitStatusEntry | None = None,
) -> tuple[
    EntityMappingStatus,
    MappedEntity | None,
    tuple[MappedEntity, ...],
    str,
    tuple[str, ...],
]:
    norm_path = normalize_relative_path(proj_path)
    limitations: list[str] = []

    matching_files = [
        f
        for f in project.files
        if normalize_relative_path(f.path.as_posix()) == norm_path
    ]

    matching_dirs = [
        d
        for d in project.directories
        if normalize_relative_path(d.path.as_posix()) == norm_path
    ]

    total_matches = len(matching_files) + len(matching_dirs)

    if total_matches > 1:
        candidates: list[MappedEntity] = []
        for f in matching_files:
            source_exists = (project.root_path / f.path).is_file()
            candidates.append(
                MappedEntity(
                    entity_id=f.id,
                    entity_type="file",
                    path=f.path.as_posix(),
                    name=f.name,
                    exists_in_source=source_exists,
                )
            )
        for d in matching_dirs:
            source_exists = (project.root_path / d.path).is_dir()
            candidates.append(
                MappedEntity(
                    entity_id=d.id,
                    entity_type="directory",
                    path=d.path.as_posix(),
                    name=d.name,
                    exists_in_source=source_exists,
                )
            )
        return (
            EntityMappingStatus.AMBIGUOUS,
            None,
            tuple(candidates),
            f"Multiple entities match path '{norm_path}'",
            (
                "Multiple entities match path; ambiguity cannot be resolved automatically.",
            ),
        )

    if len(matching_files) == 1:
        f = matching_files[0]
        source_exists = (project.root_path / f.path).is_file()
        if not source_exists:
            limitations.append(
                "Entity exists in project inventory, but source file is deleted or absent on disk."
            )

        entity = MappedEntity(
            entity_id=f.id,
            entity_type="file",
            path=f.path.as_posix(),
            name=f.name,
            exists_in_source=source_exists,
        )
        return (
            EntityMappingStatus.MATCHED,
            entity,
            (),
            "Matched known repository file",
            tuple(limitations),
        )

    if len(matching_dirs) == 1:
        d = matching_dirs[0]
        source_exists = (project.root_path / d.path).is_dir()
        if not source_exists:
            limitations.append(
                "Entity exists in project inventory, but directory is deleted or absent on disk."
            )

        entity = MappedEntity(
            entity_id=d.id,
            entity_type="directory",
            path=d.path.as_posix(),
            name=d.name,
            exists_in_source=source_exists,
        )
        return (
            EntityMappingStatus.MATCHED,
            entity,
            (),
            "Matched known repository directory",
            tuple(limitations),
        )

    if git_status_entry and git_status_entry.is_untracked:
        limitations.append("Path is untracked and has not been analyzed.")
    elif git_status_entry and git_status_entry.is_added:
        limitations.append("Path is a newly added file not yet analyzed.")
    elif git_status_entry and git_status_entry.is_deleted:
        limitations.append("Path is deleted and absent from project inventory.")

    return (
        EntityMappingStatus.UNMATCHED,
        None,
        (),
        "No matching file or directory entity in project inventory",
        tuple(limitations),
    )


def map_changed_paths(
    project: Project,
    git_status: GitStatusResult,
) -> GitNavigationContext:
    project_root = project.root_path.resolve()
    git_root = git_status.root_path

    if not git_status.is_repository:
        return GitNavigationContext(
            git_root=None,
            project_root=project_root,
            is_git_repository=False,
            git_status=git_status,
            mappings=(),
            outcome=git_status.outcome,
            diagnostics=git_status.outcome.diagnostics,
            limitations=git_status.limitations,
        )

    if git_status.outcome.is_failed or git_status.outcome.is_blocked:
        return GitNavigationContext(
            git_root=git_root,
            project_root=project_root,
            is_git_repository=True,
            git_status=git_status,
            mappings=(),
            outcome=git_status.outcome,
            diagnostics=git_status.outcome.diagnostics,
            limitations=git_status.limitations,
        )

    if git_status.is_clean:
        return GitNavigationContext(
            git_root=git_root,
            project_root=project_root,
            is_git_repository=True,
            git_status=git_status,
            mappings=(),
            matched_count=0,
            unmatched_count=0,
            ambiguous_count=0,
            unavailable_count=0,
            outcome=OperationOutcome.success(
                "Working tree is clean; no changes to map"
            ),
            diagnostics=(),
            limitations=(),
        )

    assert git_root is not None

    # TODO: support mapping submodule paths when repository contains submodules
    try:
        project_root.relative_to(git_root.resolve())
        roots_compatible = True
    except ValueError:
        roots_compatible = git_root.resolve() == project_root

    if not roots_compatible:
        diag = DiagnosticItem.blocker(
            f"Git root '{git_root}' and project root '{project_root}' cannot be reconciled",
            code="ROOT_RECONCILIATION_FAILED",
            source="git",
        )
        return GitNavigationContext(
            git_root=git_root,
            project_root=project_root,
            is_git_repository=True,
            git_status=git_status,
            mappings=(),
            unavailable_count=len(git_status.entries),
            outcome=OperationOutcome.blocked(
                "Git and project roots could not be reconciled",
                diagnostics=(diag,),
                limitations=(
                    f"Git root '{git_root}' and project root '{project_root}' cannot be reconciled.",
                ),
            ),
            diagnostics=(diag,),
            limitations=(
                f"Git root '{git_root}' and project root '{project_root}' cannot be reconciled.",
            ),
        )

    mappings: list[PathEntityMapping] = []
    matched_count = 0
    unmatched_count = 0
    ambiguous_count = 0
    unavailable_count = 0
    diagnostics_list: list[DiagnosticItem] = []
    limitations_list: list[str] = []

    for entry in git_status.entries:
        proj_path, root_limitation = reconcile_git_path_to_project(
            entry.path, git_root, project_root
        )

        is_rename = entry.is_renamed and entry.orig_path is not None
        orig_proj_path: str | None = None
        orig_status: EntityMappingStatus | None = None
        orig_matched_entity: MappedEntity | None = None

        if is_rename and entry.orig_path is not None:
            orig_proj_path, _ = reconcile_git_path_to_project(
                entry.orig_path, git_root, project_root
            )
            if orig_proj_path is not None:
                (
                    orig_status,
                    orig_matched_entity,
                    _,
                    _,
                    _,
                ) = _match_project_entity(orig_proj_path, project, entry)

        if proj_path is None:
            mapping = PathEntityMapping(
                git_path=entry.path,
                project_path=None,
                status=EntityMappingStatus.UNMATCHED,
                git_status_entry=entry,
                reason=root_limitation or "Path is outside project root",
                limitations=(root_limitation,) if root_limitation else (),
                is_rename=is_rename,
                orig_git_path=entry.orig_path,
                orig_project_path=orig_proj_path,
                orig_status=orig_status,
                orig_matched_entity=orig_matched_entity,
            )
            unmatched_count += 1
            mappings.append(mapping)
            if root_limitation and root_limitation not in limitations_list:
                limitations_list.append(root_limitation)
            continue

        status, matched_entity, candidates, reason, path_limitations = (
            _match_project_entity(proj_path, project, entry)
        )

        mapping = PathEntityMapping(
            git_path=entry.path,
            project_path=proj_path,
            status=status,
            git_status_entry=entry,
            matched_entity=matched_entity,
            candidate_entities=candidates,
            reason=reason,
            limitations=path_limitations,
            is_rename=is_rename,
            orig_git_path=entry.orig_path,
            orig_project_path=orig_proj_path,
            orig_status=orig_status,
            orig_matched_entity=orig_matched_entity,
        )
        mappings.append(mapping)

        if status == EntityMappingStatus.MATCHED:
            matched_count += 1
        elif status == EntityMappingStatus.UNMATCHED:
            unmatched_count += 1
        elif status == EntityMappingStatus.AMBIGUOUS:
            ambiguous_count += 1
            diagnostics_list.append(
                DiagnosticItem.warning(
                    f"Ambiguous entity match for path: {proj_path}",
                    code="AMBIGUOUS_PATH_MATCH",
                    source="git",
                    path=proj_path,
                )
            )
        elif status == EntityMappingStatus.UNAVAILABLE:
            unavailable_count += 1

        for lim in path_limitations:
            if lim not in limitations_list:
                limitations_list.append(lim)

    sorted_mappings = tuple(
        sorted(
            mappings,
            key=lambda m: (m.git_path, m.status.value, m.project_path or ""),
        )
    )

    total_entries = len(sorted_mappings)
    if matched_count == total_entries and total_entries > 0:
        outcome = OperationOutcome.success(
            f"All {matched_count} changed path(s) successfully mapped to known repository entities",
            diagnostics=tuple(diagnostics_list),
            limitations=tuple(limitations_list),
        )
    else:
        parts: list[str] = []
        if matched_count:
            parts.append(f"{matched_count} matched")
        if unmatched_count:
            parts.append(f"{unmatched_count} unmatched")
        if ambiguous_count:
            parts.append(f"{ambiguous_count} ambiguous")
        if unavailable_count:
            parts.append(f"{unavailable_count} unavailable")

        summary_msg = f"Git-aware navigation context: {', '.join(parts)}"
        outcome = OperationOutcome.partial(
            summary_msg,
            diagnostics=tuple(diagnostics_list),
            limitations=tuple(limitations_list),
        )

    return GitNavigationContext(
        git_root=git_root,
        project_root=project_root,
        is_git_repository=True,
        git_status=git_status,
        mappings=sorted_mappings,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        ambiguous_count=ambiguous_count,
        unavailable_count=unavailable_count,
        outcome=outcome,
        diagnostics=tuple(diagnostics_list),
        limitations=tuple(limitations_list),
    )
