# files/strategy/filters.py
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

from files.core.types import MarketState, Trend, VolRegime
from files.data.features import validate_latest_features


@dataclass(frozen=True)
class MarketStateConfig:
    """
    Conservative defaults for 5m crypto.
    Tweak later based on your data-quality reports and backtests.
    """
    # Trend thresholds (ema_spread is normalized by ema_slow)
    trend_up_spread: float = 0.0010     # +0.10%
    trend_down_spread: float = -0.0010  # -0.10%
    flat_spread_band: float = 0.0007    # inside +/- 0.07% => flat

    # Volatility buckets (atr_pct is ATR/close)
    vol_low_max: float = 0.0015         # <= 0.15% ATR
    vol_high_min: float = 0.0030        # >= 0.30% ATR

    # Cadence tolerance (median step)
    cadence_tolerance_frac: float = 0.02  # 2% timing jitter allowed
    cadence_tolerance_abs_s: float = 2.0  # or 2 seconds, whichever larger


DEFAULT_STATE_CFG = MarketStateConfig()


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


def _cadence_ok(df: pd.DataFrame, expected_step_s: int, cfg: MarketStateConfig) -> bool:
    """
    Defensive cadence check:
    - coerce timestamp to UTC datetime
    - sort by timestamp
    - compare median step to expected step within tolerance
    """
    if df is None or len(df) < 3:
        return False
    if "timestamp" not in df.columns:
        return False

    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    if ts.isna().all():
        return False

    # sort by timestamp to avoid out-of-order noise
    ts = ts.sort_values()

    diffs = ts.diff().dt.total_seconds().dropna()
    if len(diffs) == 0:
        return False

    med = float(diffs.median())
    tol = max(cfg.cadence_tolerance_abs_s, expected_step_s * cfg.cadence_tolerance_frac)
    return abs(med - expected_step_s) <= tol


def _classify_trend(ema_spread: float, cfg: MarketStateConfig) -> Trend:
    # flat band has priority (reduces flip-flopping)
    if abs(ema_spread) <= cfg.flat_spread_band:
        return "flat"
    if ema_spread >= cfg.trend_up_spread:
        return "up"
    if ema_spread <= cfg.trend_down_spread:
        return "down"
    # between flat band and strong thresholds => treat as flat for now
    return "flat"


def _classify_vol(atr_pct: float, cfg: MarketStateConfig) -> VolRegime:
    if atr_pct <= cfg.vol_low_max:
        return "low"
    if atr_pct >= cfg.vol_high_min:
        return "high"
    return "normal"


def determine_market_state(
    feats: pd.DataFrame,
    *,
    timeframe: str,
    min_bars: int,
    cfg: MarketStateConfig = DEFAULT_STATE_CFG,
) -> MarketState:
    """
    Build a MarketState from the feature DataFrame (not raw OHLCV).

    Rules:
    - If not enough bars, not tradable.
    - If cadence is off (partial outage / stale data), not tradable.
    - If latest row has NaNs, not tradable.
    - Otherwise classify trend + vol regime from last row.
    """
    if feats is None or len(feats) == 0:
        return MarketState(
            tradable=False,
            trend="flat",
            volatility="normal",
            cadence_ok=False,
            has_enough_bars=False,
            reason="no_features",
        )

    # Required columns for state logic
    required_cols = {"timestamp", "ema_spread", "atr_pct"}
    missing = required_cols - set(feats.columns)
    if missing:
        return MarketState(
            tradable=False,
            trend="flat",
            volatility="normal",
            cadence_ok=False,
            has_enough_bars=len(feats) >= min_bars,
            reason=f"missing_feature_columns {sorted(missing)}",
        )

    has_enough = len(feats) >= min_bars
    expected_step_s = _timeframe_to_seconds(timeframe)
    cadence = _cadence_ok(feats, expected_step_s, cfg)

    # NaN gate (super important)
    try:
        validate_latest_features(feats)
        latest_ok = True
    except Exception:
        latest_ok = False

    if not has_enough:
        return MarketState(
            tradable=False,
            trend="flat",
            volatility="normal",
            cadence_ok=cadence,
            has_enough_bars=False,
            reason=f"not_enough_bars rows={len(feats)} min_bars={min_bars}",
        )

    if not cadence:
        return MarketState(
            tradable=False,
            trend="flat",
            volatility="normal",
            cadence_ok=False,
            has_enough_bars=True,
            reason="cadence_not_ok (possible partial outage / stale feed)",
        )

    if not latest_ok:
        return MarketState(
            tradable=False,
            trend="flat",
            volatility="normal",
            cadence_ok=True,
            has_enough_bars=True,
            reason="latest_features_invalid (NaNs)",
        )

    last = feats.iloc[-1]
    ema_spread = float(last["ema_spread"])
    atr_pct = float(last["atr_pct"])

    trend = _classify_trend(ema_spread, cfg)
    vol = _classify_vol(atr_pct, cfg)

    return MarketState(
        tradable=True,
        trend=trend,
        volatility=vol,
        cadence_ok=True,
        has_enough_bars=True,
        reason=f"ok ema_spread={ema_spread:.6f} atr_pct={atr_pct:.6f}",
    )

