from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
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
    PERIODS,
    PRIMARY_SYMBOLS,
    RANGE_POLICY_ID,
    RESEARCH_ORDER_NOTIONAL_USD,
    RESERVED_2026_START,
    TIMEFRAME_MS,
    AtrPolicy,
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


EXPERIMENT_ID = "adaptive_range_atr_robustness_v1"

OUTPUT_ROOT = (
    Path("data/processed/research/experiments")
    / EXPERIMENT_ID
)

DEVELOPMENT_RESULT = (
    Path("data/processed/research/experiments")
    / "adaptive_range_atr_development_v1"
    / "result.json"
)

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

MINIMUM_TOTAL_TRADES = 20
MINIMUM_TRADES_PER_ASSET_PERIOD = 3

MAX_ASSETS_DD_DETERIORATION_OVER_25_PERCENT = 2


class RobustnessError(RuntimeError):
    pass


@dataclass(frozen=True)
class CostScenario:
    scenario_id: str
    multiplier: float


COST_SCENARIOS = (
    CostScenario(
        scenario_id="stress_1_5x",
        multiplier=1.5,
    ),
    CostScenario(
        scenario_id="stress_2_0x",
        multiplier=2.0,
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Final development robustness battery for the "
            "adaptive-range + ATR>=0.005 candidate."
        )
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
    )

    return parser


def validate_contract() -> None:
    if CANDIDATE_POLICY.atr_floor != 0.005:
        raise RobustnessError(
            "Candidate ATR floor changed."
        )

    if tuple(
        policy.policy_id
        for policy in POLICIES
    ) != (
        "adaptive_range_control",
        "adaptive_range_atr_ge_0_005",
    ):
        raise RobustnessError(
            "Robustness policy family changed."
        )

    if tuple(
        scenario.multiplier
        for scenario in COST_SCENARIOS
    ) != (1.5, 2.0):
        raise RobustnessError(
            "Cost-stress schedule changed."
        )

    for period in PERIODS:
        if utc_ms(period.end_exclusive) > utc_ms(
            RESERVED_2026_START
        ):
            raise RobustnessError(
                f"{period.period_id} consumes reserved 2026 data."
            )


def load_development_result() -> dict[str, Any]:
    if not DEVELOPMENT_RESULT.exists():
        raise RobustnessError(
            "Verified development result is missing: "
            f"{DEVELOPMENT_RESULT}"
        )

    payload = json.loads(
        DEVELOPMENT_RESULT.read_text(
            encoding="utf-8"
        )
    )

    if payload.get(
        "experiment_id"
    ) != "adaptive_range_atr_development_v1":
        raise RobustnessError(
            "Unexpected development experiment identity."
        )

    if payload.get(
        "reserved_2026_outcomes_consumed"
    ) is not False:
        raise RobustnessError(
            "Development result does not prove 2026 remained sealed."
        )

    return payload


def plan_payload(
    *,
    base_fee_bps: float,
    base_slippage_bps: float,
) -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "candidate_policy_id": (
            CANDIDATE_POLICY.policy_id
        ),
        "candidate_atr_floor": (
            CANDIDATE_POLICY.atr_floor
        ),
        "control_policy_id": (
            CONTROL_POLICY.policy_id
        ),
        "development_result": str(
            DEVELOPMENT_RESULT
        ),
        "development_periods": [
            period.period_id
            for period in PERIODS
        ],
        "symbols": list(PRIMARY_SYMBOLS),
        "cost_scenarios": [
            {
                "scenario_id": (
                    scenario.scenario_id
                ),
                "multiplier": (
                    scenario.multiplier
                ),
                "fee_bps": (
                    base_fee_bps
                    * scenario.multiplier
                ),
                "slippage_bps": (
                    base_slippage_bps
                    * scenario.multiplier
                ),
            }
            for scenario in COST_SCENARIOS
        ],
        "stress_execution_count": (
            len(COST_SCENARIOS)
            * len(PERIODS)
            * len(PRIMARY_SYMBOLS)
            * len(POLICIES)
        ),
        "minimum_total_trades": (
            MINIMUM_TOTAL_TRADES
        ),
        "minimum_trades_per_asset_period": (
            MINIMUM_TRADES_PER_ASSET_PERIOD
        ),
        "reserved_2026_start": (
            RESERVED_2026_START
        ),
        "reserved_2026_outcomes_consumed": False,
    }


def run_execution(
    *,
    period: Any,
    policy: AtrPolicy,
    scenario: CostScenario,
    symbol: str,
    member: dict[str, Any],
) -> dict[str, Any]:
    data_tag = str(member["data_tag"])
    timeframe = str(member["timeframe"])
    manifest_path = Path(
        str(member["manifest_path"])
    )

    if timeframe != "5m":
        raise RobustnessError(
            f"{symbol}: timeframe is not 5m."
        )

    source = load_and_resolve_historical_research_source(
        data_tag=data_tag,
        expected_symbol=symbol,
        expected_timeframe=timeframe,
        manifest_path=manifest_path,
    )

    if source.symbol != symbol:
        raise RobustnessError(
            f"{symbol}: resolved symbol mismatch."
        )

    if source.data_tag != data_tag:
        raise RobustnessError(
            f"{symbol}: resolved data_tag mismatch."
        )

    if source.timeframe != timeframe:
        raise RobustnessError(
            f"{symbol}: resolved timeframe mismatch."
        )

    if str(source.manifest_path) != str(
        manifest_path
    ):
        raise RobustnessError(
            f"{symbol}: manifest path mismatch."
        )

    trading_config = load_trading_config()

    member_config = replace(
        trading_config,
        symbol=symbol,
        data_tag=data_tag,
        timeframe=timeframe,
        dry_run=True,
        fee_bps=(
            float(trading_config.fee_bps)
            * scenario.multiplier
        ),
        slippage_bps=(
            float(trading_config.slippage_bps)
            * scenario.multiplier
        ),
    )

    adaptive_range_role = (
        RANGE_POLICY_ID
        if symbol in period.range_symbols
        else BASELINE_POLICY_ID
    )

    research_policy_id = (
        f"{EXPERIMENT_ID}:"
        f"{scenario.scenario_id}:"
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
        period.start_inclusive
    )
    end_exclusive_ts_ms = utc_ms(
        period.end_exclusive
    )
    inclusive_end_ts_ms = (
        end_exclusive_ts_ms - TIMEFRAME_MS
    )

    if end_exclusive_ts_ms > utc_ms(
        RESERVED_2026_START
    ):
        raise RobustnessError(
            f"{symbol}/{period.period_id}: "
            "execution would consume reserved 2026 data."
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
        raise RobustnessError(
            f"{symbol}/{period.period_id}: "
            "start boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms
        != inclusive_end_ts_ms
    ):
        raise RobustnessError(
            f"{symbol}/{period.period_id}: "
            "inclusive end boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms_exclusive
        != end_exclusive_ts_ms
    ):
        raise RobustnessError(
            f"{symbol}/{period.period_id}: "
            "end-exclusive boundary drifted."
        )

    replay_plan = build_research_replay_plan(
        dataset=dataset
    )

    trial = frozen_baseline_trial()

    if trial.trial_id != BASELINE_TRIAL_ID:
        raise RobustnessError(
            "Frozen baseline trial changed."
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
        f"robust_{EXPERIMENT_ID}_"
        f"{scenario.scenario_id}_"
        f"{period.period_id}_"
        f"{symbol_storage}_"
        f"{policy.policy_id}"
    )

    _remove_partial_backtest_outputs(
        data_tag=safe_tag(data_tag),
        run_id=safe_tag(runid),
        symbol_storage=symbol_storage,
        timeframe=timeframe,
    )

    result = run_single_trial(
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
        trades_csv=result.backtest.trades_csv
    )

    if metrics.short_trade_count != 0:
        raise RobustnessError(
            f"{symbol}/{period.period_id}/"
            f"{scenario.scenario_id}/"
            f"{policy.policy_id}: SHORT trade detected."
        )

    return {
        "experiment_id": EXPERIMENT_ID,
        "cost_scenario_id": (
            scenario.scenario_id
        ),
        "cost_multiplier": (
            scenario.multiplier
        ),
        "fee_bps": (
            member_config.fee_bps
        ),
        "slippage_bps": (
            member_config.slippage_bps
        ),
        "period_id": period.period_id,
        "symbol": symbol,
        "policy_id": policy.policy_id,
        "atr_floor": policy.atr_floor,
        "adaptive_range_role": (
            adaptive_range_role
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
        "metrics": metrics.as_dict(),
        "reserved_2026_outcomes_consumed": False,
    }


def development_asset_rows(
    payload: dict[str, Any],
    *,
    policy_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for period_row in payload[
        "period_results"
    ]:
        if period_row["policy_id"] != policy_id:
            continue

        for asset in period_row["assets"]:
            rows.append(
                {
                    "period_id": (
                        period_row["period_id"]
                    ),
                    "symbol": asset["symbol"],
                    "pnl_usd": float(
                        asset["pnl_usd"]
                    ),
                    "control_pnl_usd": float(
                        asset[
                            "control_pnl_usd"
                        ]
                    ),
                    "delta_pnl_usd": float(
                        asset["delta_pnl_usd"]
                    ),
                    "trade_count": int(
                        asset["trade_count"]
                    ),
                    "maximum_drawdown_usd": float(
                        asset[
                            "maximum_drawdown_usd"
                        ]
                    ),
                    "control_maximum_drawdown_usd": float(
                        asset[
                            "control_maximum_drawdown_usd"
                        ]
                    ),
                }
            )

    return rows


def leave_one_out(
    rows: list[dict[str, Any]],
    *,
    dimension: str,
) -> list[dict[str, Any]]:
    values = sorted(
        {
            str(row[dimension])
            for row in rows
        }
    )

    output = []

    for omitted in values:
        remaining = [
            row
            for row in rows
            if str(row[dimension]) != omitted
        ]

        candidate_pnl = sum(
            row["pnl_usd"]
            for row in remaining
        )

        control_pnl = sum(
            row["control_pnl_usd"]
            for row in remaining
        )

        output.append(
            {
                f"omitted_{dimension}": (
                    omitted
                ),
                "candidate_pnl_usd": (
                    candidate_pnl
                ),
                "control_pnl_usd": (
                    control_pnl
                ),
                "delta_pnl_usd": (
                    candidate_pnl
                    - control_pnl
                ),
                "candidate_positive": (
                    candidate_pnl > 0.0
                ),
                "candidate_beats_control": (
                    candidate_pnl
                    > control_pnl + EPSILON
                ),
            }
        )

    return output


def contribution_concentration(
    values: list[float],
) -> float:
    positive = [
        value
        for value in values
        if value > 0.0
    ]

    total = sum(positive)

    if total <= 0.0:
        return 0.0

    return max(positive) / total


def aggregate_stress(
    executions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results = []

    for scenario in COST_SCENARIOS:
        scenario_rows = [
            row
            for row in executions
            if row["cost_scenario_id"]
            == scenario.scenario_id
        ]

        period_rows = []

        for period in PERIODS:
            selected_period = [
                row
                for row in scenario_rows
                if row["period_id"]
                == period.period_id
            ]

            control = [
                row
                for row in selected_period
                if row["policy_id"]
                == CONTROL_POLICY.policy_id
            ]

            candidate = [
                row
                for row in selected_period
                if row["policy_id"]
                == CANDIDATE_POLICY.policy_id
            ]

            control_pnl = sum(
                float(row["metrics"]["total_pnl_usd"])
                for row in control
            )

            candidate_pnl = sum(
                float(row["metrics"]["total_pnl_usd"])
                for row in candidate
            )

            period_rows.append(
                {
                    "period_id": (
                        period.period_id
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
                    "candidate_trade_count": sum(
                        int(
                            row["metrics"][
                                "trade_count"
                            ]
                        )
                        for row in candidate
                    ),
                }
            )

        results.append(
            {
                "cost_scenario_id": (
                    scenario.scenario_id
                ),
                "cost_multiplier": (
                    scenario.multiplier
                ),
                "candidate_total_pnl_usd": sum(
                    row["candidate_pnl_usd"]
                    for row in period_rows
                ),
                "control_total_pnl_usd": sum(
                    row["control_pnl_usd"]
                    for row in period_rows
                ),
                "candidate_delta_pnl_usd": sum(
                    row["delta_pnl_usd"]
                    for row in period_rows
                ),
                "candidate_positive_period_count": sum(
                    row["candidate_pnl_usd"] > 0.0
                    for row in period_rows
                ),
                "period_count": len(
                    period_rows
                ),
                "worst_candidate_period_pnl_usd": min(
                    row["candidate_pnl_usd"]
                    for row in period_rows
                ),
                "periods": period_rows,
            }
        )

    return results


def build_result(
    *,
    development: dict[str, Any],
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    base_rows = development_asset_rows(
        development,
        policy_id=CANDIDATE_POLICY.policy_id,
    )

    if len(base_rows) != (
        len(PERIODS)
        * len(PRIMARY_SYMBOLS)
    ):
        raise RobustnessError(
            "Development candidate asset-period count mismatch."
        )

    total_trades = sum(
        row["trade_count"]
        for row in base_rows
    )

    insufficient = [
        {
            "period_id": row["period_id"],
            "symbol": row["symbol"],
            "trade_count": row["trade_count"],
        }
        for row in base_rows
        if row["trade_count"]
        < MINIMUM_TRADES_PER_ASSET_PERIOD
    ]

    candidate_median_dd = median(
        row["maximum_drawdown_usd"]
        for row in base_rows
    )

    control_median_dd = median(
        row["control_maximum_drawdown_usd"]
        for row in base_rows
    )

    severe_dd = sum(
        (
            row["maximum_drawdown_usd"]
            > row[
                "control_maximum_drawdown_usd"
            ]
            * 1.25
            + EPSILON
        )
        if row[
            "control_maximum_drawdown_usd"
        ] > EPSILON
        else (
            row["maximum_drawdown_usd"]
            > row[
                "control_maximum_drawdown_usd"
            ]
            + EPSILON
        )
        for row in base_rows
    )

    by_asset_delta = {
        symbol: sum(
            row["delta_pnl_usd"]
            for row in base_rows
            if row["symbol"] == symbol
        )
        for symbol in PRIMARY_SYMBOLS
    }

    by_period_delta = {
        period.period_id: sum(
            row["delta_pnl_usd"]
            for row in base_rows
            if row["period_id"]
            == period.period_id
        )
        for period in PERIODS
    }

    asset_loo = leave_one_out(
        base_rows,
        dimension="symbol",
    )

    period_loo = leave_one_out(
        base_rows,
        dimension="period_id",
    )

    stress = aggregate_stress(
        executions
    )

    rules = {
        "base_total_trades_at_least_20": (
            total_trades
            >= MINIMUM_TOTAL_TRADES
        ),
        "base_every_asset_period_at_least_3_trades": (
            not insufficient
        ),
        "base_median_drawdown_not_worse": (
            candidate_median_dd
            <= control_median_dd
            + EPSILON
        ),
        "base_maximum_2_asset_periods_over_25pct_dd_deterioration": (
            severe_dd
            <= MAX_ASSETS_DD_DETERIORATION_OVER_25_PERCENT
        ),
        "leave_one_asset_out_all_positive": all(
            row["candidate_positive"]
            for row in asset_loo
        ),
        "leave_one_asset_out_all_beat_control": all(
            row["candidate_beats_control"]
            for row in asset_loo
        ),
        "leave_one_period_out_all_positive": all(
            row["candidate_positive"]
            for row in period_loo
        ),
        "leave_one_period_out_all_beat_control": all(
            row["candidate_beats_control"]
            for row in period_loo
        ),
        "all_cost_stress_totals_positive": all(
            row["candidate_total_pnl_usd"] > 0.0
            for row in stress
        ),
        "all_cost_stress_periods_positive": all(
            row["candidate_positive_period_count"]
            == row["period_count"]
            for row in stress
        ),
    }

    return {
        "experiment_id": EXPERIMENT_ID,
        "candidate_policy_id": (
            CANDIDATE_POLICY.policy_id
        ),
        "candidate_atr_floor": (
            CANDIDATE_POLICY.atr_floor
        ),
        "control_policy_id": (
            CONTROL_POLICY.policy_id
        ),
        "reserved_2026_outcomes_consumed": False,
        "decision": (
            "PASS"
            if all(rules.values())
            else "FAIL"
        ),
        "all_required_rules_passed": (
            all(rules.values())
        ),
        "rules": rules,
        "base_robustness": {
            "total_trade_count": (
                total_trades
            ),
            "insufficient_asset_periods": (
                insufficient
            ),
            "candidate_median_asset_period_drawdown_usd": (
                candidate_median_dd
            ),
            "control_median_asset_period_drawdown_usd": (
                control_median_dd
            ),
            "asset_periods_with_drawdown_deterioration_over_25_percent": (
                severe_dd
            ),
            "asset_delta_pnl_usd": (
                by_asset_delta
            ),
            "period_delta_pnl_usd": (
                by_period_delta
            ),
            "asset_positive_delta_concentration": (
                contribution_concentration(
                    list(
                        by_asset_delta.values()
                    )
                )
            ),
            "period_positive_delta_concentration": (
                contribution_concentration(
                    list(
                        by_period_delta.values()
                    )
                )
            ),
            "leave_one_asset_out": (
                asset_loo
            ),
            "leave_one_period_out": (
                period_loo
            ),
        },
        "cost_stress": stress,
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
        raise RobustnessError(
            f"Refusing to overwrite artifact: {path}"
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

    validate_contract()

    development = load_development_result()

    universe = load_universe_contract()

    if universe.get(
        "universe_id"
    ) != EXPECTED_UNIVERSE_ID:
        raise RobustnessError(
            "Universe ID mismatch."
        )

    if universe.get(
        "universe_fingerprint"
    ) != EXPECTED_UNIVERSE_FINGERPRINT:
        raise RobustnessError(
            "Universe fingerprint mismatch."
        )

    members = resolve_primary_members(
        universe
    )

    if tuple(
        str(member["symbol"])
        for member in members
    ) != PRIMARY_SYMBOLS:
        raise RobustnessError(
            "PRIMARY universe membership/order changed."
        )

    base_config = load_trading_config()

    plan = plan_payload(
        base_fee_bps=float(
            base_config.fee_bps
        ),
        base_slippage_bps=float(
            base_config.slippage_bps
        ),
    )

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
        raise RobustnessError(
            "Robustness output root already exists; "
            "refusing to overwrite or partially rerun: "
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

    member_by_symbol = {
        str(member["symbol"]): member
        for member in members
    }

    executions = []

    for scenario in COST_SCENARIOS:
        for period in PERIODS:
            for symbol in PRIMARY_SYMBOLS:
                member = member_by_symbol[
                    symbol
                ]

                for policy in POLICIES:
                    result = run_execution(
                        period=period,
                        policy=policy,
                        scenario=scenario,
                        symbol=symbol,
                        member=member,
                    )

                    executions.append(
                        result
                    )

                    execution_path = (
                        OUTPUT_ROOT
                        / "executions"
                        / (
                            f"{scenario.scenario_id}__"
                            f"{period.period_id}__"
                            f"{symbol.replace('/', '_')}__"
                            f"{policy.policy_id}.json"
                        )
                    )

                    write_json(
                        execution_path,
                        result,
                    )

    expected_count = (
        len(COST_SCENARIOS)
        * len(PERIODS)
        * len(PRIMARY_SYMBOLS)
        * len(POLICIES)
    )

    if len(executions) != expected_count:
        raise RobustnessError(
            "Stress execution count mismatch."
        )

    result = build_result(
        development=development,
        executions=executions,
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
