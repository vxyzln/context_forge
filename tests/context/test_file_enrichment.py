from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.context.file_enrichment import FileContextEnricher
from context_forge.context.models import ContextUnit
from context_forge.context.types import ContextUnitType
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project


def test_file_enricher_adds_file_facts(tmp_path: Path) -> None:
    source_path = tmp_path / "src" / "auth.py"
    source_path.parent.mkdir()
    source_path.write_text(
        "def authenticate(username, password):\n    return True\n",
        encoding="utf-8",
    )

    project = Project(
        name="demo",
        root_path=tmp_path,
    )

    file = File(
        project_id=project.id,
        path=Path("src/auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
        size=128,
    )
    project.add_file(file)

    unit = ContextUnit(
        entity_id=file.id,
        unit_type=ContextUnitType.FILE,
        relevance=0.8,
    )

    enriched = FileContextEnricher().enrich(project, unit)

    assert len(enriched.facts) == 6
    assert enriched.facts[0].fact_type == "file_path"
    assert enriched.facts[0].value == "src/auth.py"
    assert enriched.facts[0].evidence[0].source_id == file.id
    assert enriched.facts[2].value == ".py"
    assert enriched.facts[3].value == "128"


def test_file_enricher_ignores_non_file_units() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type=ContextUnitType.SYMBOL,
    )

    enriched = FileContextEnricher().enrich(project, unit)

    assert enriched == unit


def test_file_enricher_adds_source_content(tmp_path: Path) -> None:
    source = "def authenticate(username, password):\n    return True\n"
    source_path = tmp_path / "src" / "auth.py"
    source_path.parent.mkdir()
    source_path.write_text(source, encoding="utf-8")

    project = Project(
        name="demo",
        root_path=tmp_path,
    )

    file = File(
        project_id=project.id,
        path=Path("src/auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
        size=len(source),
    )
    project.add_file(file)

    unit = ContextUnit(
        entity_id=file.id,
        unit_type=ContextUnitType.FILE,
    )

    enriched = FileContextEnricher().enrich(project, unit)

    assert enriched.content == source


def test_file_enricher_skips_unavailable_source_content(
    tmp_path: Path,
) -> None:
    project = Project(
        name="demo",
        root_path=tmp_path,
    )

    file = File(
        project_id=project.id,
        path=Path("src/missing.py"),
        name="missing.py",
        extension=".py",
        file_type=FileType.SOURCE,
        size=0,
    )
    project.add_file(file)

    unit = ContextUnit(
        entity_id=file.id,
        unit_type=ContextUnitType.FILE,
    )

    enriched = FileContextEnricher().enrich(project, unit)

    assert enriched.content is None
    assert len(enriched.facts) == 6
    assert enriched.facts[0].value == "src/missing.py"