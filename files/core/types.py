# files/core/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

StrategySide = Literal["LONG", "SHORT"]

# These are required by files/strategy/filters.py
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
    symbol: str
    qty: float
    side: StrategySide
    entry_price: float
    entry_ts_ms: Optional[int]
    stop_price: Optional[float] = None

    # v2 trailing stop state:
    # - LONG: highest favorable price since entry (bar high)
    # - SHORT: lowest favorable price since entry (bar low)
    trailing_anchor_price: Optional[float] = None
