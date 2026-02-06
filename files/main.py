from __future__ import annotations

import csv
import os
import time
from collections import deque

import pandas as pd

from files.broker.paper import PaperBroker
from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.features import compute_features, validate_latest_features
from files.data.trades import append_trade_csv
from files.data.decisions import append_decision_csv, decisions_csv_path
from files.strategy.filters import determine_market_state
from files.strategy.rules import (
    evaluate_entry,
    evaluate_exit,
    size_position,
    compute_initial_stop,
    compute_trailing_stop_update,
    ATR_MULT,
)
from files.utils.logger import get_logger

logger = get_logger(__name__)


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
        # Take last tail_n then last window_k
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


def main() -> None:
    cfg = load_trading_config()

    logger.info("🚀 Trading system starting")
    logger.info(
        "Trading config loaded",
        extra={
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "loop_sleep_seconds": cfg.loop_sleep_seconds,
            "dry_run": cfg.dry_run,
            "ccxt_exchange": cfg.ccxt_exchange,
            "max_order_size": cfg.max_order_size,
            "min_bars": cfg.min_bars,
            "fee_bps": getattr(cfg, "fee_bps", None),
            "slippage_bps": getattr(cfg, "slippage_bps", None),
            "cooldown_bars": getattr(cfg, "cooldown_bars", None),
        },
    )

    broker = PaperBroker(
        dry_run=cfg.dry_run,
        fee_bps=getattr(cfg, "fee_bps", 0.0),
        slippage_bps=getattr(cfg, "slippage_bps", 0.0),
    )

    expected_step_s = _timeframe_to_seconds(cfg.timeframe)
    step_ms = int(expected_step_s * 1000)

    # ---- Restart-safe decision dedupe: seed last_decision_ts_ms from existing CSV ----
    last_decision_ts_ms: int | None = None
    dpath_existing = decisions_csv_path(
        exchange=cfg.ccxt_exchange, symbol=cfg.symbol, timeframe=cfg.timeframe
    )
    last_decision_ts_ms = _read_last_ts_ms_from_decisions_csv(dpath_existing)
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
            exchange=cfg.ccxt_exchange,
            symbol=cfg.symbol,
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

    while True:
        loop_start = time.time()
        try:
            # ------------------------
            # FETCH + PERSIST
            # ------------------------
            fetched = fetch_market_data(
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
                limit=int(fetch_limit),
                min_bars_warn=cfg.min_bars,
                ccxt_exchange=cfg.ccxt_exchange,
            )
            fetched = _normalize_df(fetched)
            fetched = _drop_in_progress_last_bar_if_safe(fetched, min_bars=cfg.min_bars)

            append_ohlcv_parquet(
                df=fetched,
                exchange=cfg.ccxt_exchange,
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
            )

            # ------------------------
            # LOAD STORE + MERGE (robust)
            # ------------------------
            store_df = load_recent_ohlcv_parquet(
                exchange=cfg.ccxt_exchange,
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
                tail_n=int(store_tail_n),
            )
            store_df = _normalize_df(store_df)
            store_df = _drop_in_progress_last_bar_if_safe(store_df, min_bars=cfg.min_bars)

            combined = pd.concat([store_df, fetched], ignore_index=True)
            combined = _normalize_df(combined)

            # Keep recent tail (with headroom), then drop last if safe
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

            # Bar identity for skip-recording and watchdog markers
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

            # Always have current position available for recording
            position = broker.get_tracked_position(
                symbol=cfg.symbol,
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
                        "symbol": cfg.symbol,
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

            # ---- v0.3 watchdog: evaluate degraded_mode BEFORE features/trading ----
            internal_cadence_ok = cadence_ok  # already True here, but kept for contract clarity
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
                logger.warning(
                    "Latest features invalid; skipping loop",
                    extra={"symbol": cfg.symbol, "error": repr(e)},
                )

                # record a decision at the features tail timestamp if available
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

            market_state = determine_market_state(
                feats,
                timeframe=cfg.timeframe,
                min_bars=cfg.min_bars,
            )

            latest_row = feats.iloc[-1]
            latest_close = float(latest_row["close"])
            latest_high = float(latest_row.get("high", latest_close))
            latest_low = float(latest_row.get("low", latest_close))
            latest_atr = float(latest_row["atr"])

            ts = latest_row.get("timestamp", None)
            now_ts_ms = int(getattr(ts, "value", 0) // 1_000_000) if ts is not None else 0
            now_iso = ts.isoformat() if hasattr(ts, "isoformat") else ""

            position = broker.get_tracked_position(
                symbol=cfg.symbol,
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
            # EXIT / MANAGE POSITION
            # ------------------------
            if position is not None:
                u_usd, u_pct = broker.get_unrealized_pnl(symbol=cfg.symbol, last_price=latest_close)
                decision_row["unrealized_pnl_usd"] = float(u_usd)
                decision_row["unrealized_pnl_pct"] = float(u_pct)

                # v0.3 watchdog behavior: optionally freeze trailing stop updates when degraded.
                if not degraded_mode:
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
                            symbol=cfg.symbol,
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
                        symbol=cfg.symbol,
                        exit_price=float(exit_price),
                        reason=exit_reason,
                        exit_ts_ms=now_ts_ms if now_ts_ms > 0 else None,
                    )

                    csv_path = append_trade_csv(
                        trade=trade,
                        exchange=cfg.ccxt_exchange,
                        symbol=cfg.symbol,
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
                    symbol=cfg.symbol,
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

                # v0.3 watchdog behavior: block new entries while degraded
                if degraded_mode:
                    decision_row["entry_should_enter"] = False
                    decision_row["entry_reason"] = f"blocked_by_degraded({degraded_why})"
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
                    size = min(size_position(signal=entry_sig, market_state=market_state), cfg.max_order_size)

                    # Model entries as next-bar to prevent same-bar stop hits
                    entry_ts_ms = now_ts_ms + step_ms

                    stop_price = compute_initial_stop(
                        side=entry_sig.side,
                        entry_price=latest_close,
                        atr=latest_atr,
                    )

                    broker.open_position(
                        symbol=cfg.symbol,
                        side=entry_sig.side,
                        size=size,
                        entry_price=latest_close,
                        entry_ts_ms=entry_ts_ms,
                        stop_price=stop_price,
                        trailing_anchor_price=(latest_high if entry_sig.side == "LONG" else latest_low),
                    )

                    position = broker.get_tracked_position(
                        symbol=cfg.symbol,
                        latest_close=latest_close,
                        latest_atr=latest_atr,
                        atr_mult=float(ATR_MULT),
                    )
                    _fill_position_fields(decision_row, position)

            _write_decision_once_per_bar(decision_row)

            # Update watchdog rolling window with the "reason" we recorded this bar
            # (strip DEPRECATED marker prefix when counting).
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
