
# files/core/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


StrategySide = Literal["LONG", "SHORT"]

Trend = Literal["up", "down", "flat"]
VolRegime = Literal["low", "normal", "high"]

@dataclass(frozen=True)
class MarketState:
    tradable: bool
    trend: Trend
    volatility: VolRegime
    cadence_ok: bool
    has_enough_bars: bool
    reason: Optional[str] = None

@dataclass(frozen=True)
class EntrySignal:
    should_enter: bool
    side: StrategySide
    confidence: float
    reason: Optional[str] = None

@dataclass(frozen=True)
class ExitSignal:
    should_exit: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class Position:
    """Local, strategy-oriented view of an open position.

    Notes:
    - entry_ts_ms is epoch milliseconds.
    - stop_price is the *current* stop we intend to respect (v1: fixed at entry).
    """

    symbol: str
    qty: float
    side: StrategySide
    entry_price: float
    entry_ts_ms: Optional[int]
    stop_price: Optional[float] = None


