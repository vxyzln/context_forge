import re
from pathlib import Path
from uuid import UUID

from context_forge.models.project import Project

from .models import (
    GroundedEntity,
    GroundedTask,
    TaskInterpretation,
    TaskReference,
)


class TaskGroundingService:
    """Resolve explicit task references against a repository."""

    _PATH_PATTERN = re.compile(
        r"(?<![\w./-])"
        r"(?:[A-Za-z0-9_.-]+/)+"
        r"[A-Za-z0-9_.-]+"
        r"(?![\w./-])"
    )

    _IDENTIFIER_PATTERN = re.compile(
        r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b"
    )

    def ground(
        self,
        project: Project,
        interpretation: TaskInterpretation,
    ) -> GroundedTask:
        references = self._extract_references(interpretation)

        entities: list[GroundedEntity] = []
        unresolved: list[TaskReference] = []
        ambiguous: list[TaskReference] = []

        seen_entities: set[UUID] = set()
        seen_references: set[tuple[str, str]] = set()

        for reference in references:
            key = (reference.kind, reference.value)

            if key in seen_references:
                continue

            seen_references.add(key)

            matches = self._resolve(project, reference)

            if len(matches) == 1:
                entity = matches[0]

                if entity.entity_id not in seen_entities:
                    entities.append(entity)
                    seen_entities.add(entity.entity_id)

            elif not matches:
                unresolved.append(reference)

            else:
                ambiguous.append(reference)

        return GroundedTask(
            interpretation=interpretation,
            entities=tuple(entities),
            unresolved_references=tuple(unresolved),
            ambiguous_references=tuple(ambiguous),
        )

    def _extract_references(
        self,
        interpretation: TaskInterpretation,
    ) -> tuple[TaskReference, ...]:
        values: list[TaskReference] = []

        for value in self._extract_paths(interpretation.task):
            values.append(TaskReference(value=value, kind="file"))

        semantic_values = (
            interpretation.target,
            *interpretation.concepts,
        )

        for value in semantic_values:
            if value is None:
                continue

            value = value.strip()

            if not value:
                continue

            if "/" in value or "\\" in value:
                values.append(TaskReference(value=value, kind="file"))
            elif self._looks_like_identifier(value):
                values.append(TaskReference(value=value, kind="symbol"))

        return tuple(values)

    def _resolve(
        self,
        project: Project,
        reference: TaskReference,
    ) -> list[GroundedEntity]:
        if reference.kind == "file":
            return self._resolve_file(project, reference)

        if reference.kind == "symbol":
            return self._resolve_symbol(project, reference)

        return []

    def _resolve_file(
        self,
        project: Project,
        reference: TaskReference,
    ) -> list[GroundedEntity]:
        normalized_reference = self._normalize_path(reference.value)

        matches = [
            file
            for file in project.files
            if self._normalize_path(file.path.as_posix()) == normalized_reference
        ]

        return [
            GroundedEntity(
                entity_id=file.id,
                entity_type="file",
                reference=reference.value,
                confidence=1.0,
                provenance="exact repository-relative file path",
            )
            for file in matches
        ]

    def _resolve_symbol(
        self,
        project: Project,
        reference: TaskReference,
    ) -> list[GroundedEntity]:
        qualified_matches = [
            symbol
            for symbol in project.symbols
            if symbol.qualified_name == reference.value
        ]

        if qualified_matches:
            return [
                GroundedEntity(
                    entity_id=symbol.id,
                    entity_type="symbol",
                    reference=reference.value,
                    confidence=1.0,
                    provenance="exact symbol qualified name",
                )
                for symbol in qualified_matches
            ]

        name_matches = [
            symbol for symbol in project.symbols if symbol.name == reference.value
        ]

        return [
            GroundedEntity(
                entity_id=symbol.id,
                entity_type="symbol",
                reference=reference.value,
                confidence=0.9,
                provenance="unique exact symbol name",
            )
            for symbol in name_matches
        ]

    @classmethod
    def _extract_paths(cls, task: str) -> tuple[str, ...]:
        return tuple(match.group(0) for match in cls._PATH_PATTERN.finditer(task))

    @classmethod
    def _looks_like_identifier(cls, value: str) -> bool:
        return bool(cls._IDENTIFIER_PATTERN.fullmatch(value))

    @staticmethod
    def _normalize_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        normalized = str(Path(normalized))
        return normalized.replace("\\", "/").lstrip("./")
