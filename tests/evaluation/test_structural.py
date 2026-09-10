from pathlib import Path

import pytest

from context_forge.evaluation.ground_truth import (
    ExpectedFile,
    ExpectedRelationship,
    ExpectedSymbol,
    StructuralGroundTruth,
)
from context_forge.evaluation.structural import StructuralEvaluator
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship, RelationshipType
from context_forge.models.symbol import Symbol


def build_project() -> Project:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    source_file = File(
        project_id=project.id,
        path=Path("src/main.py"),
        name="main.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    helper_file = File(
        project_id=project.id,
        path=Path("src/helper.py"),
        name="helper.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(source_file)
    project.add_file(helper_file)

    main_symbol = Symbol(
        file_id=source_file.id,
        name="main",
        kind="function",
        start_line=1,
        end_line=3,
        qualified_name="main",
    )

    helper_symbol = Symbol(
        file_id=helper_file.id,
        name="helper",
        kind="function",
        start_line=1,
        end_line=3,
        qualified_name="helper",
    )

    project.add_symbol(main_symbol)
    project.add_symbol(helper_symbol)

    project.add_relationship(
        Relationship(
            source_id=source_file.id,
            target_id=main_symbol.id,
            relationship_type=RelationshipType.DEFINES,
        )
    )

    project.add_relationship(
        Relationship(
            source_id=helper_file.id,
            target_id=helper_symbol.id,
            relationship_type=RelationshipType.DEFINES,
        )
    )

    return project


def test_structural_evaluator_matches_exact_files() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            files=(
                ExpectedFile(Path("src/main.py")),
                ExpectedFile(Path("src/helper.py")),
            ),
        ),
    )

    assert result.files.expected == 2
    assert result.files.actual == 2
    assert result.files.matched == 2
    assert result.files.precision == pytest.approx(1.0)
    assert result.files.recall == pytest.approx(1.0)
    assert result.files.f1 == pytest.approx(1.0)


def test_structural_evaluator_detects_missing_file() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            files=(
                ExpectedFile(Path("src/main.py")),
                ExpectedFile(Path("src/missing.py")),
            ),
        ),
    )

    assert result.files.expected == 2
    assert result.files.actual == 2
    assert result.files.matched == 1
    assert result.files.precision == pytest.approx(0.5)
    assert result.files.recall == pytest.approx(0.5)


def test_structural_evaluator_detects_extra_file() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            files=(ExpectedFile(Path("src/main.py")),),
        ),
    )

    assert result.files.expected == 1
    assert result.files.actual == 2
    assert result.files.matched == 1
    assert result.files.precision == pytest.approx(0.5)
    assert result.files.recall == pytest.approx(1.0)


def test_structural_evaluator_matches_exact_symbols() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            symbols=(
                ExpectedSymbol(
                    qualified_name="main",
                    file_path=Path("src/main.py"),
                ),
                ExpectedSymbol(
                    qualified_name="helper",
                    file_path=Path("src/helper.py"),
                ),
            ),
        ),
    )

    assert result.symbols.expected == 2
    assert result.symbols.actual == 2
    assert result.symbols.matched == 2
    assert result.symbols.precision == pytest.approx(1.0)
    assert result.symbols.recall == pytest.approx(1.0)
    assert result.symbols.f1 == pytest.approx(1.0)


def test_structural_evaluator_rejects_symbol_in_wrong_file() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            symbols=(
                ExpectedSymbol(
                    qualified_name="main",
                    file_path=Path("src/helper.py"),
                ),
            ),
        ),
    )

    assert result.symbols.expected == 1
    assert result.symbols.actual == 2
    assert result.symbols.matched == 0
    assert result.symbols.precision == pytest.approx(0.0)
    assert result.symbols.recall == pytest.approx(0.0)


def test_structural_evaluator_matches_exact_relationships() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            relationships=(
                ExpectedRelationship(
                    source="file:src/main.py",
                    target="symbol:main",
                    relationship_type=RelationshipType.DEFINES,
                ),
                ExpectedRelationship(
                    source="file:src/helper.py",
                    target="symbol:helper",
                    relationship_type=RelationshipType.DEFINES,
                ),
            ),
        ),
    )

    assert result.relationships.expected == 2
    assert result.relationships.actual == 2
    assert result.relationships.matched == 2
    assert result.relationships.precision == pytest.approx(1.0)
    assert result.relationships.recall == pytest.approx(1.0)
    assert result.relationships.f1 == pytest.approx(1.0)


def test_structural_evaluator_rejects_wrong_relationship_endpoint() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            relationships=(
                ExpectedRelationship(
                    source="file:src/main.py",
                    target="symbol:helper",
                    relationship_type=RelationshipType.DEFINES,
                ),
            ),
        ),
    )

    assert result.relationships.expected == 1
    assert result.relationships.actual == 2
    assert result.relationships.matched == 0
    assert result.relationships.precision == pytest.approx(0.0)
    assert result.relationships.recall == pytest.approx(0.0)


def test_structural_evaluator_handles_empty_ground_truth() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(),
    )

    assert result.files.expected == 0
    assert result.symbols.expected == 0
    assert result.relationships.expected == 0

    assert result.files.matched == 0
    assert result.symbols.matched == 0
    assert result.relationships.matched == 0


def test_structural_evaluator_combines_all_categories() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            files=(
                ExpectedFile(Path("src/main.py")),
                ExpectedFile(Path("src/helper.py")),
            ),
            symbols=(
                ExpectedSymbol(
                    qualified_name="main",
                    file_path=Path("src/main.py"),
                ),
                ExpectedSymbol(
                    qualified_name="helper",
                    file_path=Path("src/helper.py"),
                ),
            ),
            relationships=(
                ExpectedRelationship(
                    source="file:src/main.py",
                    target="symbol:main",
                    relationship_type=RelationshipType.DEFINES,
                ),
                ExpectedRelationship(
                    source="file:src/helper.py",
                    target="symbol:helper",
                    relationship_type=RelationshipType.DEFINES,
                ),
            ),
        ),
    )

    assert result.files.f1 == pytest.approx(1.0)
    assert result.symbols.f1 == pytest.approx(1.0)
    assert result.relationships.f1 == pytest.approx(1.0)

    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(1.0)
    assert result.f1 == pytest.approx(1.0)


def test_structural_evaluation_aggregates_category_metrics() -> None:
    project = build_project()

    result = StructuralEvaluator().evaluate(
        project,
        StructuralGroundTruth(
            files=(ExpectedFile(Path("src/main.py")),),
            symbols=(
                ExpectedSymbol(
                    qualified_name="missing",
                    file_path=Path("src/missing.py"),
                ),
            ),
            relationships=(
                ExpectedRelationship(
                    source="file:src/main.py",
                    target="symbol:main",
                    relationship_type=RelationshipType.DEFINES,
                ),
            ),
        ),
    )

    expected_precision = (
        result.files.precision
        + result.symbols.precision
        + result.relationships.precision
    ) / 3

    expected_recall = (
        result.files.recall + result.symbols.recall + result.relationships.recall
    ) / 3

    expected_f1 = (result.files.f1 + result.symbols.f1 + result.relationships.f1) / 3

    assert result.precision == pytest.approx(expected_precision)
    assert result.recall == pytest.approx(expected_recall)
    assert result.f1 == pytest.approx(expected_f1)
