from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from files.research.entry_quality_cross_asset_characterization import (
    FEATURE_NAMES,
    OUTCOME_NOT_REACHED_1R,
    OUTCOME_REACHED_1R,
    SourcePair,
    _binary_effect_row,
    _continuous_effect_row,
    _load_source_pair,
)
from files.research.scorer_campaign_spec import load_runtime_git_identity


EVENT_DEPENDENCE_SCHEMA_VERSION = 1
EVENT_DEPENDENCE_DATASET_TYPE = (
    "entry_quality_event_dependence_v1"
)
EVENT_DEPENDENCE_SPECIFICATION_VERSION = (
    "entry_quality_event_dependence_v1"
)

CLUSTER_GAP_MINUTES = (5, 15, 30)
PRIMARY_CLUSTER_GAP_MINUTES = 15
MIN_CLUSTER_COUNT = 8


class EntryQualityEventDependenceError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class EventDependenceArtifactPaths:
    root: Path
    manifest_json: Path
    cluster_summary_csv: Path
    fold_cluster_summary_csv: Path
    event_membership_csv: Path
    feature_event_level_effects_csv: Path


def _research_dir() -> Path:
    return Path(
        "data/processed/research/entry_quality"
    )


def _artifact_paths(
    *,
    dataset_id: str,
) -> EventDependenceArtifactPaths:
    root = _research_dir() / dataset_id

    return EventDependenceArtifactPaths(
        root=root,
        manifest_json=root / "manifest.json",
        cluster_summary_csv=(
            root / "cluster_summary.csv"
        ),
        fold_cluster_summary_csv=(
            root / "fold_cluster_summary.csv"
        ),
        event_membership_csv=(
            root / "event_membership.csv"
        ),
        feature_event_level_effects_csv=(
            root
            / "feature_event_level_effects.csv"
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
    generator_git_commit: str,
    verification_only: bool,
) -> dict[str, Any]:
    return {
        "dataset_schema_version": (
            EVENT_DEPENDENCE_SCHEMA_VERSION
        ),
        "dataset_type": (
            EVENT_DEPENDENCE_DATASET_TYPE
        ),
        "event_dependence_specification_version": (
            EVENT_DEPENDENCE_SPECIFICATION_VERSION
        ),
        "universe_id": universe_id,
        "universe_fingerprint": (
            universe_fingerprint
        ),
        "eligibility_policy_id": (
            eligibility_policy_id
        ),
        "research_tier": research_tier,
        "cluster_gap_minutes": list(
            CLUSTER_GAP_MINUTES
        ),
        "primary_cluster_gap_minutes": (
            PRIMARY_CLUSTER_GAP_MINUTES
        ),
        "source_provenance": list(
            source_provenance
        ),
        "generator_git_commit": (
            generator_git_commit
        ),
        "verification_only": (
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
        "entry_quality_event_dependence_"
        f"{digest}"
    )


def _assign_event_clusters(
    frame: pd.DataFrame,
    *,
    gap_minutes: int,
) -> pd.DataFrame:
    if gap_minutes <= 0:
        raise EntryQualityEventDependenceError(
            "gap_minutes must be positive."
        )

    gap_ms = int(
        gap_minutes * 60 * 1000
    )

    result_frames: list[pd.DataFrame] = []

    # Never join observations across validation
    # folds. Each fold remains an independent
    # research period.
    for split_name, fold in frame.groupby(
        "split_name",
        sort=True,
    ):
        ordered = fold.sort_values(
            [
                "entry_ts_ms",
                "asset",
                "signal_ts_ms",
            ],
            kind="mergesort",
        ).reset_index(drop=True)

        cluster_numbers: list[int] = []
        cluster_number = 0
        prior_ts: int | None = None

        for ts in ordered[
            "entry_ts_ms"
        ].astype("int64"):
            current_ts = int(ts)

            if (
                prior_ts is None
                or current_ts - prior_ts
                > gap_ms
            ):
                cluster_number += 1

            cluster_numbers.append(
                cluster_number
            )
            prior_ts = current_ts

        ordered["cluster_gap_minutes"] = (
            gap_minutes
        )
        ordered["cluster_number"] = (
            cluster_numbers
        )
        ordered["event_cluster_id"] = [
            (
                f"{split_name}"
                f"__g{gap_minutes}"
                f"__c{number:06d}"
            )
            for number in cluster_numbers
        ]

        result_frames.append(ordered)

    if not result_frames:
        raise EntryQualityEventDependenceError(
            "No rows available for clustering."
        )

    return pd.concat(
        result_frames,
        ignore_index=True,
    )


def _cluster_summary_rows(
    clustered: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    grouped = clustered.groupby(
        [
            "cluster_gap_minutes",
            "split_name",
            "event_cluster_id",
        ],
        sort=True,
    )

    for (
        gap_minutes,
        split_name,
        cluster_id,
    ), group in grouped:
        start_ts = int(
            group["entry_ts_ms"].min()
        )
        end_ts = int(
            group["entry_ts_ms"].max()
        )
        assets = sorted(
            group["asset"]
            .astype(str)
            .unique()
            .tolist()
        )

        rows.append(
            {
                "cluster_gap_minutes": int(
                    gap_minutes
                ),
                "split_name": str(
                    split_name
                ),
                "event_cluster_id": str(
                    cluster_id
                ),
                "entry_count": int(
                    len(group)
                ),
                "asset_count": int(
                    len(assets)
                ),
                "assets": ",".join(assets),
                "cluster_start_ts_ms": (
                    start_ts
                ),
                "cluster_end_ts_ms": end_ts,
                "cluster_span_minutes": (
                    (end_ts - start_ts)
                    / 60_000.0
                ),
                "multi_asset": bool(
                    len(assets) > 1
                ),
            }
        )

    return rows


def _fold_cluster_summary_rows(
    cluster_summary: pd.DataFrame,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    grouped = cluster_summary.groupby(
        [
            "cluster_gap_minutes",
            "split_name",
        ],
        sort=True,
    )

    for (
        gap_minutes,
        split_name,
    ), group in grouped:
        multi = group["multi_asset"].astype(
            bool
        )

        rows.append(
            {
                "cluster_gap_minutes": int(
                    gap_minutes
                ),
                "split_name": str(
                    split_name
                ),
                "cluster_count": int(
                    len(group)
                ),
                "multi_asset_cluster_count": (
                    int(multi.sum())
                ),
                "singleton_asset_cluster_count": (
                    int((~multi).sum())
                ),
                "mean_entries_per_cluster": (
                    float(
                        group[
                            "entry_count"
                        ].mean()
                    )
                ),
                "median_entries_per_cluster": (
                    float(
                        group[
                            "entry_count"
                        ].median()
                    )
                ),
                "mean_assets_per_cluster": (
                    float(
                        group[
                            "asset_count"
                        ].mean()
                    )
                ),
                "maximum_assets_per_cluster": (
                    int(
                        group[
                            "asset_count"
                        ].max()
                    )
                ),
                "mean_cluster_span_minutes": (
                    float(
                        group[
                            "cluster_span_minutes"
                        ].mean()
                    )
                ),
                "maximum_cluster_span_minutes": (
                    float(
                        group[
                            "cluster_span_minutes"
                        ].max()
                    )
                ),
            }
        )

    return rows


def _cluster_balanced_frame(
    clustered: pd.DataFrame,
) -> pd.DataFrame:
    # Each event receives total weight 1.0,
    # regardless of the number of asset entries
    # occurring inside that event.
    counts = (
        clustered.groupby(
            "event_cluster_id"
        )["event_cluster_id"]
        .transform("size")
        .astype(float)
    )

    result = clustered.copy()
    result["cluster_weight"] = (
        1.0 / counts
    )

    return result


def _weighted_rank_expansion(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    # A deterministic representation for
    # event-level descriptive effects:
    # collapse each event to one observation
    # using equal-weight means for numeric
    # features/continuous outcome and majority
    # rates for binary outcomes.
    rows: list[dict[str, Any]] = []

    for (
        split_name,
        cluster_id,
    ), group in frame.groupby(
        [
            "split_name",
            "event_cluster_id",
        ],
        sort=True,
    ):
        row: dict[str, Any] = {
            "split_name": str(split_name),
            "event_cluster_id": str(
                cluster_id
            ),
            "entry_count": int(len(group)),
            "asset_count": int(
                group["asset"].nunique()
            ),
        }

        for feature in FEATURE_NAMES:
            values = pd.to_numeric(
                group[feature],
                errors="coerce",
            )
            row[feature] = (
                float(values.mean())
                if values.notna().any()
                else float("nan")
            )

        canonical = group[
            "outcome_group"
        ].isin(
            (
                OUTCOME_REACHED_1R,
                OUTCOME_NOT_REACHED_1R,
            )
        )

        if canonical.any():
            row[
                "canonical_positive_rate"
            ] = float(
                (
                    group.loc[
                        canonical,
                        "outcome_group",
                    ]
                    == OUTCOME_REACHED_1R
                ).mean()
            )
        else:
            row[
                "canonical_positive_rate"
            ] = float("nan")

        barrier = group[
            "first_barrier_outcome"
        ].isin(
            (
                "target_first",
                "stop_first",
            )
        )

        if barrier.any():
            row[
                "barrier_target_rate"
            ] = float(
                (
                    group.loc[
                        barrier,
                        "first_barrier_outcome",
                    ]
                    == "target_first"
                ).mean()
            )
        else:
            row[
                "barrier_target_rate"
            ] = float("nan")

        mfe = pd.to_numeric(
            group.loc[
                group["horizon_available"],
                "mfe_24b_r",
            ],
            errors="coerce",
        ).dropna()

        row["mean_mfe_24b_r"] = (
            float(mfe.mean())
            if not mfe.empty
            else float("nan")
        )

        rows.append(row)

    return pd.DataFrame(rows)


def _cluster_effect_rows(
    cluster_frame: pd.DataFrame,
    *,
    gap_minutes: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for feature in FEATURE_NAMES:
        canonical = _continuous_effect_row(
            feature_name=feature,
            values=cluster_frame[feature],
            target=cluster_frame[
                "canonical_positive_rate"
            ],
        )
        canonical[
            "analysis_target"
        ] = "cluster_canonical_positive_rate"

        barrier = _continuous_effect_row(
            feature_name=feature,
            values=cluster_frame[feature],
            target=cluster_frame[
                "barrier_target_rate"
            ],
        )
        barrier[
            "analysis_target"
        ] = "cluster_barrier_target_rate"

        mfe = _continuous_effect_row(
            feature_name=feature,
            values=cluster_frame[feature],
            target=cluster_frame[
                "mean_mfe_24b_r"
            ],
        )
        mfe[
            "analysis_target"
        ] = "cluster_mean_mfe_24b_r"

        for row in (
            canonical,
            barrier,
            mfe,
        ):
            row[
                "cluster_gap_minutes"
            ] = int(gap_minutes)
            row[
                "cluster_count"
            ] = int(len(cluster_frame))
            rows.append(row)

    return rows


def build_entry_quality_event_dependence(
    *,
    universe_id: str,
    universe_fingerprint: str,
    eligibility_policy_id: str,
    research_tier: str,
    sources: Sequence[SourcePair],
    write_artifacts: bool = True,
) -> dict[str, Any]:
    if len(sources) < 2:
        raise EntryQualityEventDependenceError(
            "Event-dependence analysis requires "
            "at least two source assets."
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
        raise EntryQualityEventDependenceError(
            "No combined research rows."
        )

    all_memberships: list[pd.DataFrame] = []
    all_cluster_rows: list[
        dict[str, Any]
    ] = []
    all_effect_rows: list[
        dict[str, Any]
    ] = []

    for gap_minutes in CLUSTER_GAP_MINUTES:
        clustered = _assign_event_clusters(
            combined,
            gap_minutes=gap_minutes,
        )

        all_memberships.append(
            clustered[
                [
                    "asset",
                    "split_name",
                    "signal_ts_ms",
                    "entry_ts_ms",
                    "cluster_gap_minutes",
                    "event_cluster_id",
                ]
            ].copy()
        )

        cluster_rows = _cluster_summary_rows(
            clustered
        )
        all_cluster_rows.extend(
            cluster_rows
        )

        cluster_frame = (
            _weighted_rank_expansion(
                _cluster_balanced_frame(
                    clustered
                )
            )
        )

        all_effect_rows.extend(
            _cluster_effect_rows(
                cluster_frame,
                gap_minutes=gap_minutes,
            )
        )

    membership_df = pd.concat(
        all_memberships,
        ignore_index=True,
    )

    cluster_summary_df = pd.DataFrame(
        all_cluster_rows
    )

    fold_cluster_summary_rows = (
        _fold_cluster_summary_rows(
            cluster_summary_df
        )
    )

    feature_effects_df = pd.DataFrame(
        all_effect_rows
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
        generator_git_commit=(
            generator_git_commit
        ),
        verification_only=(
            verification_only
        ),
    )

    dataset_id = _dataset_id_for_payload(
        identity
    )
    artifacts = _artifact_paths(
        dataset_id=dataset_id
    )

    primary = cluster_summary_df.loc[
        cluster_summary_df[
            "cluster_gap_minutes"
        ]
        == PRIMARY_CLUSTER_GAP_MINUTES
    ]

    manifest = {
        **identity,
        "dataset_id": dataset_id,
        "asset_count": int(
            combined["asset"].nunique()
        ),
        "trade_count": int(len(combined)),
        "primary_cluster_count": int(
            len(primary)
        ),
        "primary_multi_asset_cluster_count": (
            int(
                primary[
                    "multi_asset"
                ].astype(bool).sum()
            )
        ),
        "analysis_contract": {
            "purpose": (
                "descriptive event-dependence "
                "characterization"
            ),
            "feature_selection_applied": False,
            "feature_promotion_applied": False,
            "scorer_parameters_modified": False,
            "fold_boundaries_preserved": True,
            "cluster_assignment_uses_entry_ts_ms": True,
            "cluster_rule": (
                "new cluster when adjacent entry "
                "timestamp gap exceeds configured "
                "gap; chaining is explicit and "
                "cluster span is reported"
            ),
            "cluster_sensitivity_minutes": list(
                CLUSTER_GAP_MINUTES
            ),
            "primary_cluster_gap_minutes": (
                PRIMARY_CLUSTER_GAP_MINUTES
            ),
            "event_level_effects_are_descriptive": True,
            "cluster_bootstrap_applied": False,
            "cluster_aware_permutation_applied": False,
        },
        "artifacts": {
            "manifest_json": str(
                artifacts.manifest_json
            ),
            "cluster_summary_csv": str(
                artifacts.cluster_summary_csv
            ),
            "fold_cluster_summary_csv": str(
                artifacts.fold_cluster_summary_csv
            ),
            "event_membership_csv": str(
                artifacts.event_membership_csv
            ),
            "feature_event_level_effects_csv": str(
                artifacts.feature_event_level_effects_csv
            ),
        },
    }

    if write_artifacts:
        if artifacts.root.exists():
            raise EntryQualityEventDependenceError(
                f"Artifact already exists: "
                f"{artifacts.root}"
            )

        artifacts.root.mkdir(
            parents=True,
            exist_ok=False,
        )

        membership_df.to_csv(
            artifacts.event_membership_csv,
            index=False,
        )
        cluster_summary_df.to_csv(
            artifacts.cluster_summary_csv,
            index=False,
        )
        pd.DataFrame(
            fold_cluster_summary_rows
        ).to_csv(
            artifacts.fold_cluster_summary_csv,
            index=False,
        )
        feature_effects_df.to_csv(
            artifacts.feature_event_level_effects_csv,
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
