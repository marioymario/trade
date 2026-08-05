from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from files.research.scorer_campaign_builder import (
    InitializedScorerCampaign,
)
from files.research.scorer_campaign_io import (
    write_csv_atomic,
    write_json_atomic,
)


FOLD_RESULT_FIELDS = (
    "campaign_id",
    "execution_id",
    "execution_index",
    "trial_id",
    "split_name",
    "window_role",
    "cost_scenario_id",
    "run_id",
    "status",
    "trade_count",
    "winning_trades",
    "losing_trades",
    "breakeven_trades",
    "win_rate",
    "total_pnl_usd",
    "average_pnl_usd",
    "best_trade_pnl_usd",
    "worst_trade_pnl_usd",
    "maximum_drawdown_usd",
    "stop_hit_count",
    "stop_hit_rate",
    "time_stop_count",
    "long_trade_count",
    "short_trade_count",
    "first_exit_ts_ms",
    "last_exit_ts_ms",
    "decisions_csv",
    "trades_csv",
    "research_execution_events_csv",
)

CANDIDATE_RESULT_FIELDS = (
    "campaign_id",
    "trial_id",
    "disposition",
    "rank",
    "rejection_reason_count",
    "total_train_trades",
    "total_validation_trades",
    "total_validation_pnl_usd",
    "worst_validation_fold_pnl_usd",
    "average_validation_pnl_usd",
    "maximum_validation_drawdown_usd",
    "positive_validation_fold_count",
    "negative_validation_fold_count",
    "validation_fold_count",
    "validation_return_to_drawdown",
    "validation_pnl_concentration",
)

REJECTION_FIELDS = (
    "campaign_id",
    "trial_id",
    "reason_code",
    "reason_detail",
)


class CampaignAggregationError(RuntimeError):
    """Raised when campaign results cannot be aggregated safely."""


def _load_result(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise CampaignAggregationError(
            f"Unable to read execution result: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise CampaignAggregationError(
            f"Execution result must be a JSON object: {path}"
        )

    return payload


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0

    if parsed != parsed:
        return 0.0

    return parsed


def _fold_row(
    *,
    campaign: InitializedScorerCampaign,
    execution,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if payload is None:
        return {
            "campaign_id": campaign.campaign_id,
            "execution_id": execution.execution_id,
            "execution_index": execution.execution_index,
            "trial_id": execution.trial_id,
            "split_name": execution.split_name,
            "window_role": execution.window_role,
            "cost_scenario_id": execution.cost_scenario_id,
            "run_id": execution.run_id,
            "status": "incomplete",
        }

    if payload.get("campaign_id") != campaign.campaign_id:
        raise CampaignAggregationError(
            "Execution result campaign identity mismatch."
        )

    if payload.get("execution_id") != execution.execution_id:
        raise CampaignAggregationError(
            "Execution result identity mismatch."
        )

    metrics = payload.get("metrics", {})
    trial_result = payload.get("backtest", {})
    backtest = trial_result.get("backtest", {})

    return {
        "campaign_id": campaign.campaign_id,
        "execution_id": execution.execution_id,
        "execution_index": execution.execution_index,
        "trial_id": execution.trial_id,
        "split_name": execution.split_name,
        "window_role": execution.window_role,
        "cost_scenario_id": execution.cost_scenario_id,
        "run_id": execution.run_id,
        "status": payload.get("status", ""),
        "trade_count": _as_int(metrics.get("trade_count")),
        "winning_trades": _as_int(metrics.get("winning_trades")),
        "losing_trades": _as_int(metrics.get("losing_trades")),
        "breakeven_trades": _as_int(metrics.get("breakeven_trades")),
        "win_rate": _as_float(metrics.get("win_rate")),
        "total_pnl_usd": _as_float(metrics.get("total_pnl_usd")),
        "average_pnl_usd": _as_float(metrics.get("average_pnl_usd")),
        "best_trade_pnl_usd": _as_float(metrics.get("best_trade_pnl_usd")),
        "worst_trade_pnl_usd": _as_float(metrics.get("worst_trade_pnl_usd")),
        "maximum_drawdown_usd": _as_float(
            metrics.get("maximum_drawdown_usd")
        ),
        "stop_hit_count": _as_int(metrics.get("stop_hit_count")),
        "stop_hit_rate": _as_float(metrics.get("stop_hit_rate")),
        "time_stop_count": _as_int(metrics.get("time_stop_count")),
        "long_trade_count": _as_int(metrics.get("long_trade_count")),
        "short_trade_count": _as_int(metrics.get("short_trade_count")),
        "first_exit_ts_ms": metrics.get("first_exit_ts_ms"),
        "last_exit_ts_ms": metrics.get("last_exit_ts_ms"),
        "decisions_csv": backtest.get("decisions_csv", ""),
        "trades_csv": backtest.get("trades_csv", ""),
        "research_execution_events_csv": backtest.get(
            "research_execution_events_csv",
            "",
        ),
    }


def _safe_return_to_drawdown(
    *,
    pnl: float,
    drawdown: float,
) -> float:
    if drawdown > 0.0:
        return pnl / drawdown

    if pnl > 0.0:
        return pnl

    return 0.0


def _pnl_concentration(values: list[float]) -> float:
    positive_total = sum(
        value for value in values
        if value > 0.0
    )

    if positive_total <= 0.0:
        return 0.0

    return max(
        value for value in values
        if value > 0.0
    ) / positive_total


def aggregate_campaign_results(
    *,
    campaign: InitializedScorerCampaign,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    fold_rows = []

    for execution in campaign.execution_plan.executions:
        result_path = campaign.artifacts.trial_result_json(
            execution_id=execution.execution_id,
        )

        fold_rows.append(
            _fold_row(
                campaign=campaign,
                execution=execution,
                payload=_load_result(result_path),
            )
        )

    candidate_rows = []
    rejection_rows = []

    for trial in campaign.trials:
        rows = [
            row
            for row in fold_rows
            if row["trial_id"] == trial.trial_id
        ]

        expected_count = sum(
            1
            for execution in campaign.execution_plan.executions
            if execution.trial_id == trial.trial_id
        )

        successful_rows = [
            row
            for row in rows
            if row.get("status") == "succeeded"
        ]

        reasons: list[tuple[str, str]] = []

        if len(successful_rows) != expected_count:
            reasons.append(
                (
                    "execution_incomplete",
                    f"successful={len(successful_rows)} "
                    f"expected={expected_count}",
                )
            )

        if any(
            _as_int(row.get("short_trade_count")) > 0
            for row in successful_rows
        ):
            reasons.append(
                (
                    "short_trade_detected",
                    "At least one execution recorded a SHORT trade.",
                )
            )

        base_rows = [
            row
            for row in successful_rows
            if row["cost_scenario_id"] == "base"
        ]

        train_rows = [
            row
            for row in base_rows
            if row["window_role"] == "train"
        ]

        validation_rows = [
            row
            for row in base_rows
            if row["window_role"] == "validation"
        ]

        total_train_trades = sum(
            _as_int(row.get("trade_count"))
            for row in train_rows
        )

        total_validation_trades = sum(
            _as_int(row.get("trade_count"))
            for row in validation_rows
        )

        validation_pnls = [
            _as_float(row.get("total_pnl_usd"))
            for row in validation_rows
        ]

        validation_drawdowns = [
            _as_float(row.get("maximum_drawdown_usd"))
            for row in validation_rows
        ]

        total_validation_pnl = sum(validation_pnls)

        worst_validation_pnl = (
            min(validation_pnls)
            if validation_pnls
            else 0.0
        )

        average_validation_pnl = (
            total_validation_pnl / len(validation_pnls)
            if validation_pnls
            else 0.0
        )

        maximum_validation_drawdown = (
            max(validation_drawdowns)
            if validation_drawdowns
            else 0.0
        )

        positive_validation_fold_count = sum(
            1 for value in validation_pnls
            if value > 0.0
        )

        negative_validation_fold_count = sum(
            1 for value in validation_pnls
            if value < 0.0
        )

        validation_fold_count = len(validation_rows)

        if (
            total_train_trades
            + total_validation_trades
            < campaign.specification.minimum_total_trades
        ):
            reasons.append(
                (
                    "minimum_total_trades_not_met",
                    "Combined base train and validation trades "
                    f"were {total_train_trades + total_validation_trades}; "
                    f"required={campaign.specification.minimum_total_trades}",
                )
            )

        insufficient_splits = [
            row["split_name"]
            for row in validation_rows
            if _as_int(row.get("trade_count"))
            < campaign.specification.minimum_validation_trades_per_split
        ]

        if insufficient_splits:
            reasons.append(
                (
                    "minimum_validation_trades_per_split_not_met",
                    ",".join(insufficient_splits),
                )
            )

        if total_validation_pnl <= 0.0:
            reasons.append(
                (
                    "non_positive_total_validation_pnl",
                    f"value={total_validation_pnl}",
                )
            )

        if validation_rows and worst_validation_pnl <= 0.0:
            reasons.append(
                (
                    "non_positive_worst_validation_fold_pnl",
                    f"value={worst_validation_pnl}",
                )
            )

        stress_rows = [
            row
            for row in successful_rows
            if (
                row["window_role"] == "validation"
                and row["cost_scenario_id"] != "base"
            )
        ]

        stress_groups: dict[str, list[float]] = {}

        for row in stress_rows:
            stress_groups.setdefault(
                row["cost_scenario_id"],
                [],
            ).append(
                _as_float(row.get("total_pnl_usd"))
            )

        failed_stress = [
            scenario_id
            for scenario_id, values in stress_groups.items()
            if (
                sum(values) <= 0.0
                or min(values) <= 0.0
            )
        ]

        if failed_stress:
            reasons.append(
                (
                    "cost_stress_failure",
                    ",".join(sorted(failed_stress)),
                )
            )

        disposition = (
            "incomplete"
            if any(
                reason == "execution_incomplete"
                for reason, _ in reasons
            )
            else (
                "rejected"
                if reasons
                else "eligible"
            )
        )

        candidate_rows.append(
            {
                "campaign_id": campaign.campaign_id,
                "trial_id": trial.trial_id,
                "disposition": disposition,
                "rank": "",
                "rejection_reason_count": len(reasons),
                "total_train_trades": total_train_trades,
                "total_validation_trades": total_validation_trades,
                "total_validation_pnl_usd": total_validation_pnl,
                "worst_validation_fold_pnl_usd": worst_validation_pnl,
                "average_validation_pnl_usd": average_validation_pnl,
                "maximum_validation_drawdown_usd": (
                    maximum_validation_drawdown
                ),
                "positive_validation_fold_count": (
                    positive_validation_fold_count
                ),
                "negative_validation_fold_count": (
                    negative_validation_fold_count
                ),
                "validation_fold_count": validation_fold_count,
                "validation_return_to_drawdown": (
                    _safe_return_to_drawdown(
                        pnl=total_validation_pnl,
                        drawdown=maximum_validation_drawdown,
                    )
                ),
                "validation_pnl_concentration": (
                    _pnl_concentration(validation_pnls)
                ),
            }
        )

        for reason_code, detail in reasons:
            rejection_rows.append(
                {
                    "campaign_id": campaign.campaign_id,
                    "trial_id": trial.trial_id,
                    "reason_code": reason_code,
                    "reason_detail": detail,
                }
            )

    eligible_rows = [
        row
        for row in candidate_rows
        if row["disposition"] == "eligible"
    ]

    eligible_rows.sort(
        key=lambda row: (
            -_as_float(
                row["worst_validation_fold_pnl_usd"]
            ),
            -_as_float(
                row["total_validation_pnl_usd"]
            ),
            -_as_float(
                row["validation_return_to_drawdown"]
            ),
            -_as_int(
                row["positive_validation_fold_count"]
            ),
            -_as_int(
                row["total_validation_trades"]
            ),
            _as_float(
                row["validation_pnl_concentration"]
            ),
            str(row["trial_id"]),
        )
    )

    for rank, row in enumerate(
        eligible_rows,
        start=1,
    ):
        row["rank"] = rank

    candidate_rows.sort(
        key=lambda row: str(row["trial_id"])
    )

    rejection_rows.sort(
        key=lambda row: (
            str(row["trial_id"]),
            str(row["reason_code"]),
        )
    )

    summary = {
        "campaign_id": campaign.campaign_id,
        "planned_execution_count": len(
            campaign.execution_plan.executions
        ),
        "successful_execution_count": sum(
            1
            for row in fold_rows
            if row.get("status") == "succeeded"
        ),
        "candidate_count": len(candidate_rows),
        "eligible_candidate_count": sum(
            1
            for row in candidate_rows
            if row["disposition"] == "eligible"
        ),
        "rejected_candidate_count": sum(
            1
            for row in candidate_rows
            if row["disposition"] == "rejected"
        ),
        "incomplete_candidate_count": sum(
            1
            for row in candidate_rows
            if row["disposition"] == "incomplete"
        ),
        "ranked_trial_ids": [
            row["trial_id"]
            for row in eligible_rows
        ],
    }

    if write_artifacts:
        write_csv_atomic(
            path=campaign.artifacts.fold_results_csv,
            fieldnames=FOLD_RESULT_FIELDS,
            rows=fold_rows,
        )

        write_csv_atomic(
            path=campaign.artifacts.candidate_results_csv,
            fieldnames=CANDIDATE_RESULT_FIELDS,
            rows=candidate_rows,
        )

        write_csv_atomic(
            path=campaign.artifacts.rejections_csv,
            fieldnames=REJECTION_FIELDS,
            rows=rejection_rows,
        )

        write_json_atomic(
            path=campaign.artifacts.summary_json,
            value=summary,
        )

    return {
        "fold_rows": fold_rows,
        "candidate_rows": candidate_rows,
        "rejection_rows": rejection_rows,
        "summary": summary,
    }
