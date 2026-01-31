from __future__ import annotations

import time
import pandas as pd

from files.broker.paper import PaperBroker
from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.features import compute_features, validate_latest_features
from files.data.trades import append_trade_csv
from files.data.decisions import append_decision_csv
from files.strategy.filters import determine_market_state
from files.strategy.rules import (
    evaluate_entry,
    evaluate_exit,
    size_position,
    compute_initial_stop,
    compute_trailing_stop,
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
    """
    Protects you from partial exchange outages / degraded feeds.
    Consider the feed 'cadence_ok' if the median timestamp step matches
    the expected bar step within a small tolerance.
    """
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

    # Decision de-dupe: only write once per bar timestamp
    last_decision_ts_ms: int | None = None

    def _write_decision_once_per_bar(decision_row: dict) -> None:
        nonlocal last_decision_ts_ms

        ts_ms = decision_row.get("ts_ms", 0) or 0
        try:
            ts_ms = int(ts_ms)
        except Exception:
            ts_ms = 0

        if ts_ms <= 0:
            return

        if last_decision_ts_ms is not None and ts_ms == last_decision_ts_ms:
            return

        dpath = append_decision_csv(
            decision=decision_row,
            exchange=cfg.ccxt_exchange,
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
        )
        last_decision_ts_ms = ts_ms
        logger.info("Decision recorded", extra={"csv_path": dpath})

    while True:
        loop_start = time.time()
        try:
            # 1) Fetch from source (best effort)
            fetched = fetch_market_data(
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
                limit=max(cfg.min_bars, 200),
                min_bars_warn=cfg.min_bars,
                ccxt_exchange=cfg.ccxt_exchange,
            )

            # 2) Persist what we got
            append_ohlcv_parquet(
                df=fetched,
                exchange=cfg.ccxt_exchange,
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
            )

            # 3) Load stable “truth” for strategy from local storage
            market_data = load_recent_ohlcv_parquet(
                exchange=cfg.ccxt_exchange,
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
                tail_n=max(cfg.min_bars, 200),
            )
            rows = len(market_data)

            # 4) Hard gates before computing features
            has_enough_bars = rows >= cfg.min_bars
            cadence_ok = _cadence_ok(market_data, expected_step_s)

            if not has_enough_bars:
                logger.warning(
                    "Not enough bars in local store yet; skipping loop",
                    extra={"rows": rows, "min_bars": cfg.min_bars, "symbol": cfg.symbol},
                )
                time.sleep(cfg.loop_sleep_seconds)
                continue

            if not cadence_ok:
                logger.warning(
                    "Cadence check failed; skipping loop (possible partial outage / sparse feed)",
                    extra={
                        "symbol": cfg.symbol,
                        "timeframe": cfg.timeframe,
                        "expected_step_s": expected_step_s,
                        "rows": rows,
                    },
                )
                time.sleep(cfg.loop_sleep_seconds)
                continue

            # 5) Compute features
            feats = compute_features(market_data)

            # 5b) NaN guard: never trade if the last row has NaNs
            try:
                validate_latest_features(feats)
            except Exception as e:
                logger.warning(
                    "Latest features invalid; skipping loop",
                    extra={"symbol": cfg.symbol, "error": repr(e)},
                )
                time.sleep(cfg.loop_sleep_seconds)
                continue

            # 6) Market state
            market_state = determine_market_state(
                feats,
                timeframe=cfg.timeframe,
                min_bars=cfg.min_bars,
            )

            logger.info(
                "Market state",
                extra={
                    "symbol": cfg.symbol,
                    "trend": market_state.trend,
                    "volatility": market_state.volatility,
                    "tradable": market_state.tradable,
                    "cadence_ok": market_state.cadence_ok,
                    "has_enough_bars": market_state.has_enough_bars,
                    "reason": market_state.reason,
                },
            )

            latest_row = feats.iloc[-1]
            latest_close = float(latest_row["close"])
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

            # Build decision row (one per bar timestamp)
            decision_row = {
                "ts_ms": now_ts_ms,
                "timestamp": now_iso,
                "tradable": bool(market_state.tradable),
                "trend": market_state.trend,
                "volatility": market_state.volatility,
                "market_reason": market_state.reason,
                "cooldown_remaining_bars": "",
                "position_side": position.side if position is not None else "",
                "position_qty": position.qty if position is not None else "",
                "position_entry_price": position.entry_price if position is not None else "",
                "position_stop_price": position.stop_price if position is not None else "",
                "unrealized_pnl_usd": "",
                "unrealized_pnl_pct": "",
                "entry_should_enter": "",
                "entry_side": "",
                "entry_confidence": "",
                "entry_reason": "",
                "exit_should_exit": "",
                "exit_reason": "",
            }

            # 7) EXIT (evaluate first; only if in a position)
            if position is not None:
                u_usd, u_pct = broker.get_unrealized_pnl(
                    symbol=cfg.symbol,
                    last_price=latest_close,
                )
                decision_row["unrealized_pnl_usd"] = float(u_usd)
                decision_row["unrealized_pnl_pct"] = float(u_pct)

                logger.info(
                    "Position mark",
                    extra={
                        "symbol": cfg.symbol,
                        "side": position.side,
                        "qty": position.qty,
                        "entry_price": position.entry_price,
                        "stop_price": position.stop_price,
                        "last_close": latest_close,
                        "unrealized_pnl_usd": float(u_usd),
                        "unrealized_pnl_pct": float(u_pct),
                    },
                )

                # Trailing stop update
                new_stop = compute_trailing_stop(
                    position=position,
                    latest_close=latest_close,
                    atr=latest_atr,
                )
                if new_stop is not None and (
                    position.stop_price is None or float(new_stop) != float(position.stop_price)
                ):
                    updated = broker.update_stop(symbol=cfg.symbol, new_stop_price=float(new_stop))
                    if updated is not None:
                        position = updated
                        decision_row["position_stop_price"] = position.stop_price
                        logger.info(
                            "Stop trailed",
                            extra={
                                "symbol": cfg.symbol,
                                "side": position.side,
                                "new_stop_price": position.stop_price,
                                "last_close": latest_close,
                            },
                        )

                exit_sig = evaluate_exit(
                    position=position,
                    latest_features_row=latest_row,
                    market_state=market_state,
                    expected_step_s=int(expected_step_s),
                )
                decision_row["exit_should_exit"] = bool(exit_sig.should_exit)
                decision_row["exit_reason"] = exit_sig.reason or ""

                logger.info(
                    "Exit evaluated",
                    extra={
                        "symbol": cfg.symbol,
                        "should_exit": exit_sig.should_exit,
                        "exit_reason": exit_sig.reason,
                        "stop_price": position.stop_price,
                        "last_close": latest_close,
                        "market_reason": market_state.reason,
                    },
                )

                if exit_sig.should_exit:
                    # close the trade
                    trade = broker.realize_and_close(
                        symbol=cfg.symbol,
                        exit_price=latest_close,
                        reason=exit_sig.reason or "exit",
                        exit_ts_ms=now_ts_ms if now_ts_ms > 0 else None,
                    )

                    logger.info(
                        "Exit executed",
                        extra=trade,
                    )

                    csv_path = append_trade_csv(
                        trade=trade,
                        exchange=cfg.ccxt_exchange,
                        symbol=cfg.symbol,
                        timeframe=cfg.timeframe,
                        market_reason=market_state.reason,
                    )
                    logger.info("Trade recorded", extra={"csv_path": csv_path})

                    # record decision (once per bar)
                    _write_decision_once_per_bar(decision_row)

                    # After closing, treat as flat for this loop (no immediate re-entry).
                    time.sleep(cfg.loop_sleep_seconds)
                    continue

            # 8) ENTRY (only if flat)
            if position is None:
                remaining = broker.cooldown_remaining_bars(
                    symbol=cfg.symbol,
                    now_ts_ms=now_ts_ms,
                    expected_step_s=int(expected_step_s),
                    cooldown_bars=int(getattr(cfg, "cooldown_bars", 0)),
                )
                decision_row["cooldown_remaining_bars"] = int(remaining)

                if remaining > 0:
                    logger.info(
                        "Entry blocked by cooldown",
                        extra={
                            "symbol": cfg.symbol,
                            "cooldown_bars": int(getattr(cfg, "cooldown_bars", 0)),
                            "remaining_bars": int(remaining),
                        },
                    )
                    _write_decision_once_per_bar(decision_row)

                    elapsed = time.time() - loop_start
                    sleep_for = max(cfg.loop_sleep_seconds - elapsed, 0.0)
                    time.sleep(sleep_for)
                    continue

                entry_sig = evaluate_entry(features=feats, market_state=market_state)

                decision_row["entry_should_enter"] = bool(entry_sig.should_enter)
                decision_row["entry_side"] = entry_sig.side
                decision_row["entry_confidence"] = float(entry_sig.confidence)
                decision_row["entry_reason"] = entry_sig.reason

                logger.info(
                    "Entry evaluated",
                    extra={
                        "symbol": cfg.symbol,
                        "should_enter": entry_sig.should_enter,
                        "side": entry_sig.side,
                        "confidence": entry_sig.confidence,
                        "entry_reason": entry_sig.reason,
                        "market_trend": market_state.trend,
                        "market_volatility": market_state.volatility,
                        "market_reason": market_state.reason,
                    },
                )

                if entry_sig.should_enter:
                    size = size_position(signal=entry_sig, market_state=market_state)
                    size = min(size, cfg.max_order_size)

                    entry_ts = latest_row["timestamp"]
                    entry_ts_ms = int(getattr(entry_ts, "value", 0) // 1_000_000)

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
                    )

                    logger.info(
                        "Entry executed",
                        extra={
                            "symbol": cfg.symbol,
                            "side": entry_sig.side,
                            "size": size,
                            "entry_price": latest_close,
                            "stop_price": stop_price,
                            "confidence": entry_sig.confidence,
                            "entry_reason": entry_sig.reason,
                            "market_reason": market_state.reason,
                        },
                    )

            # record decision (once per bar)
            _write_decision_once_per_bar(decision_row)

            # 9) Keep loop cadence stable-ish (sleep minus time spent)
            elapsed = time.time() - loop_start
            sleep_for = max(cfg.loop_sleep_seconds - elapsed, 0.0)
            time.sleep(sleep_for)

        except KeyboardInterrupt:
            logger.info("Stopping (KeyboardInterrupt)")
            break
        except Exception:
            logger.exception("Unhandled error in main loop")
            time.sleep(cfg.loop_sleep_seconds)


if __name__ == "__main__":
    main()
