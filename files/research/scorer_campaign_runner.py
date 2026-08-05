from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from files.config import TradingConfig
from files.research.historical_dataset import (
    HistoricalDatasetContractError,
)
from files.research.scorer_campaign_aggregation import (
    CampaignAggregationError,
    aggregate_campaign_results,
)
from files.research.scorer_campaign_builder import (
    InitializedScorerCampaign,
)
from files.research.scorer_campaign_execution import (
    CampaignExecutionError,
    run_campaign_execution,
)
from files.research.scorer_campaign_io import (
    CampaignArtifactWriteError,
    write_csv_atomic,
    write_json_atomic,
)
from files.research.scorer_campaign_spec import (
    CampaignSpecificationError,
)


FAILURE_FIELDS = (
    "campaign_id",
    "execution_id",
    "trial_id",
    "split_name",
    "window_role",
    "cost_scenario_id",
    "run_id",
    "failure_type",
    "failure_message",
    "failed_at_utc",
)


class CampaignRunnerError(RuntimeError):
    """Raised when campaign orchestration cannot continue safely."""


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_failure_message(value: object) -> str:
    return " ".join(str(value).split())


def load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise CampaignRunnerError(
            f"Unable to read JSON artifact: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise CampaignRunnerError(
            f"JSON artifact must contain an object: {path}"
        )

    return payload


def load_failure_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    try:
        with path.open(
            "r",
            newline="",
            encoding="utf-8",
        ) as handle:
            return [
                {
                    field: str(row.get(field, ""))
                    for field in FAILURE_FIELDS
                }
                for row in csv.DictReader(handle)
            ]
    except Exception as exc:
        raise CampaignRunnerError(
            f"Unable to read failure artifact: {path}"
        ) from exc


def successful_execution_ids(
    campaign: InitializedScorerCampaign,
) -> set[str]:
    successful: set[str] = set()

    for execution in campaign.execution_plan.executions:
        result_path = campaign.artifacts.trial_result_json(
            execution_id=execution.execution_id,
        )

        payload = load_json_object(result_path)

        if payload is None:
            continue

        if (
            payload.get("campaign_id")
            != campaign.campaign_id
        ):
            raise CampaignRunnerError(
                "Trial result campaign identity mismatch: "
                f"{result_path}"
            )

        if (
            payload.get("execution_id")
            != execution.execution_id
        ):
            raise CampaignRunnerError(
                "Trial result execution identity mismatch: "
                f"{result_path}"
            )

        if payload.get("status") != "succeeded":
            raise CampaignRunnerError(
                "Immutable trial result is not successful: "
                f"{result_path}"
            )

        successful.add(execution.execution_id)

    return successful


def failure_rows_by_execution(
    campaign: InitializedScorerCampaign,
) -> dict[str, dict[str, str]]:
    planned_ids = {
        execution.execution_id
        for execution in campaign.execution_plan.executions
    }

    rows: dict[str, dict[str, str]] = {}

    for row in load_failure_rows(
        campaign.artifacts.failures_csv
    ):
        execution_id = row["execution_id"]

        if execution_id in planned_ids:
            rows[execution_id] = row

    return rows


def write_failures(
    *,
    campaign: InitializedScorerCampaign,
    failures: dict[str, dict[str, str]],
) -> None:
    ordered_rows = [
        failures[execution.execution_id]
        for execution in campaign.execution_plan.executions
        if execution.execution_id in failures
    ]

    write_csv_atomic(
        path=campaign.artifacts.failures_csv,
        fieldnames=FAILURE_FIELDS,
        rows=ordered_rows,
    )


def build_status(
    *,
    campaign: InitializedScorerCampaign,
    status: str,
    created_at_utc: str,
    started_at_utc: str,
    completed_at_utc: str,
    last_execution_id: str,
    successful_ids: set[str],
    failed_ids: set[str],
    eligible_candidate_count: int = 0,
    rejected_candidate_count: int = 0,
    incomplete_candidate_count: int = 0,
) -> dict[str, Any]:
    planned_count = len(
        campaign.execution_plan.executions
    )
    succeeded_count = len(successful_ids)
    failed_count = len(failed_ids)

    pending_count = (
        planned_count
        - succeeded_count
        - failed_count
    )

    if pending_count < 0:
        raise CampaignRunnerError(
            "Campaign status accounting invariant failed."
        )

    return {
        "campaign_id": campaign.campaign_id,
        "status": status,
        "created_at_utc": created_at_utc,
        "started_at_utc": started_at_utc,
        "updated_at_utc": utc_now_text(),
        "completed_at_utc": completed_at_utc,
        "planned_execution_count": planned_count,
        "succeeded_execution_count": succeeded_count,
        "failed_execution_count": failed_count,
        "pending_execution_count": pending_count,
        "eligible_candidate_count": int(
            eligible_candidate_count
        ),
        "rejected_candidate_count": int(
            rejected_candidate_count
        ),
        "incomplete_candidate_count": int(
            incomplete_candidate_count
        ),
        "last_execution_id": last_execution_id,
    }


def write_status(
    *,
    campaign: InitializedScorerCampaign,
    status: str,
    created_at_utc: str,
    started_at_utc: str,
    completed_at_utc: str,
    last_execution_id: str,
    successful_ids: set[str],
    failed_ids: set[str],
    eligible_candidate_count: int = 0,
    rejected_candidate_count: int = 0,
    incomplete_candidate_count: int = 0,
) -> dict[str, Any]:
    payload = build_status(
        campaign=campaign,
        status=status,
        created_at_utc=created_at_utc,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        last_execution_id=last_execution_id,
        successful_ids=successful_ids,
        failed_ids=failed_ids,
        eligible_candidate_count=(
            eligible_candidate_count
        ),
        rejected_candidate_count=(
            rejected_candidate_count
        ),
        incomplete_candidate_count=(
            incomplete_candidate_count
        ),
    )

    write_json_atomic(
        path=campaign.artifacts.campaign_status_json,
        value=payload,
    )

    return payload


def is_campaign_wide_failure(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            HistoricalDatasetContractError,
            CampaignAggregationError,
            CampaignArtifactWriteError,
            CampaignSpecificationError,
            CampaignRunnerError,
        ),
    ):
        return True

    message = str(exc)

    fatal_fragments = (
        "Fixed strategy contract mismatch",
        "source data_tag changed after planning",
        "source symbol changed after planning",
        "source timeframe changed after planning",
        "identity mismatch",
        "identity conflict",
        "execution plan",
    )

    return any(
        fragment in message
        for fragment in fatal_fragments
    )


def failure_row(
    *,
    campaign: InitializedScorerCampaign,
    execution,
    exc: BaseException,
) -> dict[str, str]:
    return {
        "campaign_id": campaign.campaign_id,
        "execution_id": execution.execution_id,
        "trial_id": execution.trial_id,
        "split_name": execution.split_name,
        "window_role": execution.window_role,
        "cost_scenario_id": (
            execution.cost_scenario_id
        ),
        "run_id": execution.run_id,
        "failure_type": type(exc).__name__,
        "failure_message": sanitize_failure_message(
            exc
        ),
        "failed_at_utc": utc_now_text(),
    }


def run_scorer_campaign(
    *,
    campaign: InitializedScorerCampaign,
    trading_config: TradingConfig,
    continue_after_failure: bool = True,
) -> dict[str, Any]:
    existing_status = load_json_object(
        campaign.artifacts.campaign_status_json
    )

    now = utc_now_text()

    created_at_utc = (
        str(existing_status.get("created_at_utc"))
        if existing_status
        and existing_status.get("created_at_utc")
        else now
    )

    started_at_utc = (
        str(existing_status.get("started_at_utc"))
        if existing_status
        and existing_status.get("started_at_utc")
        else now
    )

    successful_ids = successful_execution_ids(
        campaign
    )
    failures = failure_rows_by_execution(
        campaign
    )

    for execution_id in successful_ids:
        failures.pop(execution_id, None)

    write_failures(
        campaign=campaign,
        failures=failures,
    )

    last_execution_id = ""

    write_status(
        campaign=campaign,
        status="running",
        created_at_utc=created_at_utc,
        started_at_utc=started_at_utc,
        completed_at_utc="",
        last_execution_id=last_execution_id,
        successful_ids=successful_ids,
        failed_ids=set(failures),
    )

    for execution in campaign.execution_plan.executions:
        if execution.execution_id in successful_ids:
            last_execution_id = execution.execution_id
            continue

        last_execution_id = execution.execution_id

        write_status(
            campaign=campaign,
            status="running",
            created_at_utc=created_at_utc,
            started_at_utc=started_at_utc,
            completed_at_utc="",
            last_execution_id=last_execution_id,
            successful_ids=successful_ids,
            failed_ids=set(failures),
        )

        try:
            result = run_campaign_execution(
                campaign=campaign,
                trading_config=trading_config,
                execution_id=execution.execution_id,
            )

            if result.get("status") != "succeeded":
                raise CampaignExecutionError(
                    "Execution returned a non-success status."
                )

            successful_ids.add(
                execution.execution_id
            )
            failures.pop(
                execution.execution_id,
                None,
            )

        except Exception as exc:
            failures[execution.execution_id] = (
                failure_row(
                    campaign=campaign,
                    execution=execution,
                    exc=exc,
                )
            )

            write_failures(
                campaign=campaign,
                failures=failures,
            )

            if is_campaign_wide_failure(exc):
                write_status(
                    campaign=campaign,
                    status="failed",
                    created_at_utc=created_at_utc,
                    started_at_utc=started_at_utc,
                    completed_at_utc=utc_now_text(),
                    last_execution_id=last_execution_id,
                    successful_ids=successful_ids,
                    failed_ids=set(failures),
                )
                raise

            if not continue_after_failure:
                break

        write_failures(
            campaign=campaign,
            failures=failures,
        )

        write_status(
            campaign=campaign,
            status="running",
            created_at_utc=created_at_utc,
            started_at_utc=started_at_utc,
            completed_at_utc="",
            last_execution_id=last_execution_id,
            successful_ids=successful_ids,
            failed_ids=set(failures),
        )

    completed_at_utc = utc_now_text()

    try:
        aggregation = aggregate_campaign_results(
            campaign=campaign,
            write_artifacts=True,
        )
    except Exception:
        write_status(
            campaign=campaign,
            status="failed",
            created_at_utc=created_at_utc,
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
            last_execution_id=last_execution_id,
            successful_ids=successful_ids,
            failed_ids=set(failures),
        )
        raise

    summary = aggregation["summary"]

    final_status = (
        "completed_with_failures"
        if failures
        else "completed"
    )

    return write_status(
        campaign=campaign,
        status=final_status,
        created_at_utc=created_at_utc,
        started_at_utc=started_at_utc,
        completed_at_utc=completed_at_utc,
        last_execution_id=last_execution_id,
        successful_ids=successful_ids,
        failed_ids=set(failures),
        eligible_candidate_count=int(
            summary["eligible_candidate_count"]
        ),
        rejected_candidate_count=int(
            summary["rejected_candidate_count"]
        ),
        incomplete_candidate_count=int(
            summary["incomplete_candidate_count"]
        ),
    )
