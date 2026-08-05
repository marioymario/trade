from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any, Sequence

from files.research.scorer_campaign_io import (
    canonical_json_text,
)
from files.research.scorer_campaign_spec import (
    CampaignSpecification,
)
from files.research.scorer_parameter_space import (
    ScorerTrial,
)
from files.research.scorer_walk_forward import (
    ResolvedWalkForwardSplit,
)


WINDOW_ROLES = ("train", "validation")

_SAFE_NAME_RE = re.compile(
    r"^[a-z0-9_]+$"
)


class CampaignPlanError(RuntimeError):
    """Raised when a campaign execution plan is invalid."""


@dataclass(frozen=True)
class CampaignExecution:
    execution_index: int
    execution_id: str
    campaign_id: str

    trial_id: str
    split_name: str
    window_role: str
    cost_scenario_id: str

    start: str
    end_exclusive: str
    start_ts_ms: int
    end_ts_ms_exclusive: int
    inclusive_backtest_end_ts_ms: int

    run_id: str

    result_json: str
    decisions_csv: str
    trades_csv: str
    research_execution_events_csv: str

    status: str = "pending"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CampaignExecutionPlan:
    campaign_id: str
    executions: tuple[CampaignExecution, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "execution_count": len(self.executions),
            "executions": [
                execution.as_dict()
                for execution in self.executions
            ],
        }


def _validate_safe_name(
    value: str,
    *,
    name: str,
) -> str:
    text = str(value).strip().lower()

    if not _SAFE_NAME_RE.fullmatch(text):
        raise CampaignPlanError(
            f"{name} must contain only lowercase letters, "
            f"digits, and underscores: {value!r}"
        )

    return text


def _execution_identity_payload(
    *,
    campaign_id: str,
    trial_id: str,
    split_name: str,
    window_role: str,
    cost_scenario_id: str,
) -> dict[str, str]:
    return {
        "campaign_id": campaign_id,
        "trial_id": trial_id,
        "split_name": split_name,
        "window_role": window_role,
        "cost_scenario_id": cost_scenario_id,
    }


def execution_id_for_identity(
    *,
    campaign_id: str,
    trial_id: str,
    split_name: str,
    window_role: str,
    cost_scenario_id: str,
) -> str:
    payload = _execution_identity_payload(
        campaign_id=campaign_id,
        trial_id=trial_id,
        split_name=split_name,
        window_role=window_role,
        cost_scenario_id=cost_scenario_id,
    )

    digest = hashlib.sha256(
        canonical_json_text(payload).encode("utf-8")
    ).hexdigest()

    return f"execution_{digest[:16]}"


def run_id_for_execution(
    *,
    campaign_id: str,
    execution_id: str,
) -> str:
    campaign_suffix = campaign_id.removeprefix(
        "scorer_campaign_"
    )
    execution_suffix = execution_id.removeprefix(
        "execution_"
    )

    run_id = (
        f"campaign_{campaign_suffix}_"
        f"{execution_suffix}"
    )

    return _validate_safe_name(
        run_id,
        name="run_id",
    )


def _execution_artifact_paths(
    *,
    campaign_id: str,
    execution_id: str,
    run_id: str,
    data_tag: str,
    symbol: str,
    timeframe: str,
) -> dict[str, str]:
    symbol_storage = (
        str(symbol)
        .strip()
        .upper()
        .replace("/", "_")
        .replace(":", "_")
        .replace(" ", "_")
    )

    backtest_exchange = (
        f"{data_tag}_bt_{run_id}"
    )

    campaign_root = (
        "data/processed/research/scorer_campaigns/"
        f"{campaign_id}"
    )

    return {
        "result_json": (
            f"{campaign_root}/trials/"
            f"{execution_id}/result.json"
        ),
        "decisions_csv": (
            "data/processed/decisions/"
            f"{backtest_exchange}/"
            f"{symbol_storage}/{timeframe}/"
            "decisions.csv"
        ),
        "trades_csv": (
            "data/processed/trades/"
            f"{backtest_exchange}/"
            f"{symbol_storage}/{timeframe}/"
            "trades.csv"
        ),
        "research_execution_events_csv": (
            "data/processed/research/executions/"
            f"{run_id}/events.csv"
        ),
    }


def build_campaign_execution_plan(
    *,
    campaign_id: str,
    specification: CampaignSpecification,
    trials: Sequence[ScorerTrial],
    resolved_splits: Sequence[
        ResolvedWalkForwardSplit
    ],
    timeframe_step_ms: int,
) -> CampaignExecutionPlan:
    if int(timeframe_step_ms) <= 0:
        raise CampaignPlanError(
            "timeframe_step_ms must be positive."
        )

    if len(trials) != specification.trial_count:
        raise CampaignPlanError(
            "Trial count does not match campaign specification."
        )

    trial_ids = [
        trial.trial_id
        for trial in trials
    ]

    if len(trial_ids) != len(set(trial_ids)):
        raise CampaignPlanError(
            "Trial IDs must be unique."
        )

    split_names = [
        split.name
        for split in resolved_splits
    ]

    if len(split_names) != len(set(split_names)):
        raise CampaignPlanError(
            "Split names must be unique."
        )

    executions: list[CampaignExecution] = []
    execution_index = 0

    for trial in trials:
        for split in resolved_splits:
            split_name = _validate_safe_name(
                split.name,
                name="split_name",
            )

            for window_role in WINDOW_ROLES:
                window = getattr(
                    split,
                    window_role,
                )

                inclusive_end_ts_ms = (
                    int(window.end_ts_ms_exclusive)
                    - int(timeframe_step_ms)
                )

                if (
                    inclusive_end_ts_ms
                    < int(window.start_ts_ms)
                ):
                    raise CampaignPlanError(
                        "Window inclusive end precedes start: "
                        f"split={split_name!r} "
                        f"role={window_role!r}"
                    )

                for cost_scenario in (
                    specification.cost_scenarios
                ):
                    execution_index += 1

                    execution_id = (
                        execution_id_for_identity(
                            campaign_id=campaign_id,
                            trial_id=trial.trial_id,
                            split_name=split_name,
                            window_role=window_role,
                            cost_scenario_id=(
                                cost_scenario
                                .cost_scenario_id
                            ),
                        )
                    )

                    run_id = run_id_for_execution(
                        campaign_id=campaign_id,
                        execution_id=execution_id,
                    )

                    artifact_paths = (
                        _execution_artifact_paths(
                            campaign_id=campaign_id,
                            execution_id=execution_id,
                            run_id=run_id,
                            data_tag=specification.data_tag,
                            symbol=specification.symbol,
                            timeframe=specification.timeframe,
                        )
                    )

                    executions.append(
                        CampaignExecution(
                            execution_index=(
                                execution_index
                            ),
                            execution_id=execution_id,
                            campaign_id=campaign_id,
                            trial_id=trial.trial_id,
                            split_name=split_name,
                            window_role=window_role,
                            cost_scenario_id=(
                                cost_scenario
                                .cost_scenario_id
                            ),
                            start=window.start,
                            end_exclusive=(
                                window.end_exclusive
                            ),
                            start_ts_ms=int(
                                window.start_ts_ms
                            ),
                            end_ts_ms_exclusive=int(
                                window.end_ts_ms_exclusive
                            ),
                            inclusive_backtest_end_ts_ms=(
                                inclusive_end_ts_ms
                            ),
                            run_id=run_id,
                            result_json=(
                                artifact_paths["result_json"]
                            ),
                            decisions_csv=(
                                artifact_paths["decisions_csv"]
                            ),
                            trades_csv=(
                                artifact_paths["trades_csv"]
                            ),
                            research_execution_events_csv=(
                                artifact_paths[
                                    "research_execution_events_csv"
                                ]
                            ),
                        )
                    )

    execution_ids = [
        execution.execution_id
        for execution in executions
    ]
    run_ids = [
        execution.run_id
        for execution in executions
    ]

    if len(execution_ids) != len(set(execution_ids)):
        raise CampaignPlanError(
            "Execution IDs must be unique."
        )

    if len(run_ids) != len(set(run_ids)):
        raise CampaignPlanError(
            "Run IDs must be unique."
        )

    return CampaignExecutionPlan(
        campaign_id=campaign_id,
        executions=tuple(executions),
    )
