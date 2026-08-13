from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from files.research.historical_dataset import (
    HistoricalDatasetContractError,
    load_and_resolve_historical_research_source,
)
from files.research.scorer_walk_forward import (
    resolve_walk_forward_splits_for_source,
)


DEFAULT_CONTRACT_PATH = Path(
    "files/research/contracts/"
    "coinbase_usd_research_universe_v1.json"
)

DEFAULT_OUTPUT_ROOT = Path(
    "/work/data/processed/research/universe_eligibility/"
    "research_universe_coinbase_usd_v1"
)

POLICY_ID = "eligibility_policy_v1"
MIN_BARS = 200

PRIMARY_MIN_STORED_COVERAGE = 0.95
PRIMARY_MIN_STRUCTURAL_COVERAGE = 0.90

SECONDARY_MIN_STORED_COVERAGE = 0.80
SECONDARY_MIN_STRUCTURAL_COVERAGE = 0.60


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Derive research eligibility metrics from the frozen "
            "Coinbase USD Research Universe V1 contract."
        )
    )

    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT_PATH,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )

    parser.add_argument(
        "--write",
        action="store_true",
    )

    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def theoretical_window_bars(
    *,
    start_ts_ms: int,
    end_ts_ms_exclusive: int,
    step_ms: int,
) -> int:
    duration = end_ts_ms_exclusive - start_ts_ms

    if duration <= 0:
        raise RuntimeError(
            "Eligibility window has non-positive duration."
        )

    if duration % step_ms != 0:
        raise RuntimeError(
            "Eligibility window is not aligned to timeframe."
        )

    return int(duration // step_ms)


def coverage_ratio(
    numerator: int,
    denominator: int,
) -> float:
    if denominator <= 0:
        raise RuntimeError(
            "Coverage denominator must be positive."
        )

    return float(numerator / denominator)


def eligibility_tier(
    *,
    minimum_stored_coverage: float,
    minimum_structural_coverage: float,
) -> str:
    if (
        minimum_stored_coverage
        >= PRIMARY_MIN_STORED_COVERAGE
        and minimum_structural_coverage
        >= PRIMARY_MIN_STRUCTURAL_COVERAGE
    ):
        return "PRIMARY_COMPARABLE"

    if (
        minimum_stored_coverage
        >= SECONDARY_MIN_STORED_COVERAGE
        and minimum_structural_coverage
        >= SECONDARY_MIN_STRUCTURAL_COVERAGE
    ):
        return "SECONDARY_USABLE"

    return "INSUFFICIENT_COMPARABILITY"


def resolve_member(
    member: dict[str, Any],
) -> dict[str, Any]:
    manifest_path = Path(member["manifest_path"])

    if not manifest_path.exists():
        raise RuntimeError(
            f"{member['symbol']}: manifest missing: "
            f"{manifest_path}"
        )

    actual_manifest_sha256 = sha256_file(
        manifest_path
    )

    expected_manifest_sha256 = member[
        "manifest_file_sha256"
    ]

    if actual_manifest_sha256 != expected_manifest_sha256:
        raise RuntimeError(
            f"{member['symbol']}: frozen manifest SHA mismatch"
        )

    source = (
        load_and_resolve_historical_research_source(
            data_tag=member["data_tag"],
            expected_symbol=member["symbol"],
            expected_timeframe=member["timeframe"],
            manifest_path=manifest_path,
        )
    )

    try:
        resolved_splits = (
            resolve_walk_forward_splits_for_source(
                source=source,
                min_bars=MIN_BARS,
            )
        )
    except HistoricalDatasetContractError as exc:
        return {
            "symbol": member["symbol"],
            "data_tag": member["data_tag"],
            "manifest_path": str(manifest_path),
            "manifest_file_sha256": (
                actual_manifest_sha256
            ),
            "historical_manifest_fingerprint": (
                source.manifest_fingerprint
            ),
            "stored_bar_count_full_manifest": (
                member["stored_bar_count"]
            ),
            "missing_bar_count_full_manifest": (
                member["missing_bar_count"]
            ),
            "gap_count_full_manifest": (
                member["gap_count"]
            ),
            "minimum_stored_coverage": None,
            "average_stored_coverage": None,
            "minimum_structural_coverage": None,
            "average_structural_coverage": None,
            "maximum_physical_segments_in_window": None,
            "maximum_gaps_crossed_in_window": None,
            "eligibility_tier": (
                "WINDOW_BOUNDARY_INCOMPATIBLE"
            ),
            "eligibility_reason": str(exc),
            "windows": [],
        }

    windows: list[dict[str, Any]] = []

    for split in resolved_splits:
        for role, window in (
            ("train", split.train),
            ("validation", split.validation),
        ):
            theoretical = theoretical_window_bars(
                start_ts_ms=window.start_ts_ms,
                end_ts_ms_exclusive=(
                    window.end_ts_ms_exclusive
                ),
                step_ms=source.timeframe_step_ms,
            )

            stored_coverage = coverage_ratio(
                window.stored_bars_in_requested_window,
                theoretical,
            )

            structural_coverage = coverage_ratio(
                window.structurally_eligible_bar_count,
                theoretical,
            )

            windows.append(
                {
                    "split": split.name,
                    "role": role,
                    "start": window.start,
                    "end_exclusive": (
                        window.end_exclusive
                    ),
                    "theoretical_bar_count": theoretical,
                    "stored_bar_count": (
                        window.stored_bars_in_requested_window
                    ),
                    "stored_coverage": stored_coverage,
                    "structurally_eligible_bar_count": (
                        window.structurally_eligible_bar_count
                    ),
                    "structural_coverage": (
                        structural_coverage
                    ),
                    "replay_bars_including_warmup": (
                        window.replay_bars_including_warmup
                    ),
                    "warmup_bars_total": (
                        window.warmup_bars_total
                    ),
                    "physical_segment_count": (
                        window.physical_segment_count
                    ),
                    "gap_count_crossed": (
                        window.gap_count_crossed
                    ),
                }
            )

    minimum_stored = min(
        window["stored_coverage"]
        for window in windows
    )

    minimum_structural = min(
        window["structural_coverage"]
        for window in windows
    )

    average_stored = sum(
        window["stored_coverage"]
        for window in windows
    ) / len(windows)

    average_structural = sum(
        window["structural_coverage"]
        for window in windows
    ) / len(windows)

    maximum_segments = max(
        window["physical_segment_count"]
        for window in windows
    )

    maximum_gaps_crossed = max(
        window["gap_count_crossed"]
        for window in windows
    )

    tier = eligibility_tier(
        minimum_stored_coverage=minimum_stored,
        minimum_structural_coverage=minimum_structural,
    )

    return {
        "symbol": member["symbol"],
        "data_tag": member["data_tag"],
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": (
            actual_manifest_sha256
        ),
        "historical_manifest_fingerprint": (
            source.manifest_fingerprint
        ),
        "stored_bar_count_full_manifest": (
            member["stored_bar_count"]
        ),
        "missing_bar_count_full_manifest": (
            member["missing_bar_count"]
        ),
        "gap_count_full_manifest": (
            member["gap_count"]
        ),
        "minimum_stored_coverage": minimum_stored,
        "average_stored_coverage": average_stored,
        "minimum_structural_coverage": (
            minimum_structural
        ),
        "average_structural_coverage": (
            average_structural
        ),
        "maximum_physical_segments_in_window": (
            maximum_segments
        ),
        "maximum_gaps_crossed_in_window": (
            maximum_gaps_crossed
        ),
        "eligibility_tier": tier,
        "eligibility_reason": "",
        "windows": windows,
    }


def csv_row(
    member: dict[str, Any],
) -> dict[str, Any]:
    return {
        "symbol": member["symbol"],
        "eligibility_tier": (
            member["eligibility_tier"]
        ),
        "minimum_stored_coverage": (
            member["minimum_stored_coverage"]
        ),
        "minimum_structural_coverage": (
            member["minimum_structural_coverage"]
        ),
        "average_stored_coverage": (
            member["average_stored_coverage"]
        ),
        "average_structural_coverage": (
            member["average_structural_coverage"]
        ),
        "maximum_physical_segments_in_window": (
            member[
                "maximum_physical_segments_in_window"
            ]
        ),
        "maximum_gaps_crossed_in_window": (
            member["maximum_gaps_crossed_in_window"]
        ),
        "stored_bar_count_full_manifest": (
            member["stored_bar_count_full_manifest"]
        ),
        "missing_bar_count_full_manifest": (
            member["missing_bar_count_full_manifest"]
        ),
        "gap_count_full_manifest": (
            member["gap_count_full_manifest"]
        ),
        "historical_manifest_fingerprint": (
            member["historical_manifest_fingerprint"]
        ),
        "eligibility_reason": (
            member["eligibility_reason"]
        ),
    }


def main() -> None:
    args = build_parser().parse_args()

    contract_path = args.contract
    output_root = args.output_root

    contract = json.loads(
        contract_path.read_text(encoding="utf-8")
    )

    if contract.get("status") != "frozen":
        raise RuntimeError(
            "Universe contract must be frozen."
        )

    if (
        contract.get("universe_id")
        != "research_universe_coinbase_usd_v1"
    ):
        raise RuntimeError(
            "Unexpected universe contract."
        )

    if int(contract.get("member_count", 0)) != 29:
        raise RuntimeError(
            "Universe V1 must contain exactly 29 members."
        )

    members = [
        resolve_member(member)
        for member in contract["members"]
    ]

    tier_counts = Counter(
        member["eligibility_tier"]
        for member in members
    )

    report = {
        "schema_version": 1,
        "report_type": (
            "research_universe_eligibility"
        ),
        "generated_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "universe_id": contract["universe_id"],
        "universe_fingerprint": (
            contract["universe_fingerprint"]
        ),
        "policy": {
            "policy_id": POLICY_ID,
            "min_bars": MIN_BARS,
            "primary_min_stored_coverage": (
                PRIMARY_MIN_STORED_COVERAGE
            ),
            "primary_min_structural_coverage": (
                PRIMARY_MIN_STRUCTURAL_COVERAGE
            ),
            "secondary_min_stored_coverage": (
                SECONDARY_MIN_STORED_COVERAGE
            ),
            "secondary_min_structural_coverage": (
                SECONDARY_MIN_STRUCTURAL_COVERAGE
            ),
            "classification_basis": (
                "minimum coverage across every frozen "
                "train/validation window"
            ),
        },
        "member_count": len(members),
        "tier_counts": dict(
            sorted(tier_counts.items())
        ),
        "members": members,
    }

    print(
        "universe_fingerprint =",
        report["universe_fingerprint"],
    )
    print("policy_id =", POLICY_ID)
    print("member_count =", len(members))
    print()

    for tier in (
        "PRIMARY_COMPARABLE",
        "SECONDARY_USABLE",
        "INSUFFICIENT_COMPARABILITY",
        "WINDOW_BOUNDARY_INCOMPATIBLE",
    ):
        print(
            f"{tier} =",
            tier_counts.get(tier, 0),
        )

    print()
    print(
        "SYMBOL       TIER                       "
        "MIN_STORED  MIN_STRUCT  MAX_SEGMENTS"
    )

    for member in members:
        minimum_stored = member[
            "minimum_stored_coverage"
        ]
        minimum_structural = member[
            "minimum_structural_coverage"
        ]
        maximum_segments = member[
            "maximum_physical_segments_in_window"
        ]

        stored_text = (
            f"{minimum_stored:.4f}"
            if minimum_stored is not None
            else "-"
        )

        structural_text = (
            f"{minimum_structural:.4f}"
            if minimum_structural is not None
            else "-"
        )

        segments_text = (
            str(maximum_segments)
            if maximum_segments is not None
            else "-"
        )

        print(
            f"{member['symbol']:<12} "
            f"{member['eligibility_tier']:<30} "
            f"{stored_text:>10} "
            f"{structural_text:>11} "
            f"{segments_text:>12}"
        )

        if member["eligibility_reason"]:
            print(
                "             reason="
                f"{member['eligibility_reason']}"
            )

    if not args.write:
        return

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = output_root / "eligibility.json"
    csv_path = output_root / "eligibility.csv"

    json_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    rows = [
        csv_row(member)
        for member in members
    ]

    fieldnames = list(rows[0])

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    print()
    print("json_path =", json_path)
    print("csv_path =", csv_path)


if __name__ == "__main__":
    main()
