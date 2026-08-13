from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from files.config import load_trading_config
from files.research.scorer_campaign_builder import (
    InitializedScorerCampaign,
    build_default_campaign_specification,
    initialize_scorer_campaign_with_trials,
)
from files.research.scorer_campaign_runner import run_scorer_campaign
from files.research.scorer_campaign_spec import load_runtime_git_identity
from files.research.scorer_parameter_space import (
    ScorerTrial,
    trial_id_for_parameters,
)


UNIVERSE_CONTRACT_PATH = Path(
    "files/research/contracts/"
    "coinbase_usd_research_universe_v1.json"
)

EXPECTED_UNIVERSE_ID = "research_universe_coinbase_usd_v1"
EXPECTED_UNIVERSE_FINGERPRINT = (
    "f6f75adb7161a9d051a52c18967ffce0d30bcb38c5911cf958d18c2b5ba0454a"
)
EXPECTED_TIMEFRAME = "5m"

PRIMARY_SYMBOLS: tuple[str, ...] = (
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "ADA/USD",
    "XLM/USD",
    "LINK/USD",
    "DOGE/USD",
    "LTC/USD",
)

BASELINE_TRIAL_ID = "trial_096291cf0738ff2f"

BASELINE_PARAMETERS: dict[str, float] = {
    "atr_pct_full_penalty": 0.00375,
    "atr_pct_penalty_max": 0.1,
    "atr_pct_soft_penalty_start": 0.00225,
    "confidence_enter": 0.68,
    "ema_slow_slope_full_scale": 0.0015,
    "ema_spread_full_scale": 0.00325,
    "long_rsi_center": 60.0,
    "long_rsi_overbought": 72.0,
    "ret_1_full_scale": 0.004,
    "return_confirmation_floor": 0.4,
    "return_contradiction_full_scale": 0.0035,
    "return_contradiction_penalty_max": 0.1,
    "rsi_extreme_penalty_max": 0.2,
    "rsi_half_width": 20.0,
    "short_rsi_center": 40.0,
    "short_rsi_oversold": 28.0,
    "slope_confirmation_floor": 0.35,
    "slope_contradiction_full_scale": 0.0013,
    "slope_contradiction_penalty_max": 0.25,
    "weight_recent_return": 0.30927835051546393,
    "weight_rsi_quality": 0.10309278350515465,
    "weight_trend_slope": 0.3195876288659794,
    "weight_trend_strength": 0.26804123711340205,
}


class MultiAssetBaselineError(RuntimeError):
    """Raised when the frozen multi-asset baseline contract is violated."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the frozen scorer-v3 baseline across "
            "the Coinbase USD Universe V1 PRIMARY_COMPARABLE core."
        )
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Resolve and verify all eight campaigns without executing "
            "their backtests."
        ),
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help=(
            "Stop after the first isolated campaign execution failure."
        ),
    )
    return parser


def load_universe_contract() -> dict[str, Any]:
    try:
        payload = json.loads(
            UNIVERSE_CONTRACT_PATH.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise MultiAssetBaselineError(
            f"Unable to load frozen universe contract: "
            f"{UNIVERSE_CONTRACT_PATH}"
        ) from exc

    if payload.get("universe_id") != EXPECTED_UNIVERSE_ID:
        raise MultiAssetBaselineError(
            "Universe ID does not match frozen baseline contract."
        )

    if (
        payload.get("universe_fingerprint")
        != EXPECTED_UNIVERSE_FINGERPRINT
    ):
        raise MultiAssetBaselineError(
            "Universe fingerprint does not match frozen baseline contract."
        )

    if payload.get("status") != "frozen":
        raise MultiAssetBaselineError(
            f"Universe status must be 'frozen'; "
            f"got {payload.get('status')!r}."
        )

    if payload.get("timeframe") != EXPECTED_TIMEFRAME:
        raise MultiAssetBaselineError(
            "Universe timeframe does not match frozen baseline contract."
        )

    if int(payload.get("member_count", -1)) != 29:
        raise MultiAssetBaselineError(
            "Universe member_count does not match frozen V1 contract."
        )

    return payload


def resolve_primary_members(
    universe: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    members = universe.get("members")

    if not isinstance(members, list):
        raise MultiAssetBaselineError(
            "Universe contract members must be a list."
        )

    by_symbol: dict[str, dict[str, Any]] = {}

    for member in members:
        if not isinstance(member, dict):
            raise MultiAssetBaselineError(
                "Universe member must be an object."
            )

        symbol = str(member.get("symbol", "")).strip()

        if symbol:
            if symbol in by_symbol:
                raise MultiAssetBaselineError(
                    f"Duplicate universe symbol: {symbol}"
                )
            by_symbol[symbol] = member

    resolved: list[dict[str, Any]] = []

    for symbol in PRIMARY_SYMBOLS:
        member = by_symbol.get(symbol)

        if member is None:
            raise MultiAssetBaselineError(
                f"PRIMARY symbol missing from Universe V1: {symbol}"
            )

        if member.get("status") != "confirmed":
            raise MultiAssetBaselineError(
                f"PRIMARY symbol is not confirmed: {symbol}"
            )

        if member.get("timeframe") != EXPECTED_TIMEFRAME:
            raise MultiAssetBaselineError(
                f"PRIMARY symbol timeframe mismatch: {symbol}"
            )

        if str(member.get("data_tag", "")).strip() == "":
            raise MultiAssetBaselineError(
                f"PRIMARY symbol data_tag missing: {symbol}"
            )

        resolved.append(member)

    return tuple(resolved)


def frozen_baseline_trial() -> ScorerTrial:
    calculated_id = trial_id_for_parameters(
        BASELINE_PARAMETERS
    )

    if calculated_id != BASELINE_TRIAL_ID:
        raise MultiAssetBaselineError(
            "Frozen baseline parameter fingerprint mismatch: "
            f"expected={BASELINE_TRIAL_ID} "
            f"calculated={calculated_id}"
        )

    return ScorerTrial(
        trial_id=BASELINE_TRIAL_ID,
        parameters=dict(BASELINE_PARAMETERS),
    )


def campaign_summary(
    campaign: InitializedScorerCampaign,
) -> dict[str, Any]:
    return {
        "campaign_id": campaign.campaign_id,
        "data_tag": campaign.source.data_tag,
        "symbol": campaign.source.symbol,
        "timeframe": campaign.source.timeframe,
        "manifest_path": str(
            campaign.source.manifest_path
        ),
        "manifest_fingerprint": (
            campaign.source.manifest_fingerprint
        ),
        "trial_ids": [
            trial.trial_id
            for trial in campaign.trials
        ],
        "split_names": [
            split.name
            for split in campaign.resolved_splits
        ],
        "execution_count": len(
            campaign.execution_plan.executions
        ),
        "campaign_root": str(
            campaign.artifacts.root
        ),
    }


def initialize_primary_campaigns(
) -> tuple[
    tuple[InitializedScorerCampaign, Any],
    ...,
]:
    universe = load_universe_contract()
    members = resolve_primary_members(universe)
    baseline_trial = frozen_baseline_trial()

    trading_config = load_trading_config()
    git_identity = load_runtime_git_identity()

    campaigns: list[
        tuple[InitializedScorerCampaign, Any]
    ] = []

    for member in members:
        symbol = str(member["symbol"])
        data_tag = str(member["data_tag"])
        timeframe = str(member["timeframe"])

        member_config = replace(
            trading_config,
            symbol=symbol,
            data_tag=data_tag,
            timeframe=timeframe,
        )

        specification = build_default_campaign_specification(
            trading_config=member_config,
            trial_count=1,
        )

        campaign = initialize_scorer_campaign_with_trials(
            trading_config=member_config,
            git_identity=git_identity,
            specification=specification,
            trials=(baseline_trial,),
            write_artifacts=True,
        )

        if campaign.source.data_tag != data_tag:
            raise MultiAssetBaselineError(
                f"Resolved data_tag mismatch for {symbol}."
            )

        if campaign.source.symbol != symbol:
            raise MultiAssetBaselineError(
                f"Resolved symbol mismatch for {symbol}."
            )

        if campaign.source.timeframe != timeframe:
            raise MultiAssetBaselineError(
                f"Resolved timeframe mismatch for {symbol}."
            )

        expected_manifest = str(member["manifest_path"])

        if str(campaign.source.manifest_path) != expected_manifest:
            raise MultiAssetBaselineError(
                f"Manifest path mismatch for {symbol}: "
                f"expected={expected_manifest!r} "
                f"resolved={str(campaign.source.manifest_path)!r}"
            )

        campaigns.append(
            (campaign, member_config)
        )

    if len(campaigns) != len(PRIMARY_SYMBOLS):
        raise MultiAssetBaselineError(
            "PRIMARY campaign count is not exactly eight."
        )

    return tuple(campaigns)


def main() -> None:
    args = build_parser().parse_args()

    campaigns = initialize_primary_campaigns()

    output: dict[str, Any] = {
        "baseline_contract": "multi_asset_baseline_v1",
        "universe_id": EXPECTED_UNIVERSE_ID,
        "universe_fingerprint": EXPECTED_UNIVERSE_FINGERPRINT,
        "population": "PRIMARY_COMPARABLE",
        "symbols": list(PRIMARY_SYMBOLS),
        "scorer_contract": "entry_scorer_v3_normalized_slope",
        "baseline_trial_id": BASELINE_TRIAL_ID,
        "campaigns": [
            campaign_summary(campaign)
            for campaign, _ in campaigns
        ],
    }

    if args.plan_only:
        output["mode"] = "planned"
    else:
        output["mode"] = "executed"
        statuses: list[dict[str, Any]] = []

        for campaign, member_config in campaigns:
            status = run_scorer_campaign(
                campaign=campaign,
                trading_config=member_config,
                continue_after_failure=(
                    not args.stop_on_failure
                ),
            )

            statuses.append(
                {
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
