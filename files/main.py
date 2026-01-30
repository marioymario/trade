# files/main.py
from __future__ import annotations

import time
import pandas as pd

from files.broker.paper import PaperBroker
from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.features import compute_features, validate_latest_features
from files.strategy.filters import determine_market_state
from files.strategy.rules import evaluate_entry, evaluate_exit, size_position
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
    We treat the feed as 'cadence_ok' if the median timestamp step matches
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
        },
    )

    broker = PaperBroker(dry_run=cfg.dry_run)
    expected_step_s = _timeframe_to_seconds(cfg.timeframe)

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

            # 6) Market state (uses features, cadence, min_bars conceptually)
            market_state = determine_market_state(
                feats,
                timeframe=cfg.timeframe,
                min_bars=cfg.min_bars,
            )

            # Optional: keep these consistent in logs (cadence + bars are already gated above)
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

            if not market_state.tradable:
                logger.info(
                    "Market not tradable",
                    extra={
                        "symbol": cfg.symbol,
                        "trend": market_state.trend,
                        "volatility": market_state.volatility,
                        "cadence_ok": market_state.cadence_ok,
                        "has_enough_bars": market_state.has_enough_bars,
                        "reason": market_state.reason,
                    },
                )
                time.sleep(cfg.loop_sleep_seconds)
                continue

            position = broker.get_position(cfg.symbol)

            # 7) ENTRY (only if flat + tradable)
            if position is None:
                entry_signal = evaluate_entry(features=feats, market_state=market_state)

                logger.info(
                    "Entry evaluated",
                    extra={
                        "symbol": cfg.symbol,
                        "should_enter": entry_signal.should_enter,
                        "side": entry_signal.side,
                        "confidence": entry_signal.confidence,
                        "entry_reason": entry_signal.reason,
                        "market_trend": market_state.trend,
                        "market_volatility": market_state.volatility,
                        "market_reason": market_state.reason,
                    },
                )

                if entry_signal.should_enter:
                    size = size_position(signal=entry_signal, market_state=market_state)
                    size = min(size, cfg.max_order_size)

                    broker.open_position(
                        symbol=cfg.symbol,
                        side=entry_signal.side,
                        size=size,
                    )

                    logger.info(
                        "Entry executed",
                        extra={
                            "symbol": cfg.symbol,
                            "side": entry_signal.side,
                            "size": size,
                            "confidence": entry_signal.confidence,
                            "entry_reason": entry_signal.reason,
                            "market_reason": market_state.reason,
                        },
                    )

            # 8) EXIT (only if in a position)
            else:
                exit_signal = evaluate_exit(
                    position=position, features=feats, market_state=market_state
                )

                logger.info(
                    "Exit evaluated",
                    extra={
                        "symbol": cfg.symbol,
                        "should_exit": exit_signal.should_exit,
                        "exit_reason": exit_signal.reason,
                        "market_trend": market_state.trend,
                        "market_volatility": market_state.volatility,
                        "market_reason": market_state.reason,
                    },
                )

                if exit_signal.should_exit:
                    broker.close_position(symbol=cfg.symbol)
                    logger.info(
                        "Exit executed",
                        extra={
                            "symbol": cfg.symbol,
                            "exit_reason": exit_signal.reason,
                            "market_reason": market_state.reason,
                        },
                    )

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


