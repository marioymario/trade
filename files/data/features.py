from __future__ import annotations

from dataclasses import dataclass
import os
import pandas as pd
import numpy as np

from files.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class FeatureConfig:
    ema_fast: int = 12
    ema_slow: int = 26
    atr_n: int = 14
    rsi_n: int = 14
    return_n: int = 1
    zscore_n: int = 50


DEFAULT_FEATURE_CFG = FeatureConfig()


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int) -> pd.Series:
    tr = _true_range(high, low, close)
    return tr.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-12)
    return 100.0 - (100.0 / (1.0 + rs))


def _rolling_zscore(s: pd.Series, n: int) -> pd.Series:
    mu = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return (s - mu) / (sd + 1e-12)


def compute_features(market_data: pd.DataFrame, cfg: FeatureConfig = DEFAULT_FEATURE_CFG) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(market_data.columns)
    if missing:
        raise ValueError(f"market_data missing columns: {sorted(missing)}")

    df = market_data.copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    vol = df["volume"].astype(float)

    df["ret_1"] = close.pct_change(cfg.return_n)
    df["logret_1"] = np.log(close / close.shift(1))

    df["ema_fast"] = _ema(close, cfg.ema_fast)
    df["ema_slow"] = _ema(close, cfg.ema_slow)
    df["ema_spread"] = (df["ema_fast"] - df["ema_slow"]) / (df["ema_slow"] + 1e-12)
    df["ema_slow_slope"] = df["ema_slow"].diff()

    df["atr"] = _atr(high, low, close, cfg.atr_n)
    df["atr_pct"] = df["atr"] / (close + 1e-12)

    df["rsi"] = _rsi(close, cfg.rsi_n)

    df["vol_z"] = _rolling_zscore(vol, cfg.zscore_n)
    df["dollar_vol"] = close * vol
    df["dollar_vol_z"] = _rolling_zscore(df["dollar_vol"], cfg.zscore_n)

    if os.environ.get("TEST_HOOKS_ENABLED") == "1":
        try:
            n = int(os.environ.get("FORCE_FEATURES_INVALID_N", "0"))
        except Exception:
            n = 0

        if n > 0:
            os.environ["FORCE_FEATURES_INVALID_N"] = str(n - 1)
            df.loc[df.index[-1], "ema_fast"] = np.nan

    out_cols = [
        "timestamp",
        "open", "high", "low", "close", "volume",
        "ret_1", "logret_1",
        "ema_fast", "ema_slow", "ema_spread", "ema_slow_slope",
        "atr", "atr_pct",
        "rsi",
        "vol_z", "dollar_vol", "dollar_vol_z",
    ]

    return df[out_cols].copy()


def validate_latest_features(feats: pd.DataFrame) -> None:
    if feats is None or len(feats) == 0:
        raise ValueError("features empty")

    required_latest = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "ema_fast",
        "ema_slow",
        "ema_spread",
        "atr",
        "atr_pct",
    ]

    missing_cols = [c for c in required_latest if c not in feats.columns]
    if missing_cols:
        raise ValueError(f"features missing required columns: {missing_cols}")

    last = feats.iloc[-1]

    bad_nan = [c for c in required_latest if pd.isna(last[c])]
    if bad_nan:
        raise ValueError(f"latest required features contain NaNs in: {bad_nan}")

    bad_nonfinite = []
    for c in required_latest:
        try:
            v = float(last[c])
        except Exception:
            bad_nonfinite.append(c)
            continue
        if not np.isfinite(v):
            bad_nonfinite.append(c)

    if bad_nonfinite:
        raise ValueError(f"latest required features contain non-finite values in: {bad_nonfinite}")

    optional_warn = [
        "ret_1",
        "logret_1",
        "ema_slow_slope",
        "rsi",
        "vol_z",
        "dollar_vol",
        "dollar_vol_z",
    ]
    optional_bad = [c for c in optional_warn if c in feats.columns and pd.isna(last[c])]
    if optional_bad:
        logger.warning(
            "Latest optional features contain NaNs",
            extra={"columns": optional_bad},
        )
