from __future__ import annotations

import json
from pathlib import Path

import pytest

from context_forge.comparison import (
    ComparisonState,
    compare_states,
)
from context_forge.pipeline.analyzer import ProjectAnalyzer


@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "alpha.py").write_text(
        "def hello(name: str) -> str:\n    return f'Hello, {name}'\n",
        encoding="utf-8",
    )
    (ws / "src" / "beta.py").write_text(
        "from src.alpha import hello\n\ndef greet():\n    return hello('world')\n",
        encoding="utf-8",
    )
    return ws


def test_integration_analyzer_comparison(
    sample_workspace: Path, tmp_path: Path
) -> None:
    db1 = tmp_path / "state1.db"
    analyzer1 = ProjectAnalyzer(sample_workspace, db1)
    project1 = analyzer1.analyze()

    state1 = ComparisonState.from_project(
        project1,
        state_id="v1",
        is_historical=True,
    )

    (sample_workspace / "src" / "alpha.py").write_text(
        "def hello(name: str, shout: bool = False) -> str:\n    return f'Hello, {name}!'\n",
        encoding="utf-8",
    )
    (sample_workspace / "src" / "gamma.py").write_text(
        "def util():\n    pass\n",
        encoding="utf-8",
    )

    db2 = tmp_path / "state2.db"
    analyzer2 = ProjectAnalyzer(sample_workspace, db2)
    project2 = analyzer2.analyze()

    state2 = ComparisonState.from_project(
        project2,
        state_id="v2",
    )

    result = compare_states(state1, state2)

    assert result.is_complete is True
    assert result.outcome.is_success is True
    assert result.has_structural_changes is True

    added_paths = [f.path for f in result.added_files]
    assert "src/gamma.py" in added_paths

    mod_sym_names = [s.name for s in result.modified_symbols]
    assert "hello" in mod_sym_names

    affected_paths = [a.path for a in result.affected_components]
    assert "src/beta.py" in affected_paths

    payload = result.to_dict()
    assert isinstance(payload, dict)
    assert json.loads(json.dumps(payload)) == payload
