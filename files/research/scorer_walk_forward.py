from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from files.backtest.engine import (
    _load_all_ohlcv_parquet,
    _storage_symbol,
)
from files.config import TradingConfig
from files.research.scorer_search_config import (
    RESEARCH_DATA_MAX_TIMESTAMP,
    WALK_FORWARD_SPLITS,
    WalkForwardSplit,
)


DATA_MAX_TIMESTAMP_TOKEN = "DATA_MAX_TIMESTAMP"


@dataclass(frozen=True)
class ResolvedWalkForwardSplit:
    name: str

    train_start: str
    train_end: str

    validation_start: str
    validation_end: str

    train_start_ts_ms: int
    train_end_ts_ms: int

    validation_start_ts_ms: int
    validation_end_ts_ms: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_utc_timestamp(value: str) -> pd.Timestamp:
    text = value.strip()

    if not text:
        raise ValueError("Timestamp value must be non-empty.")

    parsed = pd.Timestamp(text)

    if parsed.tzinfo is None:
        parsed = parsed.tz_localize(timezone.utc)
    else:
        parsed = parsed.tz_convert(timezone.utc)

    return parsed


def timestamp_to_ms(value: pd.Timestamp) -> int:
    return int(value.value // 1_000_000)


def load_raw_timestamp_bounds(
    *,
    trading_config: TradingConfig,
) -> tuple[pd.Timestamp, pd.Timestamp, int]:
    storage_symbol = _storage_symbol(
        trading_config.symbol
    )

    bars = _load_all_ohlcv_parquet(
        exchange=trading_config.data_tag,
        symbol=storage_symbol,
        timeframe=trading_config.timeframe,
    )

    if len(bars) == 0:
        raise RuntimeError(
            "No raw bars available for walk-forward resolution."
        )

    timestamps = pd.to_datetime(
        bars["timestamp"],
        utc=True,
        errors="coerce",
    ).dropna()

    if len(timestamps) == 0:
        raise RuntimeError(
            "Raw bars contain no valid timestamps."
        )

    data_min = pd.Timestamp(timestamps.min())
    data_max = pd.Timestamp(timestamps.max())

    return data_min, data_max, int(len(timestamps))


def resolve_timestamp(
    *,
    value: str,
    data_max: pd.Timestamp,
) -> pd.Timestamp:
    if value == DATA_MAX_TIMESTAMP_TOKEN:
        return data_max

    return parse_utc_timestamp(value)


def validate_resolved_split(
    split: ResolvedWalkForwardSplit,
    *,
    data_min: pd.Timestamp,
    data_max: pd.Timestamp,
) -> None:
    data_min_ms = timestamp_to_ms(data_min)
    data_max_ms = timestamp_to_ms(data_max)

    if split.train_start_ts_ms < data_min_ms:
        raise ValueError(
            f"{split.name}: train_start precedes available data."
        )

    if split.validation_end_ts_ms > data_max_ms:
        raise ValueError(
            f"{split.name}: validation_end exceeds available data."
        )

    if split.train_end_ts_ms < split.train_start_ts_ms:
        raise ValueError(
            f"{split.name}: train_end precedes train_start."
        )

    if (
        split.validation_end_ts_ms
        < split.validation_start_ts_ms
    ):
        raise ValueError(
            f"{split.name}: validation_end precedes validation_start."
        )

    if (
        split.validation_start_ts_ms
        <= split.train_end_ts_ms
    ):
        raise ValueError(
            f"{split.name}: training and validation windows overlap."
        )


def resolve_walk_forward_split(
    *,
    split: WalkForwardSplit,
    data_min: pd.Timestamp,
    data_max: pd.Timestamp,
) -> ResolvedWalkForwardSplit:
    train_start = resolve_timestamp(
        value=split.train_start,
        data_max=data_max,
    )

    train_end = resolve_timestamp(
        value=split.train_end,
        data_max=data_max,
    )

    validation_start = resolve_timestamp(
        value=split.validation_start,
        data_max=data_max,
    )

    validation_end = resolve_timestamp(
        value=split.validation_end,
        data_max=data_max,
    )

    resolved = ResolvedWalkForwardSplit(
        name=split.name,
        train_start=train_start.isoformat(),
        train_end=train_end.isoformat(),
        validation_start=validation_start.isoformat(),
        validation_end=validation_end.isoformat(),
        train_start_ts_ms=timestamp_to_ms(train_start),
        train_end_ts_ms=timestamp_to_ms(train_end),
        validation_start_ts_ms=timestamp_to_ms(
            validation_start
        ),
        validation_end_ts_ms=timestamp_to_ms(
            validation_end
        ),
    )

    validate_resolved_split(
        resolved,
        data_min=data_min,
        data_max=data_max,
    )

    return resolved


def resolve_walk_forward_splits(
    *,
    trading_config: TradingConfig,
) -> tuple[
    tuple[ResolvedWalkForwardSplit, ...],
    pd.Timestamp,
    pd.Timestamp,
    int,
]:
    data_min, available_data_max, bar_count = (
        load_raw_timestamp_bounds(
            trading_config=trading_config
        )
    )

    frozen_data_max = parse_utc_timestamp(
        RESEARCH_DATA_MAX_TIMESTAMP
    )

    if frozen_data_max > available_data_max:
        raise RuntimeError(
            "Frozen research cutoff exceeds newest available raw bar: "
            f"cutoff={frozen_data_max.isoformat()} "
            f"available={available_data_max.isoformat()}"
        )

    storage_symbol = _storage_symbol(
        trading_config.symbol
    )

    frozen_bars = _load_all_ohlcv_parquet(
        exchange=trading_config.data_tag,
        symbol=storage_symbol,
        timeframe=trading_config.timeframe,
    )

    frozen_timestamps = pd.to_datetime(
        frozen_bars["timestamp"],
        utc=True,
        errors="coerce",
    ).dropna()

    frozen_bar_count = int(
        (frozen_timestamps <= frozen_data_max).sum()
    )

    resolved = tuple(
        resolve_walk_forward_split(
            split=split,
            data_min=data_min,
            data_max=frozen_data_max,
        )
        for split in WALK_FORWARD_SPLITS
    )

    names = [split.name for split in resolved]

    if len(names) != len(set(names)):
        raise ValueError(
            "Walk-forward split names must be unique."
        )

    return resolved, data_min, frozen_data_max, frozen_bar_count
