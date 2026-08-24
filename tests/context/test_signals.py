from context_forge.context.signals import RelevanceSignals


def test_relevance_signals_default_to_zero() -> None:
    signals = RelevanceSignals()

    assert signals.lexical == 0.0
    assert signals.structural == 0.0
    assert signals.symbol == 0.0
    assert signals.dependency == 0.0


def test_relevance_signals_total_sums_all_signals() -> None:
    signals = RelevanceSignals(
        lexical=0.2,
        structural=0.3,
        symbol=0.1,
        dependency=0.2,
    )

    assert signals.total() == 0.8
