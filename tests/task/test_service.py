import pytest

from context_forge.task import TaskUnderstandingService


def test_understand_extracts_action_and_concepts() -> None:
    service = TaskUnderstandingService()
    result = service.understand("Fix the scrolling on the settings page.")

    assert result.task == "Fix the scrolling on the settings page."
    assert result.intent == "Fix the scrolling on the settings page."
    assert result.requested_action == "fix"
    assert "scrolling" in result.concepts
    assert "settings" in result.concepts
    assert result.ambiguity is None


def test_understand_extracts_target_path() -> None:
    service = TaskUnderstandingService()
    result = service.understand("Refactor src/context_forge/application/service.py")

    assert result.requested_action == "refactor"
    assert result.target == "src/context_forge/application/service.py"
    assert "src/context_forge/application/service.py" in result.concepts


def test_understand_extracts_symbol_target() -> None:
    service = TaskUnderstandingService()
    result = service.understand("Explain ProjectAnalyzer class hierarchy")

    assert result.requested_action == "explain"
    assert result.target == "ProjectAnalyzer"
    assert "ProjectAnalyzer" in result.concepts


def test_understand_rejects_empty_task() -> None:
    service = TaskUnderstandingService()

    with pytest.raises(ValueError, match="task must not be empty"):
        service.understand("   ")


def test_understand_is_deterministic_and_reproducible() -> None:
    service = TaskUnderstandingService()
    task = "Analyze repository dependencies and imports"

    result1 = service.understand(task)
    result2 = service.understand(task)

    assert result1 == result2
