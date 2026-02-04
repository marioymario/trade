from __future__ import annotations

from files.core.types import EntrySignal, ExitSignal, MarketState, Position
from files.models.entry_model import EntryModel

_model = EntryModel()

CONFIDENCE_ENTER = 0.60  # start conservative

# Exit parameters (keep deterministic; make configurable later)
ATR_MULT: float = 2.0          # initial stop distance
TRAIL_ATR_MULT: float = 2.0    # trailing stop distance
MAX_HOLD_BARS: int = 24        # set to 2 to force exits during testing


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
    """Compute a tightened (never-loosen) trailing stop."""
    new_stop, _new_anchor, _reason = compute_trailing_stop_update(
        position=position,
        latest_close=latest_close,
        latest_high=None,
        latest_low=None,
        atr=atr,
        atr_mult=atr_mult,
    )
    return new_stop


def compute_trailing_stop_update(
    *,
    position: Position,
    latest_close: float,
    latest_high: float | None = None,
    latest_low: float | None = None,
    atr: float,
    atr_mult: float = TRAIL_ATR_MULT,
) -> tuple[float | None, float | None, str]:
    """Compute trailing stop + updated anchor + reason."""
    try:
        close = float(latest_close)
        a = float(atr)
        m = float(atr_mult)
    except Exception:
        return None, getattr(position, "trailing_anchor_price", None), "bad_inputs"

    if not (close == close):
        return None, getattr(position, "trailing_anchor_price", None), "close_nan"
    if not (a == a) or a <= 0.0:
        return None, getattr(position, "trailing_anchor_price", None), "atr_missing_or_nonpositive"
    if not (m == m) or m <= 0.0:
        return None, getattr(position, "trailing_anchor_price", None), "atr_mult_nonpositive"

    hi = close
    lo = close
    if latest_high is not None:
        try:
            hi = float(latest_high)
        except Exception:
            hi = close
    if latest_low is not None:
        try:
            lo = float(latest_low)
        except Exception:
            lo = close

    if not (hi == hi):
        hi = close
    if not (lo == lo):
        lo = close

    prev_stop = position.stop_price
    prev_stop_ok = (prev_stop is not None) and (float(prev_stop) == float(prev_stop))

    prev_anchor = getattr(position, "trailing_anchor_price", None)
    prev_anchor_ok = (prev_anchor is not None) and (float(prev_anchor) == float(prev_anchor))

    if position.side == "LONG":
        anchor = hi if not prev_anchor_ok else max(float(prev_anchor), hi)
        candidate = anchor - m * a
        if not (candidate == candidate) or candidate <= 0.0:
            return None, float(anchor), "candidate_invalid"
        if not prev_stop_ok:
            return float(candidate), float(anchor), "init_stop"
        new_stop = max(float(prev_stop), float(candidate))
        return float(new_stop), float(anchor), "ratchet"

    # SHORT
    anchor = lo if not prev_anchor_ok else min(float(prev_anchor), lo)
    candidate = anchor + m * a
    if not (candidate == candidate) or candidate <= 0.0:
        return None, float(anchor), "candidate_invalid"
    if not prev_stop_ok:
        return float(candidate), float(anchor), "init_stop"
    new_stop = min(float(prev_stop), float(candidate))
    return float(new_stop), float(anchor), "ratchet"


def evaluate_entry(features, market_state: MarketState) -> EntrySignal:
    if not market_state.tradable:
        return EntrySignal(
            should_enter=False,
            side="LONG",
            confidence=0.0,
            reason=market_state.reason or "not_tradable",
        )

    confidence = float(_model.predict_confidence(features))

    if confidence != confidence:
        return EntrySignal(
            should_enter=False,
            side="LONG",
            confidence=0.0,
            reason="confidence_nan",
        )

    import os
    force_side = os.getenv("FORCE_SIDE", "").strip().upper()
    if force_side in ("LONG", "SHORT"):
        if confidence >= CONFIDENCE_ENTER:
            return EntrySignal(
                should_enter=True,
                side=force_side,
                confidence=confidence,
                reason=f"forced_{force_side.lower()}",
            )
        return EntrySignal(
            should_enter=False,
            side=force_side,
            confidence=confidence,
            reason=f"forced_{force_side.lower()}_but_low_confidence",
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
    if not market_state.tradable:
        return ExitSignal(should_exit=True, reason=market_state.reason or "not_tradable")

    try:
        close = float(latest_features_row["close"])
    except Exception:
        return ExitSignal(should_exit=False, reason="missing_close")

    try:
        ts = latest_features_row["timestamp"]
        now_ts_ms = int(getattr(ts, "value", 0) // 1_000_000)
    except Exception:
        now_ts_ms = 0

    same_bar_as_entry = (
        position.entry_ts_ms is not None
        and now_ts_ms > 0
        and int(position.entry_ts_ms) == int(now_ts_ms)
    )

    # STOP (close-only)
    # This makes LIVE and BT comparable when LIVE may be evaluating an in-progress bar.
    if (not same_bar_as_entry) and position.stop_price is not None and position.stop_price == position.stop_price:
        sp = float(position.stop_price)
        if position.side == "LONG" and close <= sp:
            return ExitSignal(should_exit=True, reason="stop_hit")
        if position.side == "SHORT" and close >= sp:
            return ExitSignal(should_exit=True, reason="stop_hit")

    # Time stop
    if position.entry_ts_ms is not None:
        held = _bars_held(
            entry_ts_ms=int(position.entry_ts_ms),
            now_ts_ms=int(now_ts_ms),
            expected_step_s=int(expected_step_s),
        )
        if held >= int(MAX_HOLD_BARS):
            return ExitSignal(should_exit=True, reason="time_stop")

    return ExitSignal(should_exit=False, reason=None)


def size_position(signal: EntrySignal, market_state: MarketState) -> float:
    return 0.01
