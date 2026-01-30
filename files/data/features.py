# files/data/features.py
from __future__ import annotations

from dataclasses import dataclass
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
    return_n: int = 1          # 1-bar return
    zscore_n: int = 50         # rolling zscore window


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
    """
    Input: OHLCV DataFrame with columns:
      timestamp (tz-aware UTC), open, high, low, close, volume
    Output: DataFrame with stable feature columns, same number of rows.

    IMPORTANT:
    - Last row represents the most recent bar.
    - We do not forward-fill NaNs; if last row has NaNs you should skip trading.
    """
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

    # Price-derived
    df["ret_1"] = close.pct_change(cfg.return_n)
    df["logret_1"] = np.log(close / close.shift(1))

    # Trend
    df["ema_fast"] = _ema(close, cfg.ema_fast)
    df["ema_slow"] = _ema(close, cfg.ema_slow)
    df["ema_spread"] = (df["ema_fast"] - df["ema_slow"]) / (df["ema_slow"] + 1e-12)
    df["ema_slow_slope"] = df["ema_slow"].diff()

    # Volatility / risk
    df["atr"] = _atr(high, low, close, cfg.atr_n)
    df["atr_pct"] = df["atr"] / (close + 1e-12)

    # Momentum
    df["rsi"] = _rsi(close, cfg.rsi_n)

    # Volume features
    df["vol_z"] = _rolling_zscore(vol, cfg.zscore_n)
    df["dollar_vol"] = close * vol
    df["dollar_vol_z"] = _rolling_zscore(df["dollar_vol"], cfg.zscore_n)

    # Keep only columns we want downstream
    out_cols = [
        "timestamp",
        "open", "high", "low", "close", "volume",
        "ret_1", "logret_1",
        "ema_fast", "ema_slow", "ema_spread", "ema_slow_slope",
        "atr", "atr_pct",
        "rsi",
        "vol_z", "dollar_vol", "dollar_vol_z",
    ]
    out = df[out_cols].copy()

    return out


def validate_latest_features(feats: pd.DataFrame) -> None:
    """
    Raises if the last row is not usable.
    Call this before trading so you never feed NaNs into state/rules/ML.
    """
    if feats is None or len(feats) == 0:
        raise ValueError("features empty")

    last = feats.iloc[-1]
    bad = [c for c in feats.columns if c != "timestamp" and pd.isna(last[c])]
    if bad:
        raise ValueError(f"latest features contain NaNs in: {bad}")

