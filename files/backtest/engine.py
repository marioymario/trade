from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from files.broker.paper import PaperBroker
from files.config import TradingConfig, load_trading_config
from files.data.paths import raw_symbol_dir
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


@dataclass(frozen=True)
class BacktestResult:
    bt_exchange: str
    symbol: str
    timeframe: str
    bars_total: int
    bars_processed: int
    decisions_csv: str
    trades_csv: str


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


def _load_all_ohlcv_parquet(*, exchange: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Layout (canonical):
      data/raw/{exchange}/{SYMBOL}/{timeframe}/date=YYYY-MM-DD/bars.parquet
    """
    root: Path = raw_symbol_dir(exchange=exchange, symbol=symbol, timeframe=timeframe)
    if not root.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    files = sorted(root.glob("date=*/bars.parquet"))
    if not files:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    dfs: list[pd.DataFrame] = []
    for p in files:
        try:
            dfs.append(pd.read_parquet(p))
        except Exception:
            logger.exception("Failed reading parquet partition", extra={"path": str(p)})

    if not dfs:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    out = pd.concat(dfs, ignore_index=True)

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")

    out = out[required].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"])
    out = out.drop_duplicates(subset=["timestamp"], keep="last")
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out


def run_backtest(
    *,
    runid: str,
    cfg: Optional[TradingConfig] = None,
    start_ts_ms: Optional[int] = None,
    end_ts_ms: Optional[int] = None,
) -> BacktestResult:
    """
    Deterministic offline replay:
    - loads OHLCV from local parquet (data/raw/...)
    - reuses same strategy/broker/CSV writers as main.py
    - does NOT fetch, does NOT sleep
    - writes to exchange namespace: "{exchange}_bt_{runid}"
    """
    cfg = cfg or load_trading_config()

    expected_step_s = _timeframe_to_seconds(cfg.timeframe)

    bt_exchange = f"{cfg.ccxt_exchange}_bt_{runid}"

    logger.info(
        "Backtest starting",
        extra={
            "runid": runid,
            "bt_exchange": bt_exchange,
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "min_bars": cfg.min_bars,
        },
    )

    broker = PaperBroker(
        dry_run=cfg.dry_run,
        fee_bps=getattr(cfg, "fee_bps", 0.0),
        slippage_bps=getattr(cfg, "slippage_bps", 0.0),
    )

    all_bars = _load_all_ohlcv_parquet(
        exchange=cfg.ccxt_exchange,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
    )

    if len(all_bars) == 0:
        raise RuntimeError(
            f"No bars found under data/raw/{cfg.ccxt_exchange}/{cfg.symbol}/{cfg.timeframe}"
        )

    if start_ts_ms is not None or end_ts_ms is not None:
        ts_ms = (all_bars["timestamp"].astype("int64") // 1_000_000).astype("int64")
        mask = pd.Series(True, index=all_bars.index)
        if start_ts_ms is not None:
            mask &= ts_ms >= int(start_ts_ms)
        if end_ts_ms is not None:
            mask &= ts_ms <= int(end_ts_ms)
        all_bars = all_bars.loc[mask].reset_index(drop=True)

    if len(all_bars) == 0:
        raise RuntimeError("No bars left after applying start/end filters.")

    last_decision_ts_ms: int | None = None
    dpath_existing = decisions_csv_path(
        exchange=bt_exchange, symbol=cfg.symbol, timeframe=cfg.timeframe
    )
    last_decision_ts_ms = _read_last_ts_ms_from_decisions_csv(dpath_existing)
    if last_decision_ts_ms is not None:
        logger.info(
            "Decision dedupe initialized from existing CSV",
            extra={"csv_path": dpath_existing, "last_decision_ts_ms": int(last_decision_ts_ms)},
        )

    def _write_decision_once_per_bar(decision_row: dict) -> str | None:
        nonlocal last_decision_ts_ms

        ts_ms = decision_row.get("ts_ms", 0) or 0
        try:
            ts_ms = int(ts_ms)
        except Exception:
            ts_ms = 0

        if ts_ms <= 0:
            return None

        if last_decision_ts_ms is not None and ts_ms <= last_decision_ts_ms:
            return None

        dpath = append_decision_csv(
            decision=decision_row,
            exchange=bt_exchange,
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
        )
        last_decision_ts_ms = ts_ms
        return dpath

    tail_n = max(cfg.min_bars, 200)

    bars_processed = 0
    last_decisions_path: str = ""
    last_trades_path: str = ""

    for i in range(len(all_bars)):
        start_i = max(0, i - tail_n + 1)
        market_data = all_bars.iloc[start_i : i + 1].reset_index(drop=True)

        if len(market_data) < cfg.min_bars:
            continue

        feats = compute_features(market_data)

        try:
            validate_latest_features(feats)
        except Exception:
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

        # ---- Pending-entry guard (must match LIVE) ----
        pending_entry = False
        if (
            position is not None
            and position.entry_ts_ms is not None
            and now_ts_ms > 0
            and int(now_ts_ms) < int(position.entry_ts_ms)
        ):
            pending_entry = True

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

        _fill_position_fields(decision_row, position)

        if pending_entry:
            p = _write_decision_once_per_bar(decision_row)
            if p:
                last_decisions_path = p
            bars_processed += 1
            continue

        # ------------------------
        # EXIT / MANAGE POSITION
        # ------------------------
        if position is not None:
            u_usd, u_pct = broker.get_unrealized_pnl(symbol=cfg.symbol, last_price=latest_close)
            decision_row["unrealized_pnl_usd"] = float(u_usd)
            decision_row["unrealized_pnl_pct"] = float(u_pct)

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

                last_trades_path = append_trade_csv(
                    trade=trade,
                    exchange=bt_exchange,
                    symbol=cfg.symbol,
                    timeframe=cfg.timeframe,
                    market_reason=market_state.reason,
                )

                p = _write_decision_once_per_bar(decision_row)
                if p:
                    last_decisions_path = p

                bars_processed += 1
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

            if remaining <= 0:
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

                    if i + 1 < len(all_bars):
                        nxt = all_bars.iloc[i + 1]["timestamp"]
                        next_ts_ms = int(getattr(nxt, "value", 0) // 1_000_000)
                        entry_ts_ms = next_ts_ms if next_ts_ms > 0 else (now_ts_ms + expected_step_s * 1000)
                    else:
                        entry_ts_ms = now_ts_ms + expected_step_s * 1000

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
                        trailing_anchor_price=(
                            latest_high if entry_sig.side == "LONG" else latest_low
                        ),
                    )

                    position = broker.get_tracked_position(
                        symbol=cfg.symbol,
                        latest_close=latest_close,
                        latest_atr=latest_atr,
                        atr_mult=float(ATR_MULT),
                    )
                    _fill_position_fields(decision_row, position)

        p = _write_decision_once_per_bar(decision_row)
        if p:
            last_decisions_path = p

        bars_processed += 1

    decisions_out = decisions_csv_path(exchange=bt_exchange, symbol=cfg.symbol, timeframe=cfg.timeframe)
    trades_out = str(
        Path("data")
        / "processed"
        / "trades"
        / bt_exchange.lower().replace(" ", "_")
        / cfg.symbol.strip().upper().replace("/", "_").replace(":", "_").replace(" ", "_")
        / cfg.timeframe.strip().lower().replace(" ", "")
        / "trades.csv"
    )

    logger.info(
        "Backtest complete",
        extra={
            "runid": runid,
            "bt_exchange": bt_exchange,
            "decisions_csv": decisions_out,
            "trades_csv": trades_out,
            "bars_total": len(all_bars),
            "bars_processed": bars_processed,
        },
    )

    return BacktestResult(
        bt_exchange=bt_exchange,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        bars_total=len(all_bars),
        bars_processed=bars_processed,
        decisions_csv=decisions_out,
        trades_csv=trades_out,
    )
