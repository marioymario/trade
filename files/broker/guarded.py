from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from files.broker.base import Broker
from files.core.types import Position, StrategySide
from files.utils.logger import get_logger

logger = get_logger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    s = v.strip().lower()
    if s in ("1", "true", "yes", "on", "y", "t"):
        return True
    if s in ("0", "false", "no", "off", "n", "f", ""):
        return False
    return default


def _env_float(name: str, default: float = 0.0) -> float:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)


@dataclass(frozen=True)
class Guardrails:
    kill_switch_file: str
    halt_orders_file: str
    armed: bool
    dry_run: bool
    max_order_usd: float
    max_position_usd: float

    @staticmethod
    def from_env() -> "Guardrails":
        return Guardrails(
            kill_switch_file=os.environ.get("KILL_SWITCH_FILE", "/tmp/TRADING_STOP").strip(),
            halt_orders_file=os.environ.get("HALT_ORDERS_FILE", "").strip(),
            armed=_env_bool("ARMED", False),
            dry_run=_env_bool("DRY_RUN", False),
            max_order_usd=_env_float("MAX_ORDER_USD", 0.0),
            max_position_usd=_env_float("MAX_POSITION_USD", 0.0),
        )

    def halt_reason(self) -> Optional[str]:
        if self.kill_switch_file and os.path.exists(self.kill_switch_file):
            return f"kill_switch({self.kill_switch_file})"
        if self.halt_orders_file and os.path.exists(self.halt_orders_file):
            return f"halt_orders({self.halt_orders_file})"
        return None


class GuardedBroker:
    """
    Wrapper that enforces:
      - kill/halt files => block new entries
      - (optional) arming gate for real broker
      - USD caps for orders/positions
    """

    def __init__(self, inner: Broker, *, require_armed_for_entries: bool):
        self._inner = inner
        self._require_armed = bool(require_armed_for_entries)

    def _block_entry_reason(
        self,
        *,
        symbol: str,
        side: StrategySide,
        size: float,
        entry_price: float,
    ) -> Optional[str]:
        g = Guardrails.from_env()

        r = g.halt_reason()
        if r:
            return r

        if self._require_armed:
            # Two-key arming model
            if g.dry_run:
                return "dry_run"
            if not g.armed:
                return "not_armed"

        try:
            px = float(entry_price)
            qty = float(size)
        except Exception:
            return "bad_inputs"

        if px <= 0 or qty <= 0:
            return "bad_inputs"

        order_usd = px * qty
        if g.max_order_usd > 0 and order_usd > g.max_order_usd:
            return f"max_order_usd({order_usd:.2f}>{g.max_order_usd:.2f})"

        # Position cap (covers future scale-in support)
        pos = self._inner.get_tracked_position(symbol=symbol)
        existing_qty = float(pos.qty) if pos is not None else 0.0
        position_usd = px * (existing_qty + qty)
        if g.max_position_usd > 0 and position_usd > g.max_position_usd:
            return f"max_position_usd({position_usd:.2f}>{g.max_position_usd:.2f})"

        return None

    # ---- Broker passthroughs + guarded entry ----

    def get_tracked_position(
        self,
        *,
        symbol: str,
        latest_close: Optional[float] = None,
        latest_atr: Optional[float] = None,
        atr_mult: float = 2.0,
    ) -> Optional[Position]:
        return self._inner.get_tracked_position(
            symbol=symbol,
            latest_close=latest_close,
            latest_atr=latest_atr,
            atr_mult=atr_mult,
        )

    def update_stop(
        self,
        *,
        symbol: str,
        new_stop_price: float,
        new_trailing_anchor_price: Optional[float] = None,
    ) -> Optional[Position]:
        return self._inner.update_stop(
            symbol=symbol,
            new_stop_price=new_stop_price,
            new_trailing_anchor_price=new_trailing_anchor_price,
        )

    def cooldown_remaining_bars(
        self,
        *,
        symbol: str,
        now_ts_ms: int,
        expected_step_s: int,
        cooldown_bars: int,
    ) -> int:
        return self._inner.cooldown_remaining_bars(
            symbol=symbol,
            now_ts_ms=now_ts_ms,
            expected_step_s=expected_step_s,
            cooldown_bars=cooldown_bars,
        )

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
        reason = self._block_entry_reason(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
        )
        if reason:
            logger.warning(
                "Blocked entry at broker guard",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "qty": float(size),
                    "entry_price": float(entry_price),
                    "reason": reason,
                },
            )
            return

        return self._inner.open_position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            entry_ts_ms=entry_ts_ms,
            stop_price=stop_price,
            trailing_anchor_price=trailing_anchor_price,
            **kwargs,
        )

    def get_unrealized_pnl(self, *, symbol: str, last_price: float) -> tuple[float, float]:
        return self._inner.get_unrealized_pnl(symbol=symbol, last_price=last_price)

    def realize_and_close(
        self,
        *,
        symbol: str,
        exit_price: float,
        reason: str,
        exit_ts_ms: Optional[int] = None,
    ) -> dict:
        # Always allow exits (even if halted). This is safer.
        return self._inner.realize_and_close(
            symbol=symbol,
            exit_price=exit_price,
            reason=reason,
            exit_ts_ms=exit_ts_ms,
        )

