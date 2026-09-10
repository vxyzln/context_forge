from dataclasses import dataclass
from pathlib import Path

from context_forge.evaluation.ground_truth import (
    StructuralGroundTruth,
)
from context_forge.evaluation.metrics import MetricResult
from context_forge.models.project import Project


@dataclass(frozen=True)
class StructuralEvaluationResult:
    files: MetricResult
    symbols: MetricResult
    relationships: MetricResult

    @property
    def precision(self) -> float:
        return self._aggregate(
            self.files.precision,
            self.symbols.precision,
            self.relationships.precision,
        )

    @property
    def recall(self) -> float:
        return self._aggregate(
            self.files.recall,
            self.symbols.recall,
            self.relationships.recall,
        )

    @property
    def f1(self) -> float:
        return self._aggregate(
            self.files.f1,
            self.symbols.f1,
            self.relationships.f1,
        )

    @staticmethod
    def _aggregate(*values: float) -> float:
        if not values:
            return 0.0

        return sum(values) / len(values)


class StructuralEvaluator:
    def evaluate(
        self,
        project: Project,
        ground_truth: StructuralGroundTruth,
    ) -> StructuralEvaluationResult:
        actual_files = {file.path for file in project.files}

        expected_files = {expected.path for expected in ground_truth.files}

        actual_symbols = {
            (
                symbol.qualified_name,
                self._symbol_file_path(project, symbol.file_id),
            )
            for symbol in project.symbols
        }

        expected_symbols = {
            (
                expected.qualified_name,
                expected.file_path,
            )
            for expected in ground_truth.symbols
        }

        actual_relationships = {
            (
                self._entity_key(project, relationship.source_id),
                self._entity_key(project, relationship.target_id),
                self._relationship_type(relationship.relationship_type),
            )
            for relationship in project.relationships
        }

        expected_relationships = {
            (
                expected.source,
                expected.target,
                self._relationship_type(expected.relationship_type),
            )
            for expected in ground_truth.relationships
        }

        return StructuralEvaluationResult(
            files=self._metric(
                expected_files,
                actual_files,
            ),
            symbols=self._metric(
                expected_symbols,
                actual_symbols,
            ),
            relationships=self._metric(
                expected_relationships,
                actual_relationships,
            ),
        )

    @staticmethod
    def _metric(
        expected: set[object],
        actual: set[object],
    ) -> MetricResult:
        return MetricResult(
            expected=len(expected),
            actual=len(actual),
            matched=len(expected & actual),
        )

    @staticmethod
    def _relationship_type(
        relationship_type: object,
    ) -> str:
        if hasattr(relationship_type, "value"):
            return str(relationship_type.value)

        return str(relationship_type)

    @staticmethod
    def _symbol_file_path(
        project: Project,
        file_id: object,
    ) -> Path:
        for file in project.files:
            if file.id == file_id:
                return file.path

        return Path("<unknown>")

    @staticmethod
    def _entity_key(
        project: Project,
        entity_id: object,
    ) -> str:
        for file in project.files:
            if file.id == entity_id:
                return f"file:{file.path}"

        for symbol in project.symbols:
            if symbol.id == entity_id:
                return f"symbol:{symbol.qualified_name}"

        for directory in project.directories:
            if directory.id == entity_id:
                return f"directory:{directory.path}"

        return f"unknown:{entity_id}"
