from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from files.research.historical_dataset import (
    HistoricalResearchDataset,
)


@dataclass(frozen=True)
class ReplaySegment:
    segment_id: str
    bars: pd.DataFrame
    tradable_start_ts_ms: int

    physical_start_boundary_type: str
    physical_end_boundary_type: str

    requested_start_applied: bool
    requested_end_applied: bool

    preceding_gap_id: str | None
    following_gap_id: str | None

    @property
    def bar_count(self) -> int:
        return int(len(self.bars))


@dataclass(frozen=True)
class ReplayPlan:
    gap_aware: bool
    segments: tuple[ReplaySegment, ...]

    @property
    def bars_total(self) -> int:
        return sum(
            segment.bar_count
            for segment in self.segments
        )


def build_research_replay_plan(
    *,
    dataset: HistoricalResearchDataset,
) -> ReplayPlan:
    segments = tuple(
        ReplaySegment(
            segment_id=segment.segment_id,
            bars=segment.bars,
            tradable_start_ts_ms=(
                segment.tradable_start_ts_ms
            ),
            physical_start_boundary_type=(
                segment.physical_start_boundary_type
            ),
            physical_end_boundary_type=(
                segment.physical_end_boundary_type
            ),
            requested_start_applied=(
                segment.requested_start_applied
            ),
            requested_end_applied=(
                segment.requested_end_applied
            ),
            preceding_gap_id=(
                segment.preceding_gap_id
            ),
            following_gap_id=(
                segment.following_gap_id
            ),
        )
        for segment in dataset.segments
    )

    if not segments:
        raise ValueError(
            "Historical research dataset produced no replay segments."
        )

    return ReplayPlan(
        gap_aware=True,
        segments=segments,
    )


def build_legacy_replay_plan(
    *,
    bars: pd.DataFrame,
    start_ts_ms: int | None,
    end_ts_ms: int | None,
    warmup_bars: int,
) -> ReplayPlan:
    if bars.empty:
        raise ValueError(
            "Legacy replay source contains no bars."
        )

    if warmup_bars < 0:
        raise ValueError(
            "warmup_bars must be non-negative."
        )

    replay_bars = bars.copy().reset_index(drop=True)

    timestamps = pd.to_datetime(
        replay_bars["timestamp"],
        utc=True,
        errors="raise",
    )

    if timestamps.isna().any():
        raise ValueError(
            "Legacy replay source contains null timestamps."
        )

    replay_bars["timestamp"] = timestamps

    ts_ms_all = (
        replay_bars["timestamp"].astype("int64")
        // 1_000_000
    ).astype("int64")

    tradable_start_ts_ms = (
        int(start_ts_ms)
        if start_ts_ms is not None
        else int(ts_ms_all.iloc[0])
    )

    if start_ts_ms is not None:
        indexes = replay_bars.index[
            ts_ms_all >= int(start_ts_ms)
        ].tolist()

        if not indexes:
            raise ValueError(
                f"START_TS_MS={start_ts_ms} is after the "
                "newest available bar."
            )

        first_tradable_index = int(indexes[0])
        replay_start_index = max(
            0,
            first_tradable_index - int(warmup_bars),
        )

        replay_bars = (
            replay_bars.iloc[replay_start_index:]
            .reset_index(drop=True)
        )

        ts_ms_all = (
            replay_bars["timestamp"].astype("int64")
            // 1_000_000
        ).astype("int64")

    if end_ts_ms is not None:
        replay_bars = (
            replay_bars.loc[
                ts_ms_all <= int(end_ts_ms)
            ]
            .reset_index(drop=True)
        )

    if replay_bars.empty:
        raise ValueError(
            "No legacy replay bars remain after applying bounds."
        )

    return ReplayPlan(
        gap_aware=False,
        segments=(
            ReplaySegment(
                segment_id="legacy_segment_001",
                bars=replay_bars,
                tradable_start_ts_ms=tradable_start_ts_ms,
                physical_start_boundary_type="dataset_start",
                physical_end_boundary_type="dataset_end",
                requested_start_applied=(
                    start_ts_ms is not None
                ),
                requested_end_applied=(
                    end_ts_ms is not None
                ),
                preceding_gap_id=None,
                following_gap_id=None,
            ),
        ),
    )
