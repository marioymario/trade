# files/strategy/rules.py
from __future__ import annotations

from files.core.types import EntrySignal, ExitSignal, MarketState, Position
from files.models.entry_model import EntryModel

_model = EntryModel()

CONFIDENCE_ENTER = 0.60  # start conservative

# Exit parameters (keep deterministic; make configurable later)
ATR_MULT: float = 2.0          # initial stop distance
TRAIL_ATR_MULT: float = 2.0    # trailing stop distance
MAX_HOLD_BARS: int = 48        # you set this back to 48 ✅


def compute_initial_stop(*, side: str, entry_price: float, atr: float) -> float:
    """Stop computed at entry.

    v1: stop = entry_price +/- ATR_MULT * atr
    """
    if side.upper() == "LONG":
        return float(entry_price) - ATR_MULT * float(atr)
    if side.upper() == "SHORT":
        return float(entry_price) + ATR_MULT * float(atr)
    raise ValueError(f"Invalid side: {side!r}")


def compute_trailing_stop(
    *,
    position: Position,
    latest_close: float,
    atr: float,
    atr_mult: float = TRAIL_ATR_MULT,
) -> float | None:
    """Compute a tightened (never-loosen) trailing stop.

    LONG:
      candidate = latest_close - atr_mult * atr
      new_stop  = max(prev_stop, candidate)

    SHORT:
      candidate = latest_close + atr_mult * atr
      new_stop  = min(prev_stop, candidate)

    Returns:
      - new_stop (float) if computable
      - None if not computable (bad atr/close)
    """
    try:
        close = float(latest_close)
        a = float(atr)
    except Exception:
        return None

    if not (close == close) or not (a == a) or a <= 0.0:
        return None

    prev = position.stop_price
    prev_ok = (prev is not None) and (float(prev) == float(prev))

    if position.side == "LONG":
        candidate = close - float(atr_mult) * a
        if not prev_ok:
            return float(candidate)
        return float(max(float(prev), float(candidate)))

    # SHORT
    candidate = close + float(atr_mult) * a
    if not prev_ok:
        return float(candidate)
    return float(min(float(prev), float(candidate)))


def evaluate_entry(features, market_state: MarketState) -> EntrySignal:
    # Safety gate: never enter if not tradable
    if not market_state.tradable:
        return EntrySignal(
            should_enter=False,
            side="LONG",
            confidence=0.0,
            reason=market_state.reason or "not_tradable",
        )

    confidence = float(_model.predict_confidence(features))

    if confidence != confidence:  # NaN check
        return EntrySignal(
            should_enter=False,
            side="LONG",
            confidence=0.0,
            reason="confidence_nan",
        )

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


def _bars_held(*, entry_ts_ms: int, now_ts_ms: int, expected_step_s: int) -> int:
    if expected_step_s <= 0:
        return 0
    delta_ms = max(now_ts_ms - entry_ts_ms, 0)
    return int(delta_ms // (expected_step_s * 1000))


def evaluate_exit(
    *,
    position: Position,
    latest_features_row,
    market_state: MarketState,
    expected_step_s: int,
) -> ExitSignal:
    """Evaluate whether we should exit an existing position.

    Rules:
    - Exit if market becomes non-tradable (safety).
    - Exit on stop (uses position.stop_price; now can be trailed externally).
    - Exit on time stop (max bars held).
    """
    if not market_state.tradable:
        return ExitSignal(should_exit=True, reason=market_state.reason or "not_tradable")

    try:
        close = float(latest_features_row["close"])
    except Exception:
        return ExitSignal(should_exit=False, reason="missing_close")

    # Stop (hard stop)
    if position.stop_price is not None and position.stop_price == position.stop_price:
        sp = float(position.stop_price)
        if position.side == "LONG" and close <= sp:
            return ExitSignal(should_exit=True, reason="stop_hit")
        if position.side == "SHORT" and close >= sp:
            return ExitSignal(should_exit=True, reason="stop_hit")

    # Time stop (bars held)
    if position.entry_ts_ms is not None:
        try:
            ts = latest_features_row["timestamp"]
            now_ts_ms = int(getattr(ts, "value", 0) // 1_000_000)  # ns -> ms
        except Exception:
            now_ts_ms = 0

        held = _bars_held(
            entry_ts_ms=int(position.entry_ts_ms),
            now_ts_ms=int(now_ts_ms),
            expected_step_s=int(expected_step_s),
        )
        if held >= int(MAX_HOLD_BARS):
            return ExitSignal(should_exit=True, reason="time_stop")

    return ExitSignal(should_exit=False, reason=None)


def size_position(signal: EntrySignal, market_state: MarketState) -> float:
    return 1.0
