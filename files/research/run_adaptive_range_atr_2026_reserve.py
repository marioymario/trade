from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from statistics import median
from typing import Any

from files.backtest.replay import build_research_replay_plan
from files.config import load_trading_config
from files.data.paths import safe_tag
from files.research.historical_dataset import (
    build_historical_research_dataset,
    load_and_resolve_historical_research_source,
)
from files.research.run_adaptive_range_atr_development import (
    ATR_FEATURE,
    BASELINE_POLICY_ID,
    BASELINE_TRIAL_ID,
    EPSILON,
    EXPECTED_UNIVERSE_FINGERPRINT,
    EXPECTED_UNIVERSE_ID,
    PRIMARY_SYMBOLS,
    RANGE_POLICY_ID,
    RESEARCH_ORDER_NOTIONAL_USD,
    RANGE_FEATURE,
    RANGE_THRESHOLD,
    TIMEFRAME_MS,
    AtrPolicy,
    DevelopmentPeriod,
    build_entry_gate,
    frozen_baseline_trial,
    load_universe_contract,
    resolve_primary_members,
    utc_ms,
)
from files.research.scorer_campaign_builder import (
    build_default_campaign_specification,
)
from files.research.scorer_campaign_execution import (
    _remove_partial_backtest_outputs,
)
from files.research.scorer_metrics import calculate_trial_metrics
from files.research.scorer_trial import (
    TrialRunRequest,
    run_single_trial,
)


CONTRACT_ID = "adaptive_range_atr_empirical_challenger_v1"

CONTRACT_PATH = Path(
    "files/research/contracts/"
    "adaptive_range_atr_empirical_challenger_v1.json"
)

EXPERIMENT_ID = "adaptive_range_atr_2026_reserve_v1"

OUTPUT_ROOT = (
    Path("data/processed/research/reserves")
    / EXPERIMENT_ID
)

RESERVE_START = "2026-01-01T00:00:00Z"
RESERVE_END_EXCLUSIVE = "2026-02-09T00:00:00Z"

CONTROL_POLICY = AtrPolicy(
    policy_id="adaptive_range_control",
    atr_floor=None,
)

CANDIDATE_POLICY = AtrPolicy(
    policy_id="adaptive_range_atr_ge_0_005",
    atr_floor=0.005,
)

POLICIES = (
    CONTROL_POLICY,
    CANDIDATE_POLICY,
)

EXPECTED_2026_ASSET_POLICY = {
    "BTC/USD": RANGE_POLICY_ID,
    "ETH/USD": RANGE_POLICY_ID,
    "SOL/USD": RANGE_POLICY_ID,
    "ADA/USD": RANGE_POLICY_ID,
    "XLM/USD": RANGE_POLICY_ID,
    "LINK/USD": RANGE_POLICY_ID,
    "DOGE/USD": RANGE_POLICY_ID,
    "LTC/USD": BASELINE_POLICY_ID,
}

EXPECTED_RANGE_SYMBOLS = (
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "ADA/USD",
    "XLM/USD",
    "LINK/USD",
    "DOGE/USD",
)

EXPECTED_BASELINE_SYMBOLS = (
    "LTC/USD",
)

BASE_FEE_BPS = 8.0
BASE_SLIPPAGE_BPS = 5.0


class ReserveError(RuntimeError):
    """Raised when the frozen reserve contract is violated."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Consume the frozen 2026 historical reserve exactly once "
            "for the adaptive-range + ATR>=0.005 empirical challenger."
        )
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Validate all frozen identities and print the reserve "
            "execution plan without loading bars or running backtests."
        ),
    )

    return parser


def load_challenger_contract() -> dict[str, Any]:
    try:
        payload = json.loads(
            CONTRACT_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise ReserveError(
            f"Unable to load frozen challenger contract: "
            f"{CONTRACT_PATH}"
        ) from exc

    if payload.get("contract_id") != CONTRACT_ID:
        raise ReserveError(
            "Frozen challenger contract ID mismatch."
        )

    if (
        payload.get("status")
        != "FROZEN_EMPIRICAL_CHALLENGER"
    ):
        raise ReserveError(
            "Challenger contract is not frozen."
        )

    universe = payload.get(
        "research_universe",
        {},
    )

    if (
        universe.get("universe_id")
        != EXPECTED_UNIVERSE_ID
    ):
        raise ReserveError(
            "Frozen universe ID mismatch."
        )

    if (
        universe.get("universe_fingerprint")
        != EXPECTED_UNIVERSE_FINGERPRINT
    ):
        raise ReserveError(
            "Frozen universe fingerprint mismatch."
        )

    if tuple(
        universe.get("symbols", ())
    ) != PRIMARY_SYMBOLS:
        raise ReserveError(
            "Frozen PRIMARY symbol membership/order mismatch."
        )

    candidate = payload.get(
        "candidate",
        {},
    )

    if (
        candidate.get("policy_id")
        != CANDIDATE_POLICY.policy_id
    ):
        raise ReserveError(
            "Frozen candidate policy ID mismatch."
        )

    if (
        candidate.get("atr_feature")
        != ATR_FEATURE
    ):
        raise ReserveError(
            "Frozen ATR feature mismatch."
        )

    if (
        float(candidate.get("atr_floor"))
        != 0.005
    ):
        raise ReserveError(
            "Frozen ATR floor mismatch."
        )

    if (
        candidate.get("range_feature")
        != RANGE_FEATURE
    ):
        raise ReserveError(
            "Frozen range feature mismatch."
        )

    if (
        float(candidate.get("range_threshold"))
        != RANGE_THRESHOLD
    ):
        raise ReserveError(
            "Frozen range threshold mismatch."
        )

    execution = payload.get(
        "execution_contract",
        {},
    )

    if execution.get("timeframe") != "5m":
        raise ReserveError(
            "Frozen timeframe mismatch."
        )

    if (
        float(
            execution.get(
                "research_order_notional_usd"
            )
        )
        != RESEARCH_ORDER_NOTIONAL_USD
    ):
        raise ReserveError(
            "Frozen research notional mismatch."
        )

    if execution.get("long_only") is not True:
        raise ReserveError(
            "Frozen LONG-only state changed."
        )

    if execution.get("short_enabled") is not False:
        raise ReserveError(
            "Frozen SHORT state changed."
        )

    if (
        execution.get("event_risk_connected")
        is not False
    ):
        raise ReserveError(
            "Frozen Event-Risk state changed."
        )

    if (
        float(execution.get("base_fee_bps"))
        != BASE_FEE_BPS
    ):
        raise ReserveError(
            "Frozen fee assumption mismatch."
        )

    if (
        float(
            execution.get(
                "base_slippage_bps"
            )
        )
        != BASE_SLIPPAGE_BPS
    ):
        raise ReserveError(
            "Frozen slippage assumption mismatch."
        )

    reserve = payload.get(
        "final_reserve",
        {},
    )

    if (
        reserve.get("start_inclusive")
        != RESERVE_START
    ):
        raise ReserveError(
            "Frozen reserve start mismatch."
        )

    if (
        reserve.get("end_exclusive")
        != RESERVE_END_EXCLUSIVE
    ):
        raise ReserveError(
            "Frozen reserve end mismatch."
        )

    if reserve.get("consumed") is not False:
        raise ReserveError(
            "Frozen contract already marks reserve consumed."
        )

    if (
        int(
            reserve.get(
                "maximum_permitted_consumptions"
            )
        )
        != 1
    ):
        raise ReserveError(
            "Reserve consumption limit changed."
        )

    if (
        reserve.get(
            "adaptive_range_policy_frozen"
        )
        is not True
    ):
        raise ReserveError(
            "2026 adaptive range policy is not frozen."
        )

    schedule = payload.get(
        "adaptive_range_schedule",
        {},
    ).get(
        "validate_2026_reserve",
        {},
    )

    if (
        schedule.get(
            "derived_before_2026_reserve_consumption"
        )
        is not True
    ):
        raise ReserveError(
            "2026 range map was not marked pre-reserve."
        )

    if (
        schedule.get(
            "selection_evidence_cutoff"
        )
        != RESERVE_START
    ):
        raise ReserveError(
            "2026 policy evidence cutoff mismatch."
        )

    if (
        schedule.get("asset_policy")
        != EXPECTED_2026_ASSET_POLICY
    ):
        raise ReserveError(
            "Frozen 2026 asset-policy map mismatch."
        )

    if tuple(
        schedule.get("range_symbols", ())
    ) != EXPECTED_RANGE_SYMBOLS:
        raise ReserveError(
            "Frozen 2026 RANGE symbol order/membership mismatch."
        )

    if tuple(
        schedule.get("baseline_symbols", ())
    ) != EXPECTED_BASELINE_SYMBOLS:
        raise ReserveError(
            "Frozen 2026 BASELINE symbol order/membership mismatch."
        )

    freeze_rules = payload.get(
        "freeze_rules",
        {},
    )

    required_false = (
        "additional_atr_threshold_search_before_reserve",
        "asset_specific_atr_thresholds_before_reserve",
        "adaptive_range_schedule_changes_before_reserve",
        "scorer_changes_before_reserve",
        "stop_or_exit_changes_before_reserve",
        "asset_removal_before_reserve",
        "cost_assumption_changes_before_reserve",
        "repair_after_viewing_reserve",
    )

    for key in required_false:
        if freeze_rules.get(key) is not False:
            raise ReserveError(
                f"Freeze rule changed: {key}"
            )

    return payload


def reserve_period() -> DevelopmentPeriod:
    return DevelopmentPeriod(
        period_id="validate_2026_reserve",
        start_inclusive=RESERVE_START,
        end_exclusive=RESERVE_END_EXCLUSIVE,
        range_symbols=EXPECTED_RANGE_SYMBOLS,
    )


def plan_payload() -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "contract_id": CONTRACT_ID,
        "mode": "planned",
        "reserve_start_inclusive": (
            RESERVE_START
        ),
        "reserve_end_exclusive": (
            RESERVE_END_EXCLUSIVE
        ),
        "symbols": list(PRIMARY_SYMBOLS),
        "asset_policy": dict(
            EXPECTED_2026_ASSET_POLICY
        ),
        "control_policy_id": (
            CONTROL_POLICY.policy_id
        ),
        "candidate_policy_id": (
            CANDIDATE_POLICY.policy_id
        ),
        "candidate_atr_floor": (
            CANDIDATE_POLICY.atr_floor
        ),
        "range_threshold": (
            RANGE_THRESHOLD
        ),
        "fee_bps": BASE_FEE_BPS,
        "slippage_bps": (
            BASE_SLIPPAGE_BPS
        ),
        "execution_count": (
            len(PRIMARY_SYMBOLS)
            * len(POLICIES)
        ),
        "maximum_permitted_consumptions": 1,
        "reserve_consumed_before_run": False,
    }


def run_execution(
    *,
    period: DevelopmentPeriod,
    policy: AtrPolicy,
    symbol: str,
    member: dict[str, Any],
) -> dict[str, Any]:
    data_tag = str(member["data_tag"])
    timeframe = str(member["timeframe"])
    manifest_path = Path(
        str(member["manifest_path"])
    )

    if timeframe != "5m":
        raise ReserveError(
            f"{symbol}: timeframe is not frozen at 5m."
        )

    source = load_and_resolve_historical_research_source(
        data_tag=data_tag,
        expected_symbol=symbol,
        expected_timeframe=timeframe,
        manifest_path=manifest_path,
    )

    if source.symbol != symbol:
        raise ReserveError(
            f"{symbol}: resolved symbol mismatch."
        )

    if source.data_tag != data_tag:
        raise ReserveError(
            f"{symbol}: resolved data_tag mismatch."
        )

    if source.timeframe != timeframe:
        raise ReserveError(
            f"{symbol}: resolved timeframe mismatch."
        )

    if str(source.manifest_path) != str(
        manifest_path
    ):
        raise ReserveError(
            f"{symbol}: manifest path mismatch."
        )

    trading_config = load_trading_config()

    if (
        float(trading_config.fee_bps)
        != BASE_FEE_BPS
    ):
        raise ReserveError(
            "Runtime fee_bps differs from frozen base cost."
        )

    if (
        float(trading_config.slippage_bps)
        != BASE_SLIPPAGE_BPS
    ):
        raise ReserveError(
            "Runtime slippage_bps differs from frozen base cost."
        )

    member_config = replace(
        trading_config,
        symbol=symbol,
        data_tag=data_tag,
        timeframe=timeframe,
        dry_run=True,
    )

    adaptive_range_role = (
        RANGE_POLICY_ID
        if symbol in period.range_symbols
        else BASELINE_POLICY_ID
    )

    expected_role = (
        EXPECTED_2026_ASSET_POLICY[
            symbol
        ]
    )

    if adaptive_range_role != expected_role:
        raise ReserveError(
            f"{symbol}: 2026 adaptive role drifted."
        )

    research_policy_id = (
        f"{EXPERIMENT_ID}:"
        f"{period.period_id}:"
        f"{adaptive_range_role}:"
        f"{policy.policy_id}"
    )

    specification = (
        build_default_campaign_specification(
            trading_config=member_config,
            trial_count=1,
            research_order_notional_usd=(
                RESEARCH_ORDER_NOTIONAL_USD
            ),
            research_entry_policy_id=(
                research_policy_id
            ),
        )
    )

    start_ts_ms = utc_ms(
        RESERVE_START
    )

    end_exclusive_ts_ms = utc_ms(
        RESERVE_END_EXCLUSIVE
    )

    inclusive_end_ts_ms = (
        end_exclusive_ts_ms
        - TIMEFRAME_MS
    )

    dataset = build_historical_research_dataset(
        audit=source.audit,
        start_ts_ms=start_ts_ms,
        end_ts_ms=inclusive_end_ts_ms,
        warmup_bars=max(
            int(specification.min_bars),
            50,
        )
        + 5,
    )

    if (
        dataset.requested_range.requested_start_ts_ms
        != start_ts_ms
    ):
        raise ReserveError(
            f"{symbol}: reserve start boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms
        != inclusive_end_ts_ms
    ):
        raise ReserveError(
            f"{symbol}: reserve inclusive end boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms_exclusive
        != end_exclusive_ts_ms
    ):
        raise ReserveError(
            f"{symbol}: reserve end-exclusive boundary drifted."
        )

    replay_plan = build_research_replay_plan(
        dataset=dataset
    )

    trial = frozen_baseline_trial()

    if trial.trial_id != BASELINE_TRIAL_ID:
        raise ReserveError(
            "Frozen baseline scorer trial changed."
        )

    gate = build_entry_gate(
        period=period,
        symbol=symbol,
        policy=policy,
    )

    symbol_storage = symbol.replace(
        "/",
        "_",
    )

    runid = (
        f"reserve_{EXPERIMENT_ID}_"
        f"{symbol_storage}_"
        f"{policy.policy_id}"
    )

    _remove_partial_backtest_outputs(
        data_tag=safe_tag(data_tag),
        run_id=safe_tag(runid),
        symbol_storage=symbol_storage,
        timeframe=timeframe,
    )

    trial_result = run_single_trial(
        TrialRunRequest(
            trial=trial,
            runid=runid,
            trading_config=member_config,
            scorer_contract=(
                specification.scorer_contract
            ),
            start_ts_ms=start_ts_ms,
            end_ts_ms=inclusive_end_ts_ms,
            replay_plan=replay_plan,
            research_order_notional_usd=(
                RESEARCH_ORDER_NOTIONAL_USD
            ),
            research_entry_gate=gate,
        )
    )

    metrics = calculate_trial_metrics(
        trades_csv=(
            trial_result.backtest.trades_csv
        )
    )

    if metrics.short_trade_count != 0:
        raise ReserveError(
            f"{symbol}/{policy.policy_id}: "
            "SHORT trade detected."
        )

    return {
        "experiment_id": EXPERIMENT_ID,
        "contract_id": CONTRACT_ID,
        "period_id": period.period_id,
        "symbol": symbol,
        "policy_id": policy.policy_id,
        "atr_floor": policy.atr_floor,
        "adaptive_range_role": (
            adaptive_range_role
        ),
        "fee_bps": (
            member_config.fee_bps
        ),
        "slippage_bps": (
            member_config.slippage_bps
        ),
        "runid": runid,
        "source": {
            "data_tag": source.data_tag,
            "symbol": source.symbol,
            "timeframe": source.timeframe,
            "manifest_path": str(
                source.manifest_path
            ),
            "manifest_fingerprint": (
                source.manifest_fingerprint
            ),
        },
        "replay": {
            "start_ts_ms": start_ts_ms,
            "inclusive_end_ts_ms": (
                inclusive_end_ts_ms
            ),
            "end_exclusive_ts_ms": (
                end_exclusive_ts_ms
            ),
            "replay_bar_count": (
                dataset.replay_bar_count
            ),
            "physical_segment_count": len(
                dataset.segments
            ),
        },
        "metrics": metrics.as_dict(),
    }


def evaluate(
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key = {
        (
            row["symbol"],
            row["policy_id"],
        ): row
        for row in executions
    }

    expected_count = (
        len(PRIMARY_SYMBOLS)
        * len(POLICIES)
    )

    if len(by_key) != expected_count:
        raise ReserveError(
            "Reserve execution result count mismatch."
        )

    asset_rows = []

    for symbol in PRIMARY_SYMBOLS:
        control = by_key[
            (
                symbol,
                CONTROL_POLICY.policy_id,
            )
        ]

        candidate = by_key[
            (
                symbol,
                CANDIDATE_POLICY.policy_id,
            )
        ]

        control_metrics = (
            control["metrics"]
        )

        candidate_metrics = (
            candidate["metrics"]
        )

        control_pnl = float(
            control_metrics[
                "total_pnl_usd"
            ]
        )

        candidate_pnl = float(
            candidate_metrics[
                "total_pnl_usd"
            ]
        )

        control_dd = float(
            control_metrics[
                "maximum_drawdown_usd"
            ]
        )

        candidate_dd = float(
            candidate_metrics[
                "maximum_drawdown_usd"
            ]
        )

        asset_rows.append(
            {
                "symbol": symbol,
                "adaptive_range_role": (
                    candidate[
                        "adaptive_range_role"
                    ]
                ),
                "control_pnl_usd": (
                    control_pnl
                ),
                "candidate_pnl_usd": (
                    candidate_pnl
                ),
                "delta_pnl_usd": (
                    candidate_pnl
                    - control_pnl
                ),
                "candidate_beats_control": (
                    candidate_pnl
                    > control_pnl
                    + EPSILON
                ),
                "candidate_not_worse_than_control": (
                    candidate_pnl
                    >= control_pnl
                    - EPSILON
                ),
                "control_trade_count": int(
                    control_metrics[
                        "trade_count"
                    ]
                ),
                "candidate_trade_count": int(
                    candidate_metrics[
                        "trade_count"
                    ]
                ),
                "control_maximum_drawdown_usd": (
                    control_dd
                ),
                "candidate_maximum_drawdown_usd": (
                    candidate_dd
                ),
            }
        )

    control_total = sum(
        row["control_pnl_usd"]
        for row in asset_rows
    )

    candidate_total = sum(
        row["candidate_pnl_usd"]
        for row in asset_rows
    )

    delta_total = (
        candidate_total
        - control_total
    )

    candidate_positive_assets = sum(
        row["candidate_pnl_usd"] > 0.0
        for row in asset_rows
    )

    assets_beating_control = sum(
        row["candidate_beats_control"]
        for row in asset_rows
    )

    assets_not_worse = sum(
        row[
            "candidate_not_worse_than_control"
        ]
        for row in asset_rows
    )

    control_median_dd = median(
        row[
            "control_maximum_drawdown_usd"
        ]
        for row in asset_rows
    )

    candidate_median_dd = median(
        row[
            "candidate_maximum_drawdown_usd"
        ]
        for row in asset_rows
    )

    if (
        candidate_total > 0.0
        and delta_total > 0.0
        and assets_not_worse >= 5
    ):
        interpretation = (
            "STRONG_GENERALIZATION"
        )
    elif delta_total > 0.0:
        interpretation = (
            "RELATIVE_EFFECT_GENERALIZED_"
            "BUT_ABSOLUTE_ECONOMICS_INSUFFICIENT"
        )
    else:
        interpretation = (
            "EMPIRICAL_HYPOTHESIS_NOT_SUPPORTED"
        )

    return {
        "experiment_id": EXPERIMENT_ID,
        "contract_id": CONTRACT_ID,
        "reserve_window": {
            "start_inclusive": (
                RESERVE_START
            ),
            "end_exclusive": (
                RESERVE_END_EXCLUSIVE
            ),
        },
        "reserve_consumed": True,
        "reserve_consumption_count": 1,
        "interpretation": interpretation,
        "aggregate": {
            "control_total_pnl_usd": (
                control_total
            ),
            "candidate_total_pnl_usd": (
                candidate_total
            ),
            "candidate_delta_pnl_usd": (
                delta_total
            ),
            "candidate_total_trade_count": sum(
                row["candidate_trade_count"]
                for row in asset_rows
            ),
            "control_total_trade_count": sum(
                row["control_trade_count"]
                for row in asset_rows
            ),
            "candidate_positive_asset_count": (
                candidate_positive_assets
            ),
            "asset_count": len(
                asset_rows
            ),
            "assets_beating_control": (
                assets_beating_control
            ),
            "assets_not_worse_than_control": (
                assets_not_worse
            ),
            "candidate_median_maximum_drawdown_usd": (
                candidate_median_dd
            ),
            "control_median_maximum_drawdown_usd": (
                control_median_dd
            ),
        },
        "assets": asset_rows,
    }


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.exists():
        raise ReserveError(
            f"Refusing to overwrite reserve artifact: {path}"
        )

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = build_parser().parse_args()

    load_challenger_contract()

    universe = load_universe_contract()

    if (
        universe.get("universe_id")
        != EXPECTED_UNIVERSE_ID
    ):
        raise ReserveError(
            "Runtime universe ID mismatch."
        )

    if (
        universe.get("universe_fingerprint")
        != EXPECTED_UNIVERSE_FINGERPRINT
    ):
        raise ReserveError(
            "Runtime universe fingerprint mismatch."
        )

    members = resolve_primary_members(
        universe
    )

    if tuple(
        str(member["symbol"])
        for member in members
    ) != PRIMARY_SYMBOLS:
        raise ReserveError(
            "Runtime PRIMARY membership/order changed."
        )

    plan = plan_payload()

    if args.plan_only:
        print(
            json.dumps(
                plan,
                indent=2,
                sort_keys=True,
            )
        )
        return

    if OUTPUT_ROOT.exists():
        raise ReserveError(
            "Reserve output root already exists; refusing a "
            "second or partial reserve consumption: "
            f"{OUTPUT_ROOT}"
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_json(
        OUTPUT_ROOT / "execution_plan.json",
        plan,
    )

    period = reserve_period()

    member_by_symbol = {
        str(member["symbol"]): member
        for member in members
    }

    executions = []

    for symbol in PRIMARY_SYMBOLS:
        member = member_by_symbol[
            symbol
        ]

        for policy in POLICIES:
            result = run_execution(
                period=period,
                policy=policy,
                symbol=symbol,
                member=member,
            )

            executions.append(
                result
            )

            write_json(
                OUTPUT_ROOT
                / "executions"
                / (
                    f"{symbol.replace('/', '_')}__"
                    f"{policy.policy_id}.json"
                ),
                result,
            )

    result = evaluate(
        executions
    )

    write_json(
        OUTPUT_ROOT / "result.json",
        result,
    )

    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
