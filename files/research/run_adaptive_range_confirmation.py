from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
from typing import Any

from files.backtest.replay import build_research_replay_plan
from files.config import load_trading_config
from files.research.historical_dataset import (
    build_historical_research_dataset,
    load_and_resolve_historical_research_source,
)
from files.research.run_multi_asset_baseline import (
    BASELINE_TRIAL_ID,
    EXPECTED_UNIVERSE_FINGERPRINT,
    EXPECTED_UNIVERSE_ID,
    PRIMARY_SYMBOLS,
    RESEARCH_ORDER_NOTIONAL_USD,
    frozen_baseline_trial,
    load_universe_contract,
    resolve_primary_members,
)
from files.research.run_range_factor_profitability import (
    POLICIES,
    build_entry_gate,
)
from files.research.scorer_campaign_builder import (
    build_default_campaign_specification,
)
from files.research.scorer_metrics import calculate_trial_metrics
from files.research.scorer_trial import (
    TrialRunRequest,
    run_single_trial,
)


CONTRACT_PATH = Path(
    "files/research/contracts/"
    "range_factor_adaptive_confirmation_v1.json"
)

OUTPUT_ROOT = Path(
    "data/processed/research/confirmations/"
    "range_factor_adaptive_confirmation_v1"
)

CONTRACT_ID = "range_factor_adaptive_confirmation_v1"

CONFIRMATION_START = "2025-01-01T00:00:00Z"
CONFIRMATION_END_EXCLUSIVE = "2026-01-01T00:00:00Z"

TIMEFRAME_MINUTES = 5
TIMEFRAME_MS = TIMEFRAME_MINUTES * 60 * 1000

RANGE_POLICY_ID = "range_v1_ge_1_25"
BASELINE_POLICY_ID = "range_v1_baseline"

EXPECTED_2025_POLICY: dict[str, str] = {
    "BTC/USD": RANGE_POLICY_ID,
    "ETH/USD": BASELINE_POLICY_ID,
    "SOL/USD": RANGE_POLICY_ID,
    "ADA/USD": RANGE_POLICY_ID,
    "XLM/USD": RANGE_POLICY_ID,
    "LINK/USD": RANGE_POLICY_ID,
    "DOGE/USD": BASELINE_POLICY_ID,
    "LTC/USD": BASELINE_POLICY_ID,
}

MINIMUM_ASSETS_NOT_WORSE = 5
MAX_ASSETS_DRAWDOWN_DETERIORATION_OVER_25_PERCENT = 2

EPSILON = 1e-12


class ConfirmationError(RuntimeError):
    """Raised when the frozen confirmation contract is violated."""


def utc_ms(text: str) -> int:
    value = datetime.fromisoformat(
        text.replace("Z", "+00:00")
    )

    if value.tzinfo is None:
        raise ConfirmationError(
            f"Timestamp must be timezone-aware: {text}"
        )

    return int(value.timestamp() * 1000)


START_TS_MS = utc_ms(CONFIRMATION_START)
END_EXCLUSIVE_TS_MS = utc_ms(CONFIRMATION_END_EXCLUSIVE)
INCLUSIVE_END_TS_MS = END_EXCLUSIVE_TS_MS - TIMEFRAME_MS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the frozen one-shot 2025 adaptive-range "
            "confirmation against the frozen baseline."
        )
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Validate the frozen contracts and print the execution "
            "plan without loading historical bars or running backtests."
        ),
    )

    return parser


def load_confirmation_contract() -> dict[str, Any]:
    try:
        contract = json.loads(
            CONTRACT_PATH.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise ConfirmationError(
            f"Unable to load confirmation contract: {CONTRACT_PATH}"
        ) from exc

    if contract.get("contract_id") != CONTRACT_ID:
        raise ConfirmationError(
            "Confirmation contract ID mismatch."
        )

    if contract.get("status") != "frozen_before_confirmation":
        raise ConfirmationError(
            "Confirmation contract is not frozen."
        )

    window = contract.get("confirmation_window", {})

    if window.get("start_inclusive") != CONFIRMATION_START:
        raise ConfirmationError(
            "Confirmation start changed from frozen contract."
        )

    if (
        window.get("end_exclusive")
        != CONFIRMATION_END_EXCLUSIVE
    ):
        raise ConfirmationError(
            "Confirmation end changed from frozen contract."
        )

    reserve = contract.get(
        "reserved_unseen_window_after_confirmation",
        {},
    )

    if (
        reserve.get("start_inclusive")
        != CONFIRMATION_END_EXCLUSIVE
    ):
        raise ConfirmationError(
            "Reserved 2026 boundary changed."
        )

    if reserve.get("must_remain_unconsumed") is not True:
        raise ConfirmationError(
            "Reserved 2026 window is not marked protected."
        )

    universe = contract.get("universe", {})

    if universe.get("universe_id") != EXPECTED_UNIVERSE_ID:
        raise ConfirmationError(
            "Confirmation universe ID mismatch."
        )

    if (
        universe.get("universe_fingerprint")
        != EXPECTED_UNIVERSE_FINGERPRINT
    ):
        raise ConfirmationError(
            "Confirmation universe fingerprint mismatch."
        )

    if tuple(universe.get("symbols", ())) != PRIMARY_SYMBOLS:
        raise ConfirmationError(
            "Confirmation PRIMARY symbol order/membership changed."
        )

    baseline = contract.get("baseline", {})

    if baseline.get("trial_id") != BASELINE_TRIAL_ID:
        raise ConfirmationError(
            "Frozen baseline trial ID mismatch."
        )

    if (
        float(baseline.get("research_order_notional_usd"))
        != RESEARCH_ORDER_NOTIONAL_USD
    ):
        raise ConfirmationError(
            "Frozen research notional mismatch."
        )

    candidate = contract.get("candidate", {})

    if candidate.get("gate_threshold") != 1.25:
        raise ConfirmationError(
            "Frozen range threshold mismatch."
        )

    if (
        candidate.get("selection_evidence_cutoff")
        != CONFIRMATION_START
    ):
        raise ConfirmationError(
            "Candidate selection cutoff mismatch."
        )

    if (
        candidate.get("frozen_2025_asset_policy")
        != EXPECTED_2025_POLICY
    ):
        raise ConfirmationError(
            "Frozen 2025 asset-policy map mismatch."
        )

    rules = contract.get("confirmation_rules", {})

    expected_rules = {
        "all_required": True,
        "candidate_total_pnl_must_be_positive": True,
        "candidate_total_pnl_must_exceed_baseline": True,
        "minimum_assets_not_worse_than_baseline_pnl": 5,
        "asset_count": 8,
        "median_candidate_max_drawdown_must_not_exceed_baseline": True,
        "maximum_assets_with_drawdown_deterioration_over_25_percent": 2,
    }

    if rules != expected_rules:
        raise ConfirmationError(
            "Frozen confirmation rules changed."
        )

    return contract


def range_policy():
    matches = [
        policy
        for policy in POLICIES
        if policy.policy_id == RANGE_POLICY_ID
    ]

    if len(matches) != 1:
        raise ConfirmationError(
            "Unable to resolve the frozen 1.25 range policy."
        )

    policy = matches[0]

    if policy.minimum_ratio != 1.25:
        raise ConfirmationError(
            "Resolved range policy threshold is not 1.25."
        )

    return policy


def plan_payload(
    *,
    members: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    executions = []

    for member in members:
        symbol = str(member["symbol"])
        selected_policy = EXPECTED_2025_POLICY[symbol]

        executions.append(
            {
                "symbol": symbol,
                "role": "baseline",
                "policy_id": BASELINE_POLICY_ID,
            }
        )

        if selected_policy == RANGE_POLICY_ID:
            executions.append(
                {
                    "symbol": symbol,
                    "role": "candidate_range",
                    "policy_id": RANGE_POLICY_ID,
                }
            )

    return {
        "contract_id": CONTRACT_ID,
        "mode": "planned",
        "confirmation_start_inclusive": CONFIRMATION_START,
        "confirmation_end_exclusive": (
            CONFIRMATION_END_EXCLUSIVE
        ),
        "reserved_2026_outcomes_consumed": False,
        "symbols": list(PRIMARY_SYMBOLS),
        "baseline_execution_count": 8,
        "candidate_range_execution_count": 5,
        "actual_backtest_execution_count": len(executions),
        "candidate_asset_policy": dict(
            EXPECTED_2025_POLICY
        ),
        "executions": executions,
    }


def run_execution(
    *,
    symbol: str,
    member: dict[str, Any],
    role: str,
    use_range_gate: bool,
) -> dict[str, Any]:
    data_tag = str(member["data_tag"])
    timeframe = str(member["timeframe"])
    manifest_path = Path(str(member["manifest_path"]))

    if timeframe != "5m":
        raise ConfirmationError(
            f"{symbol}: timeframe is not frozen at 5m."
        )

    source = load_and_resolve_historical_research_source(
        data_tag=data_tag,
        expected_symbol=symbol,
        expected_timeframe=timeframe,
        manifest_path=manifest_path,
    )

    if source.symbol != symbol:
        raise ConfirmationError(
            f"{symbol}: resolved source symbol mismatch."
        )

    if source.data_tag != data_tag:
        raise ConfirmationError(
            f"{symbol}: resolved source data_tag mismatch."
        )

    if source.timeframe != timeframe:
        raise ConfirmationError(
            f"{symbol}: resolved source timeframe mismatch."
        )

    if str(source.manifest_path) != str(manifest_path):
        raise ConfirmationError(
            f"{symbol}: resolved manifest path mismatch."
        )

    trading_config = load_trading_config()

    member_config = replace(
        trading_config,
        symbol=symbol,
        data_tag=data_tag,
        timeframe=timeframe,
        dry_run=True,
    )

    specification = build_default_campaign_specification(
        trading_config=member_config,
        trial_count=1,
        research_order_notional_usd=(
            RESEARCH_ORDER_NOTIONAL_USD
        ),
        research_entry_policy_id=(
            RANGE_POLICY_ID
            if use_range_gate
            else BASELINE_POLICY_ID
        ),
    )

    dataset = build_historical_research_dataset(
        audit=source.audit,
        start_ts_ms=START_TS_MS,
        end_ts_ms=INCLUSIVE_END_TS_MS,
        warmup_bars=max(
            int(specification.min_bars),
            50,
        )
        + 5,
    )

    if (
        dataset.requested_range.requested_start_ts_ms
        != START_TS_MS
    ):
        raise ConfirmationError(
            f"{symbol}: replay start boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms
        != INCLUSIVE_END_TS_MS
    ):
        raise ConfirmationError(
            f"{symbol}: replay end boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms_exclusive
        != END_EXCLUSIVE_TS_MS
    ):
        raise ConfirmationError(
            f"{symbol}: replay crossed into reserved 2026."
        )

    replay_plan = build_research_replay_plan(
        dataset=dataset
    )

    trial = frozen_baseline_trial()

    if trial.trial_id != BASELINE_TRIAL_ID:
        raise ConfirmationError(
            "Baseline trial changed during execution."
        )

    gate = (
        build_entry_gate(range_policy())
        if use_range_gate
        else None
    )

    symbol_storage = symbol.replace("/", "_")

    runid = (
        f"confirm_2025_{CONTRACT_ID}_"
        f"{symbol_storage}_{role}"
    )

    trial_result = run_single_trial(
        TrialRunRequest(
            trial=trial,
            runid=runid,
            trading_config=member_config,
            scorer_contract=specification.scorer_contract,
            start_ts_ms=START_TS_MS,
            end_ts_ms=INCLUSIVE_END_TS_MS,
            replay_plan=replay_plan,
            research_order_notional_usd=(
                RESEARCH_ORDER_NOTIONAL_USD
            ),
            research_entry_gate=gate,
        )
    )

    metrics = calculate_trial_metrics(
        trades_csv=trial_result.backtest.trades_csv
    )

    if metrics.short_trade_count != 0:
        raise ConfirmationError(
            f"{symbol}/{role}: SHORT trade detected."
        )

    return {
        "symbol": symbol,
        "role": role,
        "policy_id": (
            RANGE_POLICY_ID
            if use_range_gate
            else BASELINE_POLICY_ID
        ),
        "runid": runid,
        "source": {
            "data_tag": source.data_tag,
            "timeframe": source.timeframe,
            "manifest_path": str(source.manifest_path),
            "manifest_fingerprint": (
                source.manifest_fingerprint
            ),
        },
        "replay": {
            "start_ts_ms": START_TS_MS,
            "inclusive_end_ts_ms": INCLUSIVE_END_TS_MS,
            "end_exclusive_ts_ms": END_EXCLUSIVE_TS_MS,
            "replay_bar_count": dataset.replay_bar_count,
            "physical_segment_count": len(
                dataset.segments
            ),
        },
        "metrics": metrics.as_dict(),
    }


def evaluate_confirmation(
    *,
    execution_results: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key = {
        (row["symbol"], row["role"]): row
        for row in execution_results
    }

    asset_rows: list[dict[str, Any]] = []

    for symbol in PRIMARY_SYMBOLS:
        baseline = by_key.get((symbol, "baseline"))

        if baseline is None:
            raise ConfirmationError(
                f"Missing baseline execution: {symbol}"
            )

        selected_policy = EXPECTED_2025_POLICY[symbol]

        if selected_policy == RANGE_POLICY_ID:
            candidate = by_key.get(
                (symbol, "candidate_range")
            )

            if candidate is None:
                raise ConfirmationError(
                    f"Missing candidate range execution: {symbol}"
                )
        else:
            candidate = baseline

        baseline_metrics = baseline["metrics"]
        candidate_metrics = candidate["metrics"]

        baseline_pnl = float(
            baseline_metrics["total_pnl_usd"]
        )
        candidate_pnl = float(
            candidate_metrics["total_pnl_usd"]
        )

        baseline_dd = float(
            baseline_metrics["maximum_drawdown_usd"]
        )
        candidate_dd = float(
            candidate_metrics["maximum_drawdown_usd"]
        )

        pnl_delta = candidate_pnl - baseline_pnl
        dd_delta = candidate_dd - baseline_dd

        if baseline_dd <= EPSILON:
            dd_deterioration_over_25 = (
                candidate_dd > baseline_dd + EPSILON
            )
        else:
            dd_deterioration_over_25 = (
                candidate_dd
                > baseline_dd * 1.25 + EPSILON
            )

        asset_rows.append(
            {
                "symbol": symbol,
                "selected_policy": selected_policy,
                "baseline_pnl_usd": baseline_pnl,
                "candidate_pnl_usd": candidate_pnl,
                "pnl_delta_usd": pnl_delta,
                "pnl_not_worse": (
                    candidate_pnl
                    >= baseline_pnl - EPSILON
                ),
                "baseline_max_drawdown_usd": baseline_dd,
                "candidate_max_drawdown_usd": candidate_dd,
                "drawdown_delta_usd": dd_delta,
                "drawdown_deterioration_over_25_percent": (
                    dd_deterioration_over_25
                ),
                "baseline_trade_count": int(
                    baseline_metrics["trade_count"]
                ),
                "candidate_trade_count": int(
                    candidate_metrics["trade_count"]
                ),
            }
        )

    baseline_total_pnl = sum(
        row["baseline_pnl_usd"]
        for row in asset_rows
    )

    candidate_total_pnl = sum(
        row["candidate_pnl_usd"]
        for row in asset_rows
    )

    assets_not_worse = sum(
        1
        for row in asset_rows
        if row["pnl_not_worse"]
    )

    baseline_median_dd = median(
        row["baseline_max_drawdown_usd"]
        for row in asset_rows
    )

    candidate_median_dd = median(
        row["candidate_max_drawdown_usd"]
        for row in asset_rows
    )

    severe_dd_deteriorations = sum(
        1
        for row in asset_rows
        if row[
            "drawdown_deterioration_over_25_percent"
        ]
    )

    rules = {
        "candidate_total_pnl_positive": (
            candidate_total_pnl > 0.0
        ),
        "candidate_total_pnl_exceeds_baseline": (
            candidate_total_pnl
            > baseline_total_pnl + EPSILON
        ),
        "minimum_5_of_8_assets_not_worse": (
            assets_not_worse
            >= MINIMUM_ASSETS_NOT_WORSE
        ),
        "median_max_drawdown_not_worse": (
            candidate_median_dd
            <= baseline_median_dd + EPSILON
        ),
        "maximum_2_assets_over_25pct_dd_deterioration": (
            severe_dd_deteriorations
            <= MAX_ASSETS_DRAWDOWN_DETERIORATION_OVER_25_PERCENT
        ),
    }

    passed = all(rules.values())

    return {
        "contract_id": CONTRACT_ID,
        "confirmation_window": {
            "start_inclusive": CONFIRMATION_START,
            "end_exclusive": CONFIRMATION_END_EXCLUSIVE,
        },
        "reserved_2026_outcomes_consumed": False,
        "decision": (
            "PASS"
            if passed
            else "FAIL"
        ),
        "all_required_rules_passed": passed,
        "rules": rules,
        "aggregate": {
            "baseline_total_pnl_usd": baseline_total_pnl,
            "candidate_total_pnl_usd": candidate_total_pnl,
            "candidate_delta_pnl_usd": (
                candidate_total_pnl
                - baseline_total_pnl
            ),
            "candidate_improvement_percent": (
                (
                    candidate_total_pnl
                    - baseline_total_pnl
                )
                / abs(baseline_total_pnl)
                * 100.0
                if abs(baseline_total_pnl) > EPSILON
                else None
            ),
            "assets_not_worse_than_baseline": (
                assets_not_worse
            ),
            "asset_count": len(asset_rows),
            "baseline_median_max_drawdown_usd": (
                baseline_median_dd
            ),
            "candidate_median_max_drawdown_usd": (
                candidate_median_dd
            ),
            "assets_with_drawdown_deterioration_over_25_percent": (
                severe_dd_deteriorations
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
        raise ConfirmationError(
            f"Refusing to overwrite confirmation artifact: {path}"
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

    load_confirmation_contract()

    universe = load_universe_contract()
    members = resolve_primary_members(universe)

    if tuple(
        str(member["symbol"])
        for member in members
    ) != PRIMARY_SYMBOLS:
        raise ConfirmationError(
            "Resolved PRIMARY universe changed."
        )

    plan = plan_payload(
        members=members
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
        raise ConfirmationError(
            "Confirmation output root already exists; "
            "refusing a second one-shot execution: "
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

    members_by_symbol = {
        str(member["symbol"]): member
        for member in members
    }

    execution_results: list[dict[str, Any]] = []

    for symbol in PRIMARY_SYMBOLS:
        member = members_by_symbol[symbol]

        baseline = run_execution(
            symbol=symbol,
            member=member,
            role="baseline",
            use_range_gate=False,
        )

        execution_results.append(
            baseline
        )

        write_json(
            OUTPUT_ROOT
            / "executions"
            / f"{symbol.replace('/', '_')}_baseline.json",
            baseline,
        )

        if (
            EXPECTED_2025_POLICY[symbol]
            == RANGE_POLICY_ID
        ):
            candidate = run_execution(
                symbol=symbol,
                member=member,
                role="candidate_range",
                use_range_gate=True,
            )

            execution_results.append(
                candidate
            )

            write_json(
                OUTPUT_ROOT
                / "executions"
                / (
                    f"{symbol.replace('/', '_')}"
                    "_candidate_range.json"
                ),
                candidate,
            )

    result = evaluate_confirmation(
        execution_results=execution_results
    )

    write_json(
        OUTPUT_ROOT / "confirmation_result.json",
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
