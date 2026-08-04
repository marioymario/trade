from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from files.backtest.replay import build_research_replay_plan
from files.config import TradingConfig
from files.research.historical_dataset import (
    build_historical_research_dataset,
)
from files.research.scorer_campaign_builder import (
    InitializedScorerCampaign,
)
from files.research.scorer_campaign_io import (
    write_json_immutable,
)
from files.research.scorer_campaign_plan import (
    CampaignExecution,
)
from files.research.scorer_metrics import (
    calculate_trial_metrics,
)
from files.research.scorer_trial import (
    TrialRunRequest,
    run_single_trial,
)


class CampaignExecutionError(RuntimeError):
    """Raised when one campaign execution is invalid."""


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_execution(
    *,
    campaign: InitializedScorerCampaign,
    execution_id: str,
) -> CampaignExecution:
    matches = [
        item
        for item in campaign.execution_plan.executions
        if item.execution_id == execution_id
    ]

    if len(matches) != 1:
        raise CampaignExecutionError(
            "Execution ID must resolve exactly once: "
            f"{execution_id!r}"
        )

    return matches[0]


def _find_trial(
    *,
    campaign: InitializedScorerCampaign,
    trial_id: str,
):
    matches = [
        trial
        for trial in campaign.trials
        if trial.trial_id == trial_id
    ]

    if len(matches) != 1:
        raise CampaignExecutionError(
            "Trial ID must resolve exactly once: "
            f"{trial_id!r}"
        )

    return matches[0]


def _find_cost_scenario(
    *,
    campaign: InitializedScorerCampaign,
    cost_scenario_id: str,
):
    matches = [
        scenario
        for scenario in campaign.specification.cost_scenarios
        if scenario.cost_scenario_id == cost_scenario_id
    ]

    if len(matches) != 1:
        raise CampaignExecutionError(
            "Cost scenario must resolve exactly once: "
            f"{cost_scenario_id!r}"
        )

    return matches[0]


def _load_existing_success(
    *,
    path: Path,
    campaign_id: str,
    execution_id: str,
) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise CampaignExecutionError(
            f"Existing trial result is unreadable: {path}"
        ) from exc

    if payload.get("campaign_id") != campaign_id:
        raise CampaignExecutionError(
            "Existing trial result campaign identity mismatch."
        )

    if payload.get("execution_id") != execution_id:
        raise CampaignExecutionError(
            "Existing trial result execution identity mismatch."
        )

    if payload.get("status") != "succeeded":
        raise CampaignExecutionError(
            "Existing immutable trial result is not successful."
        )

    return payload


def _remove_partial_backtest_outputs(
    *,
    data_tag: str,
    run_id: str,
    symbol_storage: str,
    timeframe: str,
) -> None:
    bt_exchange = f"{data_tag}_bt_{run_id}"

    roots = (
        Path("data/processed/decisions"),
        Path("data/processed/trades"),
        Path("data/processed/reports"),
    )

    for root in roots:
        target = (
            root
            / bt_exchange
            / symbol_storage
            / timeframe
        )

        if target.exists():
            shutil.rmtree(target)


def run_campaign_execution(
    *,
    campaign: InitializedScorerCampaign,
    trading_config: TradingConfig,
    execution_id: str,
) -> dict[str, Any]:
    result_path = campaign.artifacts.trial_result_json(
        execution_id=execution_id,
    )

    existing = _load_existing_success(
        path=result_path,
        campaign_id=campaign.campaign_id,
        execution_id=execution_id,
    )

    if existing is not None:
        return existing

    execution = _find_execution(
        campaign=campaign,
        execution_id=execution_id,
    )

    trial = _find_trial(
        campaign=campaign,
        trial_id=execution.trial_id,
    )

    scenario = _find_cost_scenario(
        campaign=campaign,
        cost_scenario_id=execution.cost_scenario_id,
    )

    source = campaign.source
    specification = campaign.specification

    if source.data_tag != specification.data_tag:
        raise CampaignExecutionError(
            "Resolved source data_tag changed after planning."
        )

    if source.symbol != specification.symbol:
        raise CampaignExecutionError(
            "Resolved source symbol changed after planning."
        )

    if source.timeframe != specification.timeframe:
        raise CampaignExecutionError(
            "Resolved source timeframe changed after planning."
        )

    symbol_storage = (
        specification.symbol
        .strip()
        .upper()
        .replace("/", "_")
    )

    _remove_partial_backtest_outputs(
        data_tag=specification.data_tag,
        run_id=execution.run_id,
        symbol_storage=symbol_storage,
        timeframe=specification.timeframe,
    )

    dataset = build_historical_research_dataset(
        audit=source.audit,
        start_ts_ms=execution.start_ts_ms,
        end_ts_ms=(
            execution.inclusive_backtest_end_ts_ms
        ),
        warmup_bars=max(
            int(specification.min_bars),
            50,
        ) + 5,
    )

    replay_plan = build_research_replay_plan(
        dataset=dataset,
    )

    execution_config = replace(
        trading_config,
        symbol=specification.symbol,
        timeframe=specification.timeframe,
        data_tag=specification.data_tag,
        min_bars=int(specification.min_bars),
        cooldown_bars=int(
            specification.cooldown_bars
        ),
        max_order_size=float(
            specification.max_order_size
        ),
        fee_bps=float(scenario.fee_bps),
        slippage_bps=float(
            scenario.slippage_bps
        ),
        dry_run=True,
    )

    trial_result = run_single_trial(
        TrialRunRequest(
            trial=trial,
            runid=execution.run_id,
            trading_config=execution_config,
            start_ts_ms=execution.start_ts_ms,
            end_ts_ms=(
                execution.inclusive_backtest_end_ts_ms
            ),
            replay_plan=replay_plan,
        )
    )

    metrics = calculate_trial_metrics(
        trades_csv=trial_result.backtest.trades_csv,
    )

    if metrics.short_trade_count != 0:
        raise CampaignExecutionError(
            "SHORT trade detected while SHORT is disabled."
        )

    if not trial_result.backtest.decisions_csv:
        raise CampaignExecutionError(
            "Backtest did not return a decisions path."
        )

    if not trial_result.backtest.trades_csv:
        raise CampaignExecutionError(
            "Backtest did not return a trades path."
        )

    payload = {
        "campaign_id": campaign.campaign_id,
        "execution_id": execution.execution_id,
        "status": "succeeded",
        "completed_at_utc": _utc_now_text(),
        "execution": execution.as_dict(),
        "trial": trial.as_dict(),
        "cost_scenario": scenario.as_dict(),
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
        "backtest": trial_result.as_dict(),
        "metrics": metrics.as_dict(),
    }

    write_json_immutable(
        path=result_path,
        value=payload,
    )

    return payload
