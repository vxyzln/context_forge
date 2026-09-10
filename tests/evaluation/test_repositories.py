from pathlib import Path

from context_forge.evaluation.repositories import default_evaluation_set


def test_default_evaluation_set_contains_at_least_ten_repositories(
    tmp_path: Path,
) -> None:
    evaluation_set = default_evaluation_set(tmp_path)

    assert evaluation_set.repository_count >= 10


def test_default_evaluation_set_contains_tasks(
    tmp_path: Path,
) -> None:
    evaluation_set = default_evaluation_set(tmp_path)

    assert evaluation_set.task_count > 0
    assert all(repository.tasks for repository in evaluation_set.repositories)


def test_default_evaluation_set_uses_local_repository_paths(
    tmp_path: Path,
) -> None:
    evaluation_set = default_evaluation_set(tmp_path)

    for repository in evaluation_set.repositories:
        assert repository.root_path.parent == tmp_path
        assert not str(repository.root_path).startswith("http://")
        assert not str(repository.root_path).startswith("https://")


def test_default_evaluation_set_repository_ids_are_unique(
    tmp_path: Path,
) -> None:
    evaluation_set = default_evaluation_set(tmp_path)

    repository_ids = [repository.id for repository in evaluation_set.repositories]

    assert len(repository_ids) == len(set(repository_ids))


def test_default_evaluation_set_task_ids_are_unique_per_repository(
    tmp_path: Path,
) -> None:
    evaluation_set = default_evaluation_set(tmp_path)

    for repository in evaluation_set.repositories:
        task_ids = [task.id for task in repository.tasks]
        assert len(task_ids) == len(set(task_ids))


def test_default_evaluation_set_resolves_root_path(
    tmp_path: Path,
) -> None:
    evaluation_set = default_evaluation_set(tmp_path)

    assert all(
        repository.root_path.is_absolute() for repository in evaluation_set.repositories
    )


def test_default_evaluation_set_is_deterministic(
    tmp_path: Path,
) -> None:
    first = default_evaluation_set(tmp_path)
    second = default_evaluation_set(tmp_path)

    assert first == second
