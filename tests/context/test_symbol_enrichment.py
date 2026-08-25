from pathlib import Path
from uuid import uuid4

from context_forge.context.models import ContextUnit
from context_forge.context.symbol_enrichment import SymbolContextEnricher
from context_forge.context.types import ContextUnitType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.symbol import Symbol


def test_symbol_enricher_adds_symbol_facts() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    file = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
        extension=".py",
    )
    project.add_file(file)

    symbol = Symbol(
        file_id=file.id,
        name="authenticate",
        kind="function",
        start_line=10,
        end_line=20,
        qualified_name="auth.authenticate",
        signature="def authenticate(user: User) -> bool",
    )
    project.add_symbol(symbol)

    unit = ContextUnit(
        entity_id=symbol.id,
        unit_type=ContextUnitType.SYMBOL,
        relevance=0.9,
    )

    enriched = SymbolContextEnricher().enrich(project, unit)

    assert len(enriched.facts) == 6
    assert enriched.facts[0].fact_type == "symbol_name"
    assert enriched.facts[0].value == "authenticate"
    assert enriched.facts[1].value == "function"
    assert enriched.facts[2].value == "10"
    assert enriched.facts[3].value == "20"
    assert enriched.facts[4].value == "auth.authenticate"
    assert enriched.facts[5].value == "def authenticate(user: User) -> bool"

    assert all(fact.evidence[0].source_id == symbol.id for fact in enriched.facts)


def test_symbol_enricher_adds_parent_symbol_fact() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    file = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
        extension=".py",
    )
    project.add_file(file)

    parent = Symbol(
        file_id=file.id,
        name="AuthService",
        kind="class",
        start_line=1,
        end_line=30,
    )

    child = Symbol(
        file_id=file.id,
        name="authenticate",
        kind="method",
        start_line=10,
        end_line=20,
        parent_symbol_id=parent.id,
    )

    project.add_symbol(parent)
    project.add_symbol(child)

    unit = ContextUnit(
        entity_id=child.id,
        unit_type=ContextUnitType.SYMBOL,
    )

    enriched = SymbolContextEnricher().enrich(project, unit)

    parent_facts = [
        fact for fact in enriched.facts if fact.fact_type == "parent_symbol"
    ]

    assert len(parent_facts) == 1
    assert parent_facts[0].value == str(parent.id)


def test_symbol_enricher_ignores_non_symbol_units() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
    )

    enriched = SymbolContextEnricher().enrich(project, unit)

    assert enriched == unit


def test_symbol_enricher_ignores_missing_symbol() -> None:
    project = Project(
        name="demo",
        root_path=Path("/tmp/context-forge-test"),
    )

    unit = ContextUnit(
        entity_id=uuid4(),
        unit_type=ContextUnitType.SYMBOL,
    )

    enriched = SymbolContextEnricher().enrich(project, unit)

    assert enriched == unit
