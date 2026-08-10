from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from files.data.historical_backfill import (
    build_ccxt_exchange,
    fetch_ohlcv_page_with_retries,
    timeframe_to_timedelta,
)
from files.data.paths import (
    historical_gap_manifest_path,
    safe_symbol,
)

SCHEMA_VERSION = 2

SOURCE_OUTAGE = "confirmed_source_outage"
PARTIAL_1M = "confirmed_timeframe_gap_partial_1m"
FULL_1M_PRESENT = "confirmed_timeframe_gap_1m_present"


@dataclass(frozen=True)
class HistoricalManifestBuildResult:
    manifest: dict[str, Any]
    output_path: Path | None


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def _load_stored_bars(
    *,
    data_root: Path,
    data_tag: str,
    symbol: str,
    timeframe: str,
) -> tuple[pd.DataFrame, tuple[Path, ...]]:
    root = (
        data_root
        / "raw"
        / data_tag
        / safe_symbol(symbol)
        / timeframe
    )

    paths = tuple(
        sorted(root.glob("date=*/bars.parquet"))
    )

    if not paths:
        raise RuntimeError(
            f"No historical partitions found under {root}"
        )

    frame = pd.concat(
        [pd.read_parquet(path) for path in paths],
        ignore_index=True,
    )

    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing_columns = required.difference(frame.columns)

    if missing_columns:
        raise RuntimeError(
            "Stored OHLCV is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    )

    frame = frame.sort_values(
        "timestamp"
    ).reset_index(drop=True)

    return frame, paths


def _group_missing_timestamps(
    missing: pd.DatetimeIndex,
    *,
    step: pd.Timedelta,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if len(missing) == 0:
        return []

    groups: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    group_start = pd.Timestamp(missing[0])
    previous = pd.Timestamp(missing[0])

    for raw_timestamp in missing[1:]:
        timestamp = pd.Timestamp(raw_timestamp)

        if timestamp != previous + step:
            groups.append(
                (
                    group_start,
                    previous + step,
                )
            )
            group_start = timestamp

        previous = timestamp

    groups.append(
        (
            group_start,
            previous + step,
        )
    )

    return groups


def _verify_one_minute_gap(
    *,
    exchange: Any,
    symbol: str,
    start_utc: pd.Timestamp,
    end_utc_exclusive: pd.Timestamp,
    max_page_attempts: int,
    initial_backoff_seconds: float,
) -> tuple[int, int, str]:
    step_ms = 60_000

    start_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc_exclusive.timestamp() * 1000)

    expected_count = int(
        (end_utc_exclusive - start_utc)
        / pd.Timedelta(minutes=1)
    )

    actual_ms: set[int] = set()
    since_ms = start_ms

    while since_ms < end_ms:
        rows = fetch_ohlcv_page_with_retries(
            exchange=exchange,
            symbol=symbol,
            timeframe="1m",
            since_ms=since_ms,
            page_limit=300,
            max_attempts=max_page_attempts,
            initial_backoff_seconds=initial_backoff_seconds,
        )

        if not rows:
            break

        raw_last_ms = int(rows[-1][0])

        for row in rows:
            row_ms = int(row[0])

            if start_ms <= row_ms < end_ms:
                actual_ms.add(row_ms)

        if raw_last_ms >= end_ms - step_ms:
            break

        next_since_ms = raw_last_ms + step_ms

        if next_since_ms <= since_ms:
            raise RuntimeError(
                "1m verification pagination did not advance"
            )

        since_ms = next_since_ms

    present_count = len(actual_ms)
    missing_count = expected_count - present_count

    if missing_count == expected_count:
        classification = SOURCE_OUTAGE
    elif missing_count == 0:
        classification = FULL_1M_PRESENT
    else:
        classification = PARTIAL_1M

    return expected_count, missing_count, classification


def build_historical_gap_manifest(
    *,
    source_exchange: str,
    data_tag: str,
    symbol: str,
    timeframe: str,
    dataset_start_utc: Any,
    dataset_end_utc_exclusive: Any,
    data_root: Path = Path("/work/data"),
    verify_one_minute: bool = True,
    max_page_attempts: int = 5,
    initial_backoff_seconds: float = 2.0,
) -> dict[str, Any]:
    start = _utc(dataset_start_utc)
    end = _utc(dataset_end_utc_exclusive)

    if end <= start:
        raise ValueError(
            "dataset_end_utc_exclusive must be later "
            "than dataset_start_utc"
        )

    step = timeframe_to_timedelta(timeframe)

    if (end - start) % step != pd.Timedelta(0):
        raise ValueError(
            "Dataset boundaries are not aligned to timeframe"
        )

    frame, partition_paths = _load_stored_bars(
        data_root=data_root,
        data_tag=data_tag,
        symbol=symbol,
        timeframe=timeframe,
    )

    timestamps = pd.DatetimeIndex(
        frame["timestamp"]
    )

    duplicate_count = int(
        timestamps.duplicated().sum()
    )

    if duplicate_count:
        raise RuntimeError(
            f"Stored dataset has {duplicate_count} duplicate timestamps"
        )

    if not timestamps.is_monotonic_increasing:
        raise RuntimeError(
            "Stored historical timestamps are not monotonic"
        )

    expected = pd.date_range(
        start=start,
        end=end - step,
        freq=step,
    )

    actual = timestamps[
        (timestamps >= start)
        & (timestamps < end)
    ]

    outside_count = len(timestamps) - len(actual)

    if outside_count:
        raise RuntimeError(
            "Stored dataset contains timestamps outside declared "
            f"boundaries: {outside_count}"
        )

    missing = expected.difference(actual)

    theoretical_bar_count = len(expected)
    stored_bar_count = len(actual)
    missing_bar_count = len(missing)

    if stored_bar_count + missing_bar_count != theoretical_bar_count:
        raise RuntimeError(
            "Historical row accounting does not reconcile"
        )

    gap_ranges = _group_missing_timestamps(
        missing,
        step=step,
    )

    exchange = None

    if verify_one_minute and gap_ranges:
        exchange = build_ccxt_exchange(
            source_exchange
        )

    gaps: list[dict[str, Any]] = []

    symbol_id = (
        symbol.lower()
        .replace("/", "")
        .replace("-", "")
        .replace("_", "")
    )

    for number, (
        gap_start,
        gap_end,
    ) in enumerate(
        gap_ranges,
        start=1,
    ):
        missing_timeframe_bars = int(
            (gap_end - gap_start) / step
        )

        if exchange is not None:
            (
                expected_1m,
                missing_1m,
                classification,
            ) = _verify_one_minute_gap(
                exchange=exchange,
                symbol=symbol,
                start_utc=gap_start,
                end_utc_exclusive=gap_end,
                max_page_attempts=max_page_attempts,
                initial_backoff_seconds=initial_backoff_seconds,
            )

            if expected_1m <= 0:
                raise RuntimeError(
                    "Invalid 1m verification interval"
                )
        else:
            missing_1m = 0
            classification = FULL_1M_PRESENT

        gaps.append(
            {
                "gap_id": (
                    f"{source_exchange}_{symbol_id}_"
                    f"{timeframe}_gap_{number:03d}"
                ),
                "start_utc": gap_start.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "end_utc_exclusive": gap_end.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                f"missing_{timeframe}_bars": (
                    missing_timeframe_bars
                ),
                "missing_1m_bars": int(missing_1m),
                "classification": classification,
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": "confirmed",
        "source_exchange": source_exchange,
        "symbol": symbol,
        "timeframe": timeframe,
        "data_tag": data_tag,
        "dataset_start_utc": start.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "dataset_end_utc_exclusive": end.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "theoretical_bar_count": theoretical_bar_count,
        "stored_bar_count": stored_bar_count,
        "missing_bar_count": missing_bar_count,
        "duplicate_timestamp_count": duplicate_count,
        "partition_count": len(partition_paths),
        "verification": {
            "five_minute_feed_checked": True,
            "one_minute_feed_checked": bool(
                verify_one_minute
            ),
            "synthetic_bars_created": False,
            "cross_exchange_substitution_used": False,
        },
        "gaps": gaps,
    }

    return manifest


def write_historical_gap_manifest(
    *,
    manifest: dict[str, Any],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = output_path.with_suffix(
        output_path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(output_path)

    return output_path


def canonical_manifest_path(
    *,
    data_tag: str,
) -> Path:
    return historical_gap_manifest_path(
        data_tag=data_tag
    )
