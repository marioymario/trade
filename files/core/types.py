# files/core/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

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
    side: Literal["LONG", "SHORT"]
    confidence: float
    reason: Optional[str] = None

@dataclass(frozen=True)
class ExitSignal:
    should_exit: bool
    reason: Optional[str] = None

