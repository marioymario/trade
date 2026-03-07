from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from files.broker.base import Broker
from files.core.types import Position, StrategySide
from files.data.trades import trades_csv_path
from files.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None  # type: ignore


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


def _env_str(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is None:
        return str(default)
    return str(v).strip()


def _exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except Exception:
        return False


def _storage_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("/", "_")


def _pick_ts_ms(row: dict) -> int | None:
    for k in ("exit_ts_ms", "entry_ts_ms", "ts_ms"):
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            return int(float(v))
        except Exception:
            continue
    return None


def _pick_pnl_usd(row: dict) -> float:
    for k in ("realized_pnl_usd", "pnl_usd", "realized_pnl"):
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except Exception:
            continue
    return 0.0


def _daily_limits_exceeded(
    *,
    trades_csv: str,
    max_trades_per_day: float,
    max_daily_loss_usd: float,
    tz_name: str,
) -> tuple[bool, str, int, float]:
    max_trades = float(max_trades_per_day)
    max_loss = float(max_daily_loss_usd)

    if max_trades <= 0 and max_loss <= 0:
        return False, "", 0, 0.0

    if not trades_csv or (not os.path.exists(trades_csv)):
        return False, "", 0, 0.0

    tz = None
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = None

    now = datetime.now(tz or timezone.utc)
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start_day.timestamp() * 1000)

    trades_today = 0
    pnl_today = 0.0

    try:
        with open(trades_csv, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                ts = _pick_ts_ms(row)
                if ts is None or ts < start_ms:
                    continue
                trades_today += 1
                pnl_today += _pick_pnl_usd(row)
    except Exception:
        return False, "read_error", 0, 0.0

    if max_trades > 0 and trades_today >= int(max_trades):
        return True, f"trades_today={trades_today} cap={int(max_trades)}", trades_today, pnl_today

    if max_loss > 0 and pnl_today <= -float(max_loss):
        return True, f"pnl_today={pnl_today:.2f} cap=-{float(max_loss):.2f}", trades_today, pnl_today

    return False, "", trades_today, pnl_today


@dataclass(frozen=True)
class Guardrails:
    flags_dir: str
    kill_switch_file: str
    halt_orders_file: str
    arm_file: str
    dry_run: bool
    max_order_usd: float
    max_position_usd: float
    max_trades_per_day: float
    max_daily_loss_usd: float
    tz_local: str
    data_tag: str
    timeframe: str

    @staticmethod
    def from_env() -> "Guardrails":
        flags_dir = _env_str("FLAGS_DIR", f"{os.path.expanduser('~')}/trade_flags")
        kill_switch_file = _env_str("KILL_SWITCH_FILE", "/tmp/TRADING_STOP")
        halt_orders_file = _env_str("HALT_ORDERS_FILE", "")
        arm_file = _env_str("ARM_FILE", "") or f"{flags_dir}/ARM"

        return Guardrails(
            flags_dir=flags_dir,
            kill_switch_file=kill_switch_file,
            halt_orders_file=halt_orders_file,
            arm_file=arm_file,
            dry_run=_env_bool("DRY_RUN", False),
            max_order_usd=_env_float("MAX_ORDER_USD", 0.0),
            max_position_usd=_env_float("MAX_POSITION_USD", 0.0),
            max_trades_per_day=_env_float("MAX_TRADES_PER_DAY", 0.0),
            max_daily_loss_usd=_env_float("MAX_DAILY_LOSS_USD", 0.0),
            tz_local=_env_str("TZ_LOCAL", "America/Los_Angeles"),
            data_tag=_env_str("DATA_TAG", ""),
            timeframe=_env_str("TIMEFRAME", ""),
        )

    def halt_code(self) -> Optional[str]:
        if self.kill_switch_file and _exists(self.kill_switch_file):
            return "STOP_BLOCK"
        if self.halt_orders_file and _exists(self.halt_orders_file):
            return "HALT_BLOCK"
        return None

    def is_armed(self) -> bool:
        return _exists(self.arm_file)

    def trades_csv_for_symbol(self, *, symbol: str) -> str:
        if not self.data_tag or not self.timeframe:
            return ""
        try:
            return trades_csv_path(
                exchange=self.data_tag,
                symbol=_storage_symbol(symbol),
                timeframe=self.timeframe,
            )
        except Exception:
            return ""


class GuardedBroker:
    """
    Submit-boundary guard wrapper.

    Enforces:
      - STOP/HALT flag files => block entries (exits always allowed)
      - file-based ARM gate (single source of truth)
      - daily limits
      - optional DRY_RUN gate for real broker
      - USD caps for orders/positions

    Contract:
      - open_position(...) returns Optional[str]
          * None => entry allowed + forwarded to inner broker
          * str  => entry blocked; caller should record exact reason
    """

    def __init__(
        self,
        inner: Broker,
        *,
        require_arm_for_entries: bool,
        block_entries_on_dry_run: bool,
    ):
        self._inner = inner
        self._require_arm = bool(require_arm_for_entries)
        self._block_on_dry_run = bool(block_entries_on_dry_run)

    def entry_block_reason(
        self,
        *,
        symbol: str,
        side: StrategySide,
        size: float,
        entry_price: float,
    ) -> Optional[str]:
        return self._block_entry_reason(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
        )

    def _block_entry_reason(
        self,
        *,
        symbol: str,
        side: StrategySide,
        size: float,
        entry_price: float,
    ) -> Optional[str]:
        g = Guardrails.from_env()

        code = g.halt_code()
        if code:
            if code == "STOP_BLOCK":
                return f"{code}(kill_switch={g.kill_switch_file})"
            return f"{code}(halt_orders={g.halt_orders_file})"

        if self._block_on_dry_run and g.dry_run:
            return "DRY_RUN_BLOCK"

        if self._require_arm and (not g.is_armed()):
            return f"ARM_BLOCK(arm_file={g.arm_file})"

        trades_csv = g.trades_csv_for_symbol(symbol=symbol)
        exceeded, why, _, _ = _daily_limits_exceeded(
            trades_csv=trades_csv,
            max_trades_per_day=g.max_trades_per_day,
            max_daily_loss_usd=g.max_daily_loss_usd,
            tz_name=g.tz_local,
        )
        if exceeded:
            return f"DAILY_LIMIT_BLOCK({why})"

        try:
            px = float(entry_price)
            qty = float(size)
        except Exception:
            return "BAD_INPUTS"

        if px <= 0 or qty <= 0:
            return "BAD_INPUTS"

        order_usd = px * qty
        if g.max_order_usd > 0 and order_usd > g.max_order_usd:
            return f"MAX_ORDER_USD_BLOCK(order_usd={order_usd:.2f} cap={g.max_order_usd:.2f})"

        pos = self._inner.get_tracked_position(symbol=symbol)
        existing_qty = float(pos.qty) if pos is not None else 0.0
        position_usd = px * (existing_qty + qty)
        if g.max_position_usd > 0 and position_usd > g.max_position_usd:
            return f"MAX_POSITION_USD_BLOCK(position_usd={position_usd:.2f} cap={g.max_position_usd:.2f})"

        return None

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
    ) -> Optional[str]:
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
            return str(reason)

        self._inner.open_position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            entry_ts_ms=entry_ts_ms,
            stop_price=stop_price,
            trailing_anchor_price=trailing_anchor_price,
            **kwargs,
        )
        return None

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
        return self._inner.realize_and_close(
            symbol=symbol,
            exit_price=exit_price,
            reason=reason,
            exit_ts_ms=exit_ts_ms,
        )
