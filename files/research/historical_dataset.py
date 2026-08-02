from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from files.data.historical_backfill import (
    normalize_utc_timestamp,
    timeframe_to_timedelta,
    timestamp_to_milliseconds,
)
from files.data.paths import (
    historical_gap_manifest_path,
    raw_symbol_dir,
)


SUPPORTED_GAP_MANIFEST_SCHEMA_VERSION = 1
CONFIRMED_MANIFEST_STATUS = "confirmed"
CONFIRMED_GAP_CLASSIFICATION = "confirmed_source_outage"


class HistoricalDatasetContractError(RuntimeError):
    """Raised when a historical dataset contract is missing or invalid."""


@dataclass(frozen=True)
class HistoricalGap:
    gap_id: str
    start_utc: pd.Timestamp
    end_utc_exclusive: pd.Timestamp
    missing_bar_count: int
    missing_1m_bar_count: int
    classification: str

    @property
    def start_ts_ms(self) -> int:
        return timestamp_to_milliseconds(self.start_utc)

    @property
    def end_ts_ms_exclusive(self) -> int:
        return timestamp_to_milliseconds(
            self.end_utc_exclusive
        )


@dataclass(frozen=True)
class HistoricalDatasetManifest:
    schema_version: int
    status: str
    source_exchange: str
    symbol: str
    timeframe: str
    data_tag: str

    dataset_start_utc: pd.Timestamp
    dataset_end_utc_exclusive: pd.Timestamp

    theoretical_bar_count: int
    stored_bar_count: int
    missing_bar_count: int
    duplicate_timestamp_count: int
    partition_count: int

    five_minute_feed_checked: bool
    one_minute_feed_checked: bool
    synthetic_bars_created: bool
    cross_exchange_substitution_used: bool

    gaps: tuple[HistoricalGap, ...]
    source_path: Path

    @property
    def dataset_start_ts_ms(self) -> int:
        return timestamp_to_milliseconds(
            self.dataset_start_utc
        )

    @property
    def dataset_end_ts_ms_exclusive(self) -> int:
        return timestamp_to_milliseconds(
            self.dataset_end_utc_exclusive
        )


def _require_mapping(
    value: Any,
    *,
    name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HistoricalDatasetContractError(
            f"{name} must be a JSON object."
        )

    return value


def _require_list(
    value: Any,
    *,
    name: str,
) -> list[Any]:
    if not isinstance(value, list):
        raise HistoricalDatasetContractError(
            f"{name} must be a JSON array."
        )

    return value


def _require_string(
    value: Any,
    *,
    name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalDatasetContractError(
            f"{name} must be a non-empty string."
        )

    return value.strip()


def _require_int(
    value: Any,
    *,
    name: str,
    minimum: int = 0,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoricalDatasetContractError(
            f"{name} must be an integer."
        )

    if value < minimum:
        raise HistoricalDatasetContractError(
            f"{name} must be at least {minimum}."
        )

    return int(value)


def _require_bool(
    value: Any,
    *,
    name: str,
) -> bool:
    if not isinstance(value, bool):
        raise HistoricalDatasetContractError(
            f"{name} must be a boolean."
        )

    return bool(value)


def _parse_timestamp(
    value: Any,
    *,
    name: str,
) -> pd.Timestamp:
    try:
        return normalize_utc_timestamp(
            value,
            name=name,
        )
    except Exception as exc:
        raise HistoricalDatasetContractError(
            f"{name} is not a valid UTC timestamp."
        ) from exc


def _validate_timestamp_alignment(
    timestamp: pd.Timestamp,
    *,
    dataset_start: pd.Timestamp,
    step: pd.Timedelta,
    name: str,
) -> None:
    offset = timestamp - dataset_start

    if offset < pd.Timedelta(0):
        raise HistoricalDatasetContractError(
            f"{name} precedes dataset_start_utc."
        )

    if offset % step != pd.Timedelta(0):
        raise HistoricalDatasetContractError(
            f"{name} is not aligned to timeframe boundaries."
        )


def _parse_gap(
    raw_gap: Any,
    *,
    index: int,
    dataset_start: pd.Timestamp,
    dataset_end_exclusive: pd.Timestamp,
    step: pd.Timedelta,
    timeframe: str,
) -> HistoricalGap:
    gap = _require_mapping(
        raw_gap,
        name=f"gaps[{index}]",
    )

    gap_id = _require_string(
        gap.get("gap_id"),
        name=f"gaps[{index}].gap_id",
    )

    start = _parse_timestamp(
        gap.get("start_utc"),
        name=f"gaps[{index}].start_utc",
    )

    end = _parse_timestamp(
        gap.get("end_utc_exclusive"),
        name=f"gaps[{index}].end_utc_exclusive",
    )

    if end <= start:
        raise HistoricalDatasetContractError(
            f"{gap_id}: end_utc_exclusive must be later than start_utc."
        )

    if start < dataset_start:
        raise HistoricalDatasetContractError(
            f"{gap_id}: gap starts before the dataset."
        )

    if end > dataset_end_exclusive:
        raise HistoricalDatasetContractError(
            f"{gap_id}: gap ends after the dataset."
        )

    _validate_timestamp_alignment(
        start,
        dataset_start=dataset_start,
        step=step,
        name=f"{gap_id}.start_utc",
    )

    _validate_timestamp_alignment(
        end,
        dataset_start=dataset_start,
        step=step,
        name=f"{gap_id}.end_utc_exclusive",
    )

    missing_bar_count = _require_int(
        gap.get(f"missing_{timeframe}_bars"),
        name=f"{gap_id}.missing_{timeframe}_bars",
        minimum=1,
    )

    missing_1m_bar_count = _require_int(
        gap.get("missing_1m_bars"),
        name=f"{gap_id}.missing_1m_bars",
        minimum=1,
    )

    classification = _require_string(
        gap.get("classification"),
        name=f"{gap_id}.classification",
    )

    if classification != CONFIRMED_GAP_CLASSIFICATION:
        raise HistoricalDatasetContractError(
            f"{gap_id}: unsupported classification "
            f"{classification!r}."
        )

    duration = end - start
    calculated_missing = int(duration // step)

    if duration % step != pd.Timedelta(0):
        raise HistoricalDatasetContractError(
            f"{gap_id}: duration is not an exact multiple "
            f"of timeframe {timeframe!r}."
        )

    if calculated_missing != missing_bar_count:
        raise HistoricalDatasetContractError(
            f"{gap_id}: declared missing count "
            f"{missing_bar_count} does not match duration-derived "
            f"count {calculated_missing}."
        )

    return HistoricalGap(
        gap_id=gap_id,
        start_utc=start,
        end_utc_exclusive=end,
        missing_bar_count=missing_bar_count,
        missing_1m_bar_count=missing_1m_bar_count,
        classification=classification,
    )


def _validate_gap_sequence(
    gaps: tuple[HistoricalGap, ...],
) -> None:
    seen_ids: set[str] = set()
    previous: HistoricalGap | None = None

    for gap in gaps:
        if gap.gap_id in seen_ids:
            raise HistoricalDatasetContractError(
                f"Duplicate gap_id: {gap.gap_id!r}."
            )

        seen_ids.add(gap.gap_id)

        if previous is not None:
            if gap.start_utc < previous.start_utc:
                raise HistoricalDatasetContractError(
                    "Gaps must be ordered by start_utc."
                )

            if gap.start_utc < previous.end_utc_exclusive:
                raise HistoricalDatasetContractError(
                    f"Gaps overlap: {previous.gap_id!r} and "
                    f"{gap.gap_id!r}."
                )

        previous = gap


def load_historical_dataset_manifest(
    *,
    data_tag: str,
    expected_symbol: str | None = None,
    expected_timeframe: str | None = None,
    manifest_path: Path | None = None,
) -> HistoricalDatasetManifest:
    path = (
        Path(manifest_path)
        if manifest_path is not None
        else historical_gap_manifest_path(
            data_tag=data_tag
        )
    )

    if not path.is_file():
        raise HistoricalDatasetContractError(
            f"Historical dataset manifest not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except json.JSONDecodeError as exc:
        raise HistoricalDatasetContractError(
            f"Historical dataset manifest is invalid JSON: {path}"
        ) from exc
    except OSError as exc:
        raise HistoricalDatasetContractError(
            f"Unable to read historical dataset manifest: {path}"
        ) from exc

    root = _require_mapping(
        raw,
        name="manifest",
    )

    schema_version = _require_int(
        root.get("schema_version"),
        name="schema_version",
        minimum=1,
    )

    if (
        schema_version
        != SUPPORTED_GAP_MANIFEST_SCHEMA_VERSION
    ):
        raise HistoricalDatasetContractError(
            "Unsupported historical gap manifest schema_version: "
            f"{schema_version}"
        )

    status = _require_string(
        root.get("status"),
        name="status",
    )

    if status != CONFIRMED_MANIFEST_STATUS:
        raise HistoricalDatasetContractError(
            f"Manifest status must be "
            f"{CONFIRMED_MANIFEST_STATUS!r}; got {status!r}."
        )

    manifest_data_tag = _require_string(
        root.get("data_tag"),
        name="data_tag",
    )

    if manifest_data_tag != data_tag:
        raise HistoricalDatasetContractError(
            "Manifest data_tag does not match requested data_tag: "
            f"manifest={manifest_data_tag!r} requested={data_tag!r}"
        )

    source_exchange = _require_string(
        root.get("source_exchange"),
        name="source_exchange",
    )

    symbol = _require_string(
        root.get("symbol"),
        name="symbol",
    )

    timeframe = _require_string(
        root.get("timeframe"),
        name="timeframe",
    )

    if (
        expected_symbol is not None
        and symbol != expected_symbol
    ):
        raise HistoricalDatasetContractError(
            "Manifest symbol does not match expected symbol: "
            f"manifest={symbol!r} expected={expected_symbol!r}"
        )

    if (
        expected_timeframe is not None
        and timeframe != expected_timeframe
    ):
        raise HistoricalDatasetContractError(
            "Manifest timeframe does not match expected timeframe: "
            f"manifest={timeframe!r} "
            f"expected={expected_timeframe!r}"
        )

    step = timeframe_to_timedelta(timeframe)

    dataset_start = _parse_timestamp(
        root.get("dataset_start_utc"),
        name="dataset_start_utc",
    )

    dataset_end_exclusive = _parse_timestamp(
        root.get("dataset_end_utc_exclusive"),
        name="dataset_end_utc_exclusive",
    )

    if dataset_end_exclusive <= dataset_start:
        raise HistoricalDatasetContractError(
            "dataset_end_utc_exclusive must be later than "
            "dataset_start_utc."
        )

    if (
        (dataset_end_exclusive - dataset_start)
        % step
        != pd.Timedelta(0)
    ):
        raise HistoricalDatasetContractError(
            "Dataset duration is not an exact multiple of the "
            "declared timeframe."
        )

    theoretical_bar_count = _require_int(
        root.get("theoretical_bar_count"),
        name="theoretical_bar_count",
        minimum=1,
    )

    stored_bar_count = _require_int(
        root.get("stored_bar_count"),
        name="stored_bar_count",
        minimum=0,
    )

    missing_bar_count = _require_int(
        root.get("missing_bar_count"),
        name="missing_bar_count",
        minimum=0,
    )

    duplicate_timestamp_count = _require_int(
        root.get("duplicate_timestamp_count"),
        name="duplicate_timestamp_count",
        minimum=0,
    )

    partition_count = _require_int(
        root.get("partition_count"),
        name="partition_count",
        minimum=1,
    )

    duration_theoretical_count = int(
        (dataset_end_exclusive - dataset_start) // step
    )

    if duration_theoretical_count != theoretical_bar_count:
        raise HistoricalDatasetContractError(
            "theoretical_bar_count does not match dataset duration: "
            f"declared={theoretical_bar_count} "
            f"calculated={duration_theoretical_count}"
        )

    if (
        stored_bar_count + missing_bar_count
        != theoretical_bar_count
    ):
        raise HistoricalDatasetContractError(
            "stored_bar_count + missing_bar_count must equal "
            "theoretical_bar_count."
        )

    verification = _require_mapping(
        root.get("verification"),
        name="verification",
    )

    five_minute_feed_checked = _require_bool(
        verification.get("five_minute_feed_checked"),
        name="verification.five_minute_feed_checked",
    )

    one_minute_feed_checked = _require_bool(
        verification.get("one_minute_feed_checked"),
        name="verification.one_minute_feed_checked",
    )

    synthetic_bars_created = _require_bool(
        verification.get("synthetic_bars_created"),
        name="verification.synthetic_bars_created",
    )

    cross_exchange_substitution_used = _require_bool(
        verification.get("cross_exchange_substitution_used"),
        name="verification.cross_exchange_substitution_used",
    )

    raw_gaps = _require_list(
        root.get("gaps"),
        name="gaps",
    )

    gaps = tuple(
        _parse_gap(
            raw_gap,
            index=index,
            dataset_start=dataset_start,
            dataset_end_exclusive=dataset_end_exclusive,
            step=step,
            timeframe=timeframe,
        )
        for index, raw_gap in enumerate(raw_gaps)
    )

    _validate_gap_sequence(gaps)

    declared_gap_total = sum(
        gap.missing_bar_count
        for gap in gaps
    )

    if declared_gap_total != missing_bar_count:
        raise HistoricalDatasetContractError(
            "Sum of declared gap counts does not match "
            "missing_bar_count: "
            f"gaps={declared_gap_total} "
            f"manifest={missing_bar_count}"
        )

    return HistoricalDatasetManifest(
        schema_version=schema_version,
        status=status,
        source_exchange=source_exchange,
        symbol=symbol,
        timeframe=timeframe,
        data_tag=manifest_data_tag,
        dataset_start_utc=dataset_start,
        dataset_end_utc_exclusive=dataset_end_exclusive,
        theoretical_bar_count=theoretical_bar_count,
        stored_bar_count=stored_bar_count,
        missing_bar_count=missing_bar_count,
        duplicate_timestamp_count=duplicate_timestamp_count,
        partition_count=partition_count,
        five_minute_feed_checked=five_minute_feed_checked,
        one_minute_feed_checked=one_minute_feed_checked,
        synthetic_bars_created=synthetic_bars_created,
        cross_exchange_substitution_used=(
            cross_exchange_substitution_used
        ),
        gaps=gaps,
        source_path=path,
    )


REQUIRED_OHLCV_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


@dataclass(frozen=True)
class HistoricalDatasetAudit:
    manifest: HistoricalDatasetManifest
    bars: pd.DataFrame
    partition_paths: tuple[Path, ...]

    @property
    def partition_count(self) -> int:
        return len(self.partition_paths)

    @property
    def stored_bar_count(self) -> int:
        return int(len(self.bars))

    @property
    def first_timestamp(self) -> pd.Timestamp:
        if self.bars.empty:
            raise HistoricalDatasetContractError(
                "Audited historical dataset contains no bars."
            )

        return pd.Timestamp(
            self.bars["timestamp"].iloc[0]
        )

    @property
    def last_timestamp(self) -> pd.Timestamp:
        if self.bars.empty:
            raise HistoricalDatasetContractError(
                "Audited historical dataset contains no bars."
            )

        return pd.Timestamp(
            self.bars["timestamp"].iloc[-1]
        )


def _read_strict_ohlcv_partition(
    path: Path,
) -> pd.DataFrame:
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:
        raise HistoricalDatasetContractError(
            f"Unable to read historical partition: {path}"
        ) from exc

    actual_columns = tuple(str(column) for column in frame.columns)

    if actual_columns != REQUIRED_OHLCV_COLUMNS:
        raise HistoricalDatasetContractError(
            f"Historical partition has unexpected columns: {path}; "
            f"expected={list(REQUIRED_OHLCV_COLUMNS)!r} "
            f"actual={list(actual_columns)!r}"
        )

    frame = frame.loc[:, REQUIRED_OHLCV_COLUMNS].copy()

    try:
        frame["timestamp"] = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        )
    except Exception as exc:
        raise HistoricalDatasetContractError(
            f"Historical partition contains an invalid timestamp: "
            f"{path}"
        ) from exc

    if frame["timestamp"].isna().any():
        raise HistoricalDatasetContractError(
            f"Historical partition contains a null timestamp: {path}"
        )

    for column in REQUIRED_OHLCV_COLUMNS[1:]:
        try:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="raise",
            ).astype(float)
        except Exception as exc:
            raise HistoricalDatasetContractError(
                f"Historical partition contains invalid numeric "
                f"values in {column!r}: {path}"
            ) from exc

        if frame[column].isna().any():
            raise HistoricalDatasetContractError(
                f"Historical partition contains null values in "
                f"{column!r}: {path}"
            )

    return frame


def _validate_audited_timestamp_grid(
    timestamps: pd.Series,
    *,
    manifest: HistoricalDatasetManifest,
) -> None:
    step = timeframe_to_timedelta(
        manifest.timeframe
    )

    offsets = timestamps - manifest.dataset_start_utc
    misaligned = offsets.mod(step) != pd.Timedelta(0)

    if bool(misaligned.any()):
        first_bad_index = misaligned[misaligned].index[0]
        first_bad = pd.Timestamp(
            timestamps.loc[first_bad_index]
        )

        raise HistoricalDatasetContractError(
            "Historical dataset contains a timestamp that is not "
            "aligned to the manifest timeframe grid: "
            f"{first_bad.isoformat()}"
        )


def _validate_no_bars_inside_declared_gaps(
    timestamps: pd.Series,
    *,
    manifest: HistoricalDatasetManifest,
) -> None:
    for gap in manifest.gaps:
        inside = (
            (timestamps >= gap.start_utc)
            & (timestamps < gap.end_utc_exclusive)
        )

        if bool(inside.any()):
            stored_inside = [
                pd.Timestamp(value).isoformat()
                for value in timestamps.loc[inside].head(10)
            ]

            raise HistoricalDatasetContractError(
                f"{gap.gap_id}: stored timestamps exist inside "
                f"the declared gap: {stored_inside}"
            )


def _validate_gap_adjacency(
    timestamp_set: set[pd.Timestamp],
    *,
    manifest: HistoricalDatasetManifest,
) -> None:
    step = timeframe_to_timedelta(
        manifest.timeframe
    )

    for gap in manifest.gaps:
        previous_timestamp = gap.start_utc - step
        resumed_timestamp = gap.end_utc_exclusive

        if previous_timestamp not in timestamp_set:
            raise HistoricalDatasetContractError(
                f"{gap.gap_id}: expected preceding bar is missing: "
                f"{previous_timestamp.isoformat()}"
            )

        if resumed_timestamp not in timestamp_set:
            raise HistoricalDatasetContractError(
                f"{gap.gap_id}: expected resumed bar is missing: "
                f"{resumed_timestamp.isoformat()}"
            )


def audit_historical_dataset(
    *,
    manifest: HistoricalDatasetManifest,
) -> HistoricalDatasetAudit:
    root = raw_symbol_dir(
        exchange=manifest.data_tag,
        symbol=manifest.symbol,
        timeframe=manifest.timeframe,
    )

    if not root.is_dir():
        raise HistoricalDatasetContractError(
            f"Historical dataset directory not found: {root}"
        )

    partition_paths = tuple(
        sorted(root.glob("date=*/bars.parquet"))
    )

    if not partition_paths:
        raise HistoricalDatasetContractError(
            f"No historical Parquet partitions found: {root}"
        )

    if len(partition_paths) != manifest.partition_count:
        raise HistoricalDatasetContractError(
            "Historical partition count does not match manifest: "
            f"actual={len(partition_paths)} "
            f"manifest={manifest.partition_count}"
        )

    partition_frames = [
        _read_strict_ohlcv_partition(path)
        for path in partition_paths
    ]

    bars = pd.concat(
        partition_frames,
        ignore_index=True,
    )

    if bars.empty:
        raise HistoricalDatasetContractError(
            "Historical dataset contains no stored bars."
        )

    duplicate_mask = bars["timestamp"].duplicated(
        keep=False
    )
    duplicate_count = int(
        bars["timestamp"].duplicated(
            keep="first"
        ).sum()
    )

    if duplicate_count != manifest.duplicate_timestamp_count:
        duplicate_examples = [
            pd.Timestamp(value).isoformat()
            for value in (
                bars.loc[duplicate_mask, "timestamp"]
                .drop_duplicates()
                .head(10)
            )
        ]

        raise HistoricalDatasetContractError(
            "Historical duplicate timestamp count does not match "
            "manifest: "
            f"actual={duplicate_count} "
            f"manifest={manifest.duplicate_timestamp_count} "
            f"examples={duplicate_examples}"
        )

    if duplicate_count > 0:
        raise HistoricalDatasetContractError(
            "Historical dataset contains duplicate timestamps; "
            "research audit requires unique stored bars."
        )

    bars = bars.sort_values(
        "timestamp",
        kind="mergesort",
    ).reset_index(drop=True)

    if len(bars) != manifest.stored_bar_count:
        raise HistoricalDatasetContractError(
            "Historical stored bar count does not match manifest: "
            f"actual={len(bars)} "
            f"manifest={manifest.stored_bar_count}"
        )

    timestamps = bars["timestamp"]

    before_dataset = (
        timestamps < manifest.dataset_start_utc
    )
    after_dataset = (
        timestamps >= manifest.dataset_end_utc_exclusive
    )

    if bool(before_dataset.any()) or bool(after_dataset.any()):
        first_timestamp = pd.Timestamp(
            timestamps.iloc[0]
        )
        last_timestamp = pd.Timestamp(
            timestamps.iloc[-1]
        )

        raise HistoricalDatasetContractError(
            "Historical dataset contains bars outside manifest "
            "bounds: "
            f"first={first_timestamp.isoformat()} "
            f"last={last_timestamp.isoformat()} "
            f"contract=[{manifest.dataset_start_utc.isoformat()}, "
            f"{manifest.dataset_end_utc_exclusive.isoformat()})"
        )

    _validate_audited_timestamp_grid(
        timestamps,
        manifest=manifest,
    )

    _validate_no_bars_inside_declared_gaps(
        timestamps,
        manifest=manifest,
    )

    timestamp_set = {
        pd.Timestamp(value)
        for value in timestamps
    }

    _validate_gap_adjacency(
        timestamp_set,
        manifest=manifest,
    )

    step = timeframe_to_timedelta(
        manifest.timeframe
    )

    expected_first = manifest.dataset_start_utc
    expected_last = (
        manifest.dataset_end_utc_exclusive - step
    )

    actual_first = pd.Timestamp(
        timestamps.iloc[0]
    )
    actual_last = pd.Timestamp(
        timestamps.iloc[-1]
    )

    if actual_first != expected_first:
        raise HistoricalDatasetContractError(
            "Historical dataset does not begin at the manifest "
            "dataset_start_utc: "
            f"actual={actual_first.isoformat()} "
            f"expected={expected_first.isoformat()}"
        )

    if actual_last != expected_last:
        raise HistoricalDatasetContractError(
            "Historical dataset does not end at the final expected "
            "timestamp: "
            f"actual={actual_last.isoformat()} "
            f"expected={expected_last.isoformat()}"
        )

    observed_missing_count = 0
    timestamp_values = timestamps.to_numpy()

    if len(timestamp_values) > 1:
        timestamp_deltas = (
            timestamps.iloc[1:].reset_index(drop=True)
            - timestamps.iloc[:-1].reset_index(drop=True)
        )

        observed_missing_count = int(
            (
                timestamp_deltas // step
                - 1
            ).sum()
        )

    if observed_missing_count != manifest.missing_bar_count:
        raise HistoricalDatasetContractError(
            "Observed missing-bar count does not match manifest: "
            f"actual={observed_missing_count} "
            f"manifest={manifest.missing_bar_count}"
        )

    return HistoricalDatasetAudit(
        manifest=manifest,
        bars=bars,
        partition_paths=partition_paths,
    )


def load_and_audit_historical_dataset(
    *,
    data_tag: str,
    expected_symbol: str,
    expected_timeframe: str,
    manifest_path: Path | None = None,
) -> HistoricalDatasetAudit:
    manifest = load_historical_dataset_manifest(
        data_tag=data_tag,
        expected_symbol=expected_symbol,
        expected_timeframe=expected_timeframe,
        manifest_path=manifest_path,
    )

    return audit_historical_dataset(
        manifest=manifest,
    )



PHYSICAL_DATASET_START = "dataset_start"
PHYSICAL_GAP_BOUNDARY = "gap_boundary"
PHYSICAL_DATASET_END = "dataset_end"


@dataclass(frozen=True)
class HistoricalResearchRange:
    requested_start_ts_ms: int
    requested_end_ts_ms: int
    requested_end_ts_ms_exclusive: int

    @property
    def requested_start_utc(self) -> pd.Timestamp:
        return pd.to_datetime(
            self.requested_start_ts_ms,
            unit="ms",
            utc=True,
        )

    @property
    def requested_end_utc(self) -> pd.Timestamp:
        return pd.to_datetime(
            self.requested_end_ts_ms,
            unit="ms",
            utc=True,
        )

    @property
    def requested_end_utc_exclusive(self) -> pd.Timestamp:
        return pd.to_datetime(
            self.requested_end_ts_ms_exclusive,
            unit="ms",
            utc=True,
        )


@dataclass(frozen=True)
class HistoricalPhysicalSegment:
    segment_id: str

    physical_start_utc: pd.Timestamp
    physical_end_utc_exclusive: pd.Timestamp

    physical_start_boundary_type: str
    physical_end_boundary_type: str

    preceding_gap_id: str | None
    following_gap_id: str | None

    @property
    def physical_start_ts_ms(self) -> int:
        return timestamp_to_milliseconds(
            self.physical_start_utc
        )

    @property
    def physical_end_ts_ms_exclusive(self) -> int:
        return timestamp_to_milliseconds(
            self.physical_end_utc_exclusive
        )


@dataclass(frozen=True)
class HistoricalResearchSegment:
    segment_id: str

    physical_start_utc: pd.Timestamp
    physical_end_utc_exclusive: pd.Timestamp

    replay_start_utc: pd.Timestamp
    replay_end_utc_exclusive: pd.Timestamp
    tradable_start_utc: pd.Timestamp

    physical_start_boundary_type: str
    physical_end_boundary_type: str

    requested_start_applied: bool
    requested_end_applied: bool

    preceding_gap_id: str | None
    following_gap_id: str | None

    bars: pd.DataFrame

    @property
    def replay_start_ts_ms(self) -> int:
        return timestamp_to_milliseconds(
            self.replay_start_utc
        )

    @property
    def replay_end_ts_ms_exclusive(self) -> int:
        return timestamp_to_milliseconds(
            self.replay_end_utc_exclusive
        )

    @property
    def tradable_start_ts_ms(self) -> int:
        return timestamp_to_milliseconds(
            self.tradable_start_utc
        )

    @property
    def bar_count(self) -> int:
        return int(len(self.bars))


@dataclass(frozen=True)
class HistoricalResearchDataset:
    audit: HistoricalDatasetAudit
    requested_range: HistoricalResearchRange
    warmup_bars: int
    segments: tuple[HistoricalResearchSegment, ...]

    @property
    def replay_bar_count(self) -> int:
        return sum(
            segment.bar_count
            for segment in self.segments
        )


def normalize_research_range(
    *,
    audit: HistoricalDatasetAudit,
    start_ts_ms: int | None,
    end_ts_ms: int | None,
) -> HistoricalResearchRange:
    step_ms = int(
        timeframe_to_timedelta(
            audit.manifest.timeframe
        ).total_seconds()
        * 1000
    )

    dataset_start_ms = (
        audit.manifest.dataset_start_ts_ms
    )
    dataset_end_exclusive_ms = (
        audit.manifest.dataset_end_ts_ms_exclusive
    )
    dataset_last_ms = (
        dataset_end_exclusive_ms - step_ms
    )

    requested_start_ms = (
        dataset_start_ms
        if start_ts_ms is None
        else int(start_ts_ms)
    )

    requested_end_ms = (
        dataset_last_ms
        if end_ts_ms is None
        else int(end_ts_ms)
    )

    if requested_start_ms < dataset_start_ms:
        raise HistoricalDatasetContractError(
            "Requested start precedes the historical dataset: "
            f"requested={requested_start_ms} "
            f"dataset_start={dataset_start_ms}"
        )

    if requested_start_ms >= dataset_end_exclusive_ms:
        raise HistoricalDatasetContractError(
            "Requested start is at or after the historical "
            "dataset end."
        )

    if requested_end_ms < dataset_start_ms:
        raise HistoricalDatasetContractError(
            "Requested end precedes the historical dataset."
        )

    if requested_end_ms > dataset_last_ms:
        raise HistoricalDatasetContractError(
            "Requested inclusive end exceeds the final stored "
            "timeframe slot: "
            f"requested={requested_end_ms} "
            f"maximum={dataset_last_ms}"
        )

    if requested_end_ms < requested_start_ms:
        raise HistoricalDatasetContractError(
            "Requested end must be greater than or equal to "
            "requested start."
        )

    if (
        (requested_start_ms - dataset_start_ms)
        % step_ms
        != 0
    ):
        raise HistoricalDatasetContractError(
            "Requested start is not aligned to the historical "
            "dataset timeframe grid."
        )

    if (
        (requested_end_ms - dataset_start_ms)
        % step_ms
        != 0
    ):
        raise HistoricalDatasetContractError(
            "Requested end is not aligned to the historical "
            "dataset timeframe grid."
        )

    return HistoricalResearchRange(
        requested_start_ts_ms=requested_start_ms,
        requested_end_ts_ms=requested_end_ms,
        requested_end_ts_ms_exclusive=(
            requested_end_ms + step_ms
        ),
    )


def build_physical_segments(
    *,
    manifest: HistoricalDatasetManifest,
) -> tuple[HistoricalPhysicalSegment, ...]:
    segments: list[HistoricalPhysicalSegment] = []

    segment_start = manifest.dataset_start_utc
    start_boundary_type = PHYSICAL_DATASET_START
    preceding_gap_id: str | None = None

    for index, gap in enumerate(
        manifest.gaps,
        start=1,
    ):
        if segment_start < gap.start_utc:
            segments.append(
                HistoricalPhysicalSegment(
                    segment_id=f"segment_{index:03d}",
                    physical_start_utc=segment_start,
                    physical_end_utc_exclusive=gap.start_utc,
                    physical_start_boundary_type=(
                        start_boundary_type
                    ),
                    physical_end_boundary_type=(
                        PHYSICAL_GAP_BOUNDARY
                    ),
                    preceding_gap_id=preceding_gap_id,
                    following_gap_id=gap.gap_id,
                )
            )

        segment_start = gap.end_utc_exclusive
        start_boundary_type = PHYSICAL_GAP_BOUNDARY
        preceding_gap_id = gap.gap_id

    if segment_start < manifest.dataset_end_utc_exclusive:
        segments.append(
            HistoricalPhysicalSegment(
                segment_id=(
                    f"segment_{len(segments) + 1:03d}"
                ),
                physical_start_utc=segment_start,
                physical_end_utc_exclusive=(
                    manifest.dataset_end_utc_exclusive
                ),
                physical_start_boundary_type=(
                    start_boundary_type
                ),
                physical_end_boundary_type=(
                    PHYSICAL_DATASET_END
                ),
                preceding_gap_id=preceding_gap_id,
                following_gap_id=None,
            )
        )

    if not segments:
        raise HistoricalDatasetContractError(
            "Historical manifest produced no physical segments."
        )

    return tuple(segments)


def build_historical_research_dataset(
    *,
    audit: HistoricalDatasetAudit,
    start_ts_ms: int | None,
    end_ts_ms: int | None,
    warmup_bars: int,
) -> HistoricalResearchDataset:
    if warmup_bars < 0:
        raise HistoricalDatasetContractError(
            "warmup_bars must be non-negative."
        )

    requested_range = normalize_research_range(
        audit=audit,
        start_ts_ms=start_ts_ms,
        end_ts_ms=end_ts_ms,
    )

    requested_start = (
        requested_range.requested_start_utc
    )
    requested_end_exclusive = (
        requested_range.requested_end_utc_exclusive
    )

    physical_segments = build_physical_segments(
        manifest=audit.manifest
    )

    research_segments: list[
        HistoricalResearchSegment
    ] = []

    for physical in physical_segments:
        overlap_start = max(
            requested_start,
            physical.physical_start_utc,
        )
        overlap_end_exclusive = min(
            requested_end_exclusive,
            physical.physical_end_utc_exclusive,
        )

        if overlap_start >= overlap_end_exclusive:
            continue

        physical_mask = (
            (
                audit.bars["timestamp"]
                >= physical.physical_start_utc
            )
            & (
                audit.bars["timestamp"]
                < physical.physical_end_utc_exclusive
            )
        )

        physical_bars = (
            audit.bars.loc[physical_mask]
            .reset_index(drop=True)
        )

        if physical_bars.empty:
            raise HistoricalDatasetContractError(
                f"{physical.segment_id}: physical segment "
                "contains no stored bars."
            )

        tradable_candidates = physical_bars.index[
            physical_bars["timestamp"] >= overlap_start
        ].tolist()

        if not tradable_candidates:
            raise HistoricalDatasetContractError(
                f"{physical.segment_id}: no tradable bar exists "
                "at or after requested overlap start."
            )

        first_tradable_index = int(
            tradable_candidates[0]
        )
        replay_start_index = max(
            0,
            first_tradable_index - warmup_bars,
        )

        replay_mask = (
            physical_bars["timestamp"]
            < overlap_end_exclusive
        )

        replay_bars = (
            physical_bars.loc[replay_mask]
            .iloc[replay_start_index:]
            .reset_index(drop=True)
        )

        if replay_bars.empty:
            raise HistoricalDatasetContractError(
                f"{physical.segment_id}: no replay bars remain "
                "after applying requested bounds."
            )

        replay_start = pd.Timestamp(
            replay_bars["timestamp"].iloc[0]
        )
        replay_end_exclusive = overlap_end_exclusive

        if replay_start < physical.physical_start_utc:
            raise HistoricalDatasetContractError(
                f"{physical.segment_id}: replay start crossed a "
                "physical segment boundary."
            )

        if (
            replay_end_exclusive
            > physical.physical_end_utc_exclusive
        ):
            raise HistoricalDatasetContractError(
                f"{physical.segment_id}: replay end crossed a "
                "physical segment boundary."
            )

        requested_start_applied = (
            requested_start
            > physical.physical_start_utc
            and requested_start
            < physical.physical_end_utc_exclusive
        )

        requested_end_applied = (
            requested_end_exclusive
            > physical.physical_start_utc
            and requested_end_exclusive
            < physical.physical_end_utc_exclusive
        )

        research_segments.append(
            HistoricalResearchSegment(
                segment_id=physical.segment_id,
                physical_start_utc=(
                    physical.physical_start_utc
                ),
                physical_end_utc_exclusive=(
                    physical.physical_end_utc_exclusive
                ),
                replay_start_utc=replay_start,
                replay_end_utc_exclusive=(
                    replay_end_exclusive
                ),
                tradable_start_utc=overlap_start,
                physical_start_boundary_type=(
                    physical.physical_start_boundary_type
                ),
                physical_end_boundary_type=(
                    physical.physical_end_boundary_type
                ),
                requested_start_applied=(
                    requested_start_applied
                ),
                requested_end_applied=(
                    requested_end_applied
                ),
                preceding_gap_id=(
                    physical.preceding_gap_id
                ),
                following_gap_id=(
                    physical.following_gap_id
                ),
                bars=replay_bars,
            )
        )

    if not research_segments:
        raise HistoricalDatasetContractError(
            "Requested range does not overlap any stored "
            "historical segment."
        )

    return HistoricalResearchDataset(
        audit=audit,
        requested_range=requested_range,
        warmup_bars=int(warmup_bars),
        segments=tuple(research_segments),
    )
