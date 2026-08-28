from uuid import uuid4

from context_forge.context.candidate import ContextCandidate
from context_forge.context.expansion import ContextExpansion
from context_forge.context.package import ContextPackageBuilder
from context_forge.context.signals import RelevanceSignals
from context_forge.context.types import ContextUnitType


def test_package_builder_preserves_task() -> None:
    package = ContextPackageBuilder().build("  Fix auth  ", [])

    assert package.task == "Fix auth"
    assert package.units == ()


def test_package_builder_converts_candidate_to_context_unit() -> None:
    candidate = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.9,
        source="deterministic_search",
    )

    package = ContextPackageBuilder().build(
        "Fix auth",
        [ContextExpansion(candidate=candidate)],
    )

    assert len(package.units) == 1
    assert package.units[0].entity_id == candidate.entity_id
    assert package.units[0].unit_type == ContextUnitType.FILE
    assert package.units[0].relevance == 0.9


def test_package_builder_includes_related_units() -> None:
    candidate = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.9,
        source="deterministic_search",
    )
    related = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.0,
        source="graph_expansion",
    )

    package = ContextPackageBuilder().build(
        "Fix auth",
        [
            ContextExpansion(
                candidate=candidate,
                related=(related,),
            )
        ],
    )

    assert len(package.units) == 2
    assert package.units[0].entity_id == candidate.entity_id
    assert package.units[1].entity_id == related.entity_id


def test_package_builder_preserves_order() -> None:
    first = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.FILE,
        score=0.9,
        source="deterministic_search",
    )
    second = ContextCandidate(
        entity_id=uuid4(),
        unit_type=ContextUnitType.SYMBOL,
        score=0.7,
        source="deterministic_search",
    )

    package = ContextPackageBuilder().build(
        "Fix auth",
        [
            ContextExpansion(candidate=first),
            ContextExpansion(candidate=second),
        ],
    )

    assert [unit.entity_id for unit in package.units] == [
        first.entity_id,
        second.entity_id,
    ]


def test_package_builder_includes_selection_reason() -> None:
    entity_id = uuid4()

    candidate = ContextCandidate(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
        reason="Exact file name match",
    )

    package = ContextPackageBuilder().build(
        "auth",
        [ContextExpansion(candidate=candidate)],
    )

    assert len(package.units) == 1

    unit = package.units[0]

    assert unit.relevance == 0.8
    assert len(unit.signals) == 1
    assert unit.signals[0].name == "selection"
    assert unit.signals[0].value == 0.8
    assert unit.signals[0].evidence
    assert "Exact file name match" in unit.signals[0].evidence[0].description


def test_package_builder_includes_git_relevance_signal() -> None:
    entity_id = uuid4()

    candidate = ContextCandidate(
        entity_id=entity_id,
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
        reason="Exact file name match",
    )

    signals = {
        entity_id: RelevanceSignals(git=0.8),
    }

    package = ContextPackageBuilder().build(
        "auth",
        [ContextExpansion(candidate=candidate)],
        signals,
    )

    unit = package.units[0]

    signal_names = {signal.name for signal in unit.signals}

    assert "selection" in signal_names
    assert "git_relevance" in signal_names

    git_signal = next(
        signal for signal in unit.signals if signal.name == "git_relevance"
    )

    assert git_signal.value == 0.8
    assert git_signal.evidence
    assert "Git history" in git_signal.evidence[0].description
