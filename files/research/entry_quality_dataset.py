from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from files.data.features import compute_features
from files.data.paths import processed_dir
from files.research.historical_dataset import (
    load_and_resolve_historical_research_source,
)
from files.research.scorer_campaign_io import (
    canonical_json_text,
    write_csv_atomic,
    write_json_immutable,
)
from files.research.scorer_campaign_spec import (
    load_runtime_git_identity,
)


ENTRY_QUALITY_DATASET_SCHEMA_VERSION = 1
ENTRY_QUALITY_DATASET_TYPE = "entry_quality_signal_structure_v1"
ENTRY_QUALITY_FEATURE_SPECIFICATION_VERSION = (
    "entry_quality_features_v1"
)

SOURCE_ENTRY_PROGRESS_SCHEMA_VERSION = 2
SOURCE_ENTRY_PROGRESS_TYPE = "read_only_entry_early_progress_v2"

OUTCOME_REACHED_1R = "reached_1r"
OUTCOME_NOT_REACHED_1R = "not_reached_1r"

_DATASET_ID_RE = re.compile(
    r"^entry_quality_dataset_[0-9a-f]{16}$"
)


class EntryQualityDatasetError(RuntimeError):
    """Raised when an entry-quality dataset cannot be built safely."""


@dataclass(frozen=True)
class EntryQualityArtifactPaths:
    root: Path
    manifest_json: Path
    trades_csv: Path
    feature_summary_csv: Path
    fold_summary_csv: Path


def entry_quality_research_dir() -> Path:
    return (
        processed_dir()
        / "research"
        / "entry_quality"
    )


def validate_entry_quality_dataset_id(
    dataset_id: str,
) -> str:
    value = str(dataset_id).strip()

    if not _DATASET_ID_RE.fullmatch(value):
        raise EntryQualityDatasetError(
            "dataset_id must match "
            "'entry_quality_dataset_<16 lowercase hex>': "
            f"{dataset_id!r}"
        )

    return value


def entry_quality_artifact_paths(
    *,
    dataset_id: str,
) -> EntryQualityArtifactPaths:
    root = (
        entry_quality_research_dir()
        / validate_entry_quality_dataset_id(
            dataset_id
        )
    )

    return EntryQualityArtifactPaths(
        root=root,
        manifest_json=root / "manifest.json",
        trades_csv=root / "trades.csv",
        feature_summary_csv=(
            root / "feature_summary.csv"
        ),
        fold_summary_csv=(
            root / "fold_summary.csv"
        ),
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise EntryQualityDatasetError(
            f"Unable to load JSON artifact: {path}"
        ) from exc

    if not isinstance(value, dict):
        raise EntryQualityDatasetError(
            f"Expected JSON object: {path}"
        )

    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        frame = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
        )
    except Exception as exc:
        raise EntryQualityDatasetError(
            f"Unable to read CSV artifact: {path}"
        ) from exc

    return [
        {
            str(key): str(value)
            for key, value in row.items()
        }
        for row in frame.to_dict(
            orient="records"
        )
    ]


def _as_float(
    value: Any,
    *,
    name: str,
) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise EntryQualityDatasetError(
            f"{name} is not numeric: {value!r}"
        ) from exc

    if not math.isfinite(result):
        raise EntryQualityDatasetError(
            f"{name} must be finite: {value!r}"
        )

    return result


def _as_int(
    value: Any,
    *,
    name: str,
) -> int:
    try:
        return int(float(value))
    except Exception as exc:
        raise EntryQualityDatasetError(
            f"{name} is not integer-like: {value!r}"
        ) from exc


def _optional_float(
    value: Any,
) -> float | None:
    if value in (None, ""):
        return None

    try:
        result = float(value)
    except Exception:
        return None

    if not math.isfinite(result):
        return None

    return result


def _close_location(
    *,
    high: float,
    low: float,
    close: float,
) -> float | None:
    width = high - low

    if width <= 0.0:
        return None

    return (close - low) / width


def _safe_ratio(
    numerator: float,
    denominator: float,
) -> float | None:
    if denominator <= 0.0:
        return None

    return numerator / denominator


def _prepare_audited_bars(
    *,
    source: Any,
) -> tuple[
    pd.DataFrame,
    dict[str, tuple[int, int]],
]:
    bars = source.audit.bars.copy()

    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing = sorted(
        required - set(bars.columns)
    )

    if missing:
        raise EntryQualityDatasetError(
            "Audited bars are missing columns: "
            f"{missing}"
        )

    bars["timestamp"] = pd.to_datetime(
        bars["timestamp"],
        utc=True,
        errors="raise",
    )

    bars = bars.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)

    bars["ts_ms"] = (
        bars["timestamp"].astype("int64")
        // 1_000_000
    )

    bars["physical_segment_id"] = ""

    segment_bounds: dict[
        str,
        tuple[int, int],
    ] = {}

    for physical in source.physical_segments:
        mask = (
            (
                bars["timestamp"]
                >= physical.physical_start_utc
            )
            & (
                bars["timestamp"]
                < physical.physical_end_utc_exclusive
            )
        )

        indices = bars.index[mask].tolist()

        if not indices:
            raise EntryQualityDatasetError(
                f"{physical.segment_id} "
                "has no audited bars."
            )

        start_index = int(indices[0])
        end_index = int(indices[-1])

        bars.loc[
            start_index:end_index,
            "physical_segment_id",
        ] = physical.segment_id

        segment_bounds[
            physical.segment_id
        ] = (
            start_index,
            end_index,
        )

    if (
        bars["physical_segment_id"] == ""
    ).any():
        raise EntryQualityDatasetError(
            "Some audited bars were not assigned "
            "to a physical segment."
        )

    return bars, segment_bounds


def _timestamp_index(
    bars: pd.DataFrame,
) -> dict[int, int]:
    return {
        int(ts_ms): int(index)
        for index, ts_ms in zip(
            bars.index,
            bars["ts_ms"],
        )
    }


def _market_feature_frame(
    *,
    bars: pd.DataFrame,
    signal_index: int,
    segment_start_index: int,
    tail_n: int,
) -> pd.DataFrame:
    start_index = max(
        segment_start_index,
        signal_index - tail_n + 1,
    )

    market_data = (
        bars.loc[
            start_index:signal_index,
            [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        ]
        .reset_index(drop=True)
    )

    return compute_features(market_data)


def _bar_return(
    bars: pd.DataFrame,
    *,
    start_index: int,
    end_index: int,
) -> float | None:
    if (
        start_index < 0
        or end_index <= start_index
    ):
        return None

    start_close = float(
        bars.loc[start_index, "close"]
    )
    end_close = float(
        bars.loc[end_index, "close"]
    )

    if start_close <= 0.0:
        return None

    return end_close / start_close - 1.0


def _positive_bar_count(
    bars: pd.DataFrame,
    *,
    signal_index: int,
    segment_start_index: int,
    window: int,
) -> int | None:
    start_index = signal_index - window + 1

    if start_index < segment_start_index:
        return None

    part = bars.loc[
        start_index:signal_index,
        ["open", "close"],
    ]

    return int(
        (
            part["close"].astype(float)
            > part["open"].astype(float)
        ).sum()
    )


def _mean_range_before_signal(
    bars: pd.DataFrame,
    *,
    signal_index: int,
    segment_start_index: int,
    window: int,
) -> float | None:
    end_index = signal_index - 1
    start_index = end_index - window + 1

    if start_index < segment_start_index:
        return None

    part = bars.loc[
        start_index:end_index,
        ["high", "low"],
    ]

    if len(part) != window:
        return None

    ranges = (
        part["high"].astype(float)
        - part["low"].astype(float)
    )

    return float(ranges.mean())


def _prior_20_high(
    bars: pd.DataFrame,
    *,
    signal_index: int,
    segment_start_index: int,
) -> float | None:
    end_index = signal_index - 1
    start_index = end_index - 20 + 1

    if start_index < segment_start_index:
        return None

    part = bars.loc[
        start_index:end_index,
        "high",
    ]

    if len(part) != 20:
        return None

    return float(part.astype(float).max())


def _ema_fast_above_slow_streak(
    features: pd.DataFrame,
) -> int:
    streak = 0

    for index in range(
        len(features) - 1,
        -1,
        -1,
    ):
        row = features.iloc[index]

        if (
            float(row["ema_fast"])
            <= float(row["ema_slow"])
        ):
            break

        streak += 1

    return streak


def _structural_features(
    *,
    bars: pd.DataFrame,
    signal_index: int,
    segment_start_index: int,
    tail_n: int,
) -> dict[str, Any]:
    signal = bars.loc[signal_index]

    open_price = float(signal["open"])
    high = float(signal["high"])
    low = float(signal["low"])
    close = float(signal["close"])

    candle_range = high - low
    body = abs(close - open_price)
    upper_wick = (
        high - max(open_price, close)
    )
    lower_wick = (
        min(open_price, close) - low
    )

    features = _market_feature_frame(
        bars=bars,
        signal_index=signal_index,
        segment_start_index=(
            segment_start_index
        ),
        tail_n=tail_n,
    )

    latest = features.iloc[-1]

    atr = float(latest["atr"])
    ema_fast = float(latest["ema_fast"])
    ema_slow = float(latest["ema_slow"])

    prior_5_mean_range = (
        _mean_range_before_signal(
            bars,
            signal_index=signal_index,
            segment_start_index=(
                segment_start_index
            ),
            window=5,
        )
    )

    prior_10_mean_range = (
        _mean_range_before_signal(
            bars,
            signal_index=signal_index,
            segment_start_index=(
                segment_start_index
            ),
            window=10,
        )
    )

    prior_high = _prior_20_high(
        bars,
        signal_index=signal_index,
        segment_start_index=(
            segment_start_index
        ),
    )

    prior_3_return = _bar_return(
        bars,
        start_index=signal_index - 3,
        end_index=signal_index,
    )

    preceding_3_return = _bar_return(
        bars,
        start_index=signal_index - 6,
        end_index=signal_index - 3,
    )

    momentum_acceleration = None

    if (
        prior_3_return is not None
        and preceding_3_return is not None
    ):
        momentum_acceleration = (
            prior_3_return
            - preceding_3_return
        )

    return {
        "signal_body_pct_of_range": (
            _safe_ratio(
                body,
                candle_range,
            )
        ),
        "signal_upper_wick_pct_of_range": (
            _safe_ratio(
                upper_wick,
                candle_range,
            )
        ),
        "signal_lower_wick_pct_of_range": (
            _safe_ratio(
                lower_wick,
                candle_range,
            )
        ),
        "signal_close_location_in_range": (
            _close_location(
                high=high,
                low=low,
                close=close,
            )
        ),
        "signal_close_vs_ema_fast_atr": (
            _safe_ratio(
                close - ema_fast,
                atr,
            )
        ),
        "signal_close_vs_ema_slow_atr": (
            _safe_ratio(
                close - ema_slow,
                atr,
            )
        ),
        "last_3_positive_bar_count": (
            _positive_bar_count(
                bars,
                signal_index=signal_index,
                segment_start_index=(
                    segment_start_index
                ),
                window=3,
            )
        ),
        "last_6_positive_bar_count": (
            _positive_bar_count(
                bars,
                signal_index=signal_index,
                segment_start_index=(
                    segment_start_index
                ),
                window=6,
            )
        ),
        "preceding_3_return": (
            preceding_3_return
        ),
        "momentum_acceleration_3": (
            momentum_acceleration
        ),
        "current_range_atr": (
            _safe_ratio(
                candle_range,
                atr,
            )
        ),
        "current_range_vs_prior_5_mean": (
            None
            if prior_5_mean_range is None
            else _safe_ratio(
                candle_range,
                prior_5_mean_range,
            )
        ),
        "current_range_vs_prior_10_mean": (
            None
            if prior_10_mean_range is None
            else _safe_ratio(
                candle_range,
                prior_10_mean_range,
            )
        ),
        "distance_from_prior_20_high_atr": (
            None
            if prior_high is None
            else _safe_ratio(
                close - prior_high,
                atr,
            )
        ),
        "ema_fast_above_slow_streak_bars": (
            _ema_fast_above_slow_streak(
                features
            )
        ),
    }


STRUCTURAL_FEATURE_NAMES = (
    "signal_body_pct_of_range",
    "signal_upper_wick_pct_of_range",
    "signal_lower_wick_pct_of_range",
    "signal_close_location_in_range",
    "signal_close_vs_ema_fast_atr",
    "signal_close_vs_ema_slow_atr",
    "last_3_positive_bar_count",
    "last_6_positive_bar_count",
    "preceding_3_return",
    "momentum_acceleration_3",
    "current_range_atr",
    "current_range_vs_prior_5_mean",
    "current_range_vs_prior_10_mean",
    "distance_from_prior_20_high_atr",
    "ema_fast_above_slow_streak_bars",
)

SOURCE_SIGNAL_FEATURE_NAMES = (
    "signal_recomputed_confidence",
    "signal_close_ratio",
    "signal_rvol_20",
    "signal_ret_1",
    "signal_ret_3",
    "signal_ret_6",
    "signal_ret_12",
    "signal_ema_spread",
    "signal_ema_slow_slope",
    "signal_atr_pct",
    "signal_rsi",
    "signal_vol_z",
    "signal_dollar_vol_z",
    "signal_close_vs_ema_fast_pct",
    "signal_close_vs_ema_slow_pct",
    "signal_distance_from_prior_20_high_pct",
)

TRADE_FIELDS = (
    "campaign_id",
    "trial_id",
    "split_name",
    "entry_ts_ms",
    "exit_ts_ms",
    "signal_ts_ms",
    "outcome_group",
    "realized_pnl_usd",
    *SOURCE_SIGNAL_FEATURE_NAMES,
    *STRUCTURAL_FEATURE_NAMES,
)


def _identity_payload(
    *,
    campaign_id: str,
    trial_id: str,
    source_manifest_fingerprint: str,
    data_tag: str,
    symbol: str,
    timeframe: str,
    split_names: Sequence[str],
    generator_git_commit: str,
    verification_only: bool,
) -> dict[str, Any]:
    return {
        "dataset_schema_version": (
            ENTRY_QUALITY_DATASET_SCHEMA_VERSION
        ),
        "dataset_type": (
            ENTRY_QUALITY_DATASET_TYPE
        ),
        "source_campaign_id": campaign_id,
        "source_trial_id": trial_id,
        "source_manifest_fingerprint": (
            source_manifest_fingerprint
        ),
        "source_entry_progress_schema_version": (
            SOURCE_ENTRY_PROGRESS_SCHEMA_VERSION
        ),
        "source_entry_progress_type": (
            SOURCE_ENTRY_PROGRESS_TYPE
        ),
        "data_tag": data_tag,
        "symbol": symbol,
        "timeframe": timeframe,
        "validation_split_names": sorted(
            str(value)
            for value in split_names
        ),
        "outcome_label_contract": {
            "positive": OUTCOME_REACHED_1R,
            "negative": OUTCOME_NOT_REACHED_1R,
            "source": (
                "canonical entry-progress "
                "diagnostic outcome_group"
            ),
        },
        "feature_specification_version": (
            ENTRY_QUALITY_FEATURE_SPECIFICATION_VERSION
        ),
        "source_signal_features": list(
            SOURCE_SIGNAL_FEATURE_NAMES
        ),
        "structural_features": list(
            STRUCTURAL_FEATURE_NAMES
        ),
        "generator_git_commit": (
            generator_git_commit
        ),
        "verification_only": bool(
            verification_only
        ),
    }


def _dataset_id_for_payload(
    payload: Mapping[str, Any],
) -> str:
    digest = hashlib.sha256(
        canonical_json_text(
            dict(payload)
        ).encode("utf-8")
    ).hexdigest()

    return (
        "entry_quality_dataset_"
        f"{digest[:16]}"
    )


def _summary_rows(
    trade_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    scopes: list[
        tuple[str, Sequence[Mapping[str, Any]]]
    ] = [
        ("all_validation", trade_rows)
    ]

    split_names = sorted(
        {
            str(row["split_name"])
            for row in trade_rows
        }
    )

    scopes.extend(
        (
            split_name,
            [
                row
                for row in trade_rows
                if row["split_name"]
                == split_name
            ],
        )
        for split_name in split_names
    )

    for scope_name, scope_rows in scopes:
        for outcome in (
            OUTCOME_REACHED_1R,
            OUTCOME_NOT_REACHED_1R,
        ):
            group = [
                row
                for row in scope_rows
                if row["outcome_group"]
                == outcome
            ]

            for feature_name in (
                *SOURCE_SIGNAL_FEATURE_NAMES,
                *STRUCTURAL_FEATURE_NAMES,
            ):
                values = [
                    value
                    for row in group
                    if (
                        value := _optional_float(
                            row.get(feature_name)
                        )
                    )
                    is not None
                ]

                series = pd.Series(
                    values,
                    dtype="float64",
                )

                rows.append(
                    {
                        "scope": scope_name,
                        "outcome_group": outcome,
                        "feature_name": (
                            feature_name
                        ),
                        "available_count": len(
                            values
                        ),
                        "missing_count": (
                            len(group) - len(values)
                        ),
                        "mean": (
                            ""
                            if series.empty
                            else float(
                                series.mean()
                            )
                        ),
                        "median": (
                            ""
                            if series.empty
                            else float(
                                series.median()
                            )
                        ),
                        "p25": (
                            ""
                            if series.empty
                            else float(
                                series.quantile(
                                    0.25
                                )
                            )
                        ),
                        "p75": (
                            ""
                            if series.empty
                            else float(
                                series.quantile(
                                    0.75
                                )
                            )
                        ),
                    }
                )

    return rows


def _fold_rows(
    trade_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    split_names = sorted(
        {
            str(row["split_name"])
            for row in trade_rows
        }
    )

    for split_name in split_names:
        split_rows = [
            row
            for row in trade_rows
            if row["split_name"]
            == split_name
        ]

        reached = sum(
            row["outcome_group"]
            == OUTCOME_REACHED_1R
            for row in split_rows
        )

        not_reached = sum(
            row["outcome_group"]
            == OUTCOME_NOT_REACHED_1R
            for row in split_rows
        )

        pnl = sum(
            _as_float(
                row["realized_pnl_usd"],
                name="realized_pnl_usd",
            )
            for row in split_rows
        )

        result.append(
            {
                "split_name": split_name,
                "trade_count": len(
                    split_rows
                ),
                "reached_1r_count": reached,
                "not_reached_1r_count": (
                    not_reached
                ),
                "total_realized_pnl_usd": pnl,
            }
        )

    return result


def build_entry_quality_dataset(
    *,
    campaign_root: Path,
    trial_id: str,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    campaign_manifest = _load_json_object(
        campaign_root
        / "campaign_manifest.json"
    )

    campaign_id = str(
        campaign_manifest.get(
            "campaign_id",
            "",
        )
    )

    if campaign_id != campaign_root.name:
        raise EntryQualityDatasetError(
            "Campaign root and manifest identity differ."
        )

    data_tag = str(
        campaign_manifest["specification"][
            "data_tag"
        ]
    )
    symbol = str(
        campaign_manifest["specification"][
            "symbol"
        ]
    )
    timeframe = str(
        campaign_manifest["specification"][
            "timeframe"
        ]
    )

    min_bars = int(
        campaign_manifest["specification"][
            "min_bars"
        ]
    )
    tail_n = max(min_bars, 200)

    expected_fingerprint = str(
        campaign_manifest[
            "manifest_fingerprint"
        ]
    )

    source = (
        load_and_resolve_historical_research_source(
            data_tag=data_tag,
            expected_symbol=symbol,
            expected_timeframe=timeframe,
        )
    )

    if (
        source.manifest_fingerprint
        != expected_fingerprint
    ):
        raise EntryQualityDatasetError(
            "Historical source fingerprint mismatch: "
            f"expected={expected_fingerprint} "
            "actual="
            f"{source.manifest_fingerprint}"
        )

    source_diagnostic_dir = (
        campaign_root
        / "diagnostics"
        / "entry_early_progress"
        / trial_id
    )

    source_summary = _load_json_object(
        source_diagnostic_dir
        / "diagnostic_summary.json"
    )

    if int(
        source_summary.get(
            "diagnostic_schema_version",
            -1,
        )
    ) != SOURCE_ENTRY_PROGRESS_SCHEMA_VERSION:
        raise EntryQualityDatasetError(
            "Unexpected source entry-progress "
            "schema version."
        )

    if str(
        source_summary.get(
            "diagnostic_type",
            "",
        )
    ) != SOURCE_ENTRY_PROGRESS_TYPE:
        raise EntryQualityDatasetError(
            "Unexpected source entry-progress "
            "diagnostic type."
        )

    if (
        str(source_summary.get("campaign_id"))
        != campaign_id
    ):
        raise EntryQualityDatasetError(
            "Source diagnostic campaign mismatch."
        )

    if (
        str(source_summary.get("trial_id"))
        != trial_id
    ):
        raise EntryQualityDatasetError(
            "Source diagnostic trial mismatch."
        )

    if (
        str(
            source_summary.get(
                "source_manifest_fingerprint"
            )
        )
        != source.manifest_fingerprint
    ):
        raise EntryQualityDatasetError(
            "Source diagnostic historical "
            "fingerprint mismatch."
        )

    source_rows = _read_csv(
        source_diagnostic_dir
        / "entry_early_progress_trades.csv"
    )

    expected_trade_count = int(
        source_summary["trade_count"]
    )

    if len(source_rows) != expected_trade_count:
        raise EntryQualityDatasetError(
            "Source diagnostic trade-count mismatch: "
            f"summary={expected_trade_count} "
            f"csv={len(source_rows)}"
        )

    bars, segment_bounds = (
        _prepare_audited_bars(
            source=source
        )
    )

    timestamp_to_index = _timestamp_index(
        bars
    )

    trade_rows: list[dict[str, Any]] = []

    for source_row in source_rows:
        outcome = str(
            source_row.get(
                "outcome_group",
                "",
            )
        )

        if outcome not in {
            OUTCOME_REACHED_1R,
            OUTCOME_NOT_REACHED_1R,
        }:
            raise EntryQualityDatasetError(
                "Unexpected outcome_group: "
                f"{outcome!r}"
            )

        signal_ts_ms = _as_int(
            source_row.get("signal_ts_ms"),
            name="signal_ts_ms",
        )

        signal_index = timestamp_to_index.get(
            signal_ts_ms
        )

        if signal_index is None:
            raise EntryQualityDatasetError(
                "Signal timestamp absent from "
                "audited bars: "
                f"{signal_ts_ms}"
            )

        segment_id = str(
            bars.loc[
                signal_index,
                "physical_segment_id",
            ]
        )

        try:
            (
                segment_start_index,
                _,
            ) = segment_bounds[segment_id]
        except KeyError as exc:
            raise EntryQualityDatasetError(
                "Signal bar has unknown physical "
                f"segment: {segment_id!r}"
            ) from exc

        structural = _structural_features(
            bars=bars,
            signal_index=signal_index,
            segment_start_index=(
                segment_start_index
            ),
            tail_n=tail_n,
        )

        row: dict[str, Any] = {
            "campaign_id": campaign_id,
            "trial_id": trial_id,
            "split_name": str(
                source_row["split_name"]
            ),
            "entry_ts_ms": _as_int(
                source_row["entry_ts_ms"],
                name="entry_ts_ms",
            ),
            "exit_ts_ms": _as_int(
                source_row["exit_ts_ms"],
                name="exit_ts_ms",
            ),
            "signal_ts_ms": signal_ts_ms,
            "outcome_group": outcome,
            "realized_pnl_usd": _as_float(
                source_row["realized_pnl_usd"],
                name="realized_pnl_usd",
            ),
        }

        for feature_name in (
            SOURCE_SIGNAL_FEATURE_NAMES
        ):
            row[feature_name] = (
                _optional_float(
                    source_row.get(
                        feature_name
                    )
                )
            )

        row.update(structural)

        trade_rows.append(row)

    trade_rows.sort(
        key=lambda row: (
            str(row["split_name"]),
            int(row["entry_ts_ms"]),
        )
    )

    split_names = sorted(
        {
            str(row["split_name"])
            for row in trade_rows
        }
    )

    if write_artifacts:
        git_identity = load_runtime_git_identity()
        generator_git_commit = (
            git_identity.git_commit
        )
        verification_only = False
    else:
        deployed_identity_path = Path(
            "files/research/contracts/"
            ".deployed_git_identity.json"
        )

        deployed_identity = _load_json_object(
            deployed_identity_path
        )

        generator_git_commit = str(
            deployed_identity.get(
                "git_commit",
                "",
            )
        ).strip()

        if not re.fullmatch(
            r"[0-9a-f]{40}",
            generator_git_commit,
        ):
            raise EntryQualityDatasetError(
                "Verification deployment does not "
                "contain a valid Git commit identity."
            )

        verification_only = bool(
            not deployed_identity.get(
                "working_tree_clean",
                False,
            )
        )

    identity_payload = _identity_payload(
        campaign_id=campaign_id,
        trial_id=trial_id,
        source_manifest_fingerprint=(
            source.manifest_fingerprint
        ),
        data_tag=data_tag,
        symbol=symbol,
        timeframe=timeframe,
        split_names=split_names,
        generator_git_commit=(
            generator_git_commit
        ),
        verification_only=verification_only,
    )

    dataset_id = _dataset_id_for_payload(
        identity_payload
    )

    artifacts = entry_quality_artifact_paths(
        dataset_id=dataset_id
    )

    fold_rows = _fold_rows(trade_rows)

    manifest = {
        "dataset_id": dataset_id,
        **identity_payload,
        "trade_count": len(trade_rows),
        "reached_1r_count": sum(
            row["outcome_group"]
            == OUTCOME_REACHED_1R
            for row in trade_rows
        ),
        "not_reached_1r_count": sum(
            row["outcome_group"]
            == OUTCOME_NOT_REACHED_1R
            for row in trade_rows
        ),
        "fold_counts": [
            {
                "split_name": (
                    row["split_name"]
                ),
                "trade_count": (
                    row["trade_count"]
                ),
                "reached_1r_count": (
                    row["reached_1r_count"]
                ),
                "not_reached_1r_count": (
                    row[
                        "not_reached_1r_count"
                    ]
                ),
            }
            for row in fold_rows
        ],
        "anti_leakage_contract": {
            "feature_timestamp": (
                "signal bar or earlier"
            ),
            "future_bars_used_for_features": (
                False
            ),
            "physical_segment_scoped": True,
            "crosses_confirmed_gap": False,
            "outcome_label_source": (
                "completed canonical "
                "entry-progress diagnostic"
            ),
            "strategy_or_backtest_replayed": (
                False
            ),
        },
        "artifacts": {
            "manifest_json": str(
                artifacts.manifest_json
            ),
            "trades_csv": str(
                artifacts.trades_csv
            ),
            "feature_summary_csv": str(
                artifacts.feature_summary_csv
            ),
            "fold_summary_csv": str(
                artifacts.fold_summary_csv
            ),
        },
    }

    if write_artifacts:
        write_csv_atomic(
            path=artifacts.trades_csv,
            fieldnames=TRADE_FIELDS,
            rows=trade_rows,
        )

        write_csv_atomic(
            path=artifacts.feature_summary_csv,
            fieldnames=(
                "scope",
                "outcome_group",
                "feature_name",
                "available_count",
                "missing_count",
                "mean",
                "median",
                "p25",
                "p75",
            ),
            rows=_summary_rows(trade_rows),
        )

        write_csv_atomic(
            path=artifacts.fold_summary_csv,
            fieldnames=(
                "split_name",
                "trade_count",
                "reached_1r_count",
                "not_reached_1r_count",
                "total_realized_pnl_usd",
            ),
            rows=fold_rows,
        )

        # The immutable manifest is the completion marker.
        # Write it only after all data artifacts succeed.
        write_json_immutable(
            path=artifacts.manifest_json,
            value=manifest,
        )

    return manifest
