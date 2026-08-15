from __future__ import annotations

import argparse
import json
from pathlib import Path

from files.research.entry_quality_cross_asset_characterization import (
    SourcePair,
)
from files.research.entry_quality_event_dependence import (
    build_entry_quality_event_dependence,
)


UNIVERSE_ID = "research_universe_coinbase_usd_v1"
UNIVERSE_FINGERPRINT = (
    "f6f75adb7161a9d051a52c18967ffce0d30bcb38c5911cf958d18c2b5ba0454a"
)
ELIGIBILITY_POLICY_ID = "eligibility_policy_v1"
RESEARCH_TIER = "PRIMARY_COMPARABLE"

ELIGIBILITY_REPORT_PATH = Path(
    "/work/data/processed/research/universe_eligibility/"
    "research_universe_coinbase_usd_v1/"
    "eligibility.json"
)


PRIMARY_8_SOURCES = (
    SourcePair(
        asset="BTC",
        feature_dataset_id="entry_quality_dataset_5da3350826403f44",
        outcome_dataset_id="entry_quality_outcomes_609b31a2250bcec8",
    ),
    SourcePair(
        asset="ETH",
        feature_dataset_id="entry_quality_dataset_5533ef3718668ded",
        outcome_dataset_id="entry_quality_outcomes_b48795297d113ac6",
    ),
    SourcePair(
        asset="SOL",
        feature_dataset_id="entry_quality_dataset_0d53be3112be7d07",
        outcome_dataset_id="entry_quality_outcomes_c12591caf9c3109a",
    ),
    SourcePair(
        asset="ADA",
        feature_dataset_id="entry_quality_dataset_0b957d1372764a96",
        outcome_dataset_id="entry_quality_outcomes_2b093eee95a46590",
    ),
    SourcePair(
        asset="XLM",
        feature_dataset_id="entry_quality_dataset_0f1a505768f2351d",
        outcome_dataset_id="entry_quality_outcomes_6f926c0a52603f9d",
    ),
    SourcePair(
        asset="LINK",
        feature_dataset_id="entry_quality_dataset_c40b1edef8fc4ac1",
        outcome_dataset_id="entry_quality_outcomes_e23dc74248b668e6",
    ),
    SourcePair(
        asset="DOGE",
        feature_dataset_id="entry_quality_dataset_8b8618e628d87132",
        outcome_dataset_id="entry_quality_outcomes_8c848dd8ae444370",
    ),
    SourcePair(
        asset="LTC",
        feature_dataset_id="entry_quality_dataset_15f5fa39514a885d",
        outcome_dataset_id="entry_quality_outcomes_08717742e4529408",
    ),
)


def verify_primary_population() -> None:
    if not ELIGIBILITY_REPORT_PATH.exists():
        raise RuntimeError(
            "Authoritative Universe V1 eligibility report is missing: "
            f"{ELIGIBILITY_REPORT_PATH}"
        )

    report = json.loads(
        ELIGIBILITY_REPORT_PATH.read_text(
            encoding="utf-8"
        )
    )

    if report.get("universe_id") != UNIVERSE_ID:
        raise RuntimeError(
            "Eligibility report universe_id mismatch."
        )

    if (
        report.get("universe_fingerprint")
        != UNIVERSE_FINGERPRINT
    ):
        raise RuntimeError(
            "Eligibility report universe fingerprint mismatch."
        )

    policy = report.get("policy")

    if not isinstance(policy, dict):
        raise RuntimeError(
            "Eligibility report policy is missing."
        )

    if (
        policy.get("policy_id")
        != ELIGIBILITY_POLICY_ID
    ):
        raise RuntimeError(
            "Eligibility report policy_id mismatch."
        )

    members = report.get("members")

    if not isinstance(members, list):
        raise RuntimeError(
            "Eligibility report members must be a list."
        )

    eligible_symbols = sorted(
        str(member["symbol"])
        for member in members
        if (
            isinstance(member, dict)
            and member.get("eligibility_tier")
            == RESEARCH_TIER
        )
    )

    source_symbols = sorted(
        f"{source.asset}/USD"
        for source in PRIMARY_8_SOURCES
    )

    if eligible_symbols != source_symbols:
        raise RuntimeError(
            "PRIMARY_COMPARABLE source set does not match "
            "eligibility_policy_v1: "
            f"policy={eligible_symbols} "
            f"sources={source_symbols}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build event-dependence characterization for the "
            "policy-derived Universe V1 PRIMARY_COMPARABLE "
            "entry-quality population."
        )
    )

    parser.add_argument(
        "--verify-only",
        action="store_true",
    )

    args = parser.parse_args()

    verify_primary_population()

    manifest = build_entry_quality_event_dependence(
        universe_id=UNIVERSE_ID,
        universe_fingerprint=UNIVERSE_FINGERPRINT,
        eligibility_policy_id=ELIGIBILITY_POLICY_ID,
        research_tier=RESEARCH_TIER,
        sources=PRIMARY_8_SOURCES,
        write_artifacts=(
            not args.verify_only
        ),
    )

    print(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
