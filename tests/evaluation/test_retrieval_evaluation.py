from pathlib import Path
from uuid import uuid4

from context_forge.context.candidate import ContextCandidate
from context_forge.evaluation.ground_truth import (
    ExpectedEntity,
    RetrievalGroundTruth,
)
from context_forge.evaluation.retrieval import RetrievalEvaluator
from context_forge.models.file import File, FileType
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol
from context_forge.task.models import GroundedTask, TaskInterpretation
from context_forge.task.repository_grounding import RepositoryGrounding


def build_project() -> tuple[Project, File, File, Symbol, Symbol]:
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

    main_symbol = Symbol(
        file_id=main_file.id,
        name="main",
        kind="function",
        start_line=1,
        end_line=5,
        qualified_name="main",
    )

    helper_symbol = Symbol(
        file_id=helper_file.id,
        name="helper",
        kind="function",
        start_line=1,
        end_line=5,
        qualified_name="helper",
    )

    project.add_file(main_file)
    project.add_file(helper_file)
    project.add_symbol(main_symbol)
    project.add_symbol(helper_symbol)

    return (
        project,
        main_file,
        helper_file,
        main_symbol,
        helper_symbol,
    )


def make_candidate(entity_id) -> ContextCandidate:
    return ContextCandidate(
        entity_id=entity_id,
        unit_type="file",
        score=1.0,
        source="test",
        reason="test candidate",
    )


def make_grounding(*entity_ids) -> RepositoryGrounding:
    task = GroundedTask(
        interpretation=TaskInterpretation(task="test task", intent="test", target=None),
    )

    return RepositoryGrounding(
        task=task,
        related_entity_ids=tuple(entity_ids),
        relationships=(),
        max_depth=1,
    )


def test_expected_entity_validates_kind() -> None:
    entity = ExpectedEntity(
        kind="file",
        value="src/main.py",
    )

    assert entity.kind == "file"
    assert entity.value == "src/main.py"


def test_expected_entity_rejects_empty_kind() -> None:
    try:
        ExpectedEntity(kind="", value="src/main.py")
    except ValueError as exc:
        assert str(exc) == "Expected entity kind must not be empty"
    else:
        raise AssertionError("ExpectedEntity should reject an empty kind")


def test_expected_entity_rejects_empty_value() -> None:
    try:
        ExpectedEntity(kind="file", value="")
    except ValueError as exc:
        assert str(exc) == "Expected entity value must not be empty"
    else:
        raise AssertionError("ExpectedEntity should reject an empty value")


def test_retrieval_ground_truth_defaults_to_empty() -> None:
    ground_truth = RetrievalGroundTruth()

    assert ground_truth.retrieved_entities == ()
    assert ground_truth.grounded_entities == ()


def test_exact_retrieval_match() -> None:
    project, main_file, _, _, _ = build_project()

    candidates = [make_candidate(main_file.id)]
    grounding = make_grounding()

    ground_truth = RetrievalGroundTruth(
        retrieved_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.retrieval.expected == 1
    assert result.retrieval.actual == 1
    assert result.retrieval.matched == 1
    assert result.retrieval.precision == 1.0
    assert result.retrieval.recall == 1.0
    assert result.retrieval.f1 == 1.0


def test_missing_retrieved_entity_reduces_recall() -> None:
    project, _, _, _, _ = build_project()

    candidates = []
    grounding = make_grounding()

    ground_truth = RetrievalGroundTruth(
        retrieved_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.retrieval.expected == 1
    assert result.retrieval.actual == 0
    assert result.retrieval.matched == 0
    assert result.retrieval.precision == 0.0
    assert result.retrieval.recall == 0.0
    assert result.retrieval.f1 == 0.0


def test_extra_retrieved_entity_reduces_precision() -> None:
    project, main_file, helper_file, _, _ = build_project()

    candidates = [
        make_candidate(main_file.id),
        make_candidate(helper_file.id),
    ]
    grounding = make_grounding()

    ground_truth = RetrievalGroundTruth(
        retrieved_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.retrieval.expected == 1
    assert result.retrieval.actual == 2
    assert result.retrieval.matched == 1
    assert result.retrieval.precision == 0.5
    assert result.retrieval.recall == 1.0


def test_symbol_retrieval_uses_qualified_name() -> None:
    project, _, _, main_symbol, _ = build_project()

    candidates = [make_candidate(main_symbol.id)]
    grounding = make_grounding()

    ground_truth = RetrievalGroundTruth(
        retrieved_entities=(ExpectedEntity("symbol", "main"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.retrieval.matched == 1
    assert result.retrieval.f1 == 1.0


def test_exact_grounding_match() -> None:
    project, main_file, _, _, _ = build_project()

    candidates = []
    grounding = make_grounding(main_file.id)

    ground_truth = RetrievalGroundTruth(
        grounded_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.grounding.expected == 1
    assert result.grounding.actual == 1
    assert result.grounding.matched == 1
    assert result.grounding.f1 == 1.0


def test_missing_grounded_entity_reduces_recall() -> None:
    project, _, _, _, _ = build_project()

    grounding = make_grounding()

    ground_truth = RetrievalGroundTruth(
        grounded_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        [],
        grounding,
        ground_truth,
    )

    assert result.grounding.expected == 1
    assert result.grounding.actual == 0
    assert result.grounding.matched == 0
    assert result.grounding.recall == 0.0
    assert result.grounding.f1 == 0.0


def test_extra_grounded_entity_reduces_precision() -> None:
    project, main_file, helper_file, _, _ = build_project()

    grounding = make_grounding(
        main_file.id,
        helper_file.id,
    )

    ground_truth = RetrievalGroundTruth(
        grounded_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        [],
        grounding,
        ground_truth,
    )

    assert result.grounding.expected == 1
    assert result.grounding.actual == 2
    assert result.grounding.matched == 1
    assert result.grounding.precision == 0.5
    assert result.grounding.recall == 1.0


def test_unknown_candidate_entities_are_not_counted() -> None:
    project, _, _, _, _ = build_project()

    unknown_id = uuid4()

    candidates = [make_candidate(unknown_id)]
    grounding = make_grounding()

    ground_truth = RetrievalGroundTruth()

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.retrieval.expected == 0
    assert result.retrieval.actual == 0
    assert result.retrieval.matched == 0


def test_unknown_grounded_entities_are_not_counted() -> None:
    project, _, _, _, _ = build_project()

    unknown_id = uuid4()

    grounding = make_grounding(unknown_id)

    result = RetrievalEvaluator().evaluate(
        project,
        [],
        grounding,
        RetrievalGroundTruth(),
    )

    assert result.grounding.expected == 0
    assert result.grounding.actual == 0
    assert result.grounding.matched == 0


def test_combined_retrieval_and_grounding_metrics() -> None:
    project, main_file, helper_file, main_symbol, _ = build_project()

    candidates = [
        make_candidate(main_file.id),
        make_candidate(main_symbol.id),
    ]

    grounding = make_grounding(
        main_file.id,
        helper_file.id,
    )

    ground_truth = RetrievalGroundTruth(
        retrieved_entities=(
            ExpectedEntity("file", "src/main.py"),
            ExpectedEntity("symbol", "main"),
        ),
        grounded_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.retrieval.f1 == 1.0
    assert result.grounding.precision == 0.5
    assert result.grounding.recall == 1.0
    assert result.grounding.f1 == 2 / 3


def test_aggregate_metrics_average_retrieval_and_grounding() -> None:
    project, main_file, helper_file, _, _ = build_project()

    candidates = [make_candidate(main_file.id)]

    grounding = make_grounding(helper_file.id)

    ground_truth = RetrievalGroundTruth(
        retrieved_entities=(ExpectedEntity("file", "src/main.py"),),
        grounded_entities=(ExpectedEntity("file", "src/main.py"),),
    )

    result = RetrievalEvaluator().evaluate(
        project,
        candidates,
        grounding,
        ground_truth,
    )

    assert result.retrieval.f1 == 1.0
    assert result.grounding.f1 == 0.0
    assert result.f1 == 0.5
