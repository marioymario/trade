from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean, median
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from files.data.paths import processed_dir
from files.research.entry_quality_dataset import (
    OUTCOME_NOT_REACHED_1R,
    OUTCOME_REACHED_1R,
    SOURCE_SIGNAL_FEATURE_NAMES,
    STRUCTURAL_FEATURE_NAMES,
    _load_json_object,
    entry_quality_artifact_paths,
    validate_entry_quality_dataset_id,
)
from files.research.scorer_campaign_io import (
    canonical_json_text,
    write_csv_atomic,
    write_json_immutable,
)
from files.research.scorer_campaign_spec import (
    load_runtime_git_identity,
)


CROSS_ASSET_SCHEMA_VERSION = 1
CROSS_ASSET_TYPE = (
    "entry_quality_cross_asset_characterization_v1"
)
CROSS_ASSET_SPECIFICATION_VERSION = (
    "entry_quality_cross_asset_characterization_v1"
)

MIN_CELL_ROWS = 8

FEATURE_NAMES = (
    *SOURCE_SIGNAL_FEATURE_NAMES,
    *STRUCTURAL_FEATURE_NAMES,
)

_OUTCOME_DATASET_ID_RE = re.compile(
    r"^entry_quality_outcomes_[0-9a-f]{16}$"
)

_CROSS_ASSET_ID_RE = re.compile(
    r"^entry_quality_cross_asset_[0-9a-f]{16}$"
)


class EntryQualityCrossAssetError(RuntimeError):
    """Raised when cross-asset characterization cannot run safely."""


@dataclass(frozen=True)
class SourcePair:
    asset: str
    feature_dataset_id: str
    outcome_dataset_id: str


@dataclass(frozen=True)
class CrossAssetArtifactPaths:
    root: Path
    manifest_json: Path
    asset_summary_csv: Path
    asset_fold_summary_csv: Path
    feature_asset_effects_csv: Path
    feature_fold_effects_csv: Path
    feature_pooled_effects_csv: Path
    feature_asset_balanced_effects_csv: Path


def _research_dir() -> Path:
    return (
        processed_dir()
        / "research"
        / "entry_quality"
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


def _validate_outcome_dataset_id(
    dataset_id: str,
) -> str:
    value = str(dataset_id).strip()

    if not _OUTCOME_DATASET_ID_RE.fullmatch(value):
        raise EntryQualityCrossAssetError(
            "outcome_dataset_id must match "
            "'entry_quality_outcomes_<16 lowercase hex>': "
            f"{dataset_id!r}"
        )

    return value


def _validate_cross_asset_id(
    dataset_id: str,
) -> str:
    value = str(dataset_id).strip()

    if not _CROSS_ASSET_ID_RE.fullmatch(value):
        raise EntryQualityCrossAssetError(
            "cross-asset dataset id is invalid: "
            f"{dataset_id!r}"
        )

    return value


def _artifact_paths(
    *,
    dataset_id: str,
) -> CrossAssetArtifactPaths:
    root = (
        _research_dir()
        / _validate_cross_asset_id(dataset_id)
    )

    return CrossAssetArtifactPaths(
        root=root,
        manifest_json=root / "manifest.json",
        asset_summary_csv=root / "asset_summary.csv",
        asset_fold_summary_csv=(
            root / "asset_fold_summary.csv"
        ),
        feature_asset_effects_csv=(
            root / "feature_asset_effects.csv"
        ),
        feature_fold_effects_csv=(
            root / "feature_fold_effects.csv"
        ),
        feature_pooled_effects_csv=(
            root / "feature_pooled_effects.csv"
        ),
        feature_asset_balanced_effects_csv=(
            root / "feature_asset_balanced_effects.csv"
        ),
    )


def _identity_payload(
    *,
    universe_id: str,
    universe_fingerprint: str,
    eligibility_policy_id: str,
    research_tier: str,
    source_provenance: Sequence[Mapping[str, Any]],
    generator_git_commit: str,
    verification_only: bool,
) -> dict[str, Any]:
    return {
        "dataset_schema_version": CROSS_ASSET_SCHEMA_VERSION,
        "dataset_type": CROSS_ASSET_TYPE,
        "characterization_specification_version": (
            CROSS_ASSET_SPECIFICATION_VERSION
        ),
        "universe_id": str(universe_id),
        "universe_fingerprint": str(universe_fingerprint),
        "eligibility_policy_id": str(eligibility_policy_id),
        "research_tier": str(research_tier),
        "minimum_cell_rows": MIN_CELL_ROWS,
        "feature_names": list(FEATURE_NAMES),
        "analysis_targets": {
            "canonical_binary": {
                "field": "outcome_group",
                "positive": OUTCOME_REACHED_1R,
                "negative": OUTCOME_NOT_REACHED_1R,
            },
            "barrier_binary": {
                "field": "first_barrier_outcome",
                "positive": "target_first",
                "negative": "stop_first",
                "excluded": [
                    "same_bar_ambiguous",
                    "neither_24b",
                    "unavailable_segment_boundary",
                ],
            },
            "continuous_path": {
                "field": "mfe_24b_r",
                "statistic": "spearman_rho",
            },
        },
        "source_provenance": [
            dict(value)
            for value in source_provenance
        ],
        "generator_git_commit": generator_git_commit,
        "verification_only": bool(verification_only),
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
        "entry_quality_cross_asset_"
        f"{digest[:16]}"
    )


def _rank_auc(
    values: Sequence[float],
    labels: Sequence[int],
) -> float:
    frame = pd.DataFrame(
        {
            "value": pd.to_numeric(
                pd.Series(values),
                errors="coerce",
            ),
            "label": pd.to_numeric(
                pd.Series(labels),
                errors="coerce",
            ),
        }
    ).dropna()

    if frame.empty:
        return float("nan")

    positives = frame["label"] == 1
    negatives = frame["label"] == 0

    n_pos = int(positives.sum())
    n_neg = int(negatives.sum())

    if n_pos == 0 or n_neg == 0:
        return float("nan")

    ranks = frame["value"].rank(
        method="average"
    )

    positive_rank_sum = float(
        ranks[positives].sum()
    )

    u_stat = (
        positive_rank_sum
        - n_pos * (n_pos + 1) / 2.0
    )

    return float(
        u_stat / (n_pos * n_neg)
    )


def _spearman(
    x: Sequence[float],
    y: Sequence[float],
) -> float:
    frame = pd.DataFrame(
        {
            "x": pd.to_numeric(
                pd.Series(x),
                errors="coerce",
            ),
            "y": pd.to_numeric(
                pd.Series(y),
                errors="coerce",
            ),
        }
    ).dropna()

    if len(frame) < 3:
        return float("nan")

    x_rank = frame["x"].rank(
        method="average"
    ).to_numpy(dtype=float)

    y_rank = frame["y"].rank(
        method="average"
    ).to_numpy(dtype=float)

    if (
        np.std(x_rank) <= 0.0
        or np.std(y_rank) <= 0.0
    ):
        return float("nan")

    return float(
        np.corrcoef(
            x_rank,
            y_rank,
        )[0, 1]
    )


def _finite_or_blank(
    value: float,
) -> float | str:
    if math.isfinite(value):
        return float(value)
    return ""


def _load_source_pair(
    source: SourcePair,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    asset = str(source.asset).strip()

    if not asset:
        raise EntryQualityCrossAssetError(
            "Source asset must not be empty."
        )

    feature_dataset_id = (
        validate_entry_quality_dataset_id(
            source.feature_dataset_id
        )
    )

    outcome_dataset_id = (
        _validate_outcome_dataset_id(
            source.outcome_dataset_id
        )
    )

    feature_paths = (
        entry_quality_artifact_paths(
            dataset_id=feature_dataset_id
        )
    )

    outcome_root = (
        _research_dir()
        / outcome_dataset_id
    )

    outcome_manifest_path = (
        outcome_root / "manifest.json"
    )
    outcome_csv_path = (
        outcome_root / "outcomes.csv"
    )

    for path in (
        feature_paths.manifest_json,
        feature_paths.trades_csv,
        outcome_manifest_path,
        outcome_csv_path,
    ):
        if not path.exists():
            raise EntryQualityCrossAssetError(
                f"{asset}: required source artifact "
                f"missing: {path}"
            )

    feature_manifest = _load_json_object(
        feature_paths.manifest_json
    )
    outcome_manifest = _load_json_object(
        outcome_manifest_path
    )

    if bool(
        feature_manifest.get(
            "verification_only",
            True,
        )
    ):
        raise EntryQualityCrossAssetError(
            f"{asset}: feature dataset is "
            "verification-only."
        )

    if bool(
        outcome_manifest.get(
            "verification_only",
            True,
        )
    ):
        raise EntryQualityCrossAssetError(
            f"{asset}: outcome dataset is "
            "verification-only."
        )

    if (
        outcome_manifest.get(
            "source_entry_quality_dataset_id"
        )
        != feature_dataset_id
    ):
        raise EntryQualityCrossAssetError(
            f"{asset}: outcome dataset does not "
            "belong to feature dataset."
        )

    for field in (
        "source_campaign_id",
        "source_trial_id",
        "source_manifest_fingerprint",
        "symbol",
        "timeframe",
    ):
        feature_value = feature_manifest.get(field)
        outcome_value = outcome_manifest.get(field)

        if feature_value != outcome_value:
            raise EntryQualityCrossAssetError(
                f"{asset}: source contract mismatch "
                f"for {field}: "
                f"{feature_value!r} != {outcome_value!r}"
            )

    symbol = str(
        feature_manifest.get(
            "symbol",
            "",
        )
    )

    expected_asset = symbol.split("/")[0]

    if asset != expected_asset:
        raise EntryQualityCrossAssetError(
            f"{asset}: asset label does not match "
            f"source symbol {symbol!r}"
        )

    features = pd.read_csv(
        feature_paths.trades_csv
    )
    outcomes = pd.read_csv(
        outcome_csv_path
    )

    key = [
        "campaign_id",
        "trial_id",
        "split_name",
        "signal_ts_ms",
        "entry_ts_ms",
    ]

    if features.duplicated(key).any():
        raise EntryQualityCrossAssetError(
            f"{asset}: duplicate feature identity."
        )

    if outcomes.duplicated(key).any():
        raise EntryQualityCrossAssetError(
            f"{asset}: duplicate outcome identity."
        )

    merged = features.merge(
        outcomes,
        on=key,
        how="inner",
        validate="one_to_one",
        suffixes=(
            "_feature",
            "_outcome",
        ),
    )

    if (
        len(merged) != len(features)
        or len(merged) != len(outcomes)
    ):
        raise EntryQualityCrossAssetError(
            f"{asset}: source row mismatch: "
            f"features={len(features)} "
            f"outcomes={len(outcomes)} "
            f"merged={len(merged)}"
        )

    required = [
        "outcome_group",
        "first_barrier_outcome",
        "mfe_24b_r",
        "horizon_available",
        *FEATURE_NAMES,
    ]

    missing = sorted(
        set(required)
        - set(merged.columns)
    )

    if missing:
        raise EntryQualityCrossAssetError(
            f"{asset}: missing required fields: "
            f"{missing}"
        )

    frame = pd.DataFrame(
        {
            "asset": asset,
            "split_name": (
                merged["split_name"].astype(str)
            ),
            "signal_ts_ms": pd.to_numeric(
                merged["signal_ts_ms"],
                errors="raise",
            ).astype("int64"),
            "entry_ts_ms": pd.to_numeric(
                merged["entry_ts_ms"],
                errors="raise",
            ).astype("int64"),
            "outcome_group": (
                merged["outcome_group"].astype(str)
            ),
            "first_barrier_outcome": (
                merged[
                    "first_barrier_outcome"
                ].astype(str)
            ),
            "horizon_available": (
                merged["horizon_available"]
                .astype(str)
                .str.lower()
                .isin(("true", "1"))
            ),
            "mfe_24b_r": pd.to_numeric(
                merged["mfe_24b_r"],
                errors="coerce",
            ),
        }
    )

    for feature in FEATURE_NAMES:
        frame[feature] = pd.to_numeric(
            merged[feature],
            errors="coerce",
        )

    provenance = {
        "asset": asset,
        "symbol": symbol,
        "feature_dataset_id": feature_dataset_id,
        "feature_manifest_sha256": (
            _sha256_file(
                feature_paths.manifest_json
            )
        ),
        "feature_trades_sha256": (
            _sha256_file(
                feature_paths.trades_csv
            )
        ),
        "outcome_dataset_id": outcome_dataset_id,
        "outcome_manifest_sha256": (
            _sha256_file(
                outcome_manifest_path
            )
        ),
        "outcomes_sha256": (
            _sha256_file(
                outcome_csv_path
            )
        ),
        "source_campaign_id": (
            feature_manifest[
                "source_campaign_id"
            ]
        ),
        "source_trial_id": (
            feature_manifest[
                "source_trial_id"
            ]
        ),
        "source_manifest_fingerprint": (
            feature_manifest[
                "source_manifest_fingerprint"
            ]
        ),
        "data_tag": feature_manifest["data_tag"],
        "timeframe": feature_manifest["timeframe"],
        "trade_count": int(len(frame)),
        "split_names": sorted(
            frame["split_name"]
            .astype(str)
            .unique()
            .tolist()
        ),
    }

    return frame, provenance


def _asset_summary_row(
    frame: pd.DataFrame,
) -> dict[str, Any]:
    canonical_positive = int(
        (
            frame["outcome_group"]
            == OUTCOME_REACHED_1R
        ).sum()
    )
    canonical_negative = int(
        (
            frame["outcome_group"]
            == OUTCOME_NOT_REACHED_1R
        ).sum()
    )

    target_first = int(
        (
            frame["first_barrier_outcome"]
            == "target_first"
        ).sum()
    )
    stop_first = int(
        (
            frame["first_barrier_outcome"]
            == "stop_first"
        ).sum()
    )
    same_bar = int(
        (
            frame["first_barrier_outcome"]
            == "same_bar_ambiguous"
        ).sum()
    )
    neither = int(
        (
            frame["first_barrier_outcome"]
            == "neither_24b"
        ).sum()
    )
    unavailable = int(
        (
            frame["first_barrier_outcome"]
            == "unavailable_segment_boundary"
        ).sum()
    )

    available_mfe = pd.to_numeric(
        frame.loc[
            frame["horizon_available"],
            "mfe_24b_r",
        ],
        errors="coerce",
    ).dropna()

    return {
        "asset": str(frame["asset"].iloc[0]),
        "trade_count": int(len(frame)),
        "canonical_positive_count": canonical_positive,
        "canonical_negative_count": canonical_negative,
        "canonical_positive_rate": (
            canonical_positive / len(frame)
            if len(frame)
            else ""
        ),
        "horizon_available_count": int(
            frame["horizon_available"].sum()
        ),
        "target_first_count": target_first,
        "stop_first_count": stop_first,
        "same_bar_ambiguous_count": same_bar,
        "neither_24b_count": neither,
        "unavailable_count": unavailable,
        "target_vs_stop_target_rate": (
            target_first
            / (target_first + stop_first)
            if (
                target_first + stop_first
            ) > 0
            else ""
        ),
        "mean_mfe_24b_r": (
            float(available_mfe.mean())
            if not available_mfe.empty
            else ""
        ),
        "median_mfe_24b_r": (
            float(available_mfe.median())
            if not available_mfe.empty
            else ""
        ),
    }


def _asset_fold_summary_rows(
    combined: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    grouped = combined.groupby(
        ["asset", "split_name"],
        sort=True,
    )

    for _, cell in grouped:
        row = _asset_summary_row(
            cell.reset_index(drop=True)
        )
        row["split_name"] = str(
            cell["split_name"].iloc[0]
        )
        rows.append(row)

    return rows


def _binary_effect_row(
    *,
    feature_name: str,
    values: pd.Series,
    labels: pd.Series,
    positive_name: str,
    negative_name: str,
) -> dict[str, Any]:
    numeric_values = pd.to_numeric(
        values,
        errors="coerce",
    )

    numeric_labels = pd.to_numeric(
        labels,
        errors="coerce",
    )

    frame = pd.DataFrame(
        {
            "value": numeric_values,
            "label": numeric_labels,
        }
    ).dropna()

    positive_values = (
        frame.loc[
            frame["label"] == 1,
            "value",
        ]
    )
    negative_values = (
        frame.loc[
            frame["label"] == 0,
            "value",
        ]
    )

    auc = _rank_auc(
        frame["value"],
        frame["label"],
    )

    if math.isfinite(auc):
        if auc > 0.5:
            direction = "HIGHER_POSITIVE"
        elif auc < 0.5:
            direction = "LOWER_POSITIVE"
        else:
            direction = "NEUTRAL"
    else:
        direction = "UNEVALUABLE"

    return {
        "feature_name": feature_name,
        "analysis_target": (
            f"{positive_name}_vs_{negative_name}"
        ),
        "row_count": int(len(frame)),
        "positive_count": int(
            (frame["label"] == 1).sum()
        ),
        "negative_count": int(
            (frame["label"] == 0).sum()
        ),
        "positive_mean": (
            float(positive_values.mean())
            if not positive_values.empty
            else ""
        ),
        "negative_mean": (
            float(negative_values.mean())
            if not negative_values.empty
            else ""
        ),
        "positive_median": (
            float(positive_values.median())
            if not positive_values.empty
            else ""
        ),
        "negative_median": (
            float(negative_values.median())
            if not negative_values.empty
            else ""
        ),
        "mean_difference": (
            float(
                positive_values.mean()
                - negative_values.mean()
            )
            if (
                not positive_values.empty
                and not negative_values.empty
            )
            else ""
        ),
        "median_difference": (
            float(
                positive_values.median()
                - negative_values.median()
            )
            if (
                not positive_values.empty
                and not negative_values.empty
            )
            else ""
        ),
        "auc": _finite_or_blank(auc),
        "effect_direction": direction,
        "spearman_rho": "",
    }


def _continuous_effect_row(
    *,
    feature_name: str,
    values: pd.Series,
    target: pd.Series,
) -> dict[str, Any]:
    rho = _spearman(
        values,
        target,
    )

    if math.isfinite(rho):
        if rho > 0.0:
            direction = "HIGHER_TARGET"
        elif rho < 0.0:
            direction = "LOWER_TARGET"
        else:
            direction = "NEUTRAL"
    else:
        direction = "UNEVALUABLE"

    complete = pd.DataFrame(
        {
            "value": pd.to_numeric(
                values,
                errors="coerce",
            ),
            "target": pd.to_numeric(
                target,
                errors="coerce",
            ),
        }
    ).dropna()

    return {
        "feature_name": feature_name,
        "analysis_target": "mfe_24b_r",
        "row_count": int(len(complete)),
        "positive_count": "",
        "negative_count": "",
        "positive_mean": "",
        "negative_mean": "",
        "positive_median": "",
        "negative_median": "",
        "mean_difference": "",
        "median_difference": "",
        "auc": "",
        "effect_direction": direction,
        "spearman_rho": _finite_or_blank(rho),
    }


def _effect_rows_for_frame(
    frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    canonical_mask = frame[
        "outcome_group"
    ].isin(
        (
            OUTCOME_REACHED_1R,
            OUTCOME_NOT_REACHED_1R,
        )
    )

    canonical_labels = (
        frame.loc[
            canonical_mask,
            "outcome_group",
        ]
        == OUTCOME_REACHED_1R
    ).astype(int)

    barrier_mask = frame[
        "first_barrier_outcome"
    ].isin(
        (
            "target_first",
            "stop_first",
        )
    )

    barrier_labels = (
        frame.loc[
            barrier_mask,
            "first_barrier_outcome",
        ]
        == "target_first"
    ).astype(int)

    continuous_mask = (
        frame["horizon_available"]
        & frame["mfe_24b_r"].notna()
    )

    for feature in FEATURE_NAMES:
        canonical = _binary_effect_row(
            feature_name=feature,
            values=frame.loc[
                canonical_mask,
                feature,
            ],
            labels=canonical_labels,
            positive_name="reached_1r",
            negative_name="not_reached_1r",
        )
        rows.append(canonical)

        barrier = _binary_effect_row(
            feature_name=feature,
            values=frame.loc[
                barrier_mask,
                feature,
            ],
            labels=barrier_labels,
            positive_name="target_first",
            negative_name="stop_first",
        )
        rows.append(barrier)

        continuous = _continuous_effect_row(
            feature_name=feature,
            values=frame.loc[
                continuous_mask,
                feature,
            ],
            target=frame.loc[
                continuous_mask,
                "mfe_24b_r",
            ],
        )
        rows.append(continuous)

    return rows


def _scoped_effect_rows(
    combined: pd.DataFrame,
    *,
    scope_columns: Sequence[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    grouped = combined.groupby(
        list(scope_columns),
        sort=True,
    )

    for keys, frame in grouped:
        if not isinstance(keys, tuple):
            keys = (keys,)

        scope = dict(
            zip(
                scope_columns,
                keys,
                strict=True,
            )
        )

        if len(frame) < MIN_CELL_ROWS:
            for feature_name in FEATURE_NAMES:
                for analysis_target in (
                    "reached_1r_vs_not_reached_1r",
                    "target_first_vs_stop_first",
                    "mfe_24b_r",
                ):
                    rows.append(
                        {
                            **scope,
                            "feature_name": feature_name,
                            "analysis_target": analysis_target,
                            "row_count": int(len(frame)),
                            "positive_count": "",
                            "negative_count": "",
                            "positive_mean": "",
                            "negative_mean": "",
                            "positive_median": "",
                            "negative_median": "",
                            "mean_difference": "",
                            "median_difference": "",
                            "auc": "",
                            "effect_direction": "UNEVALUABLE",
                            "spearman_rho": "",
                            "evaluation_status": (
                                "INSUFFICIENT_ROWS"
                            ),
                        }
                    )
            continue

        for row in _effect_rows_for_frame(
            frame.reset_index(drop=True)
        ):
            rows.append(
                {
                    **scope,
                    **row,
                    "evaluation_status": "EVALUABLE",
                }
            )

    return rows


def _pooled_effect_rows(
    combined: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows = _effect_rows_for_frame(
        combined.reset_index(drop=True)
    )

    return [
        {
            "scope": "all_assets_pooled",
            **row,
        }
        for row in rows
    ]


def _asset_balanced_rows(
    asset_effect_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    frame = pd.DataFrame(
        list(asset_effect_rows)
    )

    result: list[dict[str, Any]] = []

    for (
        feature_name,
        analysis_target,
    ), group in frame.groupby(
        [
            "feature_name",
            "analysis_target",
        ],
        sort=True,
    ):
        auc_values = pd.to_numeric(
            group["auc"],
            errors="coerce",
        ).dropna()

        rho_values = pd.to_numeric(
            group["spearman_rho"],
            errors="coerce",
        ).dropna()

        if not auc_values.empty:
            positive_effect_count = int(
                (auc_values > 0.5).sum()
            )
            negative_effect_count = int(
                (auc_values < 0.5).sum()
            )
            neutral_effect_count = int(
                (auc_values == 0.5).sum()
            )

            result.append(
                {
                    "feature_name": feature_name,
                    "analysis_target": analysis_target,
                    "evaluable_asset_count": int(
                        len(auc_values)
                    ),
                    "mean_asset_effect": float(
                        auc_values.mean()
                    ),
                    "median_asset_effect": float(
                        auc_values.median()
                    ),
                    "minimum_asset_effect": float(
                        auc_values.min()
                    ),
                    "maximum_asset_effect": float(
                        auc_values.max()
                    ),
                    "positive_effect_asset_count": (
                        positive_effect_count
                    ),
                    "negative_effect_asset_count": (
                        negative_effect_count
                    ),
                    "neutral_effect_asset_count": (
                        neutral_effect_count
                    ),
                    "effect_statistic": "auc",
                    "neutral_value": 0.5,
                }
            )

        elif not rho_values.empty:
            positive_effect_count = int(
                (rho_values > 0.0).sum()
            )
            negative_effect_count = int(
                (rho_values < 0.0).sum()
            )
            neutral_effect_count = int(
                (rho_values == 0.0).sum()
            )

            result.append(
                {
                    "feature_name": feature_name,
                    "analysis_target": analysis_target,
                    "evaluable_asset_count": int(
                        len(rho_values)
                    ),
                    "mean_asset_effect": float(
                        rho_values.mean()
                    ),
                    "median_asset_effect": float(
                        rho_values.median()
                    ),
                    "minimum_asset_effect": float(
                        rho_values.min()
                    ),
                    "maximum_asset_effect": float(
                        rho_values.max()
                    ),
                    "positive_effect_asset_count": (
                        positive_effect_count
                    ),
                    "negative_effect_asset_count": (
                        negative_effect_count
                    ),
                    "neutral_effect_asset_count": (
                        neutral_effect_count
                    ),
                    "effect_statistic": "spearman_rho",
                    "neutral_value": 0.0,
                }
            )

    return result


def build_entry_quality_cross_asset_characterization(
    *,
    universe_id: str,
    universe_fingerprint: str,
    eligibility_policy_id: str,
    research_tier: str,
    sources: Sequence[SourcePair],
    write_artifacts: bool = True,
) -> dict[str, Any]:
    if len(sources) < 2:
        raise EntryQualityCrossAssetError(
            "Cross-asset characterization requires "
            "at least two source assets."
        )

    asset_names = [
        str(source.asset).strip()
        for source in sources
    ]

    if len(asset_names) != len(set(asset_names)):
        raise EntryQualityCrossAssetError(
            "Duplicate asset labels in source set."
        )

    loaded_frames: list[pd.DataFrame] = []
    source_provenance: list[
        dict[str, Any]
    ] = []

    for source in sources:
        frame, provenance = (
            _load_source_pair(source)
        )

        loaded_frames.append(frame)
        source_provenance.append(
            provenance
        )

    source_provenance.sort(
        key=lambda row: str(row["asset"])
    )

    combined = pd.concat(
        loaded_frames,
        ignore_index=True,
    )

    if combined.empty:
        raise EntryQualityCrossAssetError(
            "No combined research rows."
        )

    asset_summary_rows = [
        _asset_summary_row(
            combined.loc[
                combined["asset"] == asset
            ].reset_index(drop=True)
        )
        for asset in sorted(
            combined["asset"].unique()
        )
    ]

    asset_fold_rows = (
        _asset_fold_summary_rows(
            combined
        )
    )

    feature_asset_rows = (
        _scoped_effect_rows(
            combined,
            scope_columns=("asset",),
        )
    )

    feature_fold_rows = (
        _scoped_effect_rows(
            combined,
            scope_columns=(
                "asset",
                "split_name",
            ),
        )
    )

    pooled_rows = (
        _pooled_effect_rows(
            combined
        )
    )

    asset_balanced_rows = (
        _asset_balanced_rows(
            feature_asset_rows
        )
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
        generator_git_commit = "verification_only"
        verification_only = True

    identity = _identity_payload(
        universe_id=universe_id,
        universe_fingerprint=universe_fingerprint,
        eligibility_policy_id=eligibility_policy_id,
        research_tier=research_tier,
        source_provenance=(
            source_provenance
        ),
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

    counts = sorted(
        (
            int(row["trade_count"])
            for row in asset_summary_rows
        ),
        reverse=True,
    )

    total_trade_count = int(
        sum(counts)
    )

    top_three_trade_count = int(
        sum(counts[:3])
    )

    manifest = {
        **identity,
        "dataset_id": dataset_id,
        "asset_count": int(
            len(asset_summary_rows)
        ),
        "assets": sorted(
            asset_names
        ),
        "trade_count": total_trade_count,
        "top_three_asset_trade_count": (
            top_three_trade_count
        ),
        "top_three_asset_trade_share": (
            top_three_trade_count
            / total_trade_count
        ),
        "asset_summary": asset_summary_rows,
        "analysis_contract": {
            "purpose": (
                "descriptive cross-asset characterization; "
                "does not select or promote features"
            ),
            "pooled_results_are_not_primary_evidence": True,
            "per_asset_results_preserved": True,
            "per_asset_fold_results_preserved": True,
            "asset_balanced_summary_is_unweighted_by_trade_count": True,
            "cross_asset_dependence_adjustment_applied": False,
            "event_cluster_analysis_deferred": True,
            "multiple_hypothesis_promotion_applied": False,
            "feature_selection_applied": False,
        },
        "artifacts": {
            "manifest_json": str(
                artifacts.manifest_json
            ),
            "asset_summary_csv": str(
                artifacts.asset_summary_csv
            ),
            "asset_fold_summary_csv": str(
                artifacts.asset_fold_summary_csv
            ),
            "feature_asset_effects_csv": str(
                artifacts.feature_asset_effects_csv
            ),
            "feature_fold_effects_csv": str(
                artifacts.feature_fold_effects_csv
            ),
            "feature_pooled_effects_csv": str(
                artifacts.feature_pooled_effects_csv
            ),
            "feature_asset_balanced_effects_csv": str(
                artifacts.feature_asset_balanced_effects_csv
            ),
        },
    }

    if write_artifacts:
        write_csv_atomic(
            path=artifacts.asset_summary_csv,
            fieldnames=tuple(
                asset_summary_rows[0]
            ),
            rows=asset_summary_rows,
        )

        write_csv_atomic(
            path=artifacts.asset_fold_summary_csv,
            fieldnames=tuple(
                asset_fold_rows[0]
            ),
            rows=asset_fold_rows,
        )

        write_csv_atomic(
            path=artifacts.feature_asset_effects_csv,
            fieldnames=tuple(
                feature_asset_rows[0]
            ),
            rows=feature_asset_rows,
        )

        write_csv_atomic(
            path=artifacts.feature_fold_effects_csv,
            fieldnames=tuple(
                feature_fold_rows[0]
            ),
            rows=feature_fold_rows,
        )

        write_csv_atomic(
            path=artifacts.feature_pooled_effects_csv,
            fieldnames=tuple(
                pooled_rows[0]
            ),
            rows=pooled_rows,
        )

        write_csv_atomic(
            path=(
                artifacts
                .feature_asset_balanced_effects_csv
            ),
            fieldnames=tuple(
                asset_balanced_rows[0]
            ),
            rows=asset_balanced_rows,
        )

        # Immutable manifest is the completion marker.
        write_json_immutable(
            path=artifacts.manifest_json,
            value=manifest,
        )

    return manifest
