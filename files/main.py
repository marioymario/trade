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
from files.core.types import EntrySignal
from files.data.decisions import append_decision_csv, decisions_csv_path
from files.data.features import compute_features, validate_latest_features
from files.data.market import fetch_market_data, MarketFetchError
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.trades import append_trade_csv
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
    decision_row["position_stop_price"] = float(position.stop_price) if position.stop_price is not None else ""
    decision_row["position_trailing_anchor_price"] = (
        float(position.trailing_anchor_price)
        if getattr(position, "trailing_anchor_price", None) is not None
        else ""
    )


def _read_last_ts_ms_from_decisions_csv(path: str) -> int | None:
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
        logger.warning("Failed to read last ts_ms from decisions CSV", extra={"path": path, "error": repr(e)})
        return None


def _read_tail_market_reasons(path: str, *, tail_n: int = 50, window_k: int = 6) -> list[str]:
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
        logger.warning("Failed to read tail market_reasons from decisions CSV", extra={"path": path, "error": repr(e)})
        return []


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
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
    if df is None:
        return df
    if len(df) >= (min_bars + 1):
        return df.iloc[:-1].reset_index(drop=True)
    return df


def _blank_decision_row(*, ts_ms: int, now_iso: str, bar_high: float, bar_low: float) -> dict:
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
        "entry_blocked_reason": "",
        "exit_should_exit": "",
        "exit_reason": "",
    }


def _is_degraded(*, recent_reasons: deque[str], internal_cadence_ok: bool) -> tuple[bool, str]:
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


def _parse_bool_env(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return bool(default)
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off", ""):
        return False
    return bool(default)


def _exists(path: str) -> bool:
    try:
        return bool(path) and os.path.exists(path)
    except Exception:
        return False


def main() -> None:
    cfg = load_trading_config()

    data_tag = cfg.data_tag
    ccxt_symbol = cfg.symbol
    storage_symbol = _storage_symbol(cfg.symbol)

    flags_dir = os.environ.get("FLAGS_DIR", f"{os.path.expanduser('~')}/trade_flags").strip()
    kill_switch_file = os.environ.get("KILL_SWITCH_FILE", "/tmp/TRADING_STOP").strip()
    halt_orders_file = os.environ.get("HALT_ORDERS_FILE", "").strip()
    arm_file = os.environ.get("ARM_FILE", "").strip() or f"{flags_dir}/ARM"

    broker_kind = os.environ.get("BROKER", "paper").strip().lower()  # paper | alpaca

    test_hooks_enabled = _parse_bool_env("TEST_HOOKS_ENABLED", False)
    force_entry_signal_once = test_hooks_enabled and _parse_bool_env("FORCE_ENTRY_SIGNAL_ONCE", False)
    force_exit_signal_once = test_hooks_enabled and _parse_bool_env("FORCE_EXIT_SIGNAL_ONCE", False)
    force_cooldown_block_once = test_hooks_enabled and _parse_bool_env("FORCE_COOLDOWN_BLOCK_ONCE", False)
    force_cooldown_bars = int(_parse_float_env("FORCE_COOLDOWN_BARS", 0.0)) if test_hooks_enabled else 0

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
            "FLAGS_DIR": flags_dir,
            "KILL_SWITCH_FILE": kill_switch_file,
            "HALT_ORDERS_FILE": halt_orders_file,
            "ARM_FILE": arm_file,
            "TEST_HOOKS_ENABLED": bool(test_hooks_enabled),
            "FORCE_ENTRY_SIGNAL_ONCE": bool(force_entry_signal_once),
            "FORCE_EXIT_SIGNAL_ONCE": bool(force_exit_signal_once),
            "FORCE_COOLDOWN_BLOCK_ONCE": bool(force_cooldown_block_once),
            "FORCE_COOLDOWN_BARS": int(force_cooldown_bars),
        },
    )

    require_armed_for_entries = True

    if broker_kind == "alpaca":
        from files.broker.alpaca import AlpacaBroker

        inner = AlpacaBroker()
    else:
        inner = PaperBroker(
            dry_run=cfg.dry_run,
            fee_bps=getattr(cfg, "fee_bps", 0.0),
            slippage_bps=getattr(cfg, "slippage_bps", 0.0),
        )

    block_entries_on_dry_run = (broker_kind == "alpaca")

    broker = GuardedBroker(
        inner,
        require_arm_for_entries=require_armed_for_entries,
        block_entries_on_dry_run=block_entries_on_dry_run,
    )

    expected_step_s = _timeframe_to_seconds(cfg.timeframe)
    step_ms = int(expected_step_s * 1000)

    dpath_existing = decisions_csv_path(exchange=data_tag, symbol=storage_symbol, timeframe=cfg.timeframe)
    last_decision_ts_ms: int | None = _read_last_ts_ms_from_decisions_csv(dpath_existing)
    if last_decision_ts_ms is not None:
        logger.info(
            "Decision dedupe initialized from existing CSV",
            extra={"csv_path": dpath_existing, "last_decision_ts_ms": int(last_decision_ts_ms)},
        )

    recent_reasons: deque[str] = deque(maxlen=12)
    for r in _read_tail_market_reasons(dpath_existing, tail_n=80, window_k=6):
        recent_reasons.append(r)

    degraded_mode = False
    degraded_why = ""
    degraded_since_ts_ms: int | None = None

    test_force_entry_used = False
    test_force_exit_used = False
    test_force_cooldown_used = False

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
            symbol=storage_symbol,
            timeframe=cfg.timeframe,
        )
        last_decision_ts_ms = ts_ms
        logger.info("Decision recorded", extra={"csv_path": dpath})

    fetch_limit = max(cfg.min_bars, 200) + 1
    tail_n = max(cfg.min_bars, 200) + 1
    store_tail_n = max(5000, tail_n)

    logger.info(
        "LIVE headroom",
        extra={"fetch_limit": int(fetch_limit), "tail_n": int(tail_n), "store_tail_n": int(store_tail_n)},
    )

    while True:
        loop_start = time.time()
        try:
            try:
                fetched = fetch_market_data(
                    symbol=ccxt_symbol,
                    timeframe=cfg.timeframe,
                    limit=int(fetch_limit),
                    min_bars_warn=cfg.min_bars,
                    ccxt_exchange=cfg.ccxt_exchange,
                )
            except MarketFetchError as e:
                mr = "fetch_failed"
                logger.warning(
                    "Market fetch failed; skipping loop",
                    extra={"symbol": ccxt_symbol, "timeframe": cfg.timeframe, "error": repr(e)},
                )

                now_ts_ms = 0
                now_iso = ""
                bar_high = 0.0
                bar_low = 0.0
                position = broker.get_tracked_position(symbol=ccxt_symbol)

                drow = _blank_decision_row(ts_ms=now_ts_ms, now_iso=now_iso, bar_high=bar_high, bar_low=bar_low)
                drow["market_reason"] = mr
                _fill_position_fields(drow, position)
                _write_decision_once_per_bar(drow)
                recent_reasons.append(mr)
                time.sleep(cfg.loop_sleep_seconds)
                continue

            fetched = _normalize_df(fetched)
            fetched = _drop_in_progress_last_bar_if_safe(fetched, min_bars=cfg.min_bars)

            append_ohlcv_parquet(df=fetched, exchange=data_tag, symbol=storage_symbol, timeframe=cfg.timeframe)

            store_df = load_recent_ohlcv_parquet(
                exchange=data_tag,
                symbol=storage_symbol,
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

            rows = len(combined)
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

            if now_ts_ms > 0 and last_decision_ts_ms is not None and now_ts_ms <= int(last_decision_ts_ms):
                logger.warning(
                    "SKIP: already-processed bar (restart-safe idempotency)",
                    extra={"now_ts_ms": int(now_ts_ms), "last_decision_ts_ms": int(last_decision_ts_ms)},
                )
                elapsed = time.time() - loop_start
                time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                continue

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
                    "Cadence check failed; skipping loop",
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

            new_degraded, why = _is_degraded(recent_reasons=recent_reasons, internal_cadence_ok=cadence_ok)
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

            feats = compute_features(combined)

            try:
                validate_latest_features(feats)
            except Exception as e:
                mr = "features_invalid"
                logger.warning("Latest features invalid; skipping loop", extra={"symbol": ccxt_symbol, "error": repr(e)})
                drow = _blank_decision_row(ts_ms=now_ts_ms, now_iso=now_iso, bar_high=bar_high, bar_low=bar_low)
                drow["market_reason"] = f"DEGRADED({degraded_why})::{mr}" if degraded_mode else mr
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

            if now_ts_ms > 0 and last_decision_ts_ms is not None and now_ts_ms <= int(last_decision_ts_ms):
                logger.warning(
                    "SKIP: already-processed bar (restart-safe idempotency)",
                    extra={"now_ts_ms": int(now_ts_ms), "last_decision_ts_ms": int(last_decision_ts_ms)},
                )
                elapsed = time.time() - loop_start
                time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                continue

            position = broker.get_tracked_position(
                symbol=ccxt_symbol,
                latest_close=latest_close,
                latest_atr=latest_atr,
                atr_mult=float(ATR_MULT),
            )

            write_eligible_bar = (now_ts_ms > 0) and (
                last_decision_ts_ms is None or now_ts_ms > int(last_decision_ts_ms)
            )

            decision_row = {
                "ts_ms": now_ts_ms,
                "timestamp": now_iso,
                "bar_high": latest_high,
                "bar_low": latest_low,
                "tradable": bool(market_state.tradable),
                "trend": market_state.trend,
                "volatility": market_state.volatility,
                "market_reason": f"DEGRADED({degraded_why})::{market_state.reason}" if degraded_mode else market_state.reason,
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
                "entry_blocked_reason": "",
                "exit_should_exit": "",
                "exit_reason": "",
            }
            _fill_position_fields(decision_row, position)

            halted_for_trailing = False
            halt_detail = ""
            if _exists(kill_switch_file):
                halted_for_trailing = True
                halt_detail = f"STOP_BLOCK(kill_switch={kill_switch_file})"
            elif _exists(halt_orders_file):
                halted_for_trailing = True
                halt_detail = f"HALT_BLOCK(halt_orders={halt_orders_file})"

            if position is not None:
                decision_row["entry_should_enter"] = ""
                decision_row["entry_side"] = ""
                decision_row["entry_confidence"] = ""
                decision_row["entry_reason"] = ""
                decision_row["entry_blocked_reason"] = ""

                u_usd, u_pct = broker.get_unrealized_pnl(symbol=ccxt_symbol, last_price=latest_close)
                decision_row["unrealized_pnl_usd"] = float(u_usd)
                decision_row["unrealized_pnl_pct"] = float(u_pct)

                cur_stop = float(position.stop_price) if position.stop_price is not None else None
                cur_anchor = (
                    float(getattr(position, "trailing_anchor_price", 0.0))
                    if getattr(position, "trailing_anchor_price", None) is not None
                    else None
                )

                if halted_for_trailing:
                    decision_row["trail_reason"] = f"halted_freeze_trailing({halt_detail})"
                    decision_row["trail_new_stop"] = float(cur_stop) if cur_stop is not None else ""
                    decision_row["trail_new_anchor"] = float(cur_anchor) if cur_anchor is not None else ""
                elif degraded_mode:
                    decision_row["trail_reason"] = f"degraded_freeze_trailing({degraded_why})"
                    decision_row["trail_new_stop"] = float(cur_stop) if cur_stop is not None else ""
                    decision_row["trail_new_anchor"] = float(cur_anchor) if cur_anchor is not None else ""
                else:
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

                exit_sig = evaluate_exit(
                    position=position,
                    latest_features_row=latest_row,
                    market_state=market_state,
                    expected_step_s=int(expected_step_s),
                )

                if write_eligible_bar and force_exit_signal_once and (not test_force_exit_used):
                    decision_row["exit_should_exit"] = True
                    decision_row["exit_reason"] = "TEST_FORCE_EXIT_SIGNAL_ONCE"
                    test_force_exit_used = True
                    logger.warning("TEST: forcing exit signal once", extra={"reason": "TEST_FORCE_EXIT_SIGNAL_ONCE"})
                else:
                    decision_row["exit_should_exit"] = bool(exit_sig.should_exit)
                    decision_row["exit_reason"] = exit_sig.reason or ""

                if decision_row["exit_should_exit"]:
                    exit_reason = decision_row["exit_reason"] or "exit"
                    exit_price = (
                        float(position.stop_price)
                        if (exit_reason == "stop_hit" and position.stop_price is not None)
                        else latest_close
                    )

                    trade = broker.realize_and_close(
                        symbol=ccxt_symbol,
                        exit_price=float(exit_price),
                        reason=exit_reason,
                        exit_ts_ms=now_ts_ms if now_ts_ms > 0 else None,
                    )
                    csv_path = append_trade_csv(
                        trade=trade,
                        exchange=data_tag,
                        symbol=storage_symbol,
                        timeframe=cfg.timeframe,
                        market_reason=market_state.reason,
                    )
                    logger.info("Trade recorded", extra={"csv_path": csv_path})

                    _write_decision_once_per_bar(decision_row)
                    time.sleep(cfg.loop_sleep_seconds)
                    continue

                _write_decision_once_per_bar(decision_row)
                elapsed = time.time() - loop_start
                time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                continue

            remaining = broker.cooldown_remaining_bars(
                symbol=ccxt_symbol,
                now_ts_ms=now_ts_ms,
                expected_step_s=int(expected_step_s),
                cooldown_bars=int(getattr(cfg, "cooldown_bars", 0)),
            )

            if write_eligible_bar and force_cooldown_block_once and (not test_force_cooldown_used):
                cb = int(force_cooldown_bars) if int(force_cooldown_bars) > 0 else int(getattr(cfg, "cooldown_bars", 0))
                cb = cb if cb > 0 else 3
                remaining = max(int(remaining), int(cb))
                test_force_cooldown_used = True
                logger.warning(
                    "TEST: forcing cooldown block once",
                    extra={"forced_remaining": int(remaining), "cooldown_bars": int(cb)},
                )

            decision_row["cooldown_remaining_bars"] = int(remaining)

            entry_sig = evaluate_entry(features=feats, market_state=market_state)

            if write_eligible_bar and force_entry_signal_once and (not test_force_entry_used):
                effective_entry_sig = EntrySignal(
                    should_enter=True,
                    side="LONG",
                    confidence=0.99,
                    reason="TEST_FORCE_ENTRY_SIGNAL_ONCE",
                )
                test_force_entry_used = True
                logger.warning("TEST: forcing entry signal once", extra={"side": "LONG", "confidence": 0.99})
            else:
                effective_entry_sig = entry_sig

            decision_row["entry_should_enter"] = bool(effective_entry_sig.should_enter)
            decision_row["entry_side"] = effective_entry_sig.side
            decision_row["entry_confidence"] = float(effective_entry_sig.confidence)
            decision_row["entry_reason"] = effective_entry_sig.reason
            decision_row["entry_blocked_reason"] = ""

            if remaining > 0:
                decision_row["entry_blocked_reason"] = f"COOLDOWN_BLOCK(remaining={int(remaining)})"
                _write_decision_once_per_bar(decision_row)
                elapsed = time.time() - loop_start
                time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                continue

            if decision_row["entry_should_enter"]:
                size = min(size_position(signal=effective_entry_sig, market_state=market_state), cfg.max_order_size)

                if float(size) <= 0.0:
                    decision_row["entry_blocked_reason"] = "SIZE_BLOCK(size<=0)"
                    _write_decision_once_per_bar(decision_row)
                    elapsed = time.time() - loop_start
                    time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                    continue

                if degraded_mode:
                    decision_row["entry_blocked_reason"] = f"DEGRADED_BLOCK({degraded_why})"
                else:
                    blocked_reason = broker.open_position(
                        symbol=ccxt_symbol,
                        side=effective_entry_sig.side,
                        size=float(size),
                        entry_price=float(latest_close),
                        entry_ts_ms=int(now_ts_ms + step_ms),
                        stop_price=compute_initial_stop(
                            side=effective_entry_sig.side,
                            entry_price=latest_close,
                            atr=latest_atr,
                        ),
                        trailing_anchor_price=(latest_high if effective_entry_sig.side == "LONG" else latest_low),
                    )
                    if blocked_reason:
                        decision_row["entry_blocked_reason"] = str(blocked_reason)

                if decision_row["entry_blocked_reason"]:
                    _write_decision_once_per_bar(decision_row)
                    elapsed = time.time() - loop_start
                    time.sleep(max(cfg.loop_sleep_seconds - elapsed, 0.0))
                    continue

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

        except KeyboardInterrupt:
            logger.info("Stopping (KeyboardInterrupt)")
            break
        except Exception:
            logger.exception("Unhandled error in main loop")
            time.sleep(cfg.loop_sleep_seconds)


if __name__ == "__main__":
    main()
