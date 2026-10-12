import json
from pathlib import Path

from context_forge.application import build_context_service
from context_forge.context.serialization import ContextPackageSerializer
from context_forge.pipeline.analyzer import ProjectAnalyzer


def test_repository_context_retrieval_end_to_end(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    auth_file = src_dir / "auth.py"
    auth_file.write_text(
        "class Authenticator:\n"
        "    def authenticate(self, username: str) -> bool:\n"
        "        return True\n",
        encoding="utf-8",
    )

    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(root_path=tmp_path, database_path=db_path)
    project = analyzer.analyze()

    service = build_context_service()
    package = service.retrieve_context(
        project=project,
        task="Explain Authenticator class in src/auth.py",
    )

    assert package.task == "Explain Authenticator class in src/auth.py"
    assert len(package.units) > 0

    serializer = ContextPackageSerializer()
    serialized = serializer.serialize(package)

    data = json.loads(serialized)
    assert data["task"] == package.task
    assert len(data["units"]) > 0

    unit_contents = [u.get("content") for u in data["units"] if u.get("content")]
    assert any("Authenticator" in c for c in unit_contents)


def test_repository_context_service_rejects_empty_task(tmp_path: Path) -> None:
    db_path = tmp_path / ".context_forge.db"
    analyzer = ProjectAnalyzer(root_path=tmp_path, database_path=db_path)
    project = analyzer.analyze()

    service = build_context_service()

    try:
        service.retrieve_context(project=project, task="   ")
    except ValueError as exc:
        assert "task must not be empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty task")
