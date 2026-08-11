from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from files.data.paths import processed_dir
from files.research.entry_quality_dataset import (
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


STRUCTURAL_SEARCH_SCHEMA_VERSION = 1
STRUCTURAL_SEARCH_TYPE = "entry_quality_structural_search_v1"
STRUCTURAL_SEARCH_SPECIFICATION_VERSION = (
    "entry_quality_structural_search_v1"
)

OUTCOME_DATASET_ID_RE = re.compile(
    r"^entry_quality_outcomes_[0-9a-f]{16}$"
)

SEARCH_ID_RE = re.compile(
    r"^entry_quality_structural_search_[0-9a-f]{16}$"
)

TARGET_NAME = "mfe_24b_r"

MIN_CELL_ROWS = 8

WEIGHTS = (
    0.2,
    0.3,
    0.4,
    0.5,
    0.6,
    0.7,
    0.8,
)

ORIENTATIONS = (
    "+",
    "-",
)

FAMILY_FEATURES: tuple[tuple[str, str], ...] = (
    (
        "breakout_distance",
        "distance_from_prior_20_high_atr",
    ),
    (
        "trend_extension",
        "signal_close_vs_ema_fast_atr",
    ),
    (
        "range_expansion",
        "current_range_atr",
    ),
    (
        "volume_activity",
        "signal_rvol_20",
    ),
    (
        "rsi_state",
        "signal_rsi",
    ),
    (
        "short_momentum",
        "last_6_positive_bar_count",
    ),
    (
        "candle_shape",
        "signal_lower_wick_pct_of_range",
    ),
    (
        "signal_strength",
        "signal_recomputed_confidence",
    ),
)


class EntryQualityStructuralSearchError(
    RuntimeError
):
    """Raised when structural search cannot run safely."""


@dataclass(frozen=True)
class StructuralSearchArtifactPaths:
    root: Path
    manifest_json: Path
    candidates_csv: Path
    top_candidates_csv: Path
    permutation_summary_json: Path


@dataclass(frozen=True)
class SourcePair:
    asset: str
    feature_dataset_id: str
    outcome_dataset_id: str


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    kind: str
    family_a: str
    feature_a: str
    orientation_a: str
    family_b: str
    feature_b: str
    orientation_b: str
    weight_a: float
    weight_b: float


def _load_json_object(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise EntryQualityStructuralSearchError(
            f"Unable to load JSON: {path}"
        ) from exc

    if not isinstance(value, dict):
        raise EntryQualityStructuralSearchError(
            f"Expected JSON object: {path}"
        )

    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def _research_dir() -> Path:
    return (
        processed_dir()
        / "research"
        / "entry_quality"
    )


def _validate_outcome_dataset_id(
    dataset_id: str,
) -> str:
    value = str(dataset_id).strip()

    if not OUTCOME_DATASET_ID_RE.fullmatch(value):
        raise EntryQualityStructuralSearchError(
            "outcome dataset id must match "
            "'entry_quality_outcomes_<16 lowercase hex>': "
            f"{dataset_id!r}"
        )

    return value


def _validate_search_id(
    search_id: str,
) -> str:
    value = str(search_id).strip()

    if not SEARCH_ID_RE.fullmatch(value):
        raise EntryQualityStructuralSearchError(
            "search id must match "
            "'entry_quality_structural_search_"
            "<16 lowercase hex>': "
            f"{search_id!r}"
        )

    return value


def _artifact_paths(
    *,
    search_id: str,
) -> StructuralSearchArtifactPaths:
    root = (
        _research_dir()
        / _validate_search_id(search_id)
    )

    return StructuralSearchArtifactPaths(
        root=root,
        manifest_json=root / "manifest.json",
        candidates_csv=root / "candidates.csv",
        top_candidates_csv=(
            root / "top_candidates.csv"
        ),
        permutation_summary_json=(
            root / "permutation_summary.json"
        ),
    )


def _verification_git_identity() -> tuple[str, bool]:
    path = Path(
        "files/research/contracts/"
        ".deployed_git_identity.json"
    )

    value = _load_json_object(path)

    commit = str(
        value.get("git_commit", "")
    ).strip()

    if not re.fullmatch(
        r"[0-9a-f]{40}",
        commit,
    ):
        raise EntryQualityStructuralSearchError(
            "Verification deployment has no valid "
            "Git commit identity."
        )

    clean = bool(
        value.get(
            "working_tree_clean",
            False,
        )
    )

    return commit, clean


def _candidate_id(
    payload: Mapping[str, Any],
) -> str:
    digest = hashlib.sha256(
        canonical_json_text(payload).encode(
            "utf-8"
        )
    ).hexdigest()

    return f"structural_candidate_{digest[:16]}"


def _candidate_specs() -> list[CandidateSpec]:
    specs: list[CandidateSpec] = []

    for family, feature in FAMILY_FEATURES:
        for orientation in ORIENTATIONS:
            payload = {
                "kind": "single",
                "family_a": family,
                "feature_a": feature,
                "orientation_a": orientation,
                "family_b": "",
                "feature_b": "",
                "orientation_b": "",
                "weight_a": 1.0,
                "weight_b": 0.0,
            }

            specs.append(
                CandidateSpec(
                    candidate_id=(
                        _candidate_id(payload)
                    ),
                    **payload,
                )
            )

    for index_a in range(
        len(FAMILY_FEATURES)
    ):
        family_a, feature_a = (
            FAMILY_FEATURES[index_a]
        )

        for index_b in range(
            index_a + 1,
            len(FAMILY_FEATURES),
        ):
            family_b, feature_b = (
                FAMILY_FEATURES[index_b]
            )

            for orientation_a in ORIENTATIONS:
                for orientation_b in ORIENTATIONS:
                    for weight_a in WEIGHTS:
                        weight_b = round(
                            1.0 - weight_a,
                            10,
                        )

                        payload = {
                            "kind": "pair",
                            "family_a": family_a,
                            "feature_a": feature_a,
                            "orientation_a": (
                                orientation_a
                            ),
                            "family_b": family_b,
                            "feature_b": feature_b,
                            "orientation_b": (
                                orientation_b
                            ),
                            "weight_a": (
                                float(weight_a)
                            ),
                            "weight_b": (
                                float(weight_b)
                            ),
                        }

                        specs.append(
                            CandidateSpec(
                                candidate_id=(
                                    _candidate_id(
                                        payload
                                    )
                                ),
                                **payload,
                            )
                        )

    ids = [
        spec.candidate_id
        for spec in specs
    ]

    if len(ids) != len(set(ids)):
        raise EntryQualityStructuralSearchError(
            "Candidate identity collision."
        )

    return specs


def _rank_pct(
    values: pd.Series,
) -> pd.Series:
    return values.rank(
        method="average",
        pct=True,
    )


def _oriented(
    values: pd.Series,
    orientation: str,
) -> pd.Series:
    if orientation == "+":
        return values

    if orientation == "-":
        return 1.0 - values

    raise EntryQualityStructuralSearchError(
        f"Unknown orientation: {orientation!r}"
    )


def _spearman(
    x: Sequence[float],
    y: Sequence[float],
) -> float:
    x_series = pd.Series(
        x,
        dtype=float,
    )

    y_series = pd.Series(
        y,
        dtype=float,
    )

    valid = (
        x_series.notna()
        & y_series.notna()
    )

    x_series = x_series[valid]
    y_series = y_series[valid]

    if len(x_series) < 3:
        return float("nan")

    x_rank = x_series.rank(
        method="average"
    ).to_numpy(dtype=float)

    y_rank = y_series.rank(
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


def _zscore_rank(
    values: Sequence[float],
) -> np.ndarray | None:
    ranks = pd.Series(
        values,
        dtype=float,
    ).rank(
        method="average"
    ).to_numpy(dtype=float)

    if len(ranks) < 3:
        return None

    std = float(
        np.std(
            ranks,
            ddof=1,
        )
    )

    if (
        not math.isfinite(std)
        or std <= 0.0
    ):
        return None

    return (
        ranks - float(np.mean(ranks))
    ) / std


def _load_source_pair(
    source: SourcePair,
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
]:
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
            raise EntryQualityStructuralSearchError(
                f"Required source artifact missing: {path}"
            )

    feature_manifest = _load_json_object(
        feature_paths.manifest_json
    )

    outcome_manifest = _load_json_object(
        outcome_manifest_path
    )

    if (
        outcome_manifest.get(
            "source_entry_quality_dataset_id"
        )
        != feature_dataset_id
    ):
        raise EntryQualityStructuralSearchError(
            f"{source.asset}: outcome dataset does not "
            "belong to feature dataset."
        )

    for field in (
        "source_campaign_id",
        "source_trial_id",
        "source_manifest_fingerprint",
        "symbol",
        "timeframe",
    ):
        feature_value = feature_manifest.get(
            field
        )

        outcome_value = outcome_manifest.get(
            field
        )

        if feature_value != outcome_value:
            raise EntryQualityStructuralSearchError(
                f"{source.asset}: source contract mismatch "
                f"for {field}: "
                f"{feature_value!r} != {outcome_value!r}"
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
        raise EntryQualityStructuralSearchError(
            f"{source.asset}: duplicate feature identity."
        )

    if outcomes.duplicated(key).any():
        raise EntryQualityStructuralSearchError(
            f"{source.asset}: duplicate outcome identity."
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
        raise EntryQualityStructuralSearchError(
            f"{source.asset}: source row mismatch: "
            f"features={len(features)} "
            f"outcomes={len(outcomes)} "
            f"merged={len(merged)}"
        )

    required = [
        TARGET_NAME,
        *[
            feature
            for _, feature
            in FAMILY_FEATURES
        ],
    ]

    missing = sorted(
        set(required)
        - set(merged.columns)
    )

    if missing:
        raise EntryQualityStructuralSearchError(
            f"{source.asset}: missing required fields: "
            f"{missing}"
        )

    frame = pd.DataFrame(
        {
            "asset": str(source.asset),
            "split_name": (
                merged["split_name"].astype(str)
            ),
            TARGET_NAME: pd.to_numeric(
                merged[TARGET_NAME],
                errors="coerce",
            ),
        }
    )

    for _, feature in FAMILY_FEATURES:
        frame[feature] = pd.to_numeric(
            merged[feature],
            errors="coerce",
        )

    complete_columns = [
        TARGET_NAME,
        *[
            feature
            for _, feature
            in FAMILY_FEATURES
        ],
    ]

    frame = (
        frame
        .dropna(
            subset=complete_columns
        )
        .reset_index(drop=True)
    )

    if frame.empty:
        raise EntryQualityStructuralSearchError(
            f"{source.asset}: no complete research rows."
        )

    for feature in (
        feature
        for _, feature
        in FAMILY_FEATURES
    ):
        frame[
            f"rank__{feature}"
        ] = (
            frame.groupby(
                "split_name"
            )[feature]
            .transform(_rank_pct)
        )

    cell_counts = (
        frame.groupby(
            "split_name"
        )
        .size()
        .to_dict()
    )

    for split_name, count in (
        cell_counts.items()
    ):
        if int(count) < MIN_CELL_ROWS:
            raise EntryQualityStructuralSearchError(
                f"{source.asset}/{split_name}: "
                f"only {count} complete rows; "
                f"minimum={MIN_CELL_ROWS}"
            )

    provenance = {
        "asset": source.asset,
        "feature_dataset_id": (
            feature_dataset_id
        ),
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
        "outcome_dataset_id": (
            outcome_dataset_id
        ),
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
        "data_tag": feature_manifest[
            "data_tag"
        ],
        "symbol": feature_manifest[
            "symbol"
        ],
        "timeframe": feature_manifest[
            "timeframe"
        ],
        "original_trade_count": int(
            len(merged)
        ),
        "complete_case_trade_count": int(
            len(frame)
        ),
        "cell_counts": {
            str(key): int(value)
            for key, value
            in sorted(
                cell_counts.items()
            )
        },
    }

    return frame, provenance


def _candidate_score(
    frame: pd.DataFrame,
    spec: CandidateSpec,
) -> pd.Series:
    score_a = _oriented(
        frame[
            f"rank__{spec.feature_a}"
        ],
        spec.orientation_a,
    )

    if spec.kind == "single":
        return score_a

    score_b = _oriented(
        frame[
            f"rank__{spec.feature_b}"
        ],
        spec.orientation_b,
    )

    return (
        float(spec.weight_a) * score_a
        + float(spec.weight_b) * score_b
    )


def _evaluate_candidates(
    *,
    combined: pd.DataFrame,
    specs: Sequence[CandidateSpec],
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, np.ndarray]],
    dict[str, np.ndarray],
]:
    cell_names = sorted(
        {
            (
                str(row.asset),
                str(row.split_name),
            )
            for row in combined[
                ["asset", "split_name"]
            ].itertuples(index=False)
        }
    )

    if len(cell_names) != 6:
        raise EntryQualityStructuralSearchError(
            "Expected exactly six asset/fold cells; "
            f"found={cell_names}"
        )

    target_z_by_cell: dict[
        str,
        np.ndarray,
    ] = {}

    cell_index_by_name: dict[
        str,
        np.ndarray,
    ] = {}

    for asset, split_name in cell_names:
        name = f"{asset}|{split_name}"

        idx = np.flatnonzero(
            (
                combined["asset"].to_numpy()
                == asset
            )
            & (
                combined[
                    "split_name"
                ].to_numpy()
                == split_name
            )
        )

        cell_index_by_name[name] = idx

        target_z = _zscore_rank(
            combined.iloc[idx][
                TARGET_NAME
            ].to_numpy(dtype=float)
        )

        if target_z is None:
            raise EntryQualityStructuralSearchError(
                f"Target is not rank-variable in {name}"
            )

        target_z_by_cell[name] = target_z

    candidate_rows: list[
        dict[str, Any]
    ] = []

    score_z_by_candidate: dict[
        str,
        dict[str, np.ndarray],
    ] = {}

    for spec in specs:
        score = _candidate_score(
            combined,
            spec,
        )

        fold_rhos: dict[
            str,
            float,
        ] = {}

        score_z_by_cell: dict[
            str,
            np.ndarray,
        ] = {}

        valid = True

        for cell_name, idx in (
            cell_index_by_name.items()
        ):
            score_values = (
                score.iloc[idx]
                .to_numpy(dtype=float)
            )

            score_z = _zscore_rank(
                score_values
            )

            if score_z is None:
                valid = False
                break

            score_z_by_cell[
                cell_name
            ] = score_z

            target_z = target_z_by_cell[
                cell_name
            ]

            rho = float(
                np.dot(
                    score_z,
                    target_z,
                )
                / (
                    len(score_z) - 1
                )
            )

            fold_rhos[
                cell_name
            ] = rho

        if not valid:
            continue

        asset_overall: dict[
            str,
            float,
        ] = {}

        for asset in sorted(
            combined["asset"].unique()
        ):
            mask = (
                combined["asset"]
                == asset
            )

            rho = _spearman(
                score[mask].to_numpy(
                    dtype=float
                ),
                combined.loc[
                    mask,
                    TARGET_NAME,
                ].to_numpy(dtype=float),
            )

            if not math.isfinite(rho):
                valid = False
                break

            asset_overall[
                str(asset)
            ] = rho

        if not valid:
            continue

        rhos = list(
            fold_rhos.values()
        )

        row = {
            "candidate_id": (
                spec.candidate_id
            ),
            "kind": spec.kind,
            "family_a": spec.family_a,
            "feature_a": spec.feature_a,
            "orientation_a": (
                spec.orientation_a
            ),
            "family_b": spec.family_b,
            "feature_b": spec.feature_b,
            "orientation_b": (
                spec.orientation_b
            ),
            "weight_a": (
                spec.weight_a
            ),
            "weight_b": (
                spec.weight_b
            ),
            "btc_overall_rho": (
                asset_overall["BTC"]
            ),
            "eth_overall_rho": (
                asset_overall["ETH"]
            ),
            "worst_asset_overall_rho": min(
                asset_overall.values()
            ),
            "min_cell_rho": min(rhos),
            "median_cell_rho": float(
                median(rhos)
            ),
            "mean_cell_rho": float(
                sum(rhos) / len(rhos)
            ),
            "positive_cell_count": sum(
                rho > 0.0
                for rho in rhos
            ),
            "all_cells_positive": all(
                rho > 0.0
                for rho in rhos
            ),
        }

        for cell_name in sorted(
            fold_rhos
        ):
            safe_name = (
                cell_name
                .replace("|", "__")
                .replace("-", "_")
            )

            row[
                f"rho__{safe_name}"
            ] = fold_rhos[
                cell_name
            ]

        candidate_rows.append(row)

        score_z_by_candidate[
            spec.candidate_id
        ] = score_z_by_cell

    if not candidate_rows:
        raise EntryQualityStructuralSearchError(
            "No evaluable candidates."
        )

    candidate_rows.sort(
        key=lambda row: (
            -float(
                row["min_cell_rho"]
            ),
            -float(
                row[
                    "worst_asset_overall_rho"
                ]
            ),
            -float(
                row["median_cell_rho"]
            ),
            str(
                row["candidate_id"]
            ),
        )
    )

    return (
        candidate_rows,
        score_z_by_candidate,
        target_z_by_cell,
    )


def _attach_neighborhood_stability(
    rows: list[dict[str, Any]],
) -> None:
    lookup: dict[
        tuple[
            str,
            str,
            str,
            str,
            str,
            float,
        ],
        dict[str, Any],
    ] = {}

    for row in rows:
        if row["kind"] != "pair":
            continue

        key = (
            str(row["family_a"]),
            str(row["orientation_a"]),
            str(row["family_b"]),
            str(row["orientation_b"]),
            "pair",
            round(
                float(row["weight_a"]),
                1,
            ),
        )

        lookup[key] = row

    for row in rows:
        if row["kind"] == "single":
            row[
                "neighbor_candidate_count"
            ] = 1

            row[
                "neighbor_min_cell_rho"
            ] = row["min_cell_rho"]

            row[
                "neighbor_mean_min_cell_rho"
            ] = row["min_cell_rho"]

            continue

        neighbor_values: list[
            float
        ] = []

        center = round(
            float(row["weight_a"]),
            1,
        )

        for weight in (
            round(center - 0.1, 1),
            center,
            round(center + 0.1, 1),
        ):
            key = (
                str(row["family_a"]),
                str(row["orientation_a"]),
                str(row["family_b"]),
                str(row["orientation_b"]),
                "pair",
                weight,
            )

            neighbor = lookup.get(key)

            if neighbor is not None:
                neighbor_values.append(
                    float(
                        neighbor[
                            "min_cell_rho"
                        ]
                    )
                )

        row[
            "neighbor_candidate_count"
        ] = len(neighbor_values)

        row[
            "neighbor_min_cell_rho"
        ] = min(
            neighbor_values
        )

        row[
            "neighbor_mean_min_cell_rho"
        ] = float(
            sum(neighbor_values)
            / len(neighbor_values)
        )


def _permutation_calibration(
    *,
    rows: Sequence[Mapping[str, Any]],
    score_z_by_candidate: Mapping[
        str,
        Mapping[str, np.ndarray],
    ],
    target_z_by_cell: Mapping[
        str,
        np.ndarray,
    ],
    permutation_count: int,
    random_seed: int,
) -> dict[str, Any]:
    candidate_ids = [
        str(row["candidate_id"])
        for row in rows
    ]

    cell_names = sorted(
        target_z_by_cell
    )

    score_matrices: dict[
        str,
        np.ndarray,
    ] = {}

    for cell_name in cell_names:
        score_matrices[
            cell_name
        ] = np.vstack(
            [
                score_z_by_candidate[
                    candidate_id
                ][cell_name]
                for candidate_id
                in candidate_ids
            ]
        )

    observed_best = float(
        rows[0]["min_cell_rho"]
    )

    rng = np.random.default_rng(
        int(random_seed)
    )

    null_best = np.empty(
        int(permutation_count),
        dtype=float,
    )

    for permutation_index in range(
        int(permutation_count)
    ):
        per_cell_rhos: list[
            np.ndarray
        ] = []

        for cell_name in cell_names:
            target_z = (
                target_z_by_cell[
                    cell_name
                ].copy()
            )

            rng.shuffle(target_z)

            matrix = score_matrices[
                cell_name
            ]

            rho = (
                matrix @ target_z
            ) / (
                matrix.shape[1] - 1
            )

            per_cell_rhos.append(
                rho
            )

        minimum_by_candidate = (
            np.min(
                np.vstack(
                    per_cell_rhos
                ),
                axis=0,
            )
        )

        null_best[
            permutation_index
        ] = float(
            np.max(
                minimum_by_candidate
            )
        )

    exceed_count = int(
        np.sum(
            null_best
            >= observed_best
        )
    )

    empirical_p = (
        exceed_count + 1
    ) / (
        int(permutation_count) + 1
    )

    return {
        "permutation_count": int(
            permutation_count
        ),
        "random_seed": int(
            random_seed
        ),
        "search_wide_statistic": (
            "maximum candidate min_cell_rho "
            "across the complete candidate search"
        ),
        "observed_best_min_cell_rho": (
            observed_best
        ),
        "null_ge_observed_count": (
            exceed_count
        ),
        "search_wide_empirical_p": (
            empirical_p
        ),
        "null_best_min_cell_rho_percentiles": {
            "p50": float(
                np.percentile(
                    null_best,
                    50,
                )
            ),
            "p75": float(
                np.percentile(
                    null_best,
                    75,
                )
            ),
            "p90": float(
                np.percentile(
                    null_best,
                    90,
                )
            ),
            "p95": float(
                np.percentile(
                    null_best,
                    95,
                )
            ),
            "p99": float(
                np.percentile(
                    null_best,
                    99,
                )
            ),
        },
    }


def _identity_payload(
    *,
    provenance: Sequence[
        Mapping[str, Any]
    ],
    candidate_count: int,
    evaluable_candidate_count: int,
    permutation_count: int,
    random_seed: int,
    generator_git_commit: str,
    verification_only: bool,
) -> dict[str, Any]:
    return {
        "search_schema_version": (
            STRUCTURAL_SEARCH_SCHEMA_VERSION
        ),
        "search_type": (
            STRUCTURAL_SEARCH_TYPE
        ),
        "search_specification_version": (
            STRUCTURAL_SEARCH_SPECIFICATION_VERSION
        ),
        "target": TARGET_NAME,
        "source_contracts": [
            dict(value)
            for value in provenance
        ],
        "feature_families": [
            {
                "family": family,
                "feature": feature,
            }
            for family, feature
            in FAMILY_FEATURES
        ],
        "candidate_contract": {
            "single_features": True,
            "two_family_weighted_blends": True,
            "orientations": list(
                ORIENTATIONS
            ),
            "weight_a_values": list(
                WEIGHTS
            ),
            "weight_b": "1 - weight_a",
            "rank_normalization": (
                "within each asset and "
                "validation fold"
            ),
            "common_complete_case_universe": (
                True
            ),
            "minimum_rows_per_asset_fold": (
                MIN_CELL_ROWS
            ),
            "candidate_count": int(
                candidate_count
            ),
            "evaluable_candidate_count": int(
                evaluable_candidate_count
            ),
        },
        "ranking_contract": {
            "primary": (
                "maximize min_cell_rho "
                "across all BTC/ETH validation folds"
            ),
            "tie_break_1": (
                "maximize worst_asset_overall_rho"
            ),
            "tie_break_2": (
                "maximize median_cell_rho"
            ),
            "neighborhood_stability": (
                "reported for adjacent pair weights; "
                "not used to select the winner"
            ),
        },
        "permutation_contract": {
            "target_shuffle_scope": (
                "independently within each asset "
                "and validation fold"
            ),
            "entire_search_repeated": True,
            "permutation_count": int(
                permutation_count
            ),
            "random_seed": int(
                random_seed
            ),
        },
        "anti_leakage_contract": {
            "predictors": (
                "entry-time features only"
            ),
            "target": (
                "future 24-bar MFE in canonical R units"
            ),
            "target_used_for_candidate_generation": (
                False
            ),
            "protected_2025_plus_data_used": (
                False
            ),
            "search_uses_only_existing_"
            "validation_populations": True,
        },
        "generator_git_commit": (
            generator_git_commit
        ),
        "verification_only": bool(
            verification_only
        ),
    }


def _search_id_for_payload(
    payload: Mapping[str, Any],
) -> str:
    digest = hashlib.sha256(
        canonical_json_text(payload).encode(
            "utf-8"
        )
    ).hexdigest()

    return (
        "entry_quality_structural_search_"
        f"{digest[:16]}"
    )


def run_entry_quality_structural_search(
    *,
    btc_feature_dataset_id: str,
    btc_outcome_dataset_id: str,
    eth_feature_dataset_id: str,
    eth_outcome_dataset_id: str,
    permutation_count: int = 10_000,
    random_seed: int = 20260811,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    if permutation_count <= 0:
        raise EntryQualityStructuralSearchError(
            "permutation_count must be positive."
        )

    sources = (
        SourcePair(
            asset="BTC",
            feature_dataset_id=(
                btc_feature_dataset_id
            ),
            outcome_dataset_id=(
                btc_outcome_dataset_id
            ),
        ),
        SourcePair(
            asset="ETH",
            feature_dataset_id=(
                eth_feature_dataset_id
            ),
            outcome_dataset_id=(
                eth_outcome_dataset_id
            ),
        ),
    )

    frames: list[pd.DataFrame] = []
    provenance: list[
        dict[str, Any]
    ] = []

    for source in sources:
        frame, source_provenance = (
            _load_source_pair(source)
        )

        frames.append(frame)
        provenance.append(
            source_provenance
        )

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    specs = _candidate_specs()

    (
        candidate_rows,
        score_z_by_candidate,
        target_z_by_cell,
    ) = _evaluate_candidates(
        combined=combined,
        specs=specs,
    )

    _attach_neighborhood_stability(
        candidate_rows
    )

    permutation_summary = (
        _permutation_calibration(
            rows=candidate_rows,
            score_z_by_candidate=(
                score_z_by_candidate
            ),
            target_z_by_cell=(
                target_z_by_cell
            ),
            permutation_count=(
                permutation_count
            ),
            random_seed=random_seed,
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
        (
            generator_git_commit,
            clean,
        ) = _verification_git_identity()

        verification_only = not clean

    identity = _identity_payload(
        provenance=provenance,
        candidate_count=len(specs),
        evaluable_candidate_count=len(
            candidate_rows
        ),
        permutation_count=(
            permutation_count
        ),
        random_seed=random_seed,
        generator_git_commit=(
            generator_git_commit
        ),
        verification_only=(
            verification_only
        ),
    )

    search_id = _search_id_for_payload(
        identity
    )

    artifacts = _artifact_paths(
        search_id=search_id
    )

    top_count = min(
        25,
        len(candidate_rows),
    )

    top_rows = candidate_rows[
        :top_count
    ]

    best = top_rows[0]

    manifest = {
        **identity,
        "search_id": search_id,
        "generated_candidate_count": (
            len(specs)
        ),
        "evaluable_candidate_count": (
            len(candidate_rows)
        ),
        "best_candidate": dict(best),
        "permutation_summary": (
            permutation_summary
        ),
        "research_conclusion_contract": {
            "winner_is_automatically_"
            "approved_for_strategy": False,
            "search_result_is_diagnostic": (
                True
            ),
            "survivors_require_full_engine_"
            "testing_before_strategy_change": True,
        },
        "artifacts": {
            "manifest_json": str(
                artifacts.manifest_json
            ),
            "candidates_csv": str(
                artifacts.candidates_csv
            ),
            "top_candidates_csv": str(
                artifacts.top_candidates_csv
            ),
            "permutation_summary_json": str(
                artifacts.permutation_summary_json
            ),
        },
    }

    if write_artifacts:
        fieldnames = list(
            candidate_rows[0].keys()
        )

        write_csv_atomic(
            path=artifacts.candidates_csv,
            fieldnames=fieldnames,
            rows=candidate_rows,
        )

        write_csv_atomic(
            path=artifacts.top_candidates_csv,
            fieldnames=fieldnames,
            rows=top_rows,
        )

        write_json_immutable(
            path=(
                artifacts.permutation_summary_json
            ),
            value=permutation_summary,
        )

        write_json_immutable(
            path=artifacts.manifest_json,
            value=manifest,
        )

    return manifest
