from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class EntryModelConfig:
    # v2: continuation evidence carries most of the score.
    weight_trend_strength: float = 0.35
    weight_trend_slope: float = 0.30
    weight_recent_return: float = 0.20
    weight_rsi_quality: float = 0.15

    # Positive directional feature scaling.
    ema_spread_full_scale: float = 0.0030
    ema_slow_slope_full_scale: float = 25.0
    ret_1_full_scale: float = 0.0030

    # RSI confirmation.
    long_rsi_center: float = 60.0
    short_rsi_center: float = 40.0
    rsi_half_width: float = 15.0

    long_rsi_overbought: float = 72.0
    short_rsi_oversold: float = 28.0
    rsi_extreme_penalty_max: float = 0.35

    # Volatility penalty.
    atr_pct_soft_penalty_start: float = 0.0018
    atr_pct_full_penalty: float = 0.0035
    atr_pct_penalty_max: float = 0.20

    # v2 directional contradiction penalties.
    slope_contradiction_full_scale: float = 25.0
    slope_contradiction_penalty_max: float = 0.30

    return_contradiction_full_scale: float = 0.0030
    return_contradiction_penalty_max: float = 0.25

    # v2 confirmation multipliers.
    # A setup with little directional slope or momentum cannot be rescued
    # by EMA spread and RSI alone.
    slope_confirmation_floor: float = 0.45
    return_confirmation_floor: float = 0.60

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

    if x != x:
        return float(default)

    return float(x)


def _latest_row(features) -> pd.Series:
    if features is None or len(features) == 0:
        raise ValueError("features empty")

    return features.iloc[-1]


class EntryModel:
    """
    Deterministic continuation-quality scorer.

    v2 contract:
    - bounded confidence in [0, 1]
    - structurally symmetric for LONG and SHORT
    - latest closed-bar features only
    - trend, slope and immediate momentum must broadly agree
    - contradictory slope or return actively reduces confidence
    - RSI confirms a setup but cannot rescue weak continuation
    """

    def __init__(self, cfg: EntryModelConfig | None = None) -> None:
        self.cfg = cfg or EntryModelConfig()

    def _directional_value(self, *, side: str, value: float) -> float:
        normalized_side = side.upper().strip()

        if normalized_side == "LONG":
            return float(value)

        if normalized_side == "SHORT":
            return float(-value)

        raise ValueError(f"Invalid side: {side!r}")

    def _trend_strength_score(self, *, side: str, ema_spread: float) -> float:
        directional = self._directional_value(
            side=side,
            value=ema_spread,
        )

        return _clip01(
            directional / max(self.cfg.ema_spread_full_scale, 1e-12)
        )

    def _trend_slope_score(self, *, side: str, ema_slow_slope: float) -> float:
        directional = self._directional_value(
            side=side,
            value=ema_slow_slope,
        )

        return _clip01(
            directional / max(self.cfg.ema_slow_slope_full_scale, 1e-12)
        )

    def _recent_return_score(self, *, side: str, ret_1: float) -> float:
        directional = self._directional_value(
            side=side,
            value=ret_1,
        )

        return _clip01(
            directional / max(self.cfg.ret_1_full_scale, 1e-12)
        )

    def _rsi_base_score(self, *, side: str, rsi: float) -> float:
        normalized_side = side.upper().strip()

        if normalized_side == "LONG":
            center = self.cfg.long_rsi_center
        elif normalized_side == "SHORT":
            center = self.cfg.short_rsi_center
        else:
            raise ValueError(f"Invalid side: {side!r}")

        distance = abs(float(rsi) - float(center))
        width = max(self.cfg.rsi_half_width, 1e-12)

        return _clip01(1.0 - distance / width)

    def _rsi_extreme_penalty(self, *, side: str, rsi: float) -> float:
        normalized_side = side.upper().strip()

        if normalized_side == "LONG":
            start = self.cfg.long_rsi_overbought

            if rsi <= start:
                return 0.0

            severity = (rsi - start) / max(100.0 - start, 1e-12)

            return (
                _clip01(severity)
                * self.cfg.rsi_extreme_penalty_max
            )

        if normalized_side == "SHORT":
            start = self.cfg.short_rsi_oversold

            if rsi >= start:
                return 0.0

            severity = (start - rsi) / max(start, 1e-12)

            return (
                _clip01(severity)
                * self.cfg.rsi_extreme_penalty_max
            )

        raise ValueError(f"Invalid side: {side!r}")

    def _rsi_quality_score(self, *, side: str, rsi: float) -> float:
        base = self._rsi_base_score(
            side=side,
            rsi=rsi,
        )

        penalty = self._rsi_extreme_penalty(
            side=side,
            rsi=rsi,
        )

        return _clip01(base - penalty)

    def _volatility_penalty(self, *, atr_pct: float) -> float:
        start = self.cfg.atr_pct_soft_penalty_start
        full = self.cfg.atr_pct_full_penalty

        if atr_pct <= start:
            return 0.0

        if atr_pct >= full:
            return self.cfg.atr_pct_penalty_max

        severity = (atr_pct - start) / max(full - start, 1e-12)

        return (
            _clip01(severity)
            * self.cfg.atr_pct_penalty_max
        )

    def _slope_contradiction_penalty(
        self,
        *,
        side: str,
        ema_slow_slope: float,
    ) -> float:
        directional = self._directional_value(
            side=side,
            value=ema_slow_slope,
        )

        if directional >= 0.0:
            return 0.0

        severity = abs(directional) / max(
            self.cfg.slope_contradiction_full_scale,
            1e-12,
        )

        return (
            _clip01(severity)
            * self.cfg.slope_contradiction_penalty_max
        )

    def _return_contradiction_penalty(
        self,
        *,
        side: str,
        ret_1: float,
    ) -> float:
        directional = self._directional_value(
            side=side,
            value=ret_1,
        )

        if directional >= 0.0:
            return 0.0

        severity = abs(directional) / max(
            self.cfg.return_contradiction_full_scale,
            1e-12,
        )

        return (
            _clip01(severity)
            * self.cfg.return_contradiction_penalty_max
        )

    def _confirmation_multiplier(
        self,
        *,
        trend_slope: float,
        recent_return: float,
    ) -> float:
        slope_multiplier = (
            self.cfg.slope_confirmation_floor
            + (1.0 - self.cfg.slope_confirmation_floor)
            * _clip01(trend_slope)
        )

        return_multiplier = (
            self.cfg.return_confirmation_floor
            + (1.0 - self.cfg.return_confirmation_floor)
            * _clip01(recent_return)
        )

        return _clip01(slope_multiplier * return_multiplier)

    def score_components(self, features, *, side: str) -> dict[str, float]:
        row = _latest_row(features)

        ema_spread = _safe_float(
            row.get("ema_spread", 0.0),
            0.0,
        )
        ema_slow_slope = _safe_float(
            row.get("ema_slow_slope", 0.0),
            0.0,
        )
        ret_1 = _safe_float(
            row.get("ret_1", 0.0),
            0.0,
        )
        rsi = _safe_float(
            row.get("rsi", 50.0),
            50.0,
        )
        atr_pct = _safe_float(
            row.get("atr_pct", 0.0),
            0.0,
        )

        trend_strength = self._trend_strength_score(
            side=side,
            ema_spread=ema_spread,
        )
        trend_slope = self._trend_slope_score(
            side=side,
            ema_slow_slope=ema_slow_slope,
        )
        recent_return = self._recent_return_score(
            side=side,
            ret_1=ret_1,
        )
        rsi_quality = self._rsi_quality_score(
            side=side,
            rsi=rsi,
        )
        volatility_penalty = self._volatility_penalty(
            atr_pct=atr_pct,
        )
        slope_contradiction_penalty = (
            self._slope_contradiction_penalty(
                side=side,
                ema_slow_slope=ema_slow_slope,
            )
        )
        return_contradiction_penalty = (
            self._return_contradiction_penalty(
                side=side,
                ret_1=ret_1,
            )
        )
        confirmation_multiplier = (
            self._confirmation_multiplier(
                trend_slope=trend_slope,
                recent_return=recent_return,
            )
        )

        return {
            "trend_strength": trend_strength,
            "trend_slope": trend_slope,
            "recent_return": recent_return,
            "rsi_quality": rsi_quality,
            "volatility_penalty": volatility_penalty,
            "slope_contradiction_penalty": slope_contradiction_penalty,
            "return_contradiction_penalty": return_contradiction_penalty,
            "confirmation_multiplier": confirmation_multiplier,
            "ema_spread": ema_spread,
            "ema_slow_slope": ema_slow_slope,
            "ret_1": ret_1,
            "rsi": rsi,
            "atr_pct": atr_pct,
        }

    def predict_confidence(
        self,
        features,
        *,
        side: str = "LONG",
    ) -> float:
        components = self.score_components(
            features,
            side=side,
        )

        weighted_score = (
            self.cfg.weight_trend_strength
            * components["trend_strength"]
            + self.cfg.weight_trend_slope
            * components["trend_slope"]
            + self.cfg.weight_recent_return
            * components["recent_return"]
            + self.cfg.weight_rsi_quality
            * components["rsi_quality"]
        )

        confirmed_score = (
            weighted_score
            * components["confirmation_multiplier"]
        )

        confidence = (
            confirmed_score
            - components["volatility_penalty"]
            - components["slope_contradiction_penalty"]
            - components["return_contradiction_penalty"]
        )

        if confidence < self.cfg.min_confidence:
            return float(self.cfg.min_confidence)

        if confidence > self.cfg.max_confidence:
            return float(self.cfg.max_confidence)

        return float(confidence)
