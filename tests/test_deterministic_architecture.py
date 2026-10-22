import json
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from context_forge.application import build_context_service
from context_forge.context.candidate import ContextCandidate
from context_forge.context.ranking import DeterministicRanker
from context_forge.context.serialization import ContextPackageSerializer
from context_forge.context.signals import RelevanceSignals
from context_forge.context.types import ContextUnitType
from context_forge.main import parse_args
from context_forge.pipeline.analyzer import ProjectAnalyzer, current_fingerprints
from context_forge.storage.cache import RepositoryIdentity
from context_forge.storage.database import Database
from context_forge.storage.repository import ProjectRepository


def test_importing_context_forge_does_not_load_provider_modules() -> None:
    prohibited_modules = {"ollama", "httpx", "fastapi", "uvicorn"}
    for module_name in prohibited_modules:
        assert module_name not in sys.modules, f"{module_name} must not be imported"


def test_cli_rejects_removed_provider_arguments() -> None:
    with pytest.raises(SystemExit):
        parse_args(["context", ".", "--provider", "ollama"])

    with pytest.raises(SystemExit):
        parse_args(["context", ".", "--model", "qwen2.5-coder:7b"])

    with pytest.raises(SystemExit):
        parse_args(["context", ".", "--temperature", "0.2"])

    with pytest.raises(SystemExit):
        parse_args(["context", ".", "--max-tokens", "1024"])

    with pytest.raises(SystemExit):
        parse_args(["context", ".", "--base-url", "http://localhost:11434"])

    with pytest.raises(SystemExit):
        parse_args(["generate", "."])

    with pytest.raises(SystemExit):
        parse_args(["runtime", "."])


def test_deterministic_ranking_produces_stable_reproducible_tie_breaking() -> None:
    from uuid import UUID

    id_a = UUID("00000000-0000-0000-0000-000000000001")
    id_b = UUID("00000000-0000-0000-0000-000000000002")

    c1 = ContextCandidate(
        entity_id=id_a,
        unit_type=ContextUnitType.FILE,
        score=0.5,
        source="test",
        reason="reason A",
    )
    c2 = ContextCandidate(
        entity_id=id_b,
        unit_type=ContextUnitType.FILE,
        score=0.5,
        source="test",
        reason="reason B",
    )

    signals = {
        id_a: RelevanceSignals(lexical=0.5),
        id_b: RelevanceSignals(lexical=0.5),
    }

    ranker = DeterministicRanker()

    result1 = ranker.rank([c1, c2], signals)
    result2 = ranker.rank([c2, c1], signals)

    assert [r.entity_id for r in result1] == [r.entity_id for r in result2]


def test_database_initialization_and_fresh_repo_analysis_work_offline(
    tmp_path: Path,
) -> None:
    src_file = tmp_path / "calc.py"
    src_file.write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )

    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(root_path=tmp_path, database_path=db_path)
    project = analyzer.analyze()

    assert db_path.exists()
    assert len(project.files) == 1
    assert len(project.symbols) == 1

    repo = ProjectRepository(Database(db_path))
    key = RepositoryIdentity(tmp_path).key
    loaded = repo.load_analysis(key)
    assert loaded is not None
    loaded_project, metadata = loaded
    assert len(loaded_project.files) == 1
    assert metadata.analyzer_version == "0.1.0"


def test_file_fingerprints_detect_modifications_offline(
    tmp_path: Path,
) -> None:
    src_file = tmp_path / "module.py"
    src_file.write_text("X = 1\n", encoding="utf-8")

    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(root_path=tmp_path, database_path=db_path)
    project = analyzer.analyze()

    repo = ProjectRepository(Database(db_path))
    key = RepositoryIdentity(tmp_path).key

    fp1 = current_fingerprints(project)
    freshness1 = repo.check_cache_freshness(key, fp1)
    assert freshness1.is_fresh

    src_file.write_text("X = 2\n", encoding="utf-8")
    fp2 = current_fingerprints(project)
    freshness2 = repo.check_cache_freshness(key, fp2)
    assert not freshness2.is_fresh
    assert Path("module.py") in freshness2.changes.modified


def test_no_network_requests_during_analysis_and_retrieval(
    tmp_path: Path,
) -> None:
    def fail_network_connect(*args, **kwargs):
        raise AssertionError("Network connection attempted during local execution!")

    src_file = tmp_path / "service.py"
    src_file.write_text(
        "class OrderService:\n"
        "    def create_order(self, item_id: str) -> str:\n"
        "        return 'order-123'\n",
        encoding="utf-8",
    )

    with patch.object(socket.socket, "connect", fail_network_connect):
        db_path = tmp_path / ".context_forge.db"
        analyzer = ProjectAnalyzer(root_path=tmp_path, database_path=db_path)
        project = analyzer.analyze()

        service = build_context_service()
        package = service.retrieve_context(project, "Explain OrderService")

        assert package.task == "Explain OrderService"
        assert len(package.units) > 0


def test_context_package_contains_verifiable_repository_evidence(
    tmp_path: Path,
) -> None:
    src_file = tmp_path / "models.py"
    src_file.write_text(
        "class Customer:\n"
        "    def __init__(self, name: str) -> None:\n"
        "        self.name = name\n",
        encoding="utf-8",
    )

    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(root_path=tmp_path, database_path=db_path)
    project = analyzer.analyze()

    service = build_context_service()
    package = service.retrieve_context(project, "Inspect Customer class in models.py")

    serializer = ContextPackageSerializer()
    serialized = serializer.serialize(package)
    data = json.loads(serialized)

    assert data["task"] == "Inspect Customer class in models.py"
    assert len(data["units"]) > 0

    unit = data["units"][0]
    assert "entity_id" in unit
    assert "unit_type" in unit
    assert "facts" in unit
    assert "signals" in unit

    facts = unit["facts"]
    assert any(len(f.get("evidence", [])) > 0 for f in facts)
    all_evidence = [ev for f in facts for ev in f.get("evidence", [])]
    assert any("description" in ev for ev in all_evidence)
