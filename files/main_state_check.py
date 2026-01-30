# files/main_state_check.py
from __future__ import annotations

import pandas as pd

from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.quality import assess_ohlcv
from files.data.features import compute_features, validate_latest_features
from files.strategy.filters import determine_market_state
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


def main() -> None:
    cfg = load_trading_config()
    expected_step_s = _timeframe_to_seconds(cfg.timeframe)

    logger.info(
        "🧪 State check starting",
        extra={
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "min_bars": cfg.min_bars,
            "ccxt_exchange": cfg.ccxt_exchange,
        },
    )

    # 1) Fetch from source
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

    # 3) Load stable truth
    ohlcv = load_recent_ohlcv_parquet(
        exchange=cfg.ccxt_exchange,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        tail_n=max(cfg.min_bars, 200),
    )

    rows = len(ohlcv)
    has_enough_bars = rows >= cfg.min_bars
    cadence_ok = _cadence_ok(ohlcv, expected_step_s)

    # 4) OHLCV quality summary
    rep = assess_ohlcv(ohlcv)
    logger.info(
        "OHLCV quality",
        extra={
            "rows": rep.rows,
            "tz_aware": rep.tz_aware,
            "monotonic": rep.monotonic,
            "duplicates": rep.duplicates,
            "median_step_s": rep.median_step_s,
            "min_step_s": rep.min_step_s,
            "max_step_s": rep.max_step_s,
            "expected_step_s": expected_step_s,
            "cadence_ok": cadence_ok,
            "has_enough_bars": has_enough_bars,
        },
    )

    if not has_enough_bars:
        logger.warning(
            "Not enough bars to trust state yet",
            extra={"rows": rows, "min_bars": cfg.min_bars},
        )
        # still print tail to help you see it
        tail = ohlcv[["timestamp", "open", "high", "low", "close", "volume"]].tail(5)
        logger.info("OHLCV tail:\n%s", tail.to_string(index=False))
        return

    if not cadence_ok:
        logger.warning(
            "Cadence failed — likely sparse feed / partial outage; refusing to compute state",
            extra={"expected_step_s": expected_step_s},
        )
        tail = ohlcv[["timestamp", "open", "high", "low", "close", "volume"]].tail(5)
        logger.info("OHLCV tail:\n%s", tail.to_string(index=False))
        return

    # 5) Compute features + validate last row
    feats = compute_features(ohlcv)
    validate_latest_features(feats)

    # 6) Determine state
    state = determine_market_state(
        feats,
        timeframe=cfg.timeframe,
        min_bars=cfg.min_bars,
    )

    logger.info(
        "✅ MarketState",
        extra={
            "tradable": state.tradable,
            "trend": state.trend,
            "volatility": state.volatility,
            "cadence_ok": state.cadence_ok,
            "has_enough_bars": state.has_enough_bars,
            "reason": state.reason,
        },
    )

    # 7) Print compact tail for eyeballing
    feats_tail = feats[["timestamp", "close", "ema_fast", "ema_slow", "ema_spread", "atr_pct", "rsi", "vol_z"]].tail(3)
    logger.info("Features tail:\n%s", feats_tail.to_string(index=False))


if __name__ == "__main__":
    main()

