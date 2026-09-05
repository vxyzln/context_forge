from itertools import pairwise
from pathlib import Path
from uuid import uuid4

import pytest

from context_forge.context.candidate import ContextCandidate
from context_forge.context.retrieval import (
    RelationshipCandidateRetriever,
    RetrievalEvidence,
)
from context_forge.context.types import ContextUnitType
from context_forge.models.enums import FileType
from context_forge.models.file import File
from context_forge.models.project import Project
from context_forge.models.relationship import Relationship


def test_relationship_candidate_retriever_expands_direct_relationship() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    second = File(
        project_id=project.id,
        path=Path("second.py"),
        name="second.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(second)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=second.id,
            relationship_type="imports",
        )
    )

    candidates = [
        ContextCandidate(
            entity_id=first.id,
            unit_type=ContextUnitType.FILE,
            score=1.0,
            source="deterministic_search",
        )
    ]

    expanded, _ = RelationshipCandidateRetriever().expand(
        project,
        candidates,
    )

    assert len(expanded) == 2
    assert expanded[0].entity_id == first.id
    assert expanded[1].entity_id == second.id


def test_relationship_candidate_retriever_preserves_original_candidate() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    file = File(
        project_id=project.id,
        path=Path("auth.py"),
        name="auth.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    project.add_file(file)

    candidate = ContextCandidate(
        entity_id=file.id,
        unit_type=ContextUnitType.FILE,
        score=0.8,
        source="deterministic_search",
        reason="File name contains query",
    )

    expanded, _ = RelationshipCandidateRetriever().expand(
        project,
        [candidate],
    )

    assert expanded == [candidate]


def test_relationship_candidate_retriever_filters_relationship_types() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    imported = File(
        project_id=project.id,
        path=Path("imported.py"),
        name="imported.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    referenced = File(
        project_id=project.id,
        path=Path("referenced.py"),
        name="referenced.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(imported)
    project.add_file(referenced)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=imported.id,
            relationship_type="imports",
        )
    )
    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=referenced.id,
            relationship_type="references",
        )
    )

    candidate = ContextCandidate(
        entity_id=first.id,
        unit_type=ContextUnitType.FILE,
        score=1.0,
        source="deterministic_search",
    )

    expanded, _ = RelationshipCandidateRetriever(
        relationship_types={"imports"},
    ).expand(project, [candidate])

    entity_ids = {candidate.entity_id for candidate in expanded}

    assert first.id in entity_ids
    assert imported.id in entity_ids
    assert referenced.id not in entity_ids


def test_relationship_candidate_retriever_supports_max_depth() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    second = File(
        project_id=project.id,
        path=Path("second.py"),
        name="second.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    third = File(
        project_id=project.id,
        path=Path("third.py"),
        name="third.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(second)
    project.add_file(third)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=second.id,
            relationship_type="imports",
        )
    )
    project.add_relationship(
        Relationship(
            source_id=second.id,
            target_id=third.id,
            relationship_type="imports",
        )
    )

    candidate = ContextCandidate(
        entity_id=first.id,
        unit_type=ContextUnitType.FILE,
        score=1.0,
        source="deterministic_search",
    )

    expanded, _ = RelationshipCandidateRetriever(max_depth=2).expand(
        project,
        [candidate],
    )

    entity_ids = {candidate.entity_id for candidate in expanded}

    assert first.id in entity_ids
    assert second.id in entity_ids
    assert third.id in entity_ids


def test_relationship_candidate_retriever_limits_candidates() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    files = [
        File(
            project_id=project.id,
            path=Path(f"file_{index}.py"),
            name=f"file_{index}.py",
            extension=".py",
            file_type=FileType.SOURCE,
        )
        for index in range(4)
    ]

    for file in files:
        project.add_file(file)

    for first, second in pairwise(files):
        project.add_relationship(
            Relationship(
                source_id=first.id,
                target_id=second.id,
                relationship_type="imports",
            )
        )

    candidate = ContextCandidate(
        entity_id=files[0].id,
        unit_type=ContextUnitType.FILE,
        score=1.0,
        source="deterministic_search",
    )

    expanded, _ = RelationshipCandidateRetriever(
        max_depth=2,
        max_candidates=3,
    ).expand(
        project,
        [candidate],
    )

    assert len(expanded) == 3
    assert expanded[0].entity_id == files[0].id


def test_relationship_candidate_retriever_deduplicates_expansion() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    second = File(
        project_id=project.id,
        path=Path("second.py"),
        name="second.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(second)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=second.id,
            relationship_type="imports",
        )
    )

    project.add_relationship(
        Relationship(
            source_id=second.id,
            target_id=first.id,
            relationship_type="references",
        )
    )

    candidates = [
        ContextCandidate(
            entity_id=first.id,
            unit_type=ContextUnitType.FILE,
            score=1.0,
            source="deterministic_search",
        ),
        ContextCandidate(
            entity_id=second.id,
            unit_type=ContextUnitType.FILE,
            score=0.9,
            source="deterministic_search",
        ),
    ]

    expanded, _ = RelationshipCandidateRetriever(max_depth=2).expand(
        project,
        candidates,
    )

    entity_ids = [candidate.entity_id for candidate in expanded]

    assert entity_ids.count(first.id) == 1
    assert entity_ids.count(second.id) == 1


def test_relationship_candidate_retriever_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="depth must be positive"):
        RelationshipCandidateRetriever(max_depth=0)

    with pytest.raises(ValueError, match="candidate count must be positive"):
        RelationshipCandidateRetriever(max_candidates=0)


def test_relationship_candidate_retriever_records_evidence() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    second = File(
        project_id=project.id,
        path=Path("second.py"),
        name="second.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(second)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=second.id,
            relationship_type="imports",
            confidence=0.8,
        )
    )

    candidate = ContextCandidate(
        entity_id=first.id,
        unit_type=ContextUnitType.FILE,
        score=1.0,
        source="deterministic_search",
    )

    expanded, evidence = RelationshipCandidateRetriever().expand(
        project,
        [candidate],
    )

    assert expanded[1].entity_id == second.id

    second_evidence = evidence[second.id]

    assert second_evidence.source_candidate_id == first.id
    assert second_evidence.relationship_type == "imports"
    assert second_evidence.depth == 1
    assert second_evidence.relationship_confidence == 0.8
    assert second_evidence.candidate_confidence == 0.8
    assert second_evidence.provenance == "relationship-aware repository expansion"


def test_relationship_candidate_retriever_caps_expanded_confidence() -> None:
    project = Project(
        name="example",
        root_path=Path("/tmp/example"),
    )

    first = File(
        project_id=project.id,
        path=Path("first.py"),
        name="first.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )
    second = File(
        project_id=project.id,
        path=Path("second.py"),
        name="second.py",
        extension=".py",
        file_type=FileType.SOURCE,
    )

    project.add_file(first)
    project.add_file(second)

    project.add_relationship(
        Relationship(
            source_id=first.id,
            target_id=second.id,
            relationship_type="imports",
            confidence=1.0,
        )
    )

    candidate = ContextCandidate(
        entity_id=first.id,
        unit_type=ContextUnitType.FILE,
        score=0.6,
        source="deterministic_search",
    )

    expanded, evidence = RelationshipCandidateRetriever().expand(
        project,
        [candidate],
    )

    expanded_candidate = next(
        candidate for candidate in expanded if candidate.entity_id == second.id
    )

    assert expanded_candidate.score == 0.6
    assert evidence[second.id].candidate_confidence == 0.6


def test_retrieval_evidence_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="depth must be positive"):
        RetrievalEvidence(
            source_candidate_id=uuid4(),
            relationship_type="imports",
            depth=0,
            relationship_confidence=1.0,
            candidate_confidence=1.0,
            provenance="test",
        )

    with pytest.raises(
        ValueError,
        match="Relationship confidence must be between",
    ):
        RetrievalEvidence(
            source_candidate_id=uuid4(),
            relationship_type="imports",
            depth=1,
            relationship_confidence=1.1,
            candidate_confidence=1.0,
            provenance="test",
        )

    with pytest.raises(
        ValueError,
        match="Candidate confidence must be between",
    ):
        RetrievalEvidence(
            source_candidate_id=uuid4(),
            relationship_type="imports",
            depth=1,
            relationship_confidence=1.0,
            candidate_confidence=-0.1,
            provenance="test",
        )

    with pytest.raises(
        ValueError,
        match="provenance cannot be empty",
    ):
        RetrievalEvidence(
            source_candidate_id=uuid4(),
            relationship_type="imports",
            depth=1,
            relationship_confidence=1.0,
            candidate_confidence=1.0,
            provenance=" ",
        )
