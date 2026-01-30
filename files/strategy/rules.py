# files/strategy/rules.py
from __future__ import annotations

from files.core.types import EntrySignal, ExitSignal, MarketState
from files.models.entry_model import EntryModel

_model = EntryModel()

CONFIDENCE_ENTER = 0.60  # start conservative


def evaluate_entry(features, market_state: MarketState) -> EntrySignal:
    # Safety gate: never enter if not tradable
    if not market_state.tradable:
        return EntrySignal(
            should_enter=False,
            side="LONG",
            confidence=0.0,
            reason=market_state.reason or "not_tradable",
        )

    # Model confidence (assumes your EntryModel looks at latest row)
    confidence = float(_model.predict_confidence(features))

    if confidence != confidence:  # NaN check
        return EntrySignal(
            should_enter=False,
            side="LONG",
            confidence=0.0,
            reason="confidence_nan",
        )

    # Directional logic (start simple)
    if market_state.trend == "up" and confidence >= CONFIDENCE_ENTER:
        return EntrySignal(
            should_enter=True,
            side="LONG",
            confidence=confidence,
            reason="trend_up_and_confident",
        )

    if market_state.trend == "down" and confidence >= CONFIDENCE_ENTER:
        return EntrySignal(
            should_enter=True,
            side="SHORT",
            confidence=confidence,
            reason="trend_down_and_confident",
        )

    return EntrySignal(
        should_enter=False,
        side="LONG",
        confidence=confidence,
        reason="not_confident_or_flat_trend",
    )


def evaluate_exit(position, features, market_state: MarketState) -> ExitSignal:
    # Super safe placeholder: exit if market becomes non-tradable
    if not market_state.tradable:
        return ExitSignal(should_exit=True, reason=market_state.reason or "not_tradable")

    return ExitSignal(should_exit=False, reason=None)


def size_position(signal: EntrySignal, market_state: MarketState) -> float:
    # placeholder sizing: later tie to ATR, volatility, confidence, and risk limits
    return 1.0



