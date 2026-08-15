from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from files.research.entry_quality_cross_asset_characterization import (
    SourcePair,
    _load_source_pair,
)
from files.research.entry_quality_event_dependence import (
    CLUSTER_GAP_MINUTES,
    PRIMARY_CLUSTER_GAP_MINUTES,
    _assign_event_clusters,
    _weighted_rank_expansion,
)
from files.research.scorer_campaign_spec import (
    load_runtime_git_identity,
)


EVENT_ROBUSTNESS_SCHEMA_VERSION = 1
EVENT_ROBUSTNESS_DATASET_TYPE = (
    "entry_quality_event_robustness_v1"
)
EVENT_ROBUSTNESS_SPECIFICATION_VERSION = (
    "entry_quality_event_robustness_v1"
)

DEFAULT_BOOTSTRAP_REPS = 5000
DEFAULT_PERMUTATION_REPS = 10000
DEFAULT_RANDOM_SEED = 20260814

PRIMARY_TARGET = "mean_mfe_24b_r"
SECONDARY_TARGET = "canonical_positive_rate"

FEATURE_DIRECTIONS = {
    "current_range_vs_prior_10_mean": 1,
    "current_range_atr": 1,
    "signal_vol_z": 1,
    "signal_rvol_20": 1,
    "distance_from_prior_20_high_atr": 1,
    "signal_ema_spread": -1,
}

FEATURE_NAMES = tuple(
    FEATURE_DIRECTIONS.keys()
)


class EntryQualityEventRobustnessError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class EventRobustnessArtifactPaths:
    root: Path
    manifest_json: Path
    observed_effects_csv: Path
    bootstrap_results_csv: Path
    permutation_results_csv: Path
    sensitivity_summary_csv: Path


def _research_dir() -> Path:
    return Path(
        "data/processed/research/entry_quality"
    )


def _artifact_paths(
    *,
    dataset_id: str,
) -> EventRobustnessArtifactPaths:
    root = _research_dir() / dataset_id

    return EventRobustnessArtifactPaths(
        root=root,
        manifest_json=root / "manifest.json",
        observed_effects_csv=(
            root / "observed_effects.csv"
        ),
        bootstrap_results_csv=(
            root / "bootstrap_results.csv"
        ),
        permutation_results_csv=(
            root / "permutation_results.csv"
        ),
        sensitivity_summary_csv=(
            root / "sensitivity_summary.csv"
        ),
    )


def _identity_payload(
    *,
    universe_id: str,
    universe_fingerprint: str,
    eligibility_policy_id: str,
    research_tier: str,
    source_provenance: Sequence[
        dict[str, Any]
    ],
    bootstrap_reps: int,
    permutation_reps: int,
    random_seed: int,
    generator_git_commit: str,
    verification_only: bool,
) -> dict[str, Any]:
    return {
        "dataset_schema_version": (
            EVENT_ROBUSTNESS_SCHEMA_VERSION
        ),
        "dataset_type": (
            EVENT_ROBUSTNESS_DATASET_TYPE
        ),
        "event_robustness_specification_version": (
            EVENT_ROBUSTNESS_SPECIFICATION_VERSION
        ),
        "universe_id": universe_id,
        "universe_fingerprint": (
            universe_fingerprint
        ),
        "eligibility_policy_id": (
            eligibility_policy_id
        ),
        "research_tier": research_tier,
        "feature_names": list(FEATURE_NAMES),
        "feature_expected_directions": {
            feature: (
                "HIGHER_TARGET"
                if direction > 0
                else "LOWER_TARGET"
            )
            for feature, direction
            in FEATURE_DIRECTIONS.items()
        },
        "primary_target": PRIMARY_TARGET,
        "secondary_target": SECONDARY_TARGET,
        "cluster_gap_minutes": list(
            CLUSTER_GAP_MINUTES
        ),
        "primary_cluster_gap_minutes": (
            PRIMARY_CLUSTER_GAP_MINUTES
        ),
        "bootstrap_reps": int(
            bootstrap_reps
        ),
        "permutation_reps": int(
            permutation_reps
        ),
        "random_seed": int(random_seed),
        "source_provenance": list(
            source_provenance
        ),
        "generator_git_commit": (
            generator_git_commit
        ),
        "verification_only": bool(
            verification_only
        ),
    }


def _dataset_id_for_payload(
    payload: dict[str, Any],
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    digest = hashlib.sha256(
        encoded
    ).hexdigest()[:16]

    return (
        "entry_quality_event_robustness_"
        f"{digest}"
    )


def _rank_average(
    values: np.ndarray,
) -> np.ndarray:
    values = np.asarray(
        values,
        dtype=float,
    )

    n = int(values.size)

    if n == 0:
        return np.asarray(
            [],
            dtype=float,
        )

    order = np.argsort(
        values,
        kind="mergesort",
    )

    sorted_values = values[order]
    ranks = np.empty(
        n,
        dtype=float,
    )

    start = 0

    while start < n:
        end = start + 1

        while (
            end < n
            and sorted_values[end]
            == sorted_values[start]
        ):
            end += 1

        average_rank = (
            (start + 1 + end) / 2.0
        )

        ranks[
            order[start:end]
        ] = average_rank

        start = end

    return ranks


def _spearman_arrays(
    x: np.ndarray,
    y: np.ndarray,
) -> float:
    x = np.asarray(
        x,
        dtype=float,
    )
    y = np.asarray(
        y,
        dtype=float,
    )

    mask = (
        np.isfinite(x)
        & np.isfinite(y)
    )

    x = x[mask]
    y = y[mask]

    if x.size < 3:
        return float("nan")

    if (
        np.all(x == x[0])
        or np.all(y == y[0])
    ):
        return float("nan")

    rx = _rank_average(x)
    ry = _rank_average(y)

    rx_centered = rx - rx.mean()
    ry_centered = ry - ry.mean()

    denominator = math.sqrt(
        float(
            np.dot(
                rx_centered,
                rx_centered,
            )
        )
        * float(
            np.dot(
                ry_centered,
                ry_centered,
            )
        )
    )

    if denominator <= 0.0:
        return float("nan")

    return float(
        np.dot(
            rx_centered,
            ry_centered,
        )
        / denominator
    )


def _build_event_frames(
    combined: pd.DataFrame,
) -> dict[int, pd.DataFrame]:
    result: dict[
        int,
        pd.DataFrame,
    ] = {}

    for gap_minutes in CLUSTER_GAP_MINUTES:
        clustered = _assign_event_clusters(
            combined,
            gap_minutes=int(
                gap_minutes
            ),
        )

        events = _weighted_rank_expansion(
            clustered
        )

        if events.empty:
            raise EntryQualityEventRobustnessError(
                "Event frame is empty for "
                f"{gap_minutes}-minute clustering."
            )

        result[int(gap_minutes)] = (
            events.reset_index(drop=True)
        )

    return result


def _fold_names(
    events: pd.DataFrame,
) -> list[str]:
    names = sorted(
        events["split_name"]
        .astype(str)
        .unique()
        .tolist()
    )

    if len(names) < 2:
        raise EntryQualityEventRobustnessError(
            "Robustness analysis requires "
            "multiple validation folds."
        )

    return names


def _observed_statistic(
    *,
    events: pd.DataFrame,
    feature_name: str,
    target_name: str,
    expected_direction: int,
) -> tuple[
    float,
    list[dict[str, Any]],
]:
    fold_rows: list[
        dict[str, Any]
    ] = []
    oriented_effects: list[
        float
    ] = []

    for split_name in _fold_names(
        events
    ):
        fold = events.loc[
            events["split_name"]
            .astype(str)
            == split_name
        ]

        rho = _spearman_arrays(
            fold[feature_name]
            .to_numpy(dtype=float),
            fold[target_name]
            .to_numpy(dtype=float),
        )

        oriented = (
            rho * expected_direction
            if math.isfinite(rho)
            else float("nan")
        )

        fold_rows.append(
            {
                "split_name": split_name,
                "event_count": int(
                    len(fold)
                ),
                "spearman_rho": rho,
                "oriented_effect": (
                    oriented
                ),
            }
        )

        if math.isfinite(oriented):
            oriented_effects.append(
                oriented
            )

    if len(oriented_effects) != len(
        fold_rows
    ):
        return (
            float("nan"),
            fold_rows,
        )

    return (
        float(
            np.mean(
                oriented_effects
            )
        ),
        fold_rows,
    )


def _bootstrap_statistic(
    *,
    events: pd.DataFrame,
    feature_name: str,
    target_name: str,
    expected_direction: int,
    rng: np.random.Generator,
) -> float:
    effects: list[float] = []

    for split_name in _fold_names(
        events
    ):
        fold = events.loc[
            events["split_name"]
            .astype(str)
            == split_name
        ]

        n = int(len(fold))

        indexes = rng.integers(
            low=0,
            high=n,
            size=n,
        )

        x = (
            fold[feature_name]
            .to_numpy(dtype=float)[
                indexes
            ]
        )
        y = (
            fold[target_name]
            .to_numpy(dtype=float)[
                indexes
            ]
        )

        rho = _spearman_arrays(
            x,
            y,
        )

        if not math.isfinite(rho):
            return float("nan")

        effects.append(
            rho * expected_direction
        )

    return float(
        np.mean(effects)
    )


def _permuted_family_statistics(
    *,
    events: pd.DataFrame,
    target_name: str,
    rng: np.random.Generator,
) -> dict[str, float]:
    fold_names = _fold_names(events)

    feature_fold_effects: dict[
        str,
        list[float],
    ] = {
        feature: []
        for feature in FEATURE_NAMES
    }

    for split_name in fold_names:
        fold = events.loc[
            events["split_name"]
            .astype(str)
            == split_name
        ]

        target = (
            fold[target_name]
            .to_numpy(dtype=float)
        )

        finite_target = np.isfinite(
            target
        )

        permuted = target.copy()

        positions = np.flatnonzero(
            finite_target
        )

        permuted[
            positions
        ] = target[
            rng.permutation(
                positions
            )
        ]

        for feature in FEATURE_NAMES:
            rho = _spearman_arrays(
                fold[feature]
                .to_numpy(dtype=float),
                permuted,
            )

            if not math.isfinite(rho):
                feature_fold_effects[
                    feature
                ].append(
                    float("nan")
                )
            else:
                feature_fold_effects[
                    feature
                ].append(
                    rho
                    * FEATURE_DIRECTIONS[
                        feature
                    ]
                )

    result: dict[str, float] = {}

    for feature in FEATURE_NAMES:
        effects = feature_fold_effects[
            feature
        ]

        if not all(
            math.isfinite(value)
            for value in effects
        ):
            result[feature] = (
                float("nan")
            )
        else:
            result[feature] = float(
                np.mean(effects)
            )

    return result


def _observed_rows(
    *,
    event_frames: dict[
        int,
        pd.DataFrame,
    ],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for (
        gap_minutes,
        events,
    ) in sorted(
        event_frames.items()
    ):
        for target_name in (
            PRIMARY_TARGET,
            SECONDARY_TARGET,
        ):
            for feature_name in (
                FEATURE_NAMES
            ):
                direction = (
                    FEATURE_DIRECTIONS[
                        feature_name
                    ]
                )

                statistic, folds = (
                    _observed_statistic(
                        events=events,
                        feature_name=(
                            feature_name
                        ),
                        target_name=(
                            target_name
                        ),
                        expected_direction=(
                            direction
                        ),
                    )
                )

                row = {
                    "cluster_gap_minutes": (
                        gap_minutes
                    ),
                    "is_primary_gap": (
                        gap_minutes
                        == PRIMARY_CLUSTER_GAP_MINUTES
                    ),
                    "target_name": (
                        target_name
                    ),
                    "is_primary_target": (
                        target_name
                        == PRIMARY_TARGET
                    ),
                    "feature_name": (
                        feature_name
                    ),
                    "expected_direction": (
                        "HIGHER_TARGET"
                        if direction > 0
                        else "LOWER_TARGET"
                    ),
                    "fold_balanced_oriented_effect": (
                        statistic
                    ),
                    "fold_count": int(
                        len(folds)
                    ),
                }

                for fold_index, fold in enumerate(
                    folds,
                    start=1,
                ):
                    prefix = (
                        f"fold_{fold_index}"
                    )
                    row[
                        f"{prefix}_name"
                    ] = fold[
                        "split_name"
                    ]
                    row[
                        f"{prefix}_event_count"
                    ] = fold[
                        "event_count"
                    ]
                    row[
                        f"{prefix}_spearman_rho"
                    ] = fold[
                        "spearman_rho"
                    ]
                    row[
                        f"{prefix}_oriented_effect"
                    ] = fold[
                        "oriented_effect"
                    ]

                rows.append(row)

    return rows


def _bootstrap_rows(
    *,
    event_frames: dict[
        int,
        pd.DataFrame,
    ],
    bootstrap_reps: int,
    random_seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for gap_minutes, events in sorted(
        event_frames.items()
    ):
        for target_index, target_name in enumerate(
            (
                PRIMARY_TARGET,
                SECONDARY_TARGET,
            )
        ):
            for feature_index, feature_name in enumerate(
                FEATURE_NAMES
            ):
                seed = (
                    int(random_seed)
                    + int(gap_minutes) * 100_000
                    + target_index * 10_000
                    + feature_index * 1_000
                )

                rng = np.random.default_rng(
                    seed
                )

                direction = (
                    FEATURE_DIRECTIONS[
                        feature_name
                    ]
                )

                observed, _ = (
                    _observed_statistic(
                        events=events,
                        feature_name=(
                            feature_name
                        ),
                        target_name=(
                            target_name
                        ),
                        expected_direction=(
                            direction
                        ),
                    )
                )

                samples = np.asarray(
                    [
                        _bootstrap_statistic(
                            events=events,
                            feature_name=(
                                feature_name
                            ),
                            target_name=(
                                target_name
                            ),
                            expected_direction=(
                                direction
                            ),
                            rng=rng,
                        )
                        for _ in range(
                            bootstrap_reps
                        )
                    ],
                    dtype=float,
                )

                finite = samples[
                    np.isfinite(samples)
                ]

                if finite.size == 0:
                    lower = float("nan")
                    upper = float("nan")
                    median = float("nan")
                    positive_probability = (
                        float("nan")
                    )
                else:
                    lower = float(
                        np.quantile(
                            finite,
                            0.025,
                        )
                    )
                    upper = float(
                        np.quantile(
                            finite,
                            0.975,
                        )
                    )
                    median = float(
                        np.median(finite)
                    )
                    positive_probability = (
                        float(
                            np.mean(
                                finite > 0.0
                            )
                        )
                    )

                rows.append(
                    {
                        "cluster_gap_minutes": (
                            gap_minutes
                        ),
                        "is_primary_gap": (
                            gap_minutes
                            == PRIMARY_CLUSTER_GAP_MINUTES
                        ),
                        "target_name": (
                            target_name
                        ),
                        "is_primary_target": (
                            target_name
                            == PRIMARY_TARGET
                        ),
                        "feature_name": (
                            feature_name
                        ),
                        "observed_fold_balanced_oriented_effect": (
                            observed
                        ),
                        "bootstrap_reps_requested": (
                            int(
                                bootstrap_reps
                            )
                        ),
                        "bootstrap_reps_finite": (
                            int(finite.size)
                        ),
                        "bootstrap_median": (
                            median
                        ),
                        "bootstrap_ci_2_5": (
                            lower
                        ),
                        "bootstrap_ci_97_5": (
                            upper
                        ),
                        "bootstrap_probability_oriented_effect_gt_zero": (
                            positive_probability
                        ),
                    }
                )

    return rows


def _permutation_rows(
    *,
    event_frames: dict[
        int,
        pd.DataFrame,
    ],
    permutation_reps: int,
    random_seed: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for gap_minutes, events in sorted(
        event_frames.items()
    ):
        for target_index, target_name in enumerate(
            (
                PRIMARY_TARGET,
                SECONDARY_TARGET,
            )
        ):
            observed: dict[
                str,
                float,
            ] = {}

            for feature_name in FEATURE_NAMES:
                statistic, _ = (
                    _observed_statistic(
                        events=events,
                        feature_name=(
                            feature_name
                        ),
                        target_name=(
                            target_name
                        ),
                        expected_direction=(
                            FEATURE_DIRECTIONS[
                                feature_name
                            ]
                        ),
                    )
                )
                observed[
                    feature_name
                ] = statistic

            seed = (
                int(random_seed)
                + 9_000_000
                + int(gap_minutes)
                * 100_000
                + target_index
                * 10_000
            )

            rng = np.random.default_rng(
                seed
            )

            exceed_uncorrected = {
                feature: 0
                for feature in FEATURE_NAMES
            }

            exceed_familywise = {
                feature: 0
                for feature in FEATURE_NAMES
            }

            finite_reps = 0

            for _ in range(
                permutation_reps
            ):
                permuted = (
                    _permuted_family_statistics(
                        events=events,
                        target_name=(
                            target_name
                        ),
                        rng=rng,
                    )
                )

                values = np.asarray(
                    [
                        permuted[feature]
                        for feature
                        in FEATURE_NAMES
                    ],
                    dtype=float,
                )

                if not np.all(
                    np.isfinite(values)
                ):
                    continue

                finite_reps += 1

                max_family_stat = float(
                    np.max(values)
                )

                for feature in FEATURE_NAMES:
                    if (
                        permuted[feature]
                        >= observed[feature]
                    ):
                        exceed_uncorrected[
                            feature
                        ] += 1

                    if (
                        max_family_stat
                        >= observed[feature]
                    ):
                        exceed_familywise[
                            feature
                        ] += 1

            for feature in FEATURE_NAMES:
                denominator = (
                    finite_reps + 1
                )

                rows.append(
                    {
                        "cluster_gap_minutes": (
                            gap_minutes
                        ),
                        "is_primary_gap": (
                            gap_minutes
                            == PRIMARY_CLUSTER_GAP_MINUTES
                        ),
                        "target_name": (
                            target_name
                        ),
                        "is_primary_target": (
                            target_name
                            == PRIMARY_TARGET
                        ),
                        "feature_name": (
                            feature
                        ),
                        "observed_fold_balanced_oriented_effect": (
                            observed[
                                feature
                            ]
                        ),
                        "permutation_reps_requested": (
                            int(
                                permutation_reps
                            )
                        ),
                        "permutation_reps_finite": (
                            int(
                                finite_reps
                            )
                        ),
                        "permutation_p_one_sided": (
                            (
                                exceed_uncorrected[
                                    feature
                                ]
                                + 1
                            )
                            / denominator
                        ),
                        "familywise_p_one_sided": (
                            (
                                exceed_familywise[
                                    feature
                                ]
                                + 1
                            )
                            / denominator
                        ),
                        "familywise_scope": (
                            "six_predeclared_features_"
                            "within_gap_and_target"
                        ),
                    }
                )

    return rows


def _sensitivity_rows(
    *,
    observed_rows: Sequence[
        dict[str, Any]
    ],
    bootstrap_rows: Sequence[
        dict[str, Any]
    ],
    permutation_rows: Sequence[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    observed = pd.DataFrame(
        observed_rows
    )
    bootstrap = pd.DataFrame(
        bootstrap_rows
    )
    permutation = pd.DataFrame(
        permutation_rows
    )

    key = [
        "cluster_gap_minutes",
        "target_name",
        "feature_name",
    ]

    merged = (
        observed.merge(
            bootstrap,
            on=key,
            how="inner",
            suffixes=(
                "_observed",
                "_bootstrap",
            ),
        )
        .merge(
            permutation,
            on=key,
            how="inner",
            suffixes=(
                "",
                "_permutation",
            ),
        )
    )

    rows: list[dict[str, Any]] = []

    for feature_name in FEATURE_NAMES:
        for target_name in (
            PRIMARY_TARGET,
            SECONDARY_TARGET,
        ):
            group = merged.loc[
                (
                    merged["feature_name"]
                    == feature_name
                )
                & (
                    merged["target_name"]
                    == target_name
                )
            ].sort_values(
                "cluster_gap_minutes"
            )

            effects = pd.to_numeric(
                group[
                    "fold_balanced_oriented_effect"
                ],
                errors="coerce",
            )

            familywise = pd.to_numeric(
                group[
                    "familywise_p_one_sided"
                ],
                errors="coerce",
            )

            bootstrap_lower = pd.to_numeric(
                group[
                    "bootstrap_ci_2_5"
                ],
                errors="coerce",
            )

            rows.append(
                {
                    "feature_name": (
                        feature_name
                    ),
                    "target_name": (
                        target_name
                    ),
                    "gap_count": int(
                        len(group)
                    ),
                    "all_gap_effects_positive": (
                        bool(
                            (
                                effects > 0.0
                            ).all()
                        )
                    ),
                    "minimum_oriented_effect": (
                        float(
                            effects.min()
                        )
                    ),
                    "maximum_oriented_effect": (
                        float(
                            effects.max()
                        )
                    ),
                    "primary_15m_effect": (
                        float(
                            group.loc[
                                group[
                                    "cluster_gap_minutes"
                                ]
                                == PRIMARY_CLUSTER_GAP_MINUTES,
                                "fold_balanced_oriented_effect",
                            ].iloc[0]
                        )
                    ),
                    "primary_15m_bootstrap_ci_lower": (
                        float(
                            group.loc[
                                group[
                                    "cluster_gap_minutes"
                                ]
                                == PRIMARY_CLUSTER_GAP_MINUTES,
                                "bootstrap_ci_2_5",
                            ].iloc[0]
                        )
                    ),
                    "primary_15m_bootstrap_ci_upper": (
                        float(
                            group.loc[
                                group[
                                    "cluster_gap_minutes"
                                ]
                                == PRIMARY_CLUSTER_GAP_MINUTES,
                                "bootstrap_ci_97_5",
                            ].iloc[0]
                        )
                    ),
                    "primary_15m_familywise_p": (
                        float(
                            group.loc[
                                group[
                                    "cluster_gap_minutes"
                                ]
                                == PRIMARY_CLUSTER_GAP_MINUTES,
                                "familywise_p_one_sided",
                            ].iloc[0]
                        )
                    ),
                    "all_gap_bootstrap_lower_gt_zero": (
                        bool(
                            (
                                bootstrap_lower
                                > 0.0
                            ).all()
                        )
                    ),
                    "all_gap_familywise_p_lt_0_05": (
                        bool(
                            (
                                familywise
                                < 0.05
                            ).all()
                        )
                    ),
                }
            )

    return rows


def build_entry_quality_event_robustness(
    *,
    universe_id: str,
    universe_fingerprint: str,
    eligibility_policy_id: str,
    research_tier: str,
    sources: Sequence[SourcePair],
    bootstrap_reps: int = (
        DEFAULT_BOOTSTRAP_REPS
    ),
    permutation_reps: int = (
        DEFAULT_PERMUTATION_REPS
    ),
    random_seed: int = (
        DEFAULT_RANDOM_SEED
    ),
    write_artifacts: bool = True,
) -> dict[str, Any]:
    if len(sources) < 2:
        raise EntryQualityEventRobustnessError(
            "Event robustness requires "
            "at least two source assets."
        )

    if bootstrap_reps <= 0:
        raise EntryQualityEventRobustnessError(
            "bootstrap_reps must be positive."
        )

    if permutation_reps <= 0:
        raise EntryQualityEventRobustnessError(
            "permutation_reps must be positive."
        )

    loaded_frames: list[
        pd.DataFrame
    ] = []
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
        key=lambda row: str(
            row["asset"]
        )
    )

    combined = pd.concat(
        loaded_frames,
        ignore_index=True,
    )

    if combined.empty:
        raise EntryQualityEventRobustnessError(
            "No combined research rows."
        )

    event_frames = _build_event_frames(
        combined
    )

    observed_rows = _observed_rows(
        event_frames=event_frames
    )

    bootstrap_rows = _bootstrap_rows(
        event_frames=event_frames,
        bootstrap_reps=bootstrap_reps,
        random_seed=random_seed,
    )

    permutation_rows = (
        _permutation_rows(
            event_frames=event_frames,
            permutation_reps=(
                permutation_reps
            ),
            random_seed=random_seed,
        )
    )

    sensitivity_rows = (
        _sensitivity_rows(
            observed_rows=observed_rows,
            bootstrap_rows=(
                bootstrap_rows
            ),
            permutation_rows=(
                permutation_rows
            ),
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
        generator_git_commit = (
            "verification_only"
        )
        verification_only = True

    identity = _identity_payload(
        universe_id=universe_id,
        universe_fingerprint=(
            universe_fingerprint
        ),
        eligibility_policy_id=(
            eligibility_policy_id
        ),
        research_tier=research_tier,
        source_provenance=(
            source_provenance
        ),
        bootstrap_reps=bootstrap_reps,
        permutation_reps=(
            permutation_reps
        ),
        random_seed=random_seed,
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

    manifest = {
        **identity,
        "dataset_id": dataset_id,
        "asset_count": int(
            combined["asset"].nunique()
        ),
        "trade_count": int(
            len(combined)
        ),
        "event_counts_by_gap": {
            str(gap): int(
                len(events)
            )
            for gap, events
            in sorted(
                event_frames.items()
            )
        },
        "analysis_contract": {
            "purpose": (
                "post-selection robustness "
                "assessment of previously "
                "observed entry-quality hypotheses"
            ),
            "confirmatory_test": False,
            "reason_not_confirmatory": (
                "feature family was identified "
                "using the same development data"
            ),
            "feature_selection_applied_in_this_stage": False,
            "feature_promotion_applied_in_this_stage": False,
            "scorer_parameters_modified": False,
            "untouched_holdout_consumed": False,
            "event_is_resampling_unit": True,
            "fold_stratified_resampling": True,
            "fold_balanced_primary_statistic": True,
            "folds_equal_weight": True,
            "primary_target": PRIMARY_TARGET,
            "secondary_target": SECONDARY_TARGET,
            "primary_cluster_gap_minutes": (
                PRIMARY_CLUSTER_GAP_MINUTES
            ),
            "cluster_gap_sensitivity_minutes": (
                list(
                    CLUSTER_GAP_MINUTES
                )
            ),
            "bootstrap_interval": (
                "percentile_95"
            ),
            "permutation_test": (
                "one_sided_expected_direction"
            ),
            "familywise_correction": (
                "max_statistic_across_"
                "six_predeclared_features"
            ),
        },
        "artifacts": {
            "manifest_json": str(
                artifacts.manifest_json
            ),
            "observed_effects_csv": str(
                artifacts.observed_effects_csv
            ),
            "bootstrap_results_csv": str(
                artifacts.bootstrap_results_csv
            ),
            "permutation_results_csv": str(
                artifacts.permutation_results_csv
            ),
            "sensitivity_summary_csv": str(
                artifacts.sensitivity_summary_csv
            ),
        },
    }

    if write_artifacts:
        if artifacts.root.exists():
            raise EntryQualityEventRobustnessError(
                "Artifact already exists: "
                f"{artifacts.root}"
            )

        artifacts.root.mkdir(
            parents=True,
            exist_ok=False,
        )

        pd.DataFrame(
            observed_rows
        ).to_csv(
            artifacts.observed_effects_csv,
            index=False,
        )

        pd.DataFrame(
            bootstrap_rows
        ).to_csv(
            artifacts.bootstrap_results_csv,
            index=False,
        )

        pd.DataFrame(
            permutation_rows
        ).to_csv(
            artifacts.permutation_results_csv,
            index=False,
        )

        pd.DataFrame(
            sensitivity_rows
        ).to_csv(
            artifacts.sensitivity_summary_csv,
            index=False,
        )

        artifacts.manifest_json.write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return manifest
