from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RangeSpec:
    minimum: float
    maximum: float
    step: float


@dataclass(frozen=True)
class FixedStrategySettings:
    enable_long: bool = True
    enable_short: bool = False

    atr_mult: float = 2.0
    trail_atr_mult: float = 2.0
    max_hold_bars: int = 24

    event_risk_enabled: bool = False


@dataclass(frozen=True)
class SearchControls:
    method: str = "deterministic_random"
    random_seed: int = 5080
    trial_count: int = 100

    minimum_total_trades: int = 20
    minimum_validation_trades_per_split: int = 3


@dataclass(frozen=True)
class WalkForwardSplit:
    name: str

    train_start: str
    train_end_exclusive: str

    validation_start: str
    validation_end_exclusive: str


FIXED_SETTINGS = FixedStrategySettings()
SEARCH_CONTROLS = SearchControls()

MANIFEST_BACKED_SOURCE_CONTRACT = "manifest_backed_v1"
LEGACY_FROZEN_SOURCE_CONTRACT = "legacy_frozen_2026_v1"

SOURCE_CONTRACT = MANIFEST_BACKED_SOURCE_CONTRACT

FINAL_OUT_OF_SAMPLE_START = "2025-01-01T00:00:00+00:00"
FINAL_OUT_OF_SAMPLE_END_EXCLUSIVE = (
    "2026-02-09T00:00:00+00:00"
)

LEGACY_FROZEN_RESEARCH_DATA_MAX_TIMESTAMP = (
    "2026-07-18T19:30:00+00:00"
)


PARAMETER_RANGES: dict[str, RangeSpec] = {
    "confidence_enter": RangeSpec(
        minimum=0.68,
        maximum=0.80,
        step=0.01,
    ),
    "weight_trend_strength": RangeSpec(
        minimum=0.25,
        maximum=0.45,
        step=0.01,
    ),
    "weight_trend_slope": RangeSpec(
        minimum=0.20,
        maximum=0.40,
        step=0.01,
    ),
    "weight_recent_return": RangeSpec(
        minimum=0.10,
        maximum=0.30,
        step=0.01,
    ),
    "weight_rsi_quality": RangeSpec(
        minimum=0.05,
        maximum=0.20,
        step=0.01,
    ),
    "ema_spread_full_scale": RangeSpec(
        minimum=0.0020,
        maximum=0.0045,
        step=0.00025,
    ),
    "ema_slow_slope_full_scale": RangeSpec(
        minimum=15.0,
        maximum=60.0,
        step=5.0,
    ),
    "ret_1_full_scale": RangeSpec(
        minimum=0.0020,
        maximum=0.0050,
        step=0.00025,
    ),
    "long_rsi_center": RangeSpec(
        minimum=55.0,
        maximum=65.0,
        step=2.5,
    ),
    "rsi_half_width": RangeSpec(
        minimum=10.0,
        maximum=20.0,
        step=2.5,
    ),
    "long_rsi_overbought": RangeSpec(
        minimum=68.0,
        maximum=78.0,
        step=2.0,
    ),
    "rsi_extreme_penalty_max": RangeSpec(
        minimum=0.20,
        maximum=0.50,
        step=0.05,
    ),
    "atr_pct_soft_penalty_start": RangeSpec(
        minimum=0.0015,
        maximum=0.0025,
        step=0.00025,
    ),
    "atr_pct_full_penalty": RangeSpec(
        minimum=0.0030,
        maximum=0.0050,
        step=0.00025,
    ),
    "atr_pct_penalty_max": RangeSpec(
        minimum=0.10,
        maximum=0.35,
        step=0.05,
    ),
    "slope_contradiction_full_scale": RangeSpec(
        minimum=15.0,
        maximum=50.0,
        step=5.0,
    ),
    "slope_contradiction_penalty_max": RangeSpec(
        minimum=0.15,
        maximum=0.45,
        step=0.05,
    ),
    "return_contradiction_full_scale": RangeSpec(
        minimum=0.0015,
        maximum=0.0040,
        step=0.00025,
    ),
    "return_contradiction_penalty_max": RangeSpec(
        minimum=0.10,
        maximum=0.40,
        step=0.05,
    ),
    "slope_confirmation_floor": RangeSpec(
        minimum=0.30,
        maximum=0.70,
        step=0.05,
    ),
    "return_confirmation_floor": RangeSpec(
        minimum=0.40,
        maximum=0.80,
        step=0.05,
    ),
}


PARAMETER_CONSTRAINTS: tuple[str, ...] = (
    "Normalized component weights must sum to 1.0.",
    "weight_rsi_quality <= weight_recent_return.",
    "weight_rsi_quality <= weight_trend_slope.",
    "atr_pct_full_penalty > atr_pct_soft_penalty_start.",
    "short_rsi_center = 100.0 - long_rsi_center.",
    "short_rsi_oversold = 100.0 - long_rsi_overbought.",
)


WALK_FORWARD_SPLITS: tuple[WalkForwardSplit, ...] = (
    WalkForwardSplit(
        name="train_2022_validate_h1_2023",
        train_start="2022-01-01T00:00:00+00:00",
        train_end_exclusive="2023-01-01T00:00:00+00:00",
        validation_start="2023-01-01T00:00:00+00:00",
        validation_end_exclusive="2023-07-01T00:00:00+00:00",
    ),
    WalkForwardSplit(
        name="train_to_h1_2023_validate_h2_2023",
        train_start="2022-01-01T00:00:00+00:00",
        train_end_exclusive="2023-07-01T00:00:00+00:00",
        validation_start="2023-07-01T00:00:00+00:00",
        validation_end_exclusive="2024-01-01T00:00:00+00:00",
    ),
    WalkForwardSplit(
        name="train_to_2024_validate_2024",
        train_start="2022-01-01T00:00:00+00:00",
        train_end_exclusive="2024-01-01T00:00:00+00:00",
        validation_start="2024-01-01T00:00:00+00:00",
        validation_end_exclusive="2025-01-01T00:00:00+00:00",
    ),
)


LEGACY_FROZEN_WALK_FORWARD_SPLITS: tuple[dict[str, str], ...] = (
    {
        "name": "march_april_to_may",
        "train_start": "2026-03-01T00:00:00+00:00",
        "train_end": "2026-04-30T23:59:59.999000+00:00",
        "validation_start": "2026-05-01T00:00:00+00:00",
        "validation_end": "2026-05-31T23:59:59.999000+00:00",
    },
    {
        "name": "march_may_to_june",
        "train_start": "2026-03-01T00:00:00+00:00",
        "train_end": "2026-05-31T23:59:59.999000+00:00",
        "validation_start": "2026-06-01T00:00:00+00:00",
        "validation_end": "2026-06-30T23:59:59.999000+00:00",
    },
    {
        "name": "march_june_to_july",
        "train_start": "2026-03-01T00:00:00+00:00",
        "train_end": "2026-06-30T23:59:59.999000+00:00",
        "validation_start": "2026-07-01T00:00:00+00:00",
        "validation_end": "DATA_MAX_TIMESTAMP",
    },
)


RANKING_PRIORITIES: tuple[str, ...] = (
    "validation performance across splits",
    "worst validation-period pnl",
    "maximum drawdown",
    "average pnl per trade",
    "sufficient trade count",
    "stop-hit rate",
    "total pnl",
    "nearby-configuration stability",
)


EXCLUDED_FROM_PHASE_1: tuple[str, ...] = (
    "ATR_MULT",
    "TRAIL_ATR_MULT",
    "MAX_HOLD_BARS",
    "position size",
    "cooldown",
    "market-state thresholds",
    "SHORT enablement",
    "event-risk behavior",
)


def contract_as_dict() -> dict[str, Any]:
    return {
        "fixed_settings": asdict(FIXED_SETTINGS),
        "search_controls": asdict(SEARCH_CONTROLS),
        "source_contract": SOURCE_CONTRACT,
        "final_out_of_sample": {
            "start": FINAL_OUT_OF_SAMPLE_START,
            "end_exclusive": FINAL_OUT_OF_SAMPLE_END_EXCLUSIVE,
        },
        "legacy_frozen_campaign": {
            "source_contract": LEGACY_FROZEN_SOURCE_CONTRACT,
            "research_data_max_timestamp": (
                LEGACY_FROZEN_RESEARCH_DATA_MAX_TIMESTAMP
            ),
            "walk_forward_splits": [
                dict(split)
                for split in LEGACY_FROZEN_WALK_FORWARD_SPLITS
            ],
        },
        "parameter_ranges": {
            name: asdict(spec)
            for name, spec in PARAMETER_RANGES.items()
        },
        "parameter_constraints": list(PARAMETER_CONSTRAINTS),
        "walk_forward_splits": [
            asdict(split)
            for split in WALK_FORWARD_SPLITS
        ],
        "ranking_priorities": list(RANKING_PRIORITIES),
        "excluded_from_phase_1": list(EXCLUDED_FROM_PHASE_1),
    }
