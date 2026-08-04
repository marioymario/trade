from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from files.data.paths import processed_dir


_CAMPAIGN_ID_RE = re.compile(
    r"^scorer_campaign_[0-9a-f]{16}$"
)

_EXECUTION_ID_RE = re.compile(
    r"^execution_[0-9a-f]{16}$"
)


class CampaignArtifactError(RuntimeError):
    """Raised when a campaign artifact identity or path is invalid."""


def validate_campaign_id(campaign_id: str) -> str:
    value = str(campaign_id).strip()

    if not _CAMPAIGN_ID_RE.fullmatch(value):
        raise CampaignArtifactError(
            "campaign_id must match "
            "'scorer_campaign_<16 lowercase hexadecimal characters>': "
            f"{campaign_id!r}"
        )

    return value


def validate_execution_id(execution_id: str) -> str:
    value = str(execution_id).strip()

    if not _EXECUTION_ID_RE.fullmatch(value):
        raise CampaignArtifactError(
            "execution_id must match "
            "'execution_<16 lowercase hexadecimal characters>': "
            f"{execution_id!r}"
        )

    return value


def scorer_campaigns_dir() -> Path:
    return (
        processed_dir()
        / "research"
        / "scorer_campaigns"
    )


def scorer_campaign_dir(
    *,
    campaign_id: str,
) -> Path:
    return (
        scorer_campaigns_dir()
        / validate_campaign_id(campaign_id)
    )


@dataclass(frozen=True)
class CampaignArtifactPaths:
    root: Path
    campaign_manifest_json: Path
    execution_plan_json: Path
    campaign_status_json: Path
    fold_results_csv: Path
    candidate_results_csv: Path
    rejections_csv: Path
    failures_csv: Path
    summary_json: Path
    trials_dir: Path

    def trial_dir(
        self,
        *,
        execution_id: str,
    ) -> Path:
        return (
            self.trials_dir
            / validate_execution_id(execution_id)
        )

    def trial_result_json(
        self,
        *,
        execution_id: str,
    ) -> Path:
        return (
            self.trial_dir(
                execution_id=execution_id,
            )
            / "result.json"
        )


def campaign_artifact_paths(
    *,
    campaign_id: str,
) -> CampaignArtifactPaths:
    root = scorer_campaign_dir(
        campaign_id=campaign_id,
    )

    return CampaignArtifactPaths(
        root=root,
        campaign_manifest_json=(
            root / "campaign_manifest.json"
        ),
        execution_plan_json=(
            root / "execution_plan.json"
        ),
        campaign_status_json=(
            root / "campaign_status.json"
        ),
        fold_results_csv=(
            root / "fold_results.csv"
        ),
        candidate_results_csv=(
            root / "candidate_results.csv"
        ),
        rejections_csv=(
            root / "rejections.csv"
        ),
        failures_csv=(
            root / "failures.csv"
        ),
        summary_json=(
            root / "summary.json"
        ),
        trials_dir=(
            root / "trials"
        ),
    )
