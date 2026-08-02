from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timezone
from typing import Any

import pandas as pd

from files.config import TradingConfig
from files.research.historical_dataset import (
    HistoricalResearchDataset,
    HistoricalResearchSource,
    build_historical_research_dataset,
    load_and_resolve_historical_research_source,
)
from files.research.scorer_search_config import (
    MANIFEST_BACKED_SOURCE_CONTRACT,
    SOURCE_CONTRACT,
    WALK_FORWARD_SPLITS,
    WalkForwardSplit,
)


@dataclass(frozen=True)
class ResolvedWindowPlan:
    start: str
    end_exclusive: str

    start_ts_ms: int
    end_ts_ms_exclusive: int

    stored_bars_in_requested_window: int
    replay_bars_including_warmup: int
    warmup_bars_total: int
    structurally_eligible_bar_count: int

    physical_segment_count: int
    gap_count_crossed: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedWalkForwardSplit:
    name: str
    train: ResolvedWindowPlan
    validation: ResolvedWindowPlan

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


def _count_window_bars(
    *,
    dataset: HistoricalResearchDataset,
) -> int:
    start_ms = dataset.requested_range.requested_start_ts_ms
    end_exclusive_ms = (
        dataset.requested_range.requested_end_ts_ms_exclusive
    )

    timestamps_ms = (
        dataset.audit.bars["timestamp"].astype("int64")
        // 1_000_000
    )

    return int(
        (
            (timestamps_ms >= start_ms)
            & (timestamps_ms < end_exclusive_ms)
        ).sum()
    )


def _count_structurally_eligible_bars(
    *,
    dataset: HistoricalResearchDataset,
    min_bars: int,
) -> int:
    total = 0

    for segment in dataset.segments:
        timestamps_ms = (
            segment.bars["timestamp"].astype("int64")
            // 1_000_000
        )

        indexes = range(len(segment.bars))

        total += sum(
            1
            for index in indexes
            if (
                index + 1 >= min_bars
                and int(timestamps_ms.iloc[index])
                >= segment.tradable_start_ts_ms
            )
        )

    return int(total)


def _count_crossed_gaps(
    *,
    source: HistoricalResearchSource,
    start_ts_ms: int,
    end_ts_ms_exclusive: int,
) -> int:
    return sum(
        1
        for gap in source.audit.manifest.gaps
        if (
            start_ts_ms < gap.start_ts_ms
            and end_ts_ms_exclusive
            > gap.end_ts_ms_exclusive
        )
    )


def resolve_window_plan(
    *,
    source: HistoricalResearchSource,
    start: str,
    end_exclusive: str,
    warmup_bars: int,
    min_bars: int,
) -> ResolvedWindowPlan:
    start_timestamp = parse_utc_timestamp(start)
    end_exclusive_timestamp = parse_utc_timestamp(
        end_exclusive
    )

    start_ts_ms = timestamp_to_ms(start_timestamp)
    end_ts_ms_exclusive = timestamp_to_ms(
        end_exclusive_timestamp
    )

    if end_ts_ms_exclusive <= start_ts_ms:
        raise ValueError(
            "Window end-exclusive must be later than start."
        )

    inclusive_end_ts_ms = (
        end_ts_ms_exclusive - source.timeframe_step_ms
    )

    dataset = build_historical_research_dataset(
        audit=source.audit,
        start_ts_ms=start_ts_ms,
        end_ts_ms=inclusive_end_ts_ms,
        warmup_bars=warmup_bars,
    )

    replay_bars = dataset.replay_bar_count
    stored_bars = _count_window_bars(dataset=dataset)
    warmup_total = sum(
        int(
            (
                (
                    segment.bars["timestamp"].astype("int64")
                    // 1_000_000
                )
                < segment.tradable_start_ts_ms
            ).sum()
        )
        for segment in dataset.segments
    )

    structurally_eligible = (
        _count_structurally_eligible_bars(
            dataset=dataset,
            min_bars=min_bars,
        )
    )

    if replay_bars != warmup_total + stored_bars:
        raise RuntimeError(
            "Resolved replay-bar accounting invariant failed: "
            f"replay={replay_bars} "
            f"warmup={warmup_total} "
            f"stored={stored_bars}"
        )

    return ResolvedWindowPlan(
        start=start_timestamp.isoformat(),
        end_exclusive=end_exclusive_timestamp.isoformat(),
        start_ts_ms=start_ts_ms,
        end_ts_ms_exclusive=end_ts_ms_exclusive,
        stored_bars_in_requested_window=stored_bars,
        replay_bars_including_warmup=replay_bars,
        warmup_bars_total=warmup_total,
        structurally_eligible_bar_count=(
            structurally_eligible
        ),
        physical_segment_count=len(dataset.segments),
        gap_count_crossed=_count_crossed_gaps(
            source=source,
            start_ts_ms=start_ts_ms,
            end_ts_ms_exclusive=end_ts_ms_exclusive,
        ),
    )


def resolve_walk_forward_split(
    *,
    source: HistoricalResearchSource,
    split: WalkForwardSplit,
    warmup_bars: int,
    min_bars: int,
) -> ResolvedWalkForwardSplit:
    train = resolve_window_plan(
        source=source,
        start=split.train_start,
        end_exclusive=split.train_end_exclusive,
        warmup_bars=warmup_bars,
        min_bars=min_bars,
    )

    validation = resolve_window_plan(
        source=source,
        start=split.validation_start,
        end_exclusive=split.validation_end_exclusive,
        warmup_bars=warmup_bars,
        min_bars=min_bars,
    )

    if validation.start_ts_ms < train.end_ts_ms_exclusive:
        raise ValueError(
            f"{split.name}: training and validation windows overlap."
        )

    return ResolvedWalkForwardSplit(
        name=split.name,
        train=train,
        validation=validation,
    )


def resolve_walk_forward_splits(
    *,
    trading_config: TradingConfig,
) -> tuple[
    tuple[ResolvedWalkForwardSplit, ...],
    HistoricalResearchSource,
]:
    if SOURCE_CONTRACT != MANIFEST_BACKED_SOURCE_CONTRACT:
        raise RuntimeError(
            "New walk-forward planning requires "
            f"{MANIFEST_BACKED_SOURCE_CONTRACT!r}; "
            f"configured={SOURCE_CONTRACT!r}"
        )

    source = load_and_resolve_historical_research_source(
        data_tag=trading_config.data_tag,
        expected_symbol=trading_config.symbol,
        expected_timeframe=trading_config.timeframe,
    )

    warmup_bars = max(
        int(trading_config.min_bars),
        50,
    ) + 5

    resolved = tuple(
        resolve_walk_forward_split(
            source=source,
            split=split,
            warmup_bars=warmup_bars,
            min_bars=int(trading_config.min_bars),
        )
        for split in WALK_FORWARD_SPLITS
    )

    names = [split.name for split in resolved]

    if len(names) != len(set(names)):
        raise ValueError(
            "Walk-forward split names must be unique."
        )

    return resolved, source
