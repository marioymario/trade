# files/models/entry_model.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class EntryModelConfig:
    # Component weights (should sum to ~1.0 for readability, but not required)
    weight_trend_strength: float = 0.40
    weight_trend_slope: float = 0.20
    weight_recent_return: float = 0.10
    weight_rsi_quality: float = 0.30

    # Trend strength scaling for ema_spread
    # Confidence contribution saturates once directional spread reaches this magnitude.
    ema_spread_full_scale: float = 0.0030  # 0.30%

    # Trend slope scaling for ema_slow_slope.
    # This is in raw price units, so keep modest and adjustable.
    ema_slow_slope_full_scale: float = 25.0

    # Recent return scaling.
    ret_1_full_scale: float = 0.0030  # 0.30% one-bar return

    # RSI preferred bands
    long_rsi_center: float = 60.0
    short_rsi_center: float = 40.0
    rsi_half_width: float = 15.0

    # Overextension soft penalties
    long_rsi_overbought: float = 72.0
    short_rsi_oversold: float = 28.0
    rsi_extreme_penalty_max: float = 0.35

    # Volatility penalty
    atr_pct_soft_penalty_start: float = 0.0018   # 0.18%
    atr_pct_full_penalty: float = 0.0035         # 0.35%
    atr_pct_penalty_max: float = 0.20

    # Final score floor/ceiling
    min_confidence: float = 0.0
    max_confidence: float = 1.0


def _clip01(x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return float(x)


def _safe_float(v, default: float = 0.0) -> float:
    try:
        x = float(v)
    except Exception:
        return float(default)
    if x != x:  # NaN
        return float(default)
    return float(x)


def _latest_row(features) -> pd.Series:
    if features is None or len(features) == 0:
        raise ValueError("features empty")
    return features.iloc[-1]


class EntryModel:
    """
    Deterministic setup-quality scorer.

    Purpose:
    - produce a bounded confidence score in [0, 1]
    - remain symmetric across LONG and SHORT structurally
    - use latest-bar features only in v1
    - be explainable and adjustable

    This is not a statistical/ML model.
    It is a deterministic scoring engine.
    """

    def __init__(self, cfg: EntryModelConfig | None = None) -> None:
        self.cfg = cfg or EntryModelConfig()

    def _directional_value(self, *, side: str, value: float) -> float:
        s = side.upper().strip()
        if s == "LONG":
            return float(value)
        if s == "SHORT":
            return float(-value)
        raise ValueError(f"Invalid side: {side!r}")

    def _trend_strength_score(self, *, side: str, ema_spread: float) -> float:
        directional = self._directional_value(side=side, value=ema_spread)
        return _clip01(directional / max(self.cfg.ema_spread_full_scale, 1e-12))

    def _trend_slope_score(self, *, side: str, ema_slow_slope: float) -> float:
        directional = self._directional_value(side=side, value=ema_slow_slope)
        return _clip01(directional / max(self.cfg.ema_slow_slope_full_scale, 1e-12))

    def _recent_return_score(self, *, side: str, ret_1: float) -> float:
        directional = self._directional_value(side=side, value=ret_1)
        return _clip01(directional / max(self.cfg.ret_1_full_scale, 1e-12))

    def _rsi_base_score(self, *, side: str, rsi: float) -> float:
        if side.upper().strip() == "LONG":
            center = self.cfg.long_rsi_center
        elif side.upper().strip() == "SHORT":
            center = self.cfg.short_rsi_center
        else:
            raise ValueError(f"Invalid side: {side!r}")

        dist = abs(float(rsi) - float(center))
        width = max(self.cfg.rsi_half_width, 1e-12)
        return _clip01(1.0 - (dist / width))

    def _rsi_extreme_penalty(self, *, side: str, rsi: float) -> float:
        if side.upper().strip() == "LONG":
            start = self.cfg.long_rsi_overbought
            if rsi <= start:
                return 0.0
            severity = (rsi - start) / max(100.0 - start, 1e-12)
            return _clip01(severity) * self.cfg.rsi_extreme_penalty_max

        if side.upper().strip() == "SHORT":
            start = self.cfg.short_rsi_oversold
            if rsi >= start:
                return 0.0
            severity = (start - rsi) / max(start, 1e-12)
            return _clip01(severity) * self.cfg.rsi_extreme_penalty_max

        raise ValueError(f"Invalid side: {side!r}")

    def _rsi_quality_score(self, *, side: str, rsi: float) -> float:
        base = self._rsi_base_score(side=side, rsi=rsi)
        penalty = self._rsi_extreme_penalty(side=side, rsi=rsi)
        return _clip01(base - penalty)

    def _volatility_penalty(self, *, atr_pct: float) -> float:
        start = self.cfg.atr_pct_soft_penalty_start
        full = self.cfg.atr_pct_full_penalty

        if atr_pct <= start:
            return 0.0
        if atr_pct >= full:
            return self.cfg.atr_pct_penalty_max

        severity = (atr_pct - start) / max(full - start, 1e-12)
        return _clip01(severity) * self.cfg.atr_pct_penalty_max

    def score_components(self, features, *, side: str) -> dict[str, float]:
        row = _latest_row(features)

        ema_spread = _safe_float(row.get("ema_spread", 0.0), 0.0)
        ema_slow_slope = _safe_float(row.get("ema_slow_slope", 0.0), 0.0)
        ret_1 = _safe_float(row.get("ret_1", 0.0), 0.0)
        rsi = _safe_float(row.get("rsi", 50.0), 50.0)
        atr_pct = _safe_float(row.get("atr_pct", 0.0), 0.0)

        trend_strength = self._trend_strength_score(side=side, ema_spread=ema_spread)
        trend_slope = self._trend_slope_score(side=side, ema_slow_slope=ema_slow_slope)
        recent_return = self._recent_return_score(side=side, ret_1=ret_1)
        rsi_quality = self._rsi_quality_score(side=side, rsi=rsi)
        volatility_penalty = self._volatility_penalty(atr_pct=atr_pct)

        return {
            "trend_strength": trend_strength,
            "trend_slope": trend_slope,
            "recent_return": recent_return,
            "rsi_quality": rsi_quality,
            "volatility_penalty": volatility_penalty,
            "ema_spread": ema_spread,
            "ema_slow_slope": ema_slow_slope,
            "ret_1": ret_1,
            "rsi": rsi,
            "atr_pct": atr_pct,
        }

    def predict_confidence(self, features, *, side: str = "LONG") -> float:
        c = self.score_components(features, side=side)

        weighted_score = (
            self.cfg.weight_trend_strength * c["trend_strength"]
            + self.cfg.weight_trend_slope * c["trend_slope"]
            + self.cfg.weight_recent_return * c["recent_return"]
            + self.cfg.weight_rsi_quality * c["rsi_quality"]
        )

        confidence = weighted_score - c["volatility_penalty"]

        if confidence < self.cfg.min_confidence:
            return float(self.cfg.min_confidence)
        if confidence > self.cfg.max_confidence:
            return float(self.cfg.max_confidence)
        return float(confidence)
