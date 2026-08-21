from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Callable

from files.backtest.replay import build_research_replay_plan
from files.config import load_trading_config
from files.data.paths import safe_tag
from files.research.historical_dataset import (
    build_historical_research_dataset,
    load_and_resolve_historical_research_source,
)
from files.research.run_adaptive_range_confirmation import (
    EXPECTED_2025_POLICY,
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
from files.research.scorer_campaign_builder import (
    build_default_campaign_specification,
)
from files.research.scorer_metrics import calculate_trial_metrics
from files.research.scorer_campaign_execution import (
    _remove_partial_backtest_outputs,
)
from files.research.scorer_trial import (
    TrialRunRequest,
    run_single_trial,
)


EXPERIMENT_ID = "adaptive_range_atr_development_v1"

OUTPUT_ROOT = Path(
    "data/processed/research/experiments"
) / EXPERIMENT_ID

TIMEFRAME_MINUTES = 5
TIMEFRAME_MS = TIMEFRAME_MINUTES * 60 * 1000

RANGE_FEATURE = "current_range_vs_prior_10_mean"
RANGE_THRESHOLD = 1.25

ATR_FEATURE = "atr_pct"

BASELINE_POLICY_ID = "range_v1_baseline"
RANGE_POLICY_ID = "range_v1_ge_1_25"

RESERVED_2026_START = "2026-01-01T00:00:00Z"

EPSILON = 1e-12


class AdaptiveRangeAtrDevelopmentError(RuntimeError):
    """Raised when the development experiment contract is violated."""


@dataclass(frozen=True)
class DevelopmentPeriod:
    period_id: str
    start_inclusive: str
    end_exclusive: str
    range_symbols: tuple[str, ...]


@dataclass(frozen=True)
class AtrPolicy:
    policy_id: str
    atr_floor: float | None


#
# Adaptive range schedule.
#
# 2023-H1:
#   No preceding OOS validation exists, so baseline is used for all assets.
#
# 2023-H2:
#   Selected from 2023-H1 range-minus-baseline PnL.
#
# 2024:
#   Selected from 2023-H2 range-minus-baseline PnL.
#
# 2025:
#   Selected from 2024 range-minus-baseline PnL and frozen before the
#   original 2025 confirmation.
#
PERIODS: tuple[DevelopmentPeriod, ...] = (
    DevelopmentPeriod(
        period_id="validate_2023_h1",
        start_inclusive="2023-01-01T00:00:00Z",
        end_exclusive="2023-07-01T00:00:00Z",
        range_symbols=(),
    ),
    DevelopmentPeriod(
        period_id="validate_2023_h2",
        start_inclusive="2023-07-01T00:00:00Z",
        end_exclusive="2024-01-01T00:00:00Z",
        range_symbols=(
            "BTC/USD",
            "ADA/USD",
            "XLM/USD",
            "LINK/USD",
            "DOGE/USD",
        ),
    ),
    DevelopmentPeriod(
        period_id="validate_2024",
        start_inclusive="2024-01-01T00:00:00Z",
        end_exclusive="2025-01-01T00:00:00Z",
        range_symbols=(
            "BTC/USD",
            "SOL/USD",
            "ADA/USD",
            "XLM/USD",
            "LINK/USD",
            "DOGE/USD",
        ),
    ),
    DevelopmentPeriod(
        period_id="validate_2025",
        start_inclusive="2025-01-01T00:00:00Z",
        end_exclusive=RESERVED_2026_START,
        range_symbols=(
            "BTC/USD",
            "SOL/USD",
            "ADA/USD",
            "XLM/USD",
            "LINK/USD",
        ),
    ),
)


#
# Deliberately small, predeclared ATR family.
#
# The exact 2025-optimal value is intentionally not included.
#
ATR_POLICIES: tuple[AtrPolicy, ...] = (
    AtrPolicy(
        policy_id="adaptive_range_control",
        atr_floor=None,
    ),
    AtrPolicy(
        policy_id="adaptive_range_atr_ge_0_005",
        atr_floor=0.005,
    ),
    AtrPolicy(
        policy_id="adaptive_range_atr_ge_0_006",
        atr_floor=0.006,
    ),
    AtrPolicy(
        policy_id="adaptive_range_atr_ge_0_007",
        atr_floor=0.007,
    ),
)


def utc_ms(text: str) -> int:
    value = datetime.fromisoformat(
        text.replace("Z", "+00:00")
    )

    if value.tzinfo is None:
        raise AdaptiveRangeAtrDevelopmentError(
            f"Timestamp must be timezone-aware: {text}"
        )

    return int(value.timestamp() * 1000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate universal signal-time ATR abstention on top of "
            "the previously established adaptive range policy across "
            "the 2023-H1, 2023-H2, 2024, and 2025 development windows."
        )
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
        help=(
            "Validate the experiment contract and print the execution "
            "plan without running backtests."
        ),
    )

    return parser


def validate_contract() -> None:
    if tuple(
        policy.policy_id
        for policy in ATR_POLICIES
    ) != (
        "adaptive_range_control",
        "adaptive_range_atr_ge_0_005",
        "adaptive_range_atr_ge_0_006",
        "adaptive_range_atr_ge_0_007",
    ):
        raise AdaptiveRangeAtrDevelopmentError(
            "ATR policy identity changed."
        )

    if tuple(
        policy.atr_floor
        for policy in ATR_POLICIES
    ) != (
        None,
        0.005,
        0.006,
        0.007,
    ):
        raise AdaptiveRangeAtrDevelopmentError(
            "ATR policy thresholds changed."
        )

    if RANGE_THRESHOLD != 1.25:
        raise AdaptiveRangeAtrDevelopmentError(
            "Validated range threshold changed."
        )

    if PERIODS[-1].end_exclusive != RESERVED_2026_START:
        raise AdaptiveRangeAtrDevelopmentError(
            "Development experiment boundary crossed into 2026."
        )

    expected_2025_from_schedule = {
        symbol: (
            RANGE_POLICY_ID
            if symbol in PERIODS[-1].range_symbols
            else BASELINE_POLICY_ID
        )
        for symbol in PRIMARY_SYMBOLS
    }

    if expected_2025_from_schedule != EXPECTED_2025_POLICY:
        raise AdaptiveRangeAtrDevelopmentError(
            "2025 adaptive schedule differs from frozen "
            "confirmation contract."
        )

    if (
        len(PRIMARY_SYMBOLS) != 8
        or len(set(PRIMARY_SYMBOLS)) != 8
    ):
        raise AdaptiveRangeAtrDevelopmentError(
            "PRIMARY universe membership changed."
        )

    for period in PERIODS:
        unknown = sorted(
            set(period.range_symbols)
            - set(PRIMARY_SYMBOLS)
        )

        if unknown:
            raise AdaptiveRangeAtrDevelopmentError(
                f"{period.period_id}: unknown range symbols: {unknown}"
            )

        start = utc_ms(period.start_inclusive)
        end = utc_ms(period.end_exclusive)

        if end <= start:
            raise AdaptiveRangeAtrDevelopmentError(
                f"{period.period_id}: invalid period boundaries."
            )

        if end > utc_ms(RESERVED_2026_START):
            raise AdaptiveRangeAtrDevelopmentError(
                f"{period.period_id}: period enters reserved 2026 data."
            )


def policy_payload(
    policy: AtrPolicy,
) -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "atr_feature": ATR_FEATURE,
        "atr_floor": policy.atr_floor,
        "range_feature": RANGE_FEATURE,
        "range_threshold": RANGE_THRESHOLD,
        "atr_applies_to_every_active_entry": (
            policy.atr_floor is not None
        ),
    }


def period_payload(
    period: DevelopmentPeriod,
) -> dict[str, Any]:
    return {
        "period_id": period.period_id,
        "start_inclusive": period.start_inclusive,
        "end_exclusive": period.end_exclusive,
        "adaptive_range_policy": {
            symbol: (
                RANGE_POLICY_ID
                if symbol in period.range_symbols
                else BASELINE_POLICY_ID
            )
            for symbol in PRIMARY_SYMBOLS
        },
    }


def plan_payload() -> dict[str, Any]:
    execution_count = (
        len(PERIODS)
        * len(ATR_POLICIES)
        * len(PRIMARY_SYMBOLS)
    )

    return {
        "experiment_id": EXPERIMENT_ID,
        "mode": "planned",
        "hypothesis": (
            "The existing adaptive-range strategy benefits from a "
            "universal point-in-time volatility abstention layer that "
            "requires sufficient signal-time ATR percentage."
        ),
        "range_policy": {
            "feature": RANGE_FEATURE,
            "threshold": RANGE_THRESHOLD,
            "selection_rule": (
                "Use range gate in a period only when the immediately "
                "preceding OOS validation period showed positive "
                "range-minus-baseline PnL for that asset."
            ),
        },
        "atr_policies": [
            policy_payload(policy)
            for policy in ATR_POLICIES
        ],
        "periods": [
            period_payload(period)
            for period in PERIODS
        ],
        "symbols": list(PRIMARY_SYMBOLS),
        "research_order_notional_usd": (
            RESEARCH_ORDER_NOTIONAL_USD
        ),
        "execution_count": execution_count,
        "reserved_2026_outcomes_consumed": False,
    }


def feature_value(
    *,
    latest: object,
    feature_name: str,
) -> float:
    try:
        if feature_name not in latest.index:
            raise KeyError(feature_name)

        value = float(latest[feature_name])
    except Exception as exc:
        raise AdaptiveRangeAtrDevelopmentError(
            f"Research feature unavailable or non-numeric: "
            f"{feature_name}"
        ) from exc

    if not math.isfinite(value):
        raise AdaptiveRangeAtrDevelopmentError(
            f"Research feature is non-finite: "
            f"{feature_name}={value!r}"
        )

    return value


def build_entry_gate(
    *,
    period: DevelopmentPeriod,
    symbol: str,
    policy: AtrPolicy,
) -> Callable[[object], tuple[bool, str]] | None:
    use_range = symbol in period.range_symbols
    atr_floor = policy.atr_floor

    if not use_range and atr_floor is None:
        return None

    def gate(
        features: object,
    ) -> tuple[bool, str]:
        try:
            latest = features.iloc[-1]
        except Exception as exc:
            raise AdaptiveRangeAtrDevelopmentError(
                "Research entry gate expected a pandas feature frame."
            ) from exc

        reasons: list[str] = []

        if use_range:
            range_value = feature_value(
                latest=latest,
                feature_name=RANGE_FEATURE,
            )

            if range_value < RANGE_THRESHOLD:
                return (
                    False,
                    (
                        f"{policy.policy_id}: "
                        f"{RANGE_FEATURE}={range_value:.12g} "
                        f"<{RANGE_THRESHOLD:.12g}"
                    ),
                )

            reasons.append(
                f"{RANGE_FEATURE}={range_value:.12g}"
                f">={RANGE_THRESHOLD:.12g}"
            )

        if atr_floor is not None:
            atr_value = feature_value(
                latest=latest,
                feature_name=ATR_FEATURE,
            )

            if atr_value < atr_floor:
                return (
                    False,
                    (
                        f"{policy.policy_id}: "
                        f"{ATR_FEATURE}={atr_value:.12g} "
                        f"<{atr_floor:.12g}"
                    ),
                )

            reasons.append(
                f"{ATR_FEATURE}={atr_value:.12g}"
                f">={atr_floor:.12g}"
            )

        return (
            True,
            f"{policy.policy_id}: " + "; ".join(reasons),
        )

    return gate


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
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}: timeframe is not 5m."
        )

    source = load_and_resolve_historical_research_source(
        data_tag=data_tag,
        expected_symbol=symbol,
        expected_timeframe=timeframe,
        manifest_path=manifest_path,
    )

    if source.symbol != symbol:
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}: resolved symbol mismatch."
        )

    if source.data_tag != data_tag:
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}: resolved data_tag mismatch."
        )

    if source.timeframe != timeframe:
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}: resolved timeframe mismatch."
        )

    if str(source.manifest_path) != str(manifest_path):
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}: manifest path mismatch."
        )

    trading_config = load_trading_config()

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

    research_policy_id = (
        f"{EXPERIMENT_ID}:"
        f"{period.period_id}:"
        f"{adaptive_range_role}:"
        f"{policy.policy_id}"
    )

    specification = build_default_campaign_specification(
        trading_config=member_config,
        trial_count=1,
        research_order_notional_usd=(
            RESEARCH_ORDER_NOTIONAL_USD
        ),
        research_entry_policy_id=research_policy_id,
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
        raise AdaptiveRangeAtrDevelopmentError(
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
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}/{period.period_id}: "
            "start boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms
        != inclusive_end_ts_ms
    ):
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}/{period.period_id}: "
            "inclusive end boundary drifted."
        )

    if (
        dataset.requested_range.requested_end_ts_ms_exclusive
        != end_exclusive_ts_ms
    ):
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}/{period.period_id}: "
            "end-exclusive boundary drifted."
        )

    replay_plan = build_research_replay_plan(
        dataset=dataset
    )

    trial = frozen_baseline_trial()

    if trial.trial_id != BASELINE_TRIAL_ID:
        raise AdaptiveRangeAtrDevelopmentError(
            "Frozen baseline trial changed."
        )

    gate = build_entry_gate(
        period=period,
        symbol=symbol,
        policy=policy,
    )

    symbol_storage = symbol.replace("/", "_")

    runid = (
        f"dev_{EXPERIMENT_ID}_"
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
        trades_csv=trial_result.backtest.trades_csv
    )

    if metrics.short_trade_count != 0:
        raise AdaptiveRangeAtrDevelopmentError(
            f"{symbol}/{period.period_id}/"
            f"{policy.policy_id}: SHORT trade detected."
        )

    return {
        "experiment_id": EXPERIMENT_ID,
        "period_id": period.period_id,
        "symbol": symbol,
        "policy_id": policy.policy_id,
        "atr_floor": policy.atr_floor,
        "adaptive_range_role": adaptive_range_role,
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
        "reserved_2026_outcomes_consumed": False,
    }


def aggregate_results(
    executions: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key = {
        (
            row["period_id"],
            row["symbol"],
            row["policy_id"],
        ): row
        for row in executions
    }

    expected_count = (
        len(PERIODS)
        * len(PRIMARY_SYMBOLS)
        * len(ATR_POLICIES)
    )

    if len(by_key) != expected_count:
        raise AdaptiveRangeAtrDevelopmentError(
            "Execution result count mismatch."
        )

    period_rows: list[dict[str, Any]] = []

    control_id = ATR_POLICIES[0].policy_id

    for period in PERIODS:
        control_by_symbol = {
            symbol: by_key[
                (
                    period.period_id,
                    symbol,
                    control_id,
                )
            ]
            for symbol in PRIMARY_SYMBOLS
        }

        for policy in ATR_POLICIES:
            asset_rows = []

            for symbol in PRIMARY_SYMBOLS:
                execution = by_key[
                    (
                        period.period_id,
                        symbol,
                        policy.policy_id,
                    )
                ]

                control = control_by_symbol[
                    symbol
                ]

                metrics = execution["metrics"]
                control_metrics = control["metrics"]

                pnl = float(
                    metrics["total_pnl_usd"]
                )
                control_pnl = float(
                    control_metrics["total_pnl_usd"]
                )

                drawdown = float(
                    metrics["maximum_drawdown_usd"]
                )

                control_drawdown = float(
                    control_metrics[
                        "maximum_drawdown_usd"
                    ]
                )

                asset_rows.append(
                    {
                        "symbol": symbol,
                        "adaptive_range_role": (
                            execution[
                                "adaptive_range_role"
                            ]
                        ),
                        "pnl_usd": pnl,
                        "control_pnl_usd": (
                            control_pnl
                        ),
                        "delta_pnl_usd": (
                            pnl - control_pnl
                        ),
                        "pnl_not_worse_than_control": (
                            pnl
                            >= control_pnl - EPSILON
                        ),
                        "trade_count": int(
                            metrics["trade_count"]
                        ),
                        "control_trade_count": int(
                            control_metrics[
                                "trade_count"
                            ]
                        ),
                        "maximum_drawdown_usd": (
                            drawdown
                        ),
                        "control_maximum_drawdown_usd": (
                            control_drawdown
                        ),
                    }
                )

            total_pnl = sum(
                row["pnl_usd"]
                for row in asset_rows
            )

            control_total_pnl = sum(
                row["control_pnl_usd"]
                for row in asset_rows
            )

            period_rows.append(
                {
                    "period_id": (
                        period.period_id
                    ),
                    "policy_id": (
                        policy.policy_id
                    ),
                    "atr_floor": (
                        policy.atr_floor
                    ),
                    "total_pnl_usd": (
                        total_pnl
                    ),
                    "control_total_pnl_usd": (
                        control_total_pnl
                    ),
                    "delta_pnl_usd": (
                        total_pnl
                        - control_total_pnl
                    ),
                    "total_trade_count": sum(
                        row["trade_count"]
                        for row in asset_rows
                    ),
                    "control_total_trade_count": sum(
                        row["control_trade_count"]
                        for row in asset_rows
                    ),
                    "positive_asset_count": sum(
                        row["pnl_usd"] > 0.0
                        for row in asset_rows
                    ),
                    "assets_not_worse_than_control": sum(
                        row[
                            "pnl_not_worse_than_control"
                        ]
                        for row in asset_rows
                    ),
                    "median_maximum_drawdown_usd": (
                        median(
                            row[
                                "maximum_drawdown_usd"
                            ]
                            for row in asset_rows
                        )
                    ),
                    "control_median_maximum_drawdown_usd": (
                        median(
                            row[
                                "control_maximum_drawdown_usd"
                            ]
                            for row in asset_rows
                        )
                    ),
                    "assets": asset_rows,
                }
            )

    overall_rows = []

    for policy in ATR_POLICIES:
        selected = [
            row
            for row in period_rows
            if row["policy_id"]
            == policy.policy_id
        ]

        all_execution_rows = [
            row
            for row in executions
            if row["policy_id"]
            == policy.policy_id
        ]

        total_pnl = sum(
            row["total_pnl_usd"]
            for row in selected
        )

        control_total_pnl = sum(
            row["control_total_pnl_usd"]
            for row in selected
        )

        overall_rows.append(
            {
                "policy_id": policy.policy_id,
                "atr_floor": policy.atr_floor,
                "development_total_pnl_usd": (
                    total_pnl
                ),
                "control_development_total_pnl_usd": (
                    control_total_pnl
                ),
                "delta_pnl_usd": (
                    total_pnl
                    - control_total_pnl
                ),
                "positive_period_count": sum(
                    row["total_pnl_usd"] > 0.0
                    for row in selected
                ),
                "period_count": len(selected),
                "worst_period_pnl_usd": min(
                    row["total_pnl_usd"]
                    for row in selected
                ),
                "total_trade_count": sum(
                    row["total_trade_count"]
                    for row in selected
                ),
                "median_asset_period_max_drawdown_usd": (
                    median(
                        float(
                            row["metrics"][
                                "maximum_drawdown_usd"
                            ]
                        )
                        for row in all_execution_rows
                    )
                ),
                "asset_periods_not_worse_than_control": sum(
                    asset[
                        "pnl_not_worse_than_control"
                    ]
                    for row in selected
                    for asset in row["assets"]
                ),
                "asset_period_count": (
                    len(PERIODS)
                    * len(PRIMARY_SYMBOLS)
                ),
            }
        )

    return {
        "experiment_id": EXPERIMENT_ID,
        "reserved_2026_outcomes_consumed": False,
        "period_results": period_rows,
        "overall_results": overall_rows,
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
        raise AdaptiveRangeAtrDevelopmentError(
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

    universe = load_universe_contract()

    if (
        universe.get("universe_id")
        != EXPECTED_UNIVERSE_ID
    ):
        raise AdaptiveRangeAtrDevelopmentError(
            "Universe ID mismatch."
        )

    if (
        universe.get("universe_fingerprint")
        != EXPECTED_UNIVERSE_FINGERPRINT
    ):
        raise AdaptiveRangeAtrDevelopmentError(
            "Universe fingerprint mismatch."
        )

    members = resolve_primary_members(
        universe
    )

    if tuple(
        str(member["symbol"])
        for member in members
    ) != PRIMARY_SYMBOLS:
        raise AdaptiveRangeAtrDevelopmentError(
            "PRIMARY universe membership/order changed."
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
        raise AdaptiveRangeAtrDevelopmentError(
            "Experiment output root already exists; "
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

    members_by_symbol = {
        str(member["symbol"]): member
        for member in members
    }

    executions: list[dict[str, Any]] = []

    for period in PERIODS:
        for policy in ATR_POLICIES:
            for symbol in PRIMARY_SYMBOLS:
                execution = run_execution(
                    period=period,
                    policy=policy,
                    symbol=symbol,
                    member=members_by_symbol[
                        symbol
                    ],
                )

                executions.append(
                    execution
                )

                write_json(
                    OUTPUT_ROOT
                    / "executions"
                    / period.period_id
                    / policy.policy_id
                    / (
                        f"{symbol.replace('/', '_')}"
                        ".json"
                    ),
                    execution,
                )

    result = aggregate_results(
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
