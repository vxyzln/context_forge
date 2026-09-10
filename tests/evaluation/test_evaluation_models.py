from pathlib import Path

import pytest

from context_forge.evaluation.models import (
    EvaluationRepository,
    EvaluationSet,
    EvaluationTask,
)


def test_evaluation_task_defaults() -> None:
    task = EvaluationTask(
        id="task-1",
        description="Locate the main application entry point.",
    )

    assert task.id == "task-1"
    assert task.description == "Locate the main application entry point."
    assert task.expected_paths == ()
    assert task.tags == ()


def test_evaluation_task_preserves_expected_paths_and_tags() -> None:
    task = EvaluationTask(
        id="task-1",
        description="Locate the parser.",
        expected_paths=(Path("src/parser.py"), Path("src/tokenizer.py")),
        tags=("parser", "architecture"),
    )

    assert task.expected_paths == (
        Path("src/parser.py"),
        Path("src/tokenizer.py"),
    )
    assert task.tags == ("parser", "architecture")


def test_evaluation_repository_defaults() -> None:
    repository = EvaluationRepository(
        id="example",
        name="Example",
        root_path=Path("/tmp/example"),
    )

    assert repository.id == "example"
    assert repository.name == "Example"
    assert repository.root_path == Path("/tmp/example")
    assert repository.tasks == ()
    assert repository.description == ""
    assert repository.language == "python"


def test_evaluation_repository_preserves_tasks() -> None:
    task = EvaluationTask(
        id="task-1",
        description="Locate the application.",
    )

    repository = EvaluationRepository(
        id="example",
        name="Example",
        root_path=Path("/tmp/example"),
        tasks=(task,),
        description="Example repository.",
        language="python",
    )

    assert repository.tasks == (task,)
    assert repository.description == "Example repository."
    assert repository.language == "python"


def test_evaluation_set_defaults() -> None:
    evaluation_set = EvaluationSet(repositories=())

    assert evaluation_set.repositories == ()
    assert evaluation_set.repository_count == 0
    assert evaluation_set.task_count == 0


def test_evaluation_set_rejects_duplicate_repository_ids() -> None:
    repository = EvaluationRepository(
        id="duplicate",
        name="Example",
        root_path=Path("/tmp/example"),
    )

    with pytest.raises(
        ValueError,
        match="Evaluation repository IDs must be unique",
    ):
        EvaluationSet(
            repositories=(repository, repository),
        )


def test_get_repository_returns_matching_repository() -> None:
    repository = EvaluationRepository(
        id="example",
        name="Example",
        root_path=Path("/tmp/example"),
    )

    evaluation_set = EvaluationSet(repositories=(repository,))

    assert evaluation_set.get_repository("example") == repository


def test_get_repository_returns_none_for_unknown_id() -> None:
    repository = EvaluationRepository(
        id="example",
        name="Example",
        root_path=Path("/tmp/example"),
    )

    evaluation_set = EvaluationSet(repositories=(repository,))

    assert evaluation_set.get_repository("missing") is None


def test_repository_and_task_counts() -> None:
    first = EvaluationRepository(
        id="first",
        name="First",
        root_path=Path("/tmp/first"),
        tasks=(
            EvaluationTask(id="first-1", description="First task"),
            EvaluationTask(id="first-2", description="Second task"),
        ),
    )
    second = EvaluationRepository(
        id="second",
        name="Second",
        root_path=Path("/tmp/second"),
        tasks=(EvaluationTask(id="second-1", description="Third task"),),
    )

    evaluation_set = EvaluationSet(repositories=(first, second))

    assert evaluation_set.repository_count == 2
    assert evaluation_set.task_count == 3
