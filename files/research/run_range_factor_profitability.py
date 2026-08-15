from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
from typing import Any, Callable

from files.config import load_trading_config
from files.research.run_multi_asset_baseline import (
    EXPECTED_UNIVERSE_FINGERPRINT,
    EXPECTED_UNIVERSE_ID,
    PRIMARY_SYMBOLS,
    RESEARCH_ORDER_NOTIONAL_USD,
    campaign_summary,
    frozen_baseline_trial,
    load_universe_contract,
    resolve_primary_members,
)
from files.research.scorer_campaign_builder import (
    InitializedScorerCampaign,
    build_default_campaign_specification,
    initialize_scorer_campaign_with_trials,
)
from files.research.scorer_campaign_runner import (
    run_scorer_campaign,
)
from files.research.scorer_campaign_spec import (
    load_runtime_git_identity,
)


FEATURE_NAME = "current_range_vs_prior_10_mean"

EXPERIMENT_ID = "range_factor_profitability_v1"


@dataclass(frozen=True)
class RangePolicy:
    policy_id: str
    description: str
    minimum_ratio: float | None


POLICIES: tuple[RangePolicy, ...] = (
    RangePolicy(
        policy_id="range_v1_baseline",
        description="Frozen baseline scorer; no range-factor gate.",
        minimum_ratio=None,
    ),
    RangePolicy(
        policy_id="range_v1_ge_0_75",
        description=(
            "Weak range preference: require current candle range "
            "to be at least 0.75x the prior 10-bar mean range."
        ),
        minimum_ratio=0.75,
    ),
    RangePolicy(
        policy_id="range_v1_ge_1_00",
        description=(
            "Moderate range preference: require current candle range "
            "to be at least the prior 10-bar mean range."
        ),
        minimum_ratio=1.00,
    ),
    RangePolicy(
        policy_id="range_v1_ge_1_25",
        description=(
            "Strong range preference: require current candle range "
            "to be at least 1.25x the prior 10-bar mean range."
        ),
        minimum_ratio=1.25,
    ),
    RangePolicy(
        policy_id="range_v1_ge_1_50",
        description=(
            "Hard range gate: require current candle range "
            "to be at least 1.50x the prior 10-bar mean range."
        ),
        minimum_ratio=1.50,
    ),
)


class RangeFactorProfitabilityError(RuntimeError):
    """Raised when the range-factor experiment contract is violated."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the predeclared range-expansion "
            "profitability experiment across the Coinbase USD "
            "Universe V1 PRIMARY_COMPARABLE core."
        )
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Resolve and verify campaigns without running backtests.",
    )

    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop after the first isolated campaign failure.",
    )

    parser.add_argument(
        "--policy",
        action="append",
        choices=tuple(
            policy.policy_id
            for policy in POLICIES
        ),
        help=(
            "Run only the selected policy. May be supplied more than "
            "once. Default: all predeclared policies."
        ),
    )

    parser.add_argument(
        "--symbol",
        action="append",
        choices=PRIMARY_SYMBOLS,
        help=(
            "Run only the selected PRIMARY symbol. May be supplied "
            "more than once. Default: all eight PRIMARY symbols."
        ),
    )

    return parser


def selected_policies(
    requested: list[str] | None,
) -> tuple[RangePolicy, ...]:
    if not requested:
        return POLICIES

    requested_set = set(requested)

    selected = tuple(
        policy
        for policy in POLICIES
        if policy.policy_id in requested_set
    )

    if len(selected) != len(requested_set):
        raise RangeFactorProfitabilityError(
            "Unable to resolve requested range policies."
        )

    return selected


def selected_symbols(
    requested: list[str] | None,
) -> tuple[str, ...]:
    if not requested:
        return PRIMARY_SYMBOLS

    requested_set = set(requested)

    selected = tuple(
        symbol
        for symbol in PRIMARY_SYMBOLS
        if symbol in requested_set
    )

    if len(selected) != len(requested_set):
        raise RangeFactorProfitabilityError(
            "Unable to resolve requested PRIMARY symbols."
        )

    return selected


def build_entry_gate(
    policy: RangePolicy,
) -> Callable[[object], tuple[bool, str]] | None:
    threshold = policy.minimum_ratio

    if threshold is None:
        return None

    threshold = float(threshold)

    def gate(features: object) -> tuple[bool, str]:
        try:
            latest = features.iloc[-1]
        except Exception as exc:
            raise RangeFactorProfitabilityError(
                "Research entry gate expected a pandas feature frame."
            ) from exc

        if FEATURE_NAME not in latest.index:
            raise RangeFactorProfitabilityError(
                f"Research feature missing: {FEATURE_NAME}"
            )

        try:
            value = float(latest[FEATURE_NAME])
        except Exception as exc:
            raise RangeFactorProfitabilityError(
                f"Research feature is not numeric: {FEATURE_NAME}"
            ) from exc

        if not math.isfinite(value):
            raise RangeFactorProfitabilityError(
                f"Research feature is non-finite: "
                f"{FEATURE_NAME}={value!r}"
            )

        if value >= threshold:
            return (
                True,
                (
                    f"{policy.policy_id}: "
                    f"{FEATURE_NAME}={value:.12g} "
                    f">={threshold:.12g}"
                ),
            )

        return (
            False,
            (
                f"{policy.policy_id}: "
                f"{FEATURE_NAME}={value:.12g} "
                f"<{threshold:.12g}"
            ),
        )

    return gate


def initialize_campaigns(
    *,
    policies: tuple[RangePolicy, ...],
    symbols: tuple[str, ...],
) -> tuple[
    tuple[
        RangePolicy,
        InitializedScorerCampaign,
        Any,
    ],
    ...,
]:
    universe = load_universe_contract()
    members = resolve_primary_members(universe)

    members_by_symbol = {
        str(member["symbol"]): member
        for member in members
    }

    baseline_trial = frozen_baseline_trial()
    trading_config = load_trading_config()
    git_identity = load_runtime_git_identity()

    campaigns: list[
        tuple[
            RangePolicy,
            InitializedScorerCampaign,
            Any,
        ]
    ] = []

    for policy in policies:
        for symbol in symbols:
            member = members_by_symbol.get(symbol)

            if member is None:
                raise RangeFactorProfitabilityError(
                    f"PRIMARY member missing: {symbol}"
                )

            data_tag = str(member["data_tag"])
            timeframe = str(member["timeframe"])

            member_config = replace(
                trading_config,
                symbol=symbol,
                data_tag=data_tag,
                timeframe=timeframe,
            )

            specification = (
                build_default_campaign_specification(
                    trading_config=member_config,
                    trial_count=1,
                    research_order_notional_usd=(
                        RESEARCH_ORDER_NOTIONAL_USD
                    ),
                    research_entry_policy_id=(
                        policy.policy_id
                    ),
                )
            )

            campaign = (
                initialize_scorer_campaign_with_trials(
                    trading_config=member_config,
                    git_identity=git_identity,
                    specification=specification,
                    trials=(baseline_trial,),
                    write_artifacts=True,
                )
            )

            if campaign.source.symbol != symbol:
                raise RangeFactorProfitabilityError(
                    f"Resolved symbol mismatch: {symbol}"
                )

            if campaign.source.data_tag != data_tag:
                raise RangeFactorProfitabilityError(
                    f"Resolved data_tag mismatch: {symbol}"
                )

            if campaign.source.timeframe != timeframe:
                raise RangeFactorProfitabilityError(
                    f"Resolved timeframe mismatch: {symbol}"
                )

            expected_manifest = str(
                member["manifest_path"]
            )

            if (
                str(campaign.source.manifest_path)
                != expected_manifest
            ):
                raise RangeFactorProfitabilityError(
                    f"Manifest mismatch: {symbol}"
                )

            if (
                campaign.specification
                .research_entry_policy_id
                != policy.policy_id
            ):
                raise RangeFactorProfitabilityError(
                    "Research policy identity was not "
                    "preserved in campaign specification."
                )

            campaigns.append(
                (
                    policy,
                    campaign,
                    member_config,
                )
            )

    expected_count = len(policies) * len(symbols)

    if len(campaigns) != expected_count:
        raise RangeFactorProfitabilityError(
            "Range-factor campaign count mismatch: "
            f"expected={expected_count} "
            f"actual={len(campaigns)}"
        )

    campaign_ids = [
        campaign.campaign_id
        for _, campaign, _ in campaigns
    ]

    if len(campaign_ids) != len(set(campaign_ids)):
        raise RangeFactorProfitabilityError(
            "Range-factor campaign IDs are not unique."
        )

    return tuple(campaigns)


def policy_payload(
    policy: RangePolicy,
) -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "description": policy.description,
        "feature": FEATURE_NAME,
        "minimum_ratio": policy.minimum_ratio,
    }


def main() -> None:
    args = build_parser().parse_args()

    policies = selected_policies(args.policy)
    symbols = selected_symbols(args.symbol)

    campaigns = initialize_campaigns(
        policies=policies,
        symbols=symbols,
    )

    output: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_role": (
            "development_profitability_intervention"
        ),
        "holdout_2025_plus_consumed": False,
        "universe_id": EXPECTED_UNIVERSE_ID,
        "universe_fingerprint": (
            EXPECTED_UNIVERSE_FINGERPRINT
        ),
        "population": "PRIMARY_COMPARABLE",
        "symbols": list(symbols),
        "research_order_notional_usd": (
            RESEARCH_ORDER_NOTIONAL_USD
        ),
        "baseline_scorer": (
            "frozen_multi_asset_baseline_v1"
        ),
        "feature_definition": {
            "name": FEATURE_NAME,
            "numerator": "current_bar_high_minus_low",
            "denominator": (
                "mean_high_minus_low_of_prior_10_bars"
            ),
            "current_bar_excluded_from_denominator": True,
            "physical_segment_scoped": True,
        },
        "policies": [
            policy_payload(policy)
            for policy in policies
        ],
        "campaign_count": len(campaigns),
        "campaigns": [
            {
                "policy": policy_payload(policy),
                **campaign_summary(campaign),
            }
            for policy, campaign, _ in campaigns
        ],
    }

    if args.plan_only:
        output["mode"] = "planned"

    else:
        output["mode"] = "executed"

        statuses: list[dict[str, Any]] = []

        for (
            policy,
            campaign,
            member_config,
        ) in campaigns:
            gate = build_entry_gate(policy)

            status = run_scorer_campaign(
                campaign=campaign,
                trading_config=member_config,
                continue_after_failure=(
                    not args.stop_on_failure
                ),
                research_entry_gate=gate,
            )

            statuses.append(
                {
                    "policy_id": policy.policy_id,
                    "symbol": campaign.source.symbol,
                    "campaign_id": campaign.campaign_id,
                    "status": status,
                }
            )

        output["campaign_statuses"] = statuses

    print(
        json.dumps(
            output,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
