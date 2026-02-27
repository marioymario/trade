## base.py
from __future__ import annotations

from typing import Protocol, Optional

from files.core.types import Position, StrategySide


class Broker(Protocol):
    def get_tracked_position(
        self,
        *,
        symbol: str,
        latest_close: Optional[float] = None,
        latest_atr: Optional[float] = None,
        atr_mult: float = 2.0,
    ) -> Optional[Position]:
        ...

    def update_stop(
        self,
        *,
        symbol: str,
        new_stop_price: float,
        new_trailing_anchor_price: Optional[float] = None,
    ) -> Optional[Position]:
        ...

    def cooldown_remaining_bars(
        self,
        *,
        symbol: str,
        now_ts_ms: int,
        expected_step_s: int,
        cooldown_bars: int,
    ) -> int:
        ...

    def open_position(
        self,
        *,
        symbol: str,
        side: StrategySide,
        size: float,
        entry_price: float,
        entry_ts_ms: int,
        stop_price: Optional[float] = None,
        trailing_anchor_price: Optional[float] = None,
        **kwargs,
    ) -> None:
        ...

    def get_unrealized_pnl(self, *, symbol: str, last_price: float) -> tuple[float, float]:
        ...

    def realize_and_close(
        self,
        *,
        symbol: str,
        exit_price: float,
        reason: str,
        exit_ts_ms: Optional[int] = None,
    ) -> dict:
        ...

