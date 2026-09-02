from uuid import uuid4

from context_forge.context import (
    ContextPackage,
    ContextPackageSerializer,
    ContextSignal,
    ContextUnit,
    ContextUnitType,
    Evidence,
    Fact,
    Inference,
)


def test_context_package_serialization_preserves_context() -> None:
    source_id = uuid4()

    evidence = Evidence(
        source_id=source_id,
        description="defined in auth.py",
    )

    package = ContextPackage(
        task="authentication",
        units=(
            ContextUnit(
                entity_id=source_id,
                unit_type=ContextUnitType.FILE,
                relevance=0.9,
                content="def authenticate(username, password):\n    return True\n",
                signals=(
                    ContextSignal(
                        name="lexical_match",
                        value=0.8,
                        evidence=(evidence,),
                    ),
                ),
                facts=(
                    Fact(
                        fact_type="file_path",
                        value="src/auth.py",
                        evidence=(evidence,),
                    ),
                ),
                inferences=(
                    Inference(
                        claim="Authentication logic is likely in this file.",
                        confidence=0.7,
                        evidence=(evidence,),
                    ),
                ),
            ),
        ),
    )

    serialized = ContextPackageSerializer().serialize(package)

    assert '"task":"authentication"' in serialized
    assert str(source_id) in serialized
    assert '"unit_type":"file"' in serialized
    assert '"relevance":0.9' in serialized
    assert '"lexical_match"' in serialized
    assert '"file_path"' in serialized
    assert '"Authentication logic is likely in this file."' in serialized
    assert (
        '"content":"def authenticate(username, password):\\n    return True\\n"'
        in serialized
    )


def test_context_package_serialization_is_deterministic() -> None:
    entity_id = uuid4()

    package = ContextPackage(
        task="authentication",
        units=(
            ContextUnit(
                entity_id=entity_id,
                unit_type=ContextUnitType.FILE,
                relevance=0.8,
            ),
        ),
    )

    serializer = ContextPackageSerializer()

    first = serializer.serialize(package)
    second = serializer.serialize(package)

    assert first == second
