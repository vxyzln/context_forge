from context_forge.context.depth import ContextDepth


def test_context_depth_values() -> None:
    assert ContextDepth.MINIMAL.value == "minimal"
    assert ContextDepth.RECOMMENDED.value == "recommended"
    assert ContextDepth.DEEP.value == "deep"
