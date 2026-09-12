from pathlib import Path
from uuid import uuid4

from context_forge.context.candidate import ContextCandidate
from context_forge.context.selection_service import (
    ContextSelectionResult,
    SelectedContextCandidate,
)
from context_forge.context.types import ContextUnitType
from context_forge.evaluation.ground_truth import ExpectedEntity
from context_forge.evaluation.selection import SelectionEvaluator
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol


def build_project() -> tuple[
    Project,
    File,
    File,
    Symbol,
]:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    main_file = File(
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

    project.add_file(main_file)
    project.add_file(helper_file)

    main_symbol = Symbol(
        file_id=main_file.id,
        name="main",
        kind="function",
        start_line=1,
        end_line=5,
        qualified_name="main",
    )

    project.add_symbol(main_symbol)

    return project, main_file, helper_file, main_symbol


def make_candidate(
    entity_id: object,
    *,
    unit_type: ContextUnitType = ContextUnitType.FILE,
) -> ContextCandidate:
    return ContextCandidate(
        entity_id=entity_id,
        unit_type=unit_type,
        score=0.9,
        source="deterministic_search",
        reason="matched task",
    )


def make_result(
    *candidates: ContextCandidate,
    confidence: float = 0.9,
) -> ContextSelectionResult:
    return ContextSelectionResult(
        candidates=tuple(
            SelectedContextCandidate(
                candidate=candidate,
                confidence=confidence,
            )
            for candidate in candidates
        )
    )


def test_exact_selection_scores_perfectly() -> None:
    project, main_file, helper_file, _ = build_project()

    candidates = [
        make_candidate(main_file.id),
        make_candidate(helper_file.id),
    ]

    result = make_result(candidates[0])

    ground_truth = (ExpectedEntity("file", "src/main.py"),)

    evaluation = SelectionEvaluator().evaluate(
        project,
        candidates,
        result,
        ground_truth,
    )

    assert evaluation.selection.expected == 1
    assert evaluation.selection.actual == 1
    assert evaluation.selection.matched == 1
    assert evaluation.precision == 1.0
    assert evaluation.recall == 1.0
    assert evaluation.f1 == 1.0


def test_missing_expected_entity_reduces_recall() -> None:
    project, main_file, helper_file, _ = build_project()

    candidates = [
        make_candidate(main_file.id),
        make_candidate(helper_file.id),
    ]

    result = make_result(candidates[0])

    ground_truth = (
        ExpectedEntity("file", "src/main.py"),
        ExpectedEntity("file", "src/helper.py"),
    )

    evaluation = SelectionEvaluator().evaluate(
        project,
        candidates,
        result,
        ground_truth,
    )

    assert evaluation.selection.expected == 2
    assert evaluation.selection.actual == 1
    assert evaluation.selection.matched == 1
    assert evaluation.precision == 1.0
    assert evaluation.recall == 0.5
    assert evaluation.f1 == 2 / 3


def test_extra_selected_entity_reduces_precision() -> None:
    project, main_file, helper_file, _ = build_project()

    candidates = [
        make_candidate(main_file.id),
        make_candidate(helper_file.id),
    ]

    result = make_result(
        candidates[0],
        candidates[1],
    )

    ground_truth = (ExpectedEntity("file", "src/main.py"),)

    evaluation = SelectionEvaluator().evaluate(
        project,
        candidates,
        result,
        ground_truth,
    )

    assert evaluation.selection.expected == 1
    assert evaluation.selection.actual == 2
    assert evaluation.selection.matched == 1
    assert evaluation.precision == 0.5
    assert evaluation.recall == 1.0
    assert evaluation.f1 == 2 / 3


def test_selection_handles_symbols() -> None:
    project, _, _, main_symbol = build_project()

    candidate = make_candidate(
        main_symbol.id,
        unit_type=ContextUnitType.SYMBOL,
    )

    result = make_result(candidate)

    ground_truth = (ExpectedEntity("symbol", "main"),)

    evaluation = SelectionEvaluator().evaluate(
        project,
        [candidate],
        result,
        ground_truth,
    )

    assert evaluation.selection.matched == 1
    assert evaluation.f1 == 1.0


def test_selection_uses_qualified_symbol_name() -> None:
    project, _, _, main_symbol = build_project()

    main_symbol.qualified_name = "example.main"

    candidate = make_candidate(
        main_symbol.id,
        unit_type=ContextUnitType.SYMBOL,
    )

    result = make_result(candidate)

    ground_truth = (ExpectedEntity("symbol", "example.main"),)

    evaluation = SelectionEvaluator().evaluate(
        project,
        [candidate],
        result,
        ground_truth,
    )

    assert evaluation.selection.matched == 1
    assert evaluation.f1 == 1.0


def test_unknown_selected_entity_is_not_counted_as_valid_selection() -> None:
    project, main_file, _, _ = build_project()

    known_candidate = make_candidate(main_file.id)
    unknown_id = uuid4()
    unknown_candidate = make_candidate(unknown_id)

    result = make_result(
        known_candidate,
        unknown_candidate,
    )

    ground_truth = (ExpectedEntity("file", "src/main.py"),)

    evaluation = SelectionEvaluator().evaluate(
        project,
        [known_candidate, unknown_candidate],
        result,
        ground_truth,
    )

    assert evaluation.selection.expected == 1
    assert evaluation.selection.actual == 1
    assert evaluation.selection.matched == 1
    assert evaluation.f1 == 1.0


def test_empty_selection_with_empty_ground_truth_is_perfect() -> None:
    project, _, _, _ = build_project()

    result = make_result()

    evaluation = SelectionEvaluator().evaluate(
        project,
        [],
        result,
        (),
    )

    assert evaluation.selection.expected == 0
    assert evaluation.selection.actual == 0
    assert evaluation.selection.matched == 0
    assert evaluation.precision == 1.0
    assert evaluation.recall == 1.0
    assert evaluation.f1 == 1.0
