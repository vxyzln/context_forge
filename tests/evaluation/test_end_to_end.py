from pathlib import Path

from context_forge.context.models import ContextUnit
from context_forge.context.package import ContextPackage
from context_forge.context.types import ContextUnitType
from context_forge.evaluation.end_to_end import EndToEndEvaluator
from context_forge.evaluation.ground_truth import ExpectedEntity
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol


def build_project() -> tuple[Project, File, File, Symbol]:
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


def make_unit(
    entity_id: object,
    *,
    unit_type: ContextUnitType = ContextUnitType.FILE,
) -> ContextUnit:
    return ContextUnit(
        entity_id=entity_id,
        unit_type=unit_type,
        relevance=0.9,
        content="test context",
    )


def make_package(
    project: Project,
    *entity_ids: object,
) -> ContextPackage:
    return ContextPackage(
        task="understand the main entry point",
        units=[make_unit(entity_id) for entity_id in entity_ids],
    )


def test_exact_final_context_scores_perfectly() -> None:
    project, main_file, _, _ = build_project()

    package = make_package(
        project,
        main_file.id,
    )

    ground_truth = (ExpectedEntity("file", "src/main.py"),)

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        ground_truth,
    )

    assert evaluation.context.expected == 1
    assert evaluation.context.actual == 1
    assert evaluation.context.matched == 1
    assert evaluation.precision == 1.0
    assert evaluation.recall == 1.0
    assert evaluation.f1 == 1.0


def test_missing_context_reduces_recall() -> None:
    project, main_file, _, _ = build_project()

    package = make_package(
        project,
        main_file.id,
    )

    ground_truth = (
        ExpectedEntity("file", "src/main.py"),
        ExpectedEntity("file", "src/helper.py"),
    )

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        ground_truth,
    )

    assert evaluation.context.expected == 2
    assert evaluation.context.actual == 1
    assert evaluation.context.matched == 1
    assert evaluation.precision == 1.0
    assert evaluation.recall == 0.5
    assert evaluation.f1 == 2 / 3


def test_extra_context_reduces_precision() -> None:
    project, main_file, helper_file, _ = build_project()

    package = make_package(
        project,
        main_file.id,
        helper_file.id,
    )

    ground_truth = (ExpectedEntity("file", "src/main.py"),)

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        ground_truth,
    )

    assert evaluation.context.expected == 1
    assert evaluation.context.actual == 2
    assert evaluation.context.matched == 1
    assert evaluation.precision == 0.5
    assert evaluation.recall == 1.0
    assert evaluation.f1 == 2 / 3


def test_symbol_context_is_evaluated() -> None:
    project, _, _, main_symbol = build_project()

    package = make_package(
        project,
        main_symbol.id,
    )

    ground_truth = (ExpectedEntity("symbol", "main"),)

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        ground_truth,
    )

    assert evaluation.context.matched == 1
    assert evaluation.f1 == 1.0


def test_qualified_symbol_name_is_used() -> None:
    project, _, _, main_symbol = build_project()

    main_symbol.qualified_name = "example.main"

    package = make_package(
        project,
        main_symbol.id,
    )

    ground_truth = (ExpectedEntity("symbol", "example.main"),)

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        ground_truth,
    )

    assert evaluation.context.matched == 1
    assert evaluation.f1 == 1.0


def test_unknown_context_entity_is_ignored() -> None:
    from uuid import uuid4

    project, main_file, _, _ = build_project()

    package = make_package(
        project,
        main_file.id,
        uuid4(),
    )

    ground_truth = (ExpectedEntity("file", "src/main.py"),)

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        ground_truth,
    )

    assert evaluation.context.expected == 1
    assert evaluation.context.actual == 1
    assert evaluation.context.matched == 1
    assert evaluation.f1 == 1.0


def test_empty_context_with_empty_ground_truth_is_perfect() -> None:
    project, _, _, _ = build_project()

    package = make_package(project)

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        (),
    )

    assert evaluation.context.expected == 0
    assert evaluation.context.actual == 0
    assert evaluation.context.matched == 0
    assert evaluation.precision == 1.0
    assert evaluation.recall == 1.0
    assert evaluation.f1 == 1.0


def test_budget_is_respected() -> None:
    project, main_file, helper_file, _ = build_project()

    package = make_package(
        project,
        main_file.id,
        helper_file.id,
    )

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        (ExpectedEntity("file", "src/main.py"),),
        budget=2,
    )

    assert evaluation.within_budget is True


def test_budget_violation_is_reported() -> None:
    project, main_file, helper_file, _ = build_project()

    package = make_package(
        project,
        main_file.id,
        helper_file.id,
    )

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        (ExpectedEntity("file", "src/main.py"),),
        budget=1,
    )

    assert evaluation.within_budget is False


def test_no_budget_is_unbounded() -> None:
    project, main_file, helper_file, _ = build_project()

    package = make_package(
        project,
        main_file.id,
        helper_file.id,
    )

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        (),
    )

    assert evaluation.within_budget is True


def test_determinism_is_reported() -> None:
    project, main_file, _, _ = build_project()

    package = make_package(
        project,
        main_file.id,
    )

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        (ExpectedEntity("file", "src/main.py"),),
        deterministic=True,
    )

    assert evaluation.deterministic is True


def test_non_determinism_is_reported() -> None:
    project, main_file, _, _ = build_project()

    package = make_package(
        project,
        main_file.id,
    )

    evaluation = EndToEndEvaluator().evaluate(
        project,
        package,
        (ExpectedEntity("file", "src/main.py"),),
        deterministic=False,
    )

    assert evaluation.deterministic is False
