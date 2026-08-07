from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any

from files.config import load_trading_config
from files.data.paths import safe_symbol
from files.research.scorer_campaign_io import (
    canonical_json_text,
    write_json_atomic,
    write_json_immutable,
)
from files.research.scorer_metrics import (
    calculate_trial_metrics,
)
from files.research.scorer_parameter_space import (
    ScorerTrial,
)
from files.research.scorer_trial import (
    TrialRunRequest,
    run_single_trial,
)
from files.strategy.rules import EarlyFailureConfig


REPLAY_SCHEMA_VERSION = 1
REPLAY_TYPE = "engine_early_failure_policy_replay_v1"

POLICY_DEFINITIONS: tuple[
    tuple[bool, int, float], ...
] = (
    (False, 3, 0.10),
    (True, 2, 0.05),
    (True, 2, 0.075),
    (True, 2, 0.10),
    (True, 3, 0.05),
    (True, 3, 0.075),
    (True, 3, 0.10),
    (True, 4, 0.05),
    (True, 4, 0.075),
    (True, 4, 0.10),
)


class EarlyFailureReplayError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise EarlyFailureReplayError(
            f"Unable to read JSON object: {path}"
        ) from exc

    if not isinstance(value, dict):
        raise EarlyFailureReplayError(
            f"JSON artifact must contain an object: {path}"
        )

    return value


def _policy_payload(
    *,
    enabled: bool,
    checkpoint_bars: int,
    mfe_threshold_r: float,
) -> dict[str, Any]:
    config = EarlyFailureConfig(
        enabled=enabled,
        checkpoint_bars=checkpoint_bars,
        mfe_threshold_r=mfe_threshold_r,
    )

    return {
        "enabled": bool(config.enabled),
        "checkpoint_bars": int(
            config.checkpoint_bars
        ),
        "mfe_threshold_r": float(
            config.mfe_threshold_r
        ),
    }


def _policy_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        canonical_json_text(payload).encode("utf-8")
    ).hexdigest()

    if not payload["enabled"]:
        return f"policy_disabled_{digest[:12]}"

    checkpoint = int(payload["checkpoint_bars"])
    threshold_text = (
        str(payload["mfe_threshold_r"])
        .replace(".", "p")
    )

    return (
        f"policy_cp{checkpoint}_"
        f"mfe{threshold_text}_{digest[:12]}"
    )


def _read_trade_rows(
    path: Path,
) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        return list(csv.DictReader(handle))


def _as_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0

    if parsed != parsed:
        return 0.0

    return parsed


def _extra_trade_metrics(
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    exit_reasons = [
        str(row.get("exit_reason", "")).strip()
        for row in rows
    ]

    pnl_values = [
        _as_float(row.get("realized_pnl_usd"))
        for row in rows
    ]

    cost_values = [
        _as_float(row.get("cost_usd"))
        for row in rows
    ]

    total_pnl = float(sum(pnl_values))
    best_trade = max(pnl_values, default=0.0)
    pnl_without_best = (
        total_pnl - best_trade
        if pnl_values
        else 0.0
    )

    positive_pnl = sum(
        value
        for value in pnl_values
        if value > 0.0
    )

    best_trade_share_of_positive_pnl = (
        best_trade / positive_pnl
        if positive_pnl > 0.0
        else 0.0
    )

    return {
        "early_failure_exit_count": sum(
            reason == "early_failure"
            for reason in exit_reasons
        ),
        "stop_hit_count": sum(
            reason == "stop_hit"
            for reason in exit_reasons
        ),
        "time_stop_count": sum(
            reason == "time_stop"
            for reason in exit_reasons
        ),
        "total_cost_usd": float(
            sum(cost_values)
        ),
        "pnl_without_best_trade_usd": float(
            pnl_without_best
        ),
        "best_trade_share_of_positive_pnl": float(
            best_trade_share_of_positive_pnl
        ),
    }


def _build_policies() -> tuple[
    dict[str, Any], ...
]:
    policies: list[dict[str, Any]] = []

    for enabled, checkpoint, threshold in (
        POLICY_DEFINITIONS
    ):
        payload = _policy_payload(
            enabled=enabled,
            checkpoint_bars=checkpoint,
            mfe_threshold_r=threshold,
        )

        policies.append(
            {
                "policy_id": _policy_id(payload),
                **payload,
            }
        )

    ids = [
        policy["policy_id"]
        for policy in policies
    ]

    if len(ids) != len(set(ids)):
        raise EarlyFailureReplayError(
            "Policy IDs must be unique."
        )

    if len(policies) != 10:
        raise EarlyFailureReplayError(
            "Fixed replay must contain exactly "
            "one baseline and nine enabled policies."
        )

    return tuple(policies)


def _build_replay_identity(
    *,
    campaign_id: str,
    trial_id: str,
    manifest_fingerprint: str,
    execution_ids: list[str],
    policies: tuple[dict[str, Any], ...],
) -> tuple[str, dict[str, Any]]:
    payload = {
        "replay_schema_version": (
            REPLAY_SCHEMA_VERSION
        ),
        "replay_type": REPLAY_TYPE,
        "campaign_id": campaign_id,
        "trial_id": trial_id,
        "manifest_fingerprint": (
            manifest_fingerprint
        ),
        "execution_ids": execution_ids,
        "policies": list(policies),
    }

    digest = hashlib.sha256(
        canonical_json_text(payload).encode("utf-8")
    ).hexdigest()

    return (
        f"early_failure_replay_{digest[:16]}",
        payload,
    )


def _result_path(
    *,
    output_root: Path,
    policy_id: str,
    execution_id: str,
) -> Path:
    return (
        output_root
        / "results"
        / policy_id
        / execution_id
        / "result.json"
    )


def _existing_result(
    *,
    path: Path,
    replay_id: str,
    policy_id: str,
    execution_id: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None

    payload = _load_json(path)

    expected = {
        "replay_id": replay_id,
        "policy_id": policy_id,
        "execution_id": execution_id,
        "status": "succeeded",
    }

    for key, value in expected.items():
        if payload.get(key) != value:
            raise EarlyFailureReplayError(
                "Existing result identity conflict: "
                f"{path}"
            )

    return payload


def _assert_clean_execution_paths(
    *,
    run_id: str,
    data_tag: str,
    symbol_storage: str,
    timeframe: str,
) -> None:
    exchange = f"{data_tag}_bt_{run_id}"

    paths = (
        Path("data/processed/decisions")
        / exchange
        / symbol_storage
        / timeframe
        / "decisions.csv",
        Path("data/processed/trades")
        / exchange
        / symbol_storage
        / timeframe
        / "trades.csv",
    )

    existing = [
        str(path)
        for path in paths
        if path.exists()
    ]

    if existing:
        raise EarlyFailureReplayError(
            "Execution artifacts already exist without "
            "a successful immutable result. Refusing "
            f"unsafe resume: {existing}"
        )


def _aggregate(
    *,
    replay_id: str,
    policies: tuple[dict[str, Any], ...],
    executions: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    by_policy: list[dict[str, Any]] = []

    for policy in policies:
        policy_results = [
            result
            for result in results
            if result["policy_id"]
            == policy["policy_id"]
        ]

        if len(policy_results) != len(executions):
            raise EarlyFailureReplayError(
                "Policy result count is incomplete: "
                f"{policy['policy_id']}"
            )

        fold_pnl = {
            result["split_name"]: float(
                result["metrics"][
                    "total_pnl_usd"
                ]
            )
            for result in policy_results
        }

        fold_drawdown = {
            result["split_name"]: float(
                result["metrics"][
                    "maximum_drawdown_usd"
                ]
            )
            for result in policy_results
        }

        total_pnl = float(sum(
            fold_pnl.values()
        ))

        total_trades = sum(
            int(result["metrics"]["trade_count"])
            for result in policy_results
        )

        total_early_failure = sum(
            int(
                result["extra_metrics"][
                    "early_failure_exit_count"
                ]
            )
            for result in policy_results
        )

        total_stops = sum(
            int(
                result["extra_metrics"][
                    "stop_hit_count"
                ]
            )
            for result in policy_results
        )

        total_time_stops = sum(
            int(
                result["extra_metrics"][
                    "time_stop_count"
                ]
            )
            for result in policy_results
        )

        total_cost = float(sum(
            float(
                result["extra_metrics"][
                    "total_cost_usd"
                ]
            )
            for result in policy_results
        ))

        by_policy.append(
            {
                **policy,
                "fold_pnl_usd": fold_pnl,
                "fold_maximum_drawdown_usd": (
                    fold_drawdown
                ),
                "total_validation_pnl_usd": (
                    total_pnl
                ),
                "worst_validation_fold_pnl_usd": (
                    min(fold_pnl.values())
                ),
                "positive_fold_count": sum(
                    value > 0.0
                    for value in fold_pnl.values()
                ),
                "maximum_fold_drawdown_usd": (
                    max(fold_drawdown.values())
                ),
                "total_trade_count": total_trades,
                "early_failure_exit_count": (
                    total_early_failure
                ),
                "stop_hit_count": total_stops,
                "time_stop_count": total_time_stops,
                "total_cost_usd": total_cost,
                "short_trade_count": sum(
                    int(
                        result["metrics"][
                            "short_trade_count"
                        ]
                    )
                    for result in policy_results
                ),
                "fold_pnl_without_best_trade_usd": {
                    result["split_name"]: float(
                        result["extra_metrics"][
                            "pnl_without_best_trade_usd"
                        ]
                    )
                    for result in policy_results
                },
            }
        )

    return {
        "replay_schema_version": (
            REPLAY_SCHEMA_VERSION
        ),
        "replay_type": REPLAY_TYPE,
        "replay_id": replay_id,
        "status": "complete",
        "policy_count": len(policies),
        "execution_count": len(results),
        "policies": by_policy,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed engine-level early-failure "
            "baseline plus 3x3 policy grid."
        )
    )

    parser.add_argument(
        "--campaign-id",
        required=True,
    )
    parser.add_argument(
        "--trial-id",
        required=True,
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    campaign_root = (
        Path(
            "data/processed/research/"
            "scorer_campaigns"
        )
        / args.campaign_id
    )

    manifest = _load_json(
        campaign_root / "campaign_manifest.json"
    )
    plan = _load_json(
        campaign_root / "execution_plan.json"
    )

    specification = manifest["specification"]

    executions = [
        execution
        for execution in plan["executions"]
        if execution["trial_id"] == args.trial_id
        and execution["window_role"]
        == "validation"
        and execution["cost_scenario_id"]
        == "base"
    ]

    executions.sort(
        key=lambda item: (
            int(item["start_ts_ms"]),
            item["execution_id"],
        )
    )

    if len(executions) != 3:
        raise EarlyFailureReplayError(
            "Expected exactly three canonical "
            "base-cost validation executions; "
            f"found {len(executions)}"
        )

    policies = _build_policies()

    replay_id, identity_payload = (
        _build_replay_identity(
            campaign_id=args.campaign_id,
            trial_id=args.trial_id,
            manifest_fingerprint=(
                manifest["manifest_fingerprint"]
            ),
            execution_ids=[
                execution["execution_id"]
                for execution in executions
            ],
            policies=policies,
        )
    )

    output_root = (
        campaign_root
        / "diagnostics"
        / "early_failure_engine_replay"
        / args.trial_id
        / replay_id
    )

    plan_payload = {
        **identity_payload,
        "replay_id": replay_id,
        "output_root": str(output_root),
        "execution_count": (
            len(executions) * len(policies)
        ),
        "executions": executions,
    }

    write_json_immutable(
        path=output_root / "replay_plan.json",
        value=plan_payload,
    )

    print(
        json.dumps(
            {
                "replay_id": replay_id,
                "output_root": str(output_root),
                "policy_count": len(policies),
                "fold_count": len(executions),
                "execution_count": (
                    len(policies) * len(executions)
                ),
                "policies": list(policies),
            },
            indent=2,
            sort_keys=True,
        )
    )

    if args.plan_only:
        return

    base_cfg = load_trading_config()
    results: list[dict[str, Any]] = []

    symbol_storage = safe_symbol(
        str(specification["symbol"])
    )

    for policy in policies:
        config = EarlyFailureConfig(
            enabled=bool(policy["enabled"]),
            checkpoint_bars=int(
                policy["checkpoint_bars"]
            ),
            mfe_threshold_r=float(
                policy["mfe_threshold_r"]
            ),
        )

        for execution in executions:
            result_path = _result_path(
                output_root=output_root,
                policy_id=policy["policy_id"],
                execution_id=(
                    execution["execution_id"]
                ),
            )

            existing = _existing_result(
                path=result_path,
                replay_id=replay_id,
                policy_id=policy["policy_id"],
                execution_id=(
                    execution["execution_id"]
                ),
            )

            if existing is not None:
                print(
                    "RESUME: "
                    f"{policy['policy_id']} "
                    f"{execution['split_name']}"
                )
                results.append(existing)
                continue

            canonical_result = _load_json(
                campaign_root
                / "trials"
                / execution["execution_id"]
                / "result.json"
            )

            trial_payload = canonical_result["trial"]
            cost = canonical_result["cost_scenario"]

            trial = ScorerTrial(
                trial_id=trial_payload["trial_id"],
                parameters={
                    key: float(value)
                    for key, value
                    in trial_payload[
                        "parameters"
                    ].items()
                },
            )

            cfg = replace(
                base_cfg,
                symbol=specification["symbol"],
                timeframe=(
                    specification["timeframe"]
                ),
                data_tag=(
                    specification["data_tag"]
                ),
                min_bars=int(
                    specification["min_bars"]
                ),
                cooldown_bars=int(
                    specification["cooldown_bars"]
                ),
                max_order_size=float(
                    specification[
                        "max_order_size"
                    ]
                ),
                fee_bps=float(cost["fee_bps"]),
                slippage_bps=float(
                    cost["slippage_bps"]
                ),
                dry_run=True,
            )

            replay_suffix = replay_id.removeprefix(
                "early_failure_replay_"
            )
            policy_suffix = policy[
                "policy_id"
            ].split("_")[-1]
            execution_suffix = execution[
                "execution_id"
            ].removeprefix("execution_")

            run_id = (
                f"ef_{replay_suffix}_"
                f"{policy_suffix}_"
                f"{execution_suffix}"
            )

            _assert_clean_execution_paths(
                run_id=run_id,
                data_tag=cfg.data_tag,
                symbol_storage=symbol_storage,
                timeframe=cfg.timeframe,
            )

            print(
                "RUN: "
                f"{policy['policy_id']} "
                f"{execution['split_name']} "
                f"run_id={run_id}"
            )

            trial_result = run_single_trial(
                TrialRunRequest(
                    trial=trial,
                    runid=run_id,
                    trading_config=cfg,
                    start_ts_ms=int(
                        execution["start_ts_ms"]
                    ),
                    end_ts_ms=int(
                        execution[
                            "inclusive_backtest_end_ts_ms"
                        ]
                    ),
                    early_failure_config=config,
                )
            )

            metrics = calculate_trial_metrics(
                trades_csv=(
                    trial_result.backtest.trades_csv
                )
            )

            if metrics.short_trade_count != 0:
                raise EarlyFailureReplayError(
                    "SHORT trade detected: "
                    f"{policy['policy_id']} "
                    f"{execution['split_name']}"
                )

            trade_rows = _read_trade_rows(
                Path(
                    trial_result.backtest.trades_csv
                )
            )

            result = {
                "replay_id": replay_id,
                "policy_id": policy["policy_id"],
                "execution_id": (
                    execution["execution_id"]
                ),
                "status": "succeeded",
                "split_name": (
                    execution["split_name"]
                ),
                "policy": policy,
                "run_id": run_id,
                "source_execution": execution,
                "backtest": (
                    trial_result.as_dict()
                ),
                "metrics": metrics.as_dict(),
                "extra_metrics": (
                    _extra_trade_metrics(
                        trade_rows
                    )
                ),
            }

            write_json_immutable(
                path=result_path,
                value=result,
            )

            results.append(result)

            print(
                "PASS: "
                f"{policy['policy_id']} "
                f"{execution['split_name']} "
                f"pnl={metrics.total_pnl_usd:.6f} "
                f"trades={metrics.trade_count}"
            )

    summary = _aggregate(
        replay_id=replay_id,
        policies=policies,
        executions=executions,
        results=results,
    )

    write_json_atomic(
        path=output_root / "summary.json",
        value=summary,
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
