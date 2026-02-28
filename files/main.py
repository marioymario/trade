from __future__ import annotations

import csv
import os
import time
from collections import deque
from datetime import datetime, timezone

import pandas as pd

from files.broker.paper import PaperBroker
from files.broker.guarded import GuardedBroker
from files.config import load_trading_config
from files.data.decisions import append_decision_csv, decisions_csv_path
from files.data.features import compute_features, validate_latest_features
from files.data.market import fetch_market_data, MarketFetchError
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.trades import append_trade_csv, trades_csv_path
from files.strategy.filters import determine_market_state
from files.strategy.rules import (
    ATR_MULT,
    compute_initial_stop,
    compute_trailing_stop_update,
    evaluate_entry,
    evaluate_exit,
    size_position,
)
from files.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None  # type: ignore


def _timeframe_to_seconds(timeframe: str) -> int:
    tf = timeframe.strip().lower()
    unit = tf[-1]
    n = int(tf[:-1])
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 60 * 60
    if unit == "d":
        return n * 60 * 60 * 24
    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def _storage_symbol(symbol: str) -> str:
    """
    Normalize symbol for filesystem + processed CSV identity:
      - BTC/USD -> BTC_USD
    """
    return symbol.strip().upper().replace("/", "_")


def _cadence_ok(df: pd.DataFrame, expected_step_s: int) -> bool:
    if df is None or len(df) < 3:
        return False
    if "timestamp" not in df.columns:
        return False

    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    if ts.isna().all():
        return False

    diffs = ts.diff().dt.total_seconds().dropna()
    if len(diffs) == 0:
        return False

    med = float(diffs.median())
    return abs(med - expected_step_s) <= max(2.0, expected_step_s * 0.02)


def _fill_position_fields(decision_row: dict, position) -> None:
    """Mutates decision_row to include position data if available."""
    if position is None:
        decision_row["position_side"] = ""
        decision_row["position_qty"] = ""
        decision_row["position_entry_price"] = ""
        decision_row["position_stop_price"] = ""
        decision_row["position_trailing_anchor_price"] = ""
        return

    decision_row["position_side"] = position.side
    decision_row["position_qty"] = float(position.qty)
    decision_row["position_entry_price"] = float(position.entry_price)
    decision_row["position_stop_price"] = (
        float(position.stop_price) if position.stop_price is not None else ""
    )
    decision_row["position_trailing_anchor_price"] = (
        float(position.trailing_anchor_price)
        if getattr(position, "trailing_anchor_price", None) is not None
        else ""
    )


def _read_last_ts_ms_from_decisions_csv(path: str) -> int | None:
    """Return the last ts_ms found in an existing decisions CSV, or None."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return None

        last: int | None = None
        with open(path, "r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                v = row.get("ts_ms", "") if row else ""
                try:
                    ts_ms = int(float(v)) if v not in (None, "", "nan") else 0
                except Exception:
                    ts_ms = 0
                if ts_ms > 0:
                    last = ts_ms
        return last
    except Exception as e:
        logger.warning(
            "Failed to read last ts_ms from decisions CSV",
            extra={"path": path, "error": repr(e)},
        )
        return None


def _read_tail_market_reasons(path: str, *, tail_n: int = 50, window_k: int = 6) -> list[str]:
    """
    Read the tail of decisions.csv and extract the last window_k market_reason values.
    Best-effort: if file missing, return [].
    """
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return []

        reasons: list[str] = []
        with open(path, "r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                mr = (row.get("market_reason") or "").strip()
                if mr:
                    reasons.append(mr)

        if not reasons:
            return []
        reasons = reasons[-tail_n:]
        return reasons[-window_k:]
    except Exception as e:
        logger.warning(
            "Failed to read tail market_reasons from decisions CSV",
            extra={"path": path, "error": repr(e)},
        )
        return []


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure timestamp is datetime UTC and rows are sorted/deduped."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    out = df.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
        out = out.dropna(subset=["timestamp"])
        out = out.drop_duplicates(subset=["timestamp"], keep="last")
        out = out.sort_values("timestamp").reset_index(drop=True)
    return out


def _drop_in_progress_last_bar_if_safe(df: pd.DataFrame, *, min_bars: int) -> pd.DataFrame:
    """Drop latest bar only if we still keep >= min_bars rows."""
    if df is None:
        return df
    if len(df) >= (min_bars + 1):
        return df.iloc[:-1].reset_index(drop=True)
    return df


def _blank_decision_row(*, ts_ms: int, now_iso: str, bar_high: float, bar_low: float) -> dict:
    """
    Create a full-shape decision row (so CSV stays consistent) even when we skip trading.
    """
    return {
        "ts_ms": int(ts_ms) if ts_ms else 0,
        "timestamp": now_iso or "",
        "bar_high": float(bar_high),
        "bar_low": float(bar_low),
        "tradable": "",
        "trend": "",
        "volatility": "",
        "market_reason": "",
        "cooldown_remaining_bars": "",
        "position_side": "",
        "position_qty": "",
        "position_entry_price": "",
        "position_stop_price": "",
        "position_trailing_anchor_price": "",
        "unrealized_pnl_usd": "",
        "unrealized_pnl_pct": "",
        "trail_reason": "",
        "trail_new_stop": "",
        "trail_new_anchor": "",
        "entry_should_enter": "",
        "entry_side": "",
        "entry_confidence": "",
        "entry_reason": "",
        "exit_should_exit": "",
        "exit_reason": "",
    }


def _is_degraded(*, recent_reasons: deque[str], internal_cadence_ok: bool) -> tuple[bool, str]:
    """
    v0.3 watchdog contract:
    degraded_mode=True if any of:
      - cadence_failed occurs >=2 times in last 6 bars
      - features_invalid occurs >=2 times in last 6 bars
      - internal cadence anomaly detected in merged bars (internal_cadence_ok=False)

    Returns (degraded, why).
    """
    last = list(recent_reasons)[-6:]
    cadence_failed_n = sum(1 for r in last if "cadence_failed" in r)
    features_invalid_n = sum(1 for r in last if "features_invalid" in r)

    if not internal_cadence_ok:
        return True, "internal_cadence_anomaly"
    if cadence_failed_n >= 2:
        return True, f"cadence_failed_x{cadence_failed_n}_in_last6"
    if features_invalid_n >= 2:
        return True, f"features_invalid_x{features_invalid_n}_in_last6"
    return False, ""


def _parse_float_env(name: str, default: float = 0.0) -> float:
    v = os.environ.get(name, "")
    if v is None or str(v).strip() == "":
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)


def _exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except Exception:
        return False


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
    """
    Returns (exceeded, reason, trades_today, pnl_today_usd).
    Disabled if both limits <= 0, or file missing.
    """
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
        return False, "daily_limits_read_error", 0, 0.0

    if max_trades > 0 and trades_today >= int(max_trades):
        return True, f"max_trades_per_day({trades_today}>={int(max_trades)})", trades_today, pnl_today
    if max_loss > 0 and pnl_today <= -float(max_loss):
        return True, f"max_daily_loss_usd({pnl_today:.2f}<=-{float(max_loss):.2f})", trades_today, pnl_today

    return False, "", trades_today, pnl_today


def main() -> None:
    cfg = load_trading_config()

    # Contract:
    # - cfg.ccxt_exchange: fetch source
    # - cfg.data_tag: storage namespace (raw/processed)
    data_tag = cfg.data_tag

    ccxt_symbol = cfg.symbol
    storage_symbol = _storage_symbol(cfg.symbol)

    # In-loop guardrails (env-driven; same knobs as ops)
    kill_switch_file = os.environ.get("KILL_SWITCH_FILE", "/tmp/TRADING_STOP").strip()
    halt_orders_file = os.environ.get("HALT_ORDERS_FILE", "").strip()
    tz_local = os.environ.get("TZ_LOCAL", "America/Los_Angeles")
    max_trades_per_day = _parse_float_env("MAX_TRADES_PER_DAY", 0.0)
    max_daily_loss_usd = _parse_float_env("MAX_DAILY_LOSS_USD", 0.0)
    max_position_usd = _parse_float_env("MAX_POSITION_USD", 0.0)

    broker_kind = os.environ.get("BROKER", "paper").strip().lower()  # paper | alpaca

    logger.info("🚀 Trading system starting")
    logger.info(
        "Trading config loaded",
        extra={
            "symbol": ccxt_symbol,
            "storage_symbol": storage_symbol,
            "timeframe": cfg.timeframe,
            "loop_sleep_seconds": cfg.loop_sleep_seconds,
            "dry_run": cfg.dry_run,
            "ccxt_exchange": cfg.ccxt_exchange,
            "data_tag": data_tag,
            "max_order_size": cfg.max_order_size,
            "min_bars": cfg.min_bars,
            "fee_bps": getattr(cfg, "fee_bps", None),
            "slippage_bps": getattr(cfg, "slippage_bps", None),
            "cooldown_bars": getattr(cfg, "cooldown_bars", None),
            "BROKER": broker_kind,
            "KILL_SWITCH_FILE": kill_switch_file,
            "HALT_ORDERS_FILE": halt_orders_file,
            "MAX_TRADES_PER_DAY": max_trades_per_day,
            "MAX_DAILY_LOSS_USD": max_daily_loss_usd,
            "TZ_LOCAL": tz_local,
            "MAX_POSITION_USD": max_position_usd,
        },
    )

    # ---- Broker selection + guard wrapper ----
    require_armed_for_entries = False
    if broker_kind == "alpaca":
        from files.broker.alpaca import AlpacaBroker  # local import so paper runs without alpaca deps

        inner = AlpacaBroker()
        require_armed_for_entries = True
    else:
        inner = PaperBroker(
            dry_run=cfg.dry_run,
            fee_bps=getattr(cfg, "fee_bps", 0.0),
            slippage_bps=getattr(cfg, "slippage_bps", 0.0),
        )

    broker = GuardedBroker(inner, require_armed_for_entries=require_armed_for_entries)

    expected_step_s = _timeframe_to_seconds(cfg.timeframe)
    step_ms = int(expected_step_s * 1000)

    # ---- Restart-safe decision dedupe: seed last_decision_ts_ms from existing CSV ----
    dpath_existing = decisions_csv_path(exchange=data_tag, symbol=storage_symbol, timeframe=cfg.timeframe)
    last_decision_ts_ms: int | None = _read_last_ts_ms_from_decisions_csv(dpath_existing)
    if last_decision_ts_ms is not None:
        logger.info(
            "Decision dedupe initialized from existing CSV",
            extra={"csv_path": dpath_existing, "last_decision_ts_ms": int(last_decision_ts_ms)},
        )

    # ---- Watchdog state (v0.3): recent market_reason window ----
    recent_reasons: deque[str] = deque(maxlen=12)
    for r in _read_tail_market_reasons(dpath_existing, tail_n=80, window_k=6):
        recent_reasons.append(r)

    degraded_mode = False
    degraded_why = ""
    degraded_since_ts_ms: int | None = None

    def _write_decision_once_per_bar(decision_row: dict) -> None:
        nonlocal last_decision_ts_ms

        ts_ms = decision_row.get("ts_ms", 0) or 0
        try:
            ts_ms = int(ts_ms)
        except Exception:
            ts_ms = 0

        if ts_ms <= 0:
            return

        if last_decision_ts_ms is not None and ts_ms <= last_decision_ts_ms:
            return

        dpath = append_decision_csv(
            decision=decision_row,
            exchange=data_tag,
            symbol=storage_symbol,   # STORAGE SYMBOL (e.g. BTC_USD)
            timeframe=cfg.timeframe,
        )
        last_decision_ts_ms = ts_ms
        logger.info("Decision recorded", extra={"csv_path": dpath})

    # Headroom so dropping the in-progress bar never starves min_bars.
    fetch_limit = max(cfg.min_bars, 200) + 1
    tail_n = max(cfg.min_bars, 200) + 1
    store_tail_n = max(5000, tail_n)

    logger.info(
        "LIVE headroom",
        extra={
            "fetch_limit": int(fetch_limit),
            "tail_n": int(tail_n),
            "store_tail_n": int(store_tail_n),
        },
    )

    trades_path = trades_csv_path(exchange=data_tag, symbol=storage_symbol, timeframe=cfg.timeframe)

    while True:
        loop_start = time.time()
        try:
            # Optional failure injections
            if os.environ.get("FORCE_FETCH_FAIL", "").strip() in ("1", "true", "yes", "on"):
                raise RuntimeError("FORCE_FETCH_FAIL=1")

            # ------------------------
            # FETCH + PERSIST
            # ------------------------
            try:
                fetched = fetch_market_data(
                symbol=ccxt_symbol,
                timeframe=cfg.timeframe,
                limit=int(fetch_limit),
                min_bars_warn=cfg.min_bars,
                ccxt_exchange=cfg.ccxt_exchange,  # FETCH SOURCE
                )
            except MarketFetchError as e:
                mr = 'fetch_failed'
                logger.warning('Market fetch failed; skipping loop', extra={'symbol': ccxt_symbol, 'timeframe': cfg.timeframe, 'error': repr(e)})
                drow = _blank_decision_row(ts_ms=now_ts_ms, now_iso=now_iso, bar_high=bar_high, bar_low=bar_low)
                drow['market_reason'] = mr
                _fill_position_fields(drow, position)
                _write_decision_once_per_bar(drow)
                recent_reasons.append(mr)
                time.sleep(cfg.loop_sleep_seconds)
                continue
            fetched = _normalize_df(fetched)
            fetched = _drop_in_progress_last_bar_if_safe(fetched, min_bars=cfg.min_bars)

            if os.environ.get("FORCE_PERSIST_FAIL", "").strip() in ("1", "true", "yes", "on"):
                raise RuntimeError("FORCE_PERSIST_FAIL=1")

            append_ohlcv_parquet(
                df=fetched,
                exchange=data_tag,          # STORAGE TAG
                symbol=storage_symbol,      # STORAGE SYMBOL
                timeframe=cfg.timeframe,
            )

            # ------------------------
            # LOAD STORE + MERGE (robust)
            # ------------------------
            store_df = load_recent_ohlcv_parquet(
                exchange=data_tag,          # STORAGE TAG
                symbol=storage_symbol,      # STORAGE SYMBOL
                timeframe=cfg.timeframe,
                tail_n=int(store_tail_n),
            )
            store_df = _normalize_df(store_df)
            store_df = _drop_in_progress_last_bar_if_safe(store_df, min_bars=cfg.min_bars)

            combined = pd.concat([store_df, fetched], ignore_index=True)
            combined = _normalize_df(combined)

            if len(combined) > int(tail_n):
                combined = combined.iloc[-int(tail_n):].reset_index(drop=True)
            combined = _drop_in_progress_last_bar_if_safe(combined, min_bars=cfg.min_bars)

            rows_store = len(store_df)
            rows_fetched = len(fetched)
            rows = len(combined)

            logger.info(
                "Bars snapshot",
                extra={
                    "rows_store": int(rows_store),
                    "rows_fetched": int(rows_fetched),
                    "rows_combined": int(rows),
                    "min_bars": int(cfg.min_bars),
                    "store_tail_ts": str(store_df.iloc[-1]["timestamp"]) if rows_store > 0 else "",
                    "fetched_tail_ts": str(fetched.iloc[-1]["timestamp"]) if rows_fetched > 0 else "",
                    "combined_tail_ts": str(combined.iloc[-1]["timestamp"]) if rows > 0 else "",
                },
            )

            has_enough_bars = rows >= cfg.min_bars
            cadence_ok = _cadence_ok(combined, expected_step_s)

            if rows > 0 and "timestamp" in combined.columns:
                tail_ts = pd.to_datetime(combined.iloc[-1]["timestamp"], utc=True, errors="coerce")
                now_ts_ms = int(getattr(tail_ts, "value", 0) // 1_000_000) if not pd.isna(tail_ts) else 0
                now_iso = tail_ts.isoformat() if hasattr(tail_ts, "isoformat") else ""
                bar_high = float(combined.iloc[-1].get("high", combined.iloc[-1].get("close", 0.0)))
                bar_low = float(combined.iloc[-1].get("low", combined.iloc[-1].get("close", 0.0)))
            else:
                now_ts_ms = 0
                now_iso = ""
                bar_high = 0.0
                bar_low = 0.0

            position = broker.get_tracked_position(
                symbol=ccxt_symbol,
                latest_close=float(combined.iloc[-1]["close"]) if rows > 0 and "close" in combined.columns else 0.0,
                latest_atr=0.0,
                atr_mult=float(ATR_MULT),
            )

            if not has_enough_bars:
                mr = "not_enough_bars"
                drow = _blank_decision_row(ts_ms=now_ts_ms, now_iso=now_iso, bar_high=bar_high, bar_low=bar_low)
                drow["market_reason"] = mr
                _fill_position_fields(drow, position)
                _write_decision_once_per_bar(drow)
                recent_reasons.append(mr)
                time.sleep(cfg.loop_sleep_seconds)
                continue

            if not cadence_ok:
                mr = "cadence_failed"
                logger.warning(
                    "Cadence check failed; skipping loop (possible partial outage / sparse feed)",
                    extra={
                        "symbol": ccxt_symbol,
                        "timeframe": cfg.timeframe,
                        "expected_step_s": int(expected_step_s),
                        "rows_combined": int(rows),
                    },
                )
                drow = _blank_decision_row(ts_ms=now_ts_ms, now_iso=now_iso, bar_high=bar_high, bar_low=bar_low)
                drow["market_reason"] = mr
                _fill_position_fields(drow, position)
                _write_decision_once_per_bar(drow)
                recent_reasons.append(mr)
                time.sleep(cfg.loop_sleep_seconds)
                continue

            internal_cadence_ok = cadence_ok
            new_degraded, why = _is_degraded(recent_reasons=recent_reasons, internal_cadence_ok=internal_cadence_ok)
            if new_degraded != degraded_mode or why != degraded_why:
                degraded_mode = new_degraded
                degraded_why = why
                degraded_since_ts_ms = now_ts_ms if degraded_mode else None
                logger.warning(
                    "WATCHDOG: DEGRADED MODE change",
                    extra={
                        "degraded_mode": bool(degraded_mode),
                        "why": degraded_why,
                        "since_ts_ms": degraded_since_ts_ms or "",
                        "recent_reasons": list(recent_reasons)[-6:],
                    },
                )

            # ------------------------
            # FEATURES + MARKET STATE
            # ------------------------
            feats = compute_features(combined)

            try:
                validate_latest_features(feats)
            except Exception as e:
                mr = "features_invalid"
                logger.warning("Latest features invalid; skipping loop", extra={"symbol": ccxt_symbol, "error": repr(e)})

                try:
                    latest_row = feats.iloc[-1]
                    ts = latest_row.get("timestamp", None)
                    ft_ts_ms = int(getattr(ts, "value", 0) // 1_000_000) if ts is not None else now_ts_ms
                    ft_iso = ts.isoformat() if hasattr(ts, "isoformat") else now_iso
                    close = float(latest_row.get("close", 0.0))
                    hi = float(latest_row.get("high", close))
                    lo = float(latest_row.get("low", close))
                except Exception:
                    ft_ts_ms = now_ts_ms
                    ft_iso = now_iso
                    hi = bar_high
                    lo = bar_low

                drow = _blank_decision_row(ts_ms=ft_ts_ms, now_iso=ft_iso, bar_high=hi, bar_low=lo)
                drow["market_reason"] = mr
                if degraded_mode:
                    drow["market_reason"] = f"DEGRADED({degraded_why})::{mr}"
                _fill_position_fields(drow, position)
                _write_decision_once_per_bar(drow)
                recent_reasons.append(mr)
                time.sleep(cfg.loop_sleep_seconds)
                continue

            market_state = determine_market_state(feats, timeframe=cfg.timeframe, min_bars=cfg.min_bars)

            latest_row = feats.iloc[-1]
            latest_close = float(latest_row["close"])
            latest_high = float(latest_row.get("high", latest_close))
            latest_low = float(latest_row.get("low", latest_close))
            latest_atr = float(latest_row["atr"])

            ts = latest_row.get("timestamp", None)
            now_ts_ms = int(getattr(ts, "value", 0) // 1_000_000) if ts is not None else 0
            now_iso = ts.isoformat() if hasattr(ts, "isoformat") else ""

            position = broker.get_tracked_position(
                symbol=ccxt_symbol,
                latest_close=latest_close,
                latest_atr=latest_atr,
                atr_mult=float(ATR_MULT),
            )

            decision_row = {
                "ts_ms": now_ts_ms,
                "timestamp": now_iso,
                "bar_high": latest_high,
                "bar_low": latest_low,
                "tradable": bool(market_state.tradable),
                "trend": market_state.trend,
                "volatility": market_state.volatility,
                "market_reason": market_state.reason,
                "cooldown_remaining_bars": "",
                "position_side": "",
                "position_qty": "",
                "position_entry_price": "",
                "position_stop_price": "",
                "position_trailing_anchor_price": "",
                "unrealized_pnl_usd": "",
                "unrealized_pnl_pct": "",
                "trail_reason": "",
                "trail_new_stop": "",
                "trail_new_anchor": "",
                "entry_should_enter": "",
                "entry_side": "",
                "entry_confidence": "",
                "entry_reason": "",
                "exit_should_exit": "",
                "exit_reason": "",
            }

            if degraded_mode:
                decision_row["market_reason"] = f"DEGRADED({degraded_why})::{decision_row['market_reason']}"

            _fill_position_fields(decision_row, position)

            # ------------------------
            # IN-LOOP GUARDRAILS (block entries; still write decisions)
            # ------------------------
            halted_reason = ""
            if _exists(kill_switch_file):
                halted_reason = f"kill_switch({kill_switch_file})"
            elif _exists(halt_orders_file):
                halted_reason = f"halt_orders({halt_orders_file})"
            else:
                exceeded, reason, trades_today, pnl_today = _daily_limits_exceeded(
                    trades_csv=trades_path,
                    max_trades_per_day=max_trades_per_day,
                    max_daily_loss_usd=max_daily_loss_usd,
                    tz_name=tz_local,
                )
                if exceeded:
                    halted_reason = f"daily_limits({reason})"

            # ------------------------
            # EXIT / MANAGE POSITION
            # ------------------------
            if position is not None:
                u_usd, u_pct = broker.get_unrealized_pnl(symbol=ccxt_symbol, last_price=latest_close)
                decision_row["unrealized_pnl_usd"] = float(u_usd)
                decision_row["unrealized_pnl_pct"] = float(u_pct)

                if halted_reason:
                    decision_row["trail_reason"] = f"halted_freeze_trailing({halted_reason})"
                elif not degraded_mode:
                    new_stop, new_anchor, trail_reason = compute_trailing_stop_update(
                        position=position,
                        latest_close=latest_close,
                        latest_high=latest_high,
                        latest_low=latest_low,
                        atr=latest_atr,
                    )

                    decision_row["trail_reason"] = trail_reason
                    decision_row["trail_new_stop"] = float(new_stop) if new_stop is not None else ""
                    decision_row["trail_new_anchor"] = float(new_anchor) if new_anchor is not None else ""

                    if new_stop is not None and (
                        position.stop_price is None or float(new_stop) != float(position.stop_price)
                    ):
                        updated = broker.update_stop(
                            symbol=ccxt_symbol,
                            new_stop_price=float(new_stop),
                            new_trailing_anchor_price=float(new_anchor) if new_anchor is not None else None,
                        )
                        if updated is not None:
                            position = updated
                            _fill_position_fields(decision_row, position)
                else:
                    decision_row["trail_reason"] = "degraded_freeze_trailing"

                exit_sig = evaluate_exit(
                    position=position,
                    latest_features_row=latest_row,
                    market_state=market_state,
                    expected_step_s=int(expected_step_s),
                )

                decision_row["exit_should_exit"] = bool(exit_sig.should_exit)
                decision_row["exit_reason"] = exit_sig.reason or ""

                if exit_sig.should_exit:
                    exit_reason = exit_sig.reason or "exit"

                    exit_price = latest_close
                    if exit_reason == "stop_hit" and position.stop_price is not None:
                        exit_price = float(position.stop_price)

                    trade = broker.realize_and_close(
                        symbol=ccxt_symbol,
                        exit_price=float(exit_price),
                        reason=exit_reason,
                        exit_ts_ms=now_ts_ms if now_ts_ms > 0 else None,
                    )

                    csv_path = append_trade_csv(
                        trade=trade,
                        exchange=data_tag,
                        symbol=storage_symbol,   # STORAGE SYMBOL
                        timeframe=cfg.timeframe,
                        market_reason=market_state.reason,
                    )
                    logger.info("Trade recorded", extra={"csv_path": csv_path})

                    _write_decision_once_per_bar(decision_row)
                    time.sleep(cfg.loop_sleep_seconds)
                    continue

            # ------------------------
            # ENTRY
            # ------------------------
            if position is None:
                remaining = broker.cooldown_remaining_bars(
                    symbol=ccxt_symbol,
                    now_ts_ms=now_ts_ms,
                    expected_step_s=int(expected_step_s),
                    cooldown_bars=int(getattr(cfg, "cooldown_bars", 0)),
                )
                decision_row["cooldown_remaining_bars"] = int(remaining)

                if remaining > 0:
                    _write_decision_once_per_bar(decision_row)
                    elapsed = time.time() - loop_start
                    time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                    continue

                if degraded_mode:
                    decision_row["entry_should_enter"] = False
                    decision_row["entry_reason"] = f"blocked_by_degraded({degraded_why})"
                    _write_decision_once_per_bar(decision_row)
                    elapsed = time.time() - loop_start
                    time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                    continue

                if halted_reason:
                    decision_row["entry_should_enter"] = False
                    decision_row["entry_reason"] = f"blocked_by_halt({halted_reason})"
                    _write_decision_once_per_bar(decision_row)
                    elapsed = time.time() - loop_start
                    time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                    continue

                entry_sig = evaluate_entry(features=feats, market_state=market_state)
                decision_row["entry_should_enter"] = bool(entry_sig.should_enter)
                decision_row["entry_side"] = entry_sig.side
                decision_row["entry_confidence"] = float(entry_sig.confidence)
                decision_row["entry_reason"] = entry_sig.reason

                if entry_sig.should_enter:
                    size = min(
                        size_position(signal=entry_sig, market_state=market_state),
                        cfg.max_order_size,
                    )

                    if max_position_usd > 0.0 and latest_close > 0.0:
                        max_qty = float(max_position_usd) / float(latest_close)
                        size = min(float(size), float(max_qty))

                    if size <= 0.0:
                        decision_row["entry_should_enter"] = False
                        decision_row["entry_reason"] = "blocked_by_size_cap"
                        _write_decision_once_per_bar(decision_row)
                        elapsed = time.time() - loop_start
                        time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                        continue

                    # Entries are modeled as next-bar (prevents same-bar stop hits)
                    entry_ts_ms = now_ts_ms + step_ms

                    stop_price = compute_initial_stop(
                        side=entry_sig.side,
                        entry_price=latest_close,
                        atr=latest_atr,
                    )

                    broker.open_position(
                        symbol=ccxt_symbol,
                        side=entry_sig.side,
                        size=size,
                        entry_price=latest_close,
                        entry_ts_ms=entry_ts_ms,
                        stop_price=stop_price,
                        trailing_anchor_price=(latest_high if entry_sig.side == "LONG" else latest_low),
                    )

                    position = broker.get_tracked_position(
                        symbol=ccxt_symbol,
                        latest_close=latest_close,
                        latest_atr=latest_atr,
                        atr_mult=float(ATR_MULT),
                    )
                    _fill_position_fields(decision_row, position)

            _write_decision_once_per_bar(decision_row)

            mr = (decision_row.get("market_reason") or "").strip()
            if mr.startswith("DEGRADED(") and "::" in mr:
                _, mr2 = mr.split("::", 1)
                mr = mr2.strip()
            if mr:
                recent_reasons.append(mr)

            elapsed = time.time() - loop_start
            time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))

        except RuntimeError as e:
            # Failure injections (fetch/persist) should behave as "skip but continue"
            msg = str(e)
            if "FORCE_FETCH_FAIL=1" in msg:
                logger.warning("Market fetch failed; recording skip decision and continuing")
                drow = _blank_decision_row(ts_ms=0, now_iso="", bar_high=0.0, bar_low=0.0)
                drow["market_reason"] = "fetch_failed"
                _write_decision_once_per_bar(drow)
                recent_reasons.append("fetch_failed")
                time.sleep(cfg.loop_sleep_seconds)
                continue
            if "FORCE_PERSIST_FAIL=1" in msg:
                logger.error("Persist failed; recording skip decision and continuing")
                drow = _blank_decision_row(ts_ms=0, now_iso="", bar_high=0.0, bar_low=0.0)
                drow["market_reason"] = "persist_failed"
                _write_decision_once_per_bar(drow)
                recent_reasons.append("persist_failed")
                time.sleep(cfg.loop_sleep_seconds)
                continue
            logger.exception("Unhandled runtime error in main loop")
            time.sleep(cfg.loop_sleep_seconds)
        except KeyboardInterrupt:
            logger.info("Stopping (KeyboardInterrupt)")
            break
        except Exception:
            logger.exception("Unhandled error in main loop")
            time.sleep(cfg.loop_sleep_seconds)


if __name__ == "__main__":
    main()
