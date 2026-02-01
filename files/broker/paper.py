# files/broker/paper.py
from __future__ import annotations

from typing import Dict, Optional

from files.core.types import Position, StrategySide
from files.utils.logger import get_logger

logger = get_logger(__name__)


class PaperBroker:
    """
    Local-only paper broker.

    - No Alpaca dependency
    - Positions tracked in memory
    - Deterministic and safe for development
    - Optional fee/slippage cost model applied at close
    - Cooldown tracking (post-exit)
    """

    def __init__(
        self,
        *,
        dry_run: bool = False,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
    ):
        self.dry_run = dry_run
        self.fee_bps = float(fee_bps)
        self.slippage_bps = float(slippage_bps)

        self._tracked: Dict[str, Position] = {}
        self._last_exit_ts_ms: Dict[str, int] = {}

        self.realized_pnl_usd_total: float = 0.0
        self.trades_closed: int = 0

        logger.info(
            "PaperBroker initialized (local-only)",
            extra={
                "dry_run": self.dry_run,
                "fee_bps": self.fee_bps,
                "slippage_bps": self.slippage_bps,
            },
        )

    def _cost_rate(self) -> float:
        bps = max(self.fee_bps, 0.0) + max(self.slippage_bps, 0.0)
        return bps / 10_000.0

    def _notional(self, price: float, qty: float) -> float:
        return float(price) * float(qty)

    def get_tracked_position(
        self,
        *,
        symbol: str,
        latest_close: Optional[float] = None,
        latest_atr: Optional[float] = None,
        atr_mult: float = 2.0,
    ) -> Optional[Position]:
        return self._tracked.get(symbol)

    def update_stop(
        self,
        *,
        symbol: str,
        new_stop_price: float,
        new_trailing_anchor_price: Optional[float] = None,
    ) -> Optional[Position]:
        pos = self._tracked.get(symbol)
        if pos is None:
            return None

        try:
            ns = float(new_stop_price)
        except Exception:
            return pos

        if not (ns == ns):
            return pos

        # Preserve anchor unless explicitly updated
        anchor = pos.trailing_anchor_price
        if new_trailing_anchor_price is not None:
            try:
                a = float(new_trailing_anchor_price)
                if a == a:
                    anchor = a
            except Exception:
                pass

        updated = Position(
            symbol=pos.symbol,
            qty=float(pos.qty),
            side=pos.side,
            entry_price=float(pos.entry_price),
            entry_ts_ms=int(pos.entry_ts_ms) if pos.entry_ts_ms is not None else None,
            stop_price=float(ns),
            trailing_anchor_price=anchor,
        )
        self._tracked[symbol] = updated
        return updated

    def cooldown_remaining_bars(
        self,
        *,
        symbol: str,
        now_ts_ms: int,
        expected_step_s: int,
        cooldown_bars: int,
    ) -> int:
        """
        Returns how many bars remain in cooldown.
        0 means you can enter now.
        """
        if cooldown_bars <= 0:
            return 0
        if expected_step_s <= 0:
            return 0
        last_exit = self._last_exit_ts_ms.get(symbol)
        if last_exit is None:
            return 0

        delta_ms = max(int(now_ts_ms) - int(last_exit), 0)
        bars_since = int(delta_ms // (int(expected_step_s) * 1000))
        remaining = int(cooldown_bars) - bars_since
        return max(0, remaining)

    def can_enter(
        self,
        *,
        symbol: str,
        now_ts_ms: int,
        expected_step_s: int,
        cooldown_bars: int,
    ) -> bool:
        return (
            self.cooldown_remaining_bars(
                symbol=symbol,
                now_ts_ms=now_ts_ms,
                expected_step_s=expected_step_s,
                cooldown_bars=cooldown_bars,
            )
            == 0
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
        """
        Open a new paper position.

        - trailing_anchor_price is optional trailing stop state:
            LONG: highest favorable price since entry (bar high)
            SHORT: lowest favorable price since entry (bar low)

        - **kwargs accepted so call sites can evolve without crashing.
        """
        if size <= 0:
            raise ValueError(f"size must be > 0, got {size}")

        if symbol in self._tracked:
            logger.warning(
                "Refusing to open: position already exists",
                extra={"symbol": symbol},
            )
            return

        pos = Position(
            symbol=symbol,
            qty=float(size),
            side=side,
            entry_price=float(entry_price),
            entry_ts_ms=int(entry_ts_ms),
            stop_price=stop_price,
            trailing_anchor_price=trailing_anchor_price,
        )
        self._tracked[symbol] = pos

        logger.info(
            "Opened paper position" if not self.dry_run else "DRY RUN: opened paper position",
            extra={
                "symbol": symbol,
                "side": side,
                "qty": float(size),
                "entry_price": float(entry_price),
                "stop_price": float(stop_price) if stop_price is not None else None,
                "trailing_anchor_price": float(trailing_anchor_price)
                if trailing_anchor_price is not None
                else None,
                "entry_ts_ms": int(entry_ts_ms),
            },
        )

    def get_unrealized_pnl(self, *, symbol: str, last_price: float) -> tuple[float, float]:
        pos = self._tracked.get(symbol)
        if pos is None:
            return 0.0, 0.0

        entry = float(pos.entry_price)
        qty = float(pos.qty)

        if entry <= 0.0:
            return 0.0, 0.0

        if pos.side == "LONG":
            pnl_usd = (float(last_price) - entry) * qty
            pnl_pct = (float(last_price) - entry) / entry
        else:  # SHORT
            pnl_usd = (entry - float(last_price)) * qty
            pnl_pct = (entry - float(last_price)) / entry

        return float(pnl_usd), float(pnl_pct)

    def realize_and_close(
        self,
        *,
        symbol: str,
        exit_price: float,
        reason: str,
        exit_ts_ms: Optional[int] = None,
    ) -> dict:
        pos = self._tracked.get(symbol)
        if pos is None:
            return {
                "symbol": symbol,
                "exit_reason": reason,
                "realized_pnl_usd": 0.0,
                "realized_pnl_pct": 0.0,
                "cum_realized_pnl_usd": self.realized_pnl_usd_total,
                "trades_closed": self.trades_closed,
                "entry_ts_ms": "",
                "exit_ts_ms": exit_ts_ms if exit_ts_ms is not None else "",
                "side": "",
                "qty": "",
                "entry_price": "",
                "exit_price": float(exit_price),
                "stop_price": "",
                "fee_bps": self.fee_bps,
                "slippage_bps": self.slippage_bps,
                "cost_usd": 0.0,
            }

        qty = float(pos.qty)
        entry_price = float(pos.entry_price)
        exit_price_f = float(exit_price)

        gross_usd, _gross_pct = self.get_unrealized_pnl(symbol=symbol, last_price=exit_price_f)

        rate = self._cost_rate()
        entry_cost = self._notional(entry_price, qty) * rate
        exit_cost = self._notional(exit_price_f, qty) * rate
        cost_usd = float(entry_cost + exit_cost)

        net_pnl_usd = float(gross_usd - cost_usd)

        entry_notional = self._notional(entry_price, qty)
        net_pnl_pct = float(net_pnl_usd / entry_notional) if entry_notional > 0 else 0.0

        self.realized_pnl_usd_total += net_pnl_usd
        self.trades_closed += 1
        self._tracked.pop(symbol, None)

        if exit_ts_ms is not None:
            self._last_exit_ts_ms[symbol] = int(exit_ts_ms)

        return {
            "symbol": symbol,
            "exit_reason": reason,
            "side": pos.side,
            "qty": qty,
            "entry_price": entry_price,
            "exit_price": exit_price_f,
            "entry_ts_ms": int(pos.entry_ts_ms) if pos.entry_ts_ms is not None else "",
            "exit_ts_ms": int(exit_ts_ms) if exit_ts_ms is not None else "",
            "stop_price": float(pos.stop_price) if pos.stop_price is not None else "",
            "fee_bps": float(self.fee_bps),
            "slippage_bps": float(self.slippage_bps),
            "cost_usd": float(cost_usd),
            "realized_pnl_usd": float(net_pnl_usd),
            "realized_pnl_pct": float(net_pnl_pct),
            "cum_realized_pnl_usd": float(self.realized_pnl_usd_total),
            "trades_closed": int(self.trades_closed),
        }
