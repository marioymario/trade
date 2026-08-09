from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean, median
from typing import Any, Mapping, Sequence

import pandas as pd

from files.data.paths import processed_dir
from files.research.entry_quality_dataset import (
    _as_float,
    _as_int,
    _load_json_object,
    _prepare_audited_bars,
    _read_csv,
    _timestamp_index,
    entry_quality_artifact_paths,
    validate_entry_quality_dataset_id,
)
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


OUTCOME_GEOMETRY_SCHEMA_VERSION = 1
OUTCOME_GEOMETRY_TYPE = "entry_quality_outcome_geometry_v1"
OUTCOME_GEOMETRY_SPECIFICATION_VERSION = (
    "entry_quality_outcome_geometry_24b_v1"
)

HORIZON_BARS = 24
TARGET_R = 1.0
STOP_R = 1.0

_DATASET_ID_RE = re.compile(
    r"^entry_quality_outcomes_[0-9a-f]{16}$"
)


class EntryQualityOutcomeGeometryError(RuntimeError):
    """Raised when outcome geometry cannot be built safely."""


@dataclass(frozen=True)
class OutcomeGeometryArtifactPaths:
    root: Path
    manifest_json: Path
    outcomes_csv: Path
    fold_summary_csv: Path


OUTCOME_FIELDS = (
    "campaign_id",
    "trial_id",
    "split_name",
    "signal_ts_ms",
    "entry_ts_ms",
    "source_exit_ts_ms",
    "source_outcome_group",
    "entry_price",
    "initial_stop_price",
    "initial_risk_price",
    "initial_risk_pct",
    "horizon_bars",
    "horizon_available",
    "horizon_end_ts_ms",
    "mfe_24b_price",
    "mae_24b_price",
    "mfe_24b_r",
    "mae_24b_r",
    "excursion_quality_24b",
    "bars_to_mfe_peak",
    "bars_to_mae_peak",
    "first_target_1r_bar",
    "first_stop_1r_bar",
    "first_barrier_bar",
    "first_barrier_outcome",
    "same_bar_barrier_ambiguity",
    "close_24b",
    "close_24b_r",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _outcome_geometry_research_dir() -> Path:
    return (
        processed_dir()
        / "research"
        / "entry_quality"
    )


def _validate_dataset_id(
    dataset_id: str,
) -> str:
    value = str(dataset_id).strip()

    if not _DATASET_ID_RE.fullmatch(value):
        raise EntryQualityOutcomeGeometryError(
            "dataset_id must match "
            "'entry_quality_outcomes_<16 lowercase hex>': "
            f"{dataset_id!r}"
        )

    return value


def _artifact_paths(
    *,
    dataset_id: str,
) -> OutcomeGeometryArtifactPaths:
    root = (
        _outcome_geometry_research_dir()
        / _validate_dataset_id(dataset_id)
    )

    return OutcomeGeometryArtifactPaths(
        root=root,
        manifest_json=root / "manifest.json",
        outcomes_csv=root / "outcomes.csv",
        fold_summary_csv=root / "fold_summary.csv",
    )


def _verification_git_commit() -> str:
    path = Path(
        "files/research/contracts/"
        ".deployed_git_identity.json"
    )

    value = _load_json_object(path)

    commit = str(
        value.get(
            "git_commit",
            "",
        )
    ).strip()

    if not commit:
        raise EntryQualityOutcomeGeometryError(
            "Deployed Git identity has no git_commit."
        )

    return commit


def _identity_payload(
    *,
    source_dataset_id: str,
    source_dataset_manifest_sha256: str,
    source_dataset_trades_sha256: str,
    source_entry_progress_sha256: str,
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
            OUTCOME_GEOMETRY_SCHEMA_VERSION
        ),
        "dataset_type": OUTCOME_GEOMETRY_TYPE,
        "outcome_specification_version": (
            OUTCOME_GEOMETRY_SPECIFICATION_VERSION
        ),
        "source_entry_quality_dataset_id": (
            source_dataset_id
        ),
        "source_entry_quality_manifest_sha256": (
            source_dataset_manifest_sha256
        ),
        "source_entry_quality_trades_sha256": (
            source_dataset_trades_sha256
        ),
        "source_entry_progress_trades_sha256": (
            source_entry_progress_sha256
        ),
        "source_campaign_id": campaign_id,
        "source_trial_id": trial_id,
        "source_manifest_fingerprint": (
            source_manifest_fingerprint
        ),
        "data_tag": data_tag,
        "symbol": symbol,
        "timeframe": timeframe,
        "validation_split_names": sorted(
            str(value)
            for value in split_names
        ),
        "path_geometry_contract": {
            "horizon_bars": HORIZON_BARS,
            "horizon_start": "entry_bar",
            "entry_bar_number": 1,
            "target_r": TARGET_R,
            "stop_r": STOP_R,
            "risk_basis": (
                "entry_price minus canonical initial_stop_price"
            ),
            "actual_strategy_exit_limits_horizon": False,
            "physical_segment_scoped": True,
            "crosses_confirmed_gap": False,
            "same_bar_target_stop_order_inferred": False,
            "same_bar_target_stop_marked_ambiguous": True,
        },
        "generator_git_commit": generator_git_commit,
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
        "entry_quality_outcomes_"
        f"{digest[:16]}"
    )


def _optional_int(
    value: int | None,
) -> int | str:
    if value is None:
        return ""
    return int(value)


def _optional_float(
    value: float | None,
) -> float | str:
    if value is None:
        return ""
    return float(value)


def _first_hit_bar(
    *,
    window: pd.DataFrame,
    entry_price: float,
    threshold_price: float,
    direction: str,
) -> int | None:
    for offset, (_, bar) in enumerate(
        window.iterrows(),
        start=1,
    ):
        if direction == "target":
            if float(bar["high"]) >= threshold_price:
                return offset
        elif direction == "stop":
            if float(bar["low"]) <= threshold_price:
                return offset
        else:
            raise EntryQualityOutcomeGeometryError(
                f"Unknown barrier direction: {direction!r}"
            )

    return None


def _peak_bar(
    *,
    values: Sequence[float],
    mode: str,
) -> int:
    if not values:
        raise EntryQualityOutcomeGeometryError(
            "Cannot identify peak in empty sequence."
        )

    if mode == "max":
        target = max(values)
    elif mode == "min":
        target = min(values)
    else:
        raise EntryQualityOutcomeGeometryError(
            f"Unknown peak mode: {mode!r}"
        )

    for index, value in enumerate(
        values,
        start=1,
    ):
        if value == target:
            return index

    raise EntryQualityOutcomeGeometryError(
        "Unable to identify peak bar."
    )


def _path_geometry(
    *,
    bars: pd.DataFrame,
    entry_index: int,
    segment_end_index: int,
    entry_price: float,
    initial_risk_price: float,
) -> dict[str, Any]:
    horizon_end_index = (
        entry_index
        + HORIZON_BARS
        - 1
    )

    if horizon_end_index > segment_end_index:
        return {
            "horizon_bars": HORIZON_BARS,
            "horizon_available": False,
            "horizon_end_ts_ms": "",
            "mfe_24b_price": "",
            "mae_24b_price": "",
            "mfe_24b_r": "",
            "mae_24b_r": "",
            "excursion_quality_24b": "",
            "bars_to_mfe_peak": "",
            "bars_to_mae_peak": "",
            "first_target_1r_bar": "",
            "first_stop_1r_bar": "",
            "first_barrier_bar": "",
            "first_barrier_outcome": (
                "unavailable_segment_boundary"
            ),
            "same_bar_barrier_ambiguity": False,
            "close_24b": "",
            "close_24b_r": "",
        }

    window = bars.loc[
        entry_index:horizon_end_index
    ]

    if len(window) != HORIZON_BARS:
        raise EntryQualityOutcomeGeometryError(
            "24-bar horizon length mismatch: "
            f"expected={HORIZON_BARS} "
            f"actual={len(window)}"
        )

    highs = [
        float(value)
        for value in window["high"]
    ]
    lows = [
        float(value)
        for value in window["low"]
    ]

    highest = max(highs)
    lowest = min(lows)

    mfe_price = max(
        highest - entry_price,
        0.0,
    )
    mae_price = max(
        entry_price - lowest,
        0.0,
    )

    mfe_r = (
        mfe_price
        / initial_risk_price
    )
    mae_r = (
        mae_price
        / initial_risk_price
    )

    excursion_denominator = (
        mfe_price + mae_price
    )

    excursion_quality = (
        None
        if excursion_denominator <= 0.0
        else (
            mfe_price
            / excursion_denominator
        )
    )

    target_price = (
        entry_price
        + TARGET_R * initial_risk_price
    )
    stop_price = (
        entry_price
        - STOP_R * initial_risk_price
    )

    target_bar = _first_hit_bar(
        window=window,
        entry_price=entry_price,
        threshold_price=target_price,
        direction="target",
    )
    stop_bar = _first_hit_bar(
        window=window,
        entry_price=entry_price,
        threshold_price=stop_price,
        direction="stop",
    )

    same_bar_ambiguity = (
        target_bar is not None
        and stop_bar is not None
        and target_bar == stop_bar
    )

    if (
        target_bar is None
        and stop_bar is None
    ):
        first_barrier_bar = None
        first_barrier_outcome = "neither_24b"

    elif target_bar is None:
        first_barrier_bar = stop_bar
        first_barrier_outcome = "stop_first"

    elif stop_bar is None:
        first_barrier_bar = target_bar
        first_barrier_outcome = "target_first"

    elif target_bar < stop_bar:
        first_barrier_bar = target_bar
        first_barrier_outcome = "target_first"

    elif stop_bar < target_bar:
        first_barrier_bar = stop_bar
        first_barrier_outcome = "stop_first"

    else:
        first_barrier_bar = target_bar
        first_barrier_outcome = (
            "same_bar_ambiguous"
        )

    close_24b = float(
        window.iloc[-1]["close"]
    )
    close_24b_r = (
        close_24b - entry_price
    ) / initial_risk_price

    return {
        "horizon_bars": HORIZON_BARS,
        "horizon_available": True,
        "horizon_end_ts_ms": int(
            window.iloc[-1]["ts_ms"]
        ),
        "mfe_24b_price": mfe_price,
        "mae_24b_price": mae_price,
        "mfe_24b_r": mfe_r,
        "mae_24b_r": mae_r,
        "excursion_quality_24b": (
            _optional_float(
                excursion_quality
            )
        ),
        "bars_to_mfe_peak": _peak_bar(
            values=highs,
            mode="max",
        ),
        "bars_to_mae_peak": _peak_bar(
            values=lows,
            mode="min",
        ),
        "first_target_1r_bar": (
            _optional_int(target_bar)
        ),
        "first_stop_1r_bar": (
            _optional_int(stop_bar)
        ),
        "first_barrier_bar": (
            _optional_int(
                first_barrier_bar
            )
        ),
        "first_barrier_outcome": (
            first_barrier_outcome
        ),
        "same_bar_barrier_ambiguity": (
            same_bar_ambiguity
        ),
        "close_24b": close_24b,
        "close_24b_r": close_24b_r,
    }


def _fold_summary_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    split_names = sorted(
        {
            str(row["split_name"])
            for row in rows
        }
    )

    for split_name in split_names:
        split_rows = [
            row
            for row in rows
            if str(row["split_name"])
            == split_name
        ]

        available = [
            row
            for row in split_rows
            if bool(row["horizon_available"])
        ]

        mfe_values = [
            float(row["mfe_24b_r"])
            for row in available
        ]
        mae_values = [
            float(row["mae_24b_r"])
            for row in available
        ]
        quality_values = [
            float(
                row[
                    "excursion_quality_24b"
                ]
            )
            for row in available
            if row[
                "excursion_quality_24b"
            ]
            not in ("", None)
        ]

        counts = {
            value: sum(
                row["first_barrier_outcome"]
                == value
                for row in split_rows
            )
            for value in (
                "target_first",
                "stop_first",
                "same_bar_ambiguous",
                "neither_24b",
                "unavailable_segment_boundary",
            )
        }

        result.append(
            {
                "split_name": split_name,
                "trade_count": len(split_rows),
                "horizon_available_count": (
                    len(available)
                ),
                "target_first_count": (
                    counts["target_first"]
                ),
                "stop_first_count": (
                    counts["stop_first"]
                ),
                "same_bar_ambiguous_count": (
                    counts[
                        "same_bar_ambiguous"
                    ]
                ),
                "neither_24b_count": (
                    counts["neither_24b"]
                ),
                "unavailable_count": (
                    counts[
                        "unavailable_segment_boundary"
                    ]
                ),
                "mean_mfe_24b_r": (
                    mean(mfe_values)
                    if mfe_values
                    else ""
                ),
                "median_mfe_24b_r": (
                    median(mfe_values)
                    if mfe_values
                    else ""
                ),
                "mean_mae_24b_r": (
                    mean(mae_values)
                    if mae_values
                    else ""
                ),
                "median_mae_24b_r": (
                    median(mae_values)
                    if mae_values
                    else ""
                ),
                "mean_excursion_quality_24b": (
                    mean(quality_values)
                    if quality_values
                    else ""
                ),
                "median_excursion_quality_24b": (
                    median(quality_values)
                    if quality_values
                    else ""
                ),
            }
        )

    return result


def build_entry_quality_outcome_geometry(
    *,
    source_dataset_id: str,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    source_dataset_id = (
        validate_entry_quality_dataset_id(
            source_dataset_id
        )
    )

    source_paths = (
        entry_quality_artifact_paths(
            dataset_id=source_dataset_id
        )
    )

    source_manifest = _load_json_object(
        source_paths.manifest_json
    )

    if (
        str(
            source_manifest.get(
                "dataset_id",
                "",
            )
        )
        != source_dataset_id
    ):
        raise EntryQualityOutcomeGeometryError(
            "Source entry-quality dataset "
            "identity mismatch."
        )

    if bool(
        source_manifest.get(
            "verification_only",
            True,
        )
    ):
        raise EntryQualityOutcomeGeometryError(
            "Source entry-quality dataset must "
            "be authoritative, not verification-only."
        )

    campaign_id = str(
        source_manifest[
            "source_campaign_id"
        ]
    )
    trial_id = str(
        source_manifest[
            "source_trial_id"
        ]
    )

    data_tag = str(
        source_manifest["data_tag"]
    )
    symbol = str(
        source_manifest["symbol"]
    )
    timeframe = str(
        source_manifest["timeframe"]
    )

    expected_fingerprint = str(
        source_manifest[
            "source_manifest_fingerprint"
        ]
    )

    source_rows = _read_csv(
        source_paths.trades_csv
    )

    campaign_root = (
        processed_dir()
        / "research"
        / "scorer_campaigns"
        / campaign_id
    )

    diagnostic_path = (
        campaign_root
        / "diagnostics"
        / "entry_early_progress"
        / trial_id
        / "entry_early_progress_trades.csv"
    )

    diagnostic_rows = _read_csv(
        diagnostic_path
    )

    diagnostic_by_key: dict[
        tuple[str, int, int],
        Mapping[str, str],
    ] = {}

    for row in diagnostic_rows:
        key = (
            str(row["split_name"]),
            _as_int(
                row["entry_ts_ms"],
                name="diagnostic entry_ts_ms",
            ),
            _as_int(
                row["signal_ts_ms"],
                name="diagnostic signal_ts_ms",
            ),
        )

        if key in diagnostic_by_key:
            raise EntryQualityOutcomeGeometryError(
                "Duplicate source diagnostic "
                f"trade identity: {key}"
            )

        diagnostic_by_key[key] = row

    if len(source_rows) != len(diagnostic_rows):
        raise EntryQualityOutcomeGeometryError(
            "Source entry-quality and diagnostic "
            "trade counts differ: "
            f"dataset={len(source_rows)} "
            f"diagnostic={len(diagnostic_rows)}"
        )

    historical_source = (
        load_and_resolve_historical_research_source(
            data_tag=data_tag,
            expected_symbol=symbol,
            expected_timeframe=timeframe,
        )
    )

    if (
        historical_source.manifest_fingerprint
        != expected_fingerprint
    ):
        raise EntryQualityOutcomeGeometryError(
            "Historical source fingerprint mismatch."
        )

    bars, segment_bounds = (
        _prepare_audited_bars(
            source=historical_source
        )
    )

    timestamp_to_index = (
        _timestamp_index(bars)
    )

    outcome_rows: list[
        dict[str, Any]
    ] = []

    for source_row in source_rows:
        split_name = str(
            source_row["split_name"]
        )

        entry_ts_ms = _as_int(
            source_row["entry_ts_ms"],
            name="entry_ts_ms",
        )
        signal_ts_ms = _as_int(
            source_row["signal_ts_ms"],
            name="signal_ts_ms",
        )

        key = (
            split_name,
            entry_ts_ms,
            signal_ts_ms,
        )

        diagnostic = (
            diagnostic_by_key.get(key)
        )

        if diagnostic is None:
            raise EntryQualityOutcomeGeometryError(
                "Source trade absent from entry-progress "
                f"diagnostic: {key}"
            )

        if (
            str(
                diagnostic["outcome_group"]
            )
            != str(
                source_row["outcome_group"]
            )
        ):
            raise EntryQualityOutcomeGeometryError(
                "Outcome mismatch between source "
                f"dataset and diagnostic: {key}"
            )

        entry_index = (
            timestamp_to_index.get(
                entry_ts_ms
            )
        )
        signal_index = (
            timestamp_to_index.get(
                signal_ts_ms
            )
        )

        if (
            entry_index is None
            or signal_index is None
        ):
            raise EntryQualityOutcomeGeometryError(
                "Signal or entry timestamp absent "
                f"from audited bars: {key}"
            )

        if signal_index + 1 != entry_index:
            raise EntryQualityOutcomeGeometryError(
                "Signal and entry bars are not "
                f"adjacent: {key}"
            )

        segment_id = str(
            bars.loc[
                entry_index,
                "physical_segment_id",
            ]
        )

        signal_segment_id = str(
            bars.loc[
                signal_index,
                "physical_segment_id",
            ]
        )

        if signal_segment_id != segment_id:
            raise EntryQualityOutcomeGeometryError(
                "Signal and entry cross a "
                "physical source gap."
            )

        try:
            (
                _,
                segment_end_index,
            ) = segment_bounds[
                segment_id
            ]
        except KeyError as exc:
            raise EntryQualityOutcomeGeometryError(
                "Unknown physical segment: "
                f"{segment_id!r}"
            ) from exc

        entry_price = _as_float(
            diagnostic["entry_price"],
            name="entry_price",
        )
        initial_stop_price = _as_float(
            diagnostic[
                "initial_stop_price"
            ],
            name="initial_stop_price",
        )

        initial_risk_price = (
            entry_price
            - initial_stop_price
        )

        if initial_risk_price <= 0.0:
            raise EntryQualityOutcomeGeometryError(
                "Invalid LONG initial risk: "
                f"entry={entry_price} "
                f"stop={initial_stop_price}"
            )

        geometry = _path_geometry(
            bars=bars,
            entry_index=entry_index,
            segment_end_index=(
                segment_end_index
            ),
            entry_price=entry_price,
            initial_risk_price=(
                initial_risk_price
            ),
        )

        row: dict[str, Any] = {
            "campaign_id": campaign_id,
            "trial_id": trial_id,
            "split_name": split_name,
            "signal_ts_ms": signal_ts_ms,
            "entry_ts_ms": entry_ts_ms,
            "source_exit_ts_ms": _as_int(
                source_row["exit_ts_ms"],
                name="source_exit_ts_ms",
            ),
            "source_outcome_group": str(
                source_row[
                    "outcome_group"
                ]
            ),
            "entry_price": entry_price,
            "initial_stop_price": (
                initial_stop_price
            ),
            "initial_risk_price": (
                initial_risk_price
            ),
            "initial_risk_pct": (
                initial_risk_price
                / entry_price
            ),
        }

        row.update(geometry)
        outcome_rows.append(row)

    outcome_rows.sort(
        key=lambda row: (
            str(row["split_name"]),
            int(row["entry_ts_ms"]),
        )
    )

    if len(outcome_rows) != len(source_rows):
        raise EntryQualityOutcomeGeometryError(
            "Outcome geometry trade-count mismatch."
        )

    split_names = sorted(
        {
            str(row["split_name"])
            for row in outcome_rows
        }
    )

    if write_artifacts:
        git_identity = (
            load_runtime_git_identity()
        )
        generator_git_commit = (
            git_identity.git_commit
        )
        verification_only = False
    else:
        generator_git_commit = (
            _verification_git_commit()
        )
        verification_only = True

    identity = _identity_payload(
        source_dataset_id=source_dataset_id,
        source_dataset_manifest_sha256=(
            _sha256_file(
                source_paths.manifest_json
            )
        ),
        source_dataset_trades_sha256=(
            _sha256_file(
                source_paths.trades_csv
            )
        ),
        source_entry_progress_sha256=(
            _sha256_file(
                diagnostic_path
            )
        ),
        campaign_id=campaign_id,
        trial_id=trial_id,
        source_manifest_fingerprint=(
            expected_fingerprint
        ),
        data_tag=data_tag,
        symbol=symbol,
        timeframe=timeframe,
        split_names=split_names,
        generator_git_commit=(
            generator_git_commit
        ),
        verification_only=(
            verification_only
        ),
    )

    dataset_id = (
        _dataset_id_for_payload(
            identity
        )
    )

    artifacts = _artifact_paths(
        dataset_id=dataset_id
    )

    fold_rows = _fold_summary_rows(
        outcome_rows
    )

    manifest = {
        **identity,
        "dataset_id": dataset_id,
        "trade_count": len(
            outcome_rows
        ),
        "horizon_available_count": sum(
            bool(
                row[
                    "horizon_available"
                ]
            )
            for row in outcome_rows
        ),
        "horizon_unavailable_count": sum(
            not bool(
                row[
                    "horizon_available"
                ]
            )
            for row in outcome_rows
        ),
        "barrier_outcome_counts": {
            value: sum(
                row[
                    "first_barrier_outcome"
                ]
                == value
                for row in outcome_rows
            )
            for value in (
                "target_first",
                "stop_first",
                "same_bar_ambiguous",
                "neither_24b",
                "unavailable_segment_boundary",
            )
        },
        "fold_counts": [
            {
                "split_name": (
                    row["split_name"]
                ),
                "trade_count": (
                    row["trade_count"]
                ),
                "horizon_available_count": (
                    row[
                        "horizon_available_count"
                    ]
                ),
                "target_first_count": (
                    row["target_first_count"]
                ),
                "stop_first_count": (
                    row["stop_first_count"]
                ),
                "same_bar_ambiguous_count": (
                    row[
                        "same_bar_ambiguous_count"
                    ]
                ),
                "neither_24b_count": (
                    row["neither_24b_count"]
                ),
                "unavailable_count": (
                    row["unavailable_count"]
                ),
            }
            for row in fold_rows
        ],
        "anti_leakage_contract": {
            "predictor_features_used": False,
            "future_bars_used_only_as_outcomes": True,
            "outcome_horizon_bars": (
                HORIZON_BARS
            ),
            "outcome_horizon_starts_at": (
                "entry_bar"
            ),
            "actual_strategy_exit_limits_horizon": (
                False
            ),
            "physical_segment_scoped": True,
            "crosses_confirmed_gap": False,
            "intrabar_target_stop_order_inferred": (
                False
            ),
        },
        "artifacts": {
            "manifest_json": str(
                artifacts.manifest_json
            ),
            "outcomes_csv": str(
                artifacts.outcomes_csv
            ),
            "fold_summary_csv": str(
                artifacts.fold_summary_csv
            ),
        },
    }

    if write_artifacts:
        write_csv_atomic(
            path=artifacts.outcomes_csv,
            fieldnames=OUTCOME_FIELDS,
            rows=outcome_rows,
        )

        write_csv_atomic(
            path=artifacts.fold_summary_csv,
            fieldnames=(
                "split_name",
                "trade_count",
                "horizon_available_count",
                "target_first_count",
                "stop_first_count",
                "same_bar_ambiguous_count",
                "neither_24b_count",
                "unavailable_count",
                "mean_mfe_24b_r",
                "median_mfe_24b_r",
                "mean_mae_24b_r",
                "median_mae_24b_r",
                "mean_excursion_quality_24b",
                "median_excursion_quality_24b",
            ),
            rows=fold_rows,
        )

        # Immutable manifest is the completion marker.
        write_json_immutable(
            path=artifacts.manifest_json,
            value=manifest,
        )

    return manifest
