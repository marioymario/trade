# files/main_features_check.py
from __future__ import annotations

import numpy as np
import pandas as pd

from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.features import compute_features, validate_latest_features
from files.data.quality import assess_ohlcv
from files.utils.logger import get_logger

logger = get_logger(__name__)


EXPECTED_FEATURE_COLS = [
    "timestamp",
    "open", "high", "low", "close", "volume",
    "ret_1", "logret_1",
    "ema_fast", "ema_slow", "ema_spread", "ema_slow_slope",
    "atr", "atr_pct",
    "rsi",
    "vol_z", "dollar_vol", "dollar_vol_z",
]


def _assert_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing expected feature columns: {missing}")


def _assert_no_inf(df: pd.DataFrame) -> None:
    num = df.select_dtypes(include=[np.number])
    if num.empty:
        return
    bad = np.isinf(num.to_numpy()).any()
    if bad:
        raise ValueError("Features contain inf/-inf values")


def _assert_basic_ranges(feats: pd.DataFrame) -> None:
    last = feats.iloc[-1]

    rsi = float(last["rsi"])
    if not (-1e-6 <= rsi <= 100.0 + 1e-6):
        raise ValueError(f"RSI out of range: {rsi}")

    atr_pct = float(last["atr_pct"])
    if atr_pct < -1e-12:
        raise ValueError(f"atr_pct negative: {atr_pct}")


def main() -> None:
    cfg = load_trading_config()

    df = fetch_market_data(
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        limit=max(cfg.min_bars, 200),
        ccxt_exchange=cfg.ccxt_exchange,
        min_bars_warn=cfg.min_bars,
    )

    # Reuse your OHLCV quality check (nice to keep this consistent)
    rep = assess_ohlcv(df)
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
        },
    )

    feats = compute_features(df)

    _assert_columns(feats, EXPECTED_FEATURE_COLS)
    _assert_no_inf(feats)
    validate_latest_features(feats)
    _assert_basic_ranges(feats)

    logger.info(
        "✅ Features OK",
        extra={
            "rows": len(feats),
            "last_ts": str(feats["timestamp"].iloc[-1]),
        },
    )

    # show last row for eyeballing
    tail = feats.tail(3)[["timestamp", "close", "ema_fast", "ema_slow", "atr_pct", "rsi"]]
    logger.info("Features tail:\n%s", tail.to_string(index=False))


if __name__ == "__main__":
    main()

