# files/backtest/engine.py
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from files.broker.paper import PaperBroker
from files.config import TradingConfig, load_trading_config
from files.data.decisions import append_decision_csv, decisions_csv_path
from files.data.features import compute_features, validate_latest_features
from files.data.paths import raw_symbol_dir, trades_csv_path
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


def _storage_symbol(symbol: str) -> str:
    """
    Normalize symbol for filesystem + processed CSV identity:
      - BTC/USD -> BTC_USD
    """
    return symbol.strip().upper().replace("/", "_")


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
    - reads from storage namespace: cfg.data_tag
    - writes to exchange namespace: "{data_tag}_bt_{runid}"

    IMPORTANT behavior for equivalence:
    - If start_ts_ms is provided, we keep the broker FLAT until now_ts_ms >= start_ts_ms.
      (We still load warmup bars prior to start_ts_ms so indicators/features are valid.)
      This prevents backtest from carrying a pre-window position into the overlap.
    """
    cfg = cfg or load_trading_config()
    data_tag = cfg.data_tag

    ccxt_symbol = cfg.symbol
    storage_symbol = _storage_symbol(cfg.symbol)

    expected_step_s = _timeframe_to_seconds(cfg.timeframe)

    # Backtest output namespace is derived from storage tag (NOT fetch source)
    bt_exchange = f"{data_tag}_bt_{runid}"

    trade_start_ts_ms: Optional[int] = int(start_ts_ms) if start_ts_ms is not None else None

    logger.info(
        "Backtest starting",
        extra={
            "runid": runid,
            "ccxt_exchange": cfg.ccxt_exchange,  # fetch source (metadata)
            "data_tag": data_tag,  # storage namespace (read root)
            "bt_exchange": bt_exchange,  # backtest output namespace
            "symbol": ccxt_symbol,
            "storage_symbol": storage_symbol,
            "timeframe": cfg.timeframe,
            "min_bars": cfg.min_bars,
            "trade_start_ts_ms": trade_start_ts_ms,
            "end_ts_ms": int(end_ts_ms) if end_ts_ms is not None else None,
        },
    )

    broker = PaperBroker(
        dry_run=cfg.dry_run,
        fee_bps=getattr(cfg, "fee_bps", 0.0),
        slippage_bps=getattr(cfg, "slippage_bps", 0.0),
    )

    # IMPORTANT: read raw bars from DATA_TAG storage namespace, using STORAGE SYMBOL
    all_bars = _load_all_ohlcv_parquet(exchange=data_tag, symbol=storage_symbol, timeframe=cfg.timeframe)

    if len(all_bars) == 0:
        raise RuntimeError(
            f"No bars found under data/raw/{data_tag}/{storage_symbol}/{cfg.timeframe} "
            f"(DATA_TAG={data_tag}, CCXT_EXCHANGE={cfg.ccxt_exchange})"
        )

    ts_ms_all = (all_bars["timestamp"].astype("int64") // 1_000_000).astype("int64")

    # If trade_start_ts_ms is set, include a warmup prefix before it, but do not trade until >= trade_start_ts_ms.
    if trade_start_ts_ms is not None:
        idxs = all_bars.index[ts_ms_all >= int(trade_start_ts_ms)].tolist()
        if not idxs:
            raise RuntimeError(f"START_TS_MS={trade_start_ts_ms} is after the newest bar in raw data.")
        first_trade_i = int(idxs[0])

        # Warmup: include enough history to compute features at trade start.
        warmup_bars = max(int(cfg.min_bars), 50) + 5
        start_i0 = max(0, first_trade_i - warmup_bars)
        all_bars = all_bars.iloc[start_i0:].reset_index(drop=True)
        ts_ms_all = (all_bars["timestamp"].astype("int64") // 1_000_000).astype("int64")

    # Apply end filter after warmup expansion (so we keep warmup, but can still cap the replay window).
    if end_ts_ms is not None:
        mask_end = ts_ms_all <= int(end_ts_ms)
        all_bars = all_bars.loc[mask_end].reset_index(drop=True)
        ts_ms_all = (all_bars["timestamp"].astype("int64") // 1_000_000).astype("int64")

    if len(all_bars) == 0:
        raise RuntimeError("No bars left after applying filters.")

    # Restart-safe decision dedupe for bt output namespace
    dpath_existing = decisions_csv_path(exchange=bt_exchange, symbol=storage_symbol, timeframe=cfg.timeframe)
    last_decision_ts_ms: int | None = _read_last_ts_ms_from_decisions_csv(dpath_existing)
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
            symbol=storage_symbol,   # STORAGE SYMBOL (e.g. BTC_USD)
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

        # If configured, hold broker flat until trade_start_ts_ms.
        allow_trading = True
        if trade_start_ts_ms is not None and now_ts_ms > 0 and int(now_ts_ms) < int(trade_start_ts_ms):
            allow_trading = False

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

        # If we're not allowed to trade yet, we force a flat snapshot and write the row.
        if not allow_trading:
            _fill_position_fields(decision_row, None)
            p = _write_decision_once_per_bar(decision_row)
            if p:
                last_decisions_path = p
            bars_processed += 1
            continue

        # ---- Pending-entry guard (must match LIVE) ----
        pending_entry = False
        if (
            position is not None
            and position.entry_ts_ms is not None
            and now_ts_ms > 0
            and int(now_ts_ms) < int(position.entry_ts_ms)
        ):
            pending_entry = True

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
            u_usd, u_pct = broker.get_unrealized_pnl(symbol=ccxt_symbol, last_price=latest_close)
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

            decision_row["exit_should_exit"] = bool(exit_sig.should_exit)
            decision_row["exit_reason"] = exit_sig.reason or ""

            if exit_sig.should_exit:
                exit_reason = exit_sig.reason or "exit"

                # Phase 2A stop-through is BACKTEST ONLY. (PnL may differ; lifecycle should match)
                exit_price = latest_close
                if exit_reason == "stop_hit" and position.stop_price is not None:
                    bar_open = float(market_data.iloc[-1].get("open", latest_close))
                    stop_px = float(position.stop_price)
                    exit_price = min(bar_open, stop_px) if position.side == "LONG" else max(bar_open, stop_px)

                trade = broker.realize_and_close(
                    symbol=ccxt_symbol,
                    exit_price=float(exit_price),
                    reason=exit_reason,
                    exit_ts_ms=now_ts_ms if now_ts_ms > 0 else None,
                )

                last_trades_path = append_trade_csv(
                    trade=trade,
                    exchange=bt_exchange,
                    symbol=storage_symbol,   # STORAGE SYMBOL
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
                symbol=ccxt_symbol,
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

                    # Entries are modeled as next-bar (prevents same-bar stop hits)
                    if i + 1 < len(all_bars):
                        nxt = all_bars.iloc[i + 1]["timestamp"]
                        next_ts_ms = int(getattr(nxt, "value", 0) // 1_000_000)
                        entry_ts_ms = next_ts_ms if next_ts_ms > 0 else (now_ts_ms + int(expected_step_s * 1000))
                    else:
                        entry_ts_ms = now_ts_ms + int(expected_step_s * 1000)

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

        p = _write_decision_once_per_bar(decision_row)
        if p:
            last_decisions_path = p

        bars_processed += 1

    decisions_out = decisions_csv_path(exchange=bt_exchange, symbol=storage_symbol, timeframe=cfg.timeframe)
    trades_out = str(trades_csv_path(exchange=bt_exchange, symbol=storage_symbol, timeframe=cfg.timeframe))

    logger.info(
        "Backtest complete",
        extra={
            "runid": runid,
            "ccxt_exchange": cfg.ccxt_exchange,
            "data_tag": data_tag,
            "bt_exchange": bt_exchange,
            "decisions_csv": decisions_out,
            "trades_csv": trades_out,
            "bars_total": len(all_bars),
            "bars_processed": bars_processed,
            "last_decisions_path": last_decisions_path,
            "last_trades_path": last_trades_path,
        },
    )

    return BacktestResult(
        bt_exchange=bt_exchange,
        symbol=ccxt_symbol,
        timeframe=cfg.timeframe,
        bars_total=len(all_bars),
        bars_processed=bars_processed,
        decisions_csv=decisions_out,
        trades_csv=trades_out,
    )

