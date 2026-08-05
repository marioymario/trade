from __future__ import annotations

import argparse
import json
from typing import Any

from files.config import load_trading_config
from files.research.scorer_campaign_builder import (
    InitializedScorerCampaign,
    initialize_scorer_campaign,
)
from files.research.scorer_campaign_runner import (
    run_scorer_campaign,
)
from files.research.scorer_campaign_spec import (
    load_runtime_git_identity,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or run a deterministic manifest-backed "
            "scorer campaign."
        )
    )

    parser.add_argument(
        "--trial-count",
        type=int,
        default=None,
        help=(
            "Override the source-controlled default candidate count."
        ),
    )

    parser.add_argument(
        "--random-seed",
        type=int,
        default=None,
        help=(
            "Override the source-controlled deterministic seed."
        ),
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Write and report the immutable campaign manifest "
            "and execution plan without running executions."
        ),
    )

    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help=(
            "Stop after the first isolated execution failure. "
            "Campaign-wide contract failures always stop."
        ),
    )

    return parser


def campaign_plan_summary(
    campaign: InitializedScorerCampaign,
) -> dict[str, Any]:
    return {
        "campaign_id": campaign.campaign_id,
        "mode": "planned",
        "campaign_root": str(
            campaign.artifacts.root
        ),
        "campaign_manifest_json": str(
            campaign.artifacts.campaign_manifest_json
        ),
        "execution_plan_json": str(
            campaign.artifacts.execution_plan_json
        ),
        "source": {
            "data_tag": campaign.source.data_tag,
            "symbol": campaign.source.symbol,
            "timeframe": campaign.source.timeframe,
            "manifest_path": str(
                campaign.source.manifest_path
            ),
            "manifest_fingerprint": (
                campaign.source.manifest_fingerprint
            ),
        },
        "trial_count": len(campaign.trials),
        "split_count": len(
            campaign.resolved_splits
        ),
        "execution_count": len(
            campaign.execution_plan.executions
        ),
    }


def main() -> None:
    args = build_parser().parse_args()

    if (
        args.trial_count is not None
        and args.trial_count <= 0
    ):
        raise SystemExit(
            "--trial-count must be positive."
        )

    trading_config = load_trading_config()
    git_identity = load_runtime_git_identity()

    campaign = initialize_scorer_campaign(
        trading_config=trading_config,
        git_identity=git_identity,
        trial_count=args.trial_count,
        random_seed=args.random_seed,
        write_artifacts=True,
    )

    if args.plan_only:
        output = campaign_plan_summary(
            campaign
        )
    else:
        status = run_scorer_campaign(
            campaign=campaign,
            trading_config=trading_config,
            continue_after_failure=(
                not args.stop_on_failure
            ),
        )

        output = {
            **campaign_plan_summary(campaign),
            "mode": "executed",
            "campaign_status": status,
            "summary_json": str(
                campaign.artifacts.summary_json
            ),
            "fold_results_csv": str(
                campaign.artifacts.fold_results_csv
            ),
            "candidate_results_csv": str(
                campaign.artifacts.candidate_results_csv
            ),
            "rejections_csv": str(
                campaign.artifacts.rejections_csv
            ),
            "failures_csv": str(
                campaign.artifacts.failures_csv
            ),
        }

    print(
        json.dumps(
            output,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
