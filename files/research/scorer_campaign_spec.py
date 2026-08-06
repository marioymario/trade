from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Sequence

from files.research.scorer_campaign_io import (
    canonical_json_text,
)
from files.research.scorer_parameter_space import (
    ScorerTrial,
)
from files.research.scorer_search_config import (
    FIXED_SETTINGS,
    MANIFEST_BACKED_SOURCE_CONTRACT,
    SEARCH_CONTROLS,
)


CAMPAIGN_SCHEMA_VERSION = 5
TRIAL_SPACE_VERSION = "scorer_parameter_space_v1"
EXECUTION_ARTIFACT_CONTRACT_VERSION = (
    "scorer_execution_artifacts_v2"
)
REJECTION_POLICY_VERSION = "scorer_rejection_policy_v3"
RANKING_POLICY_VERSION = "scorer_ranking_policy_v1"


def rejection_policy_definition() -> dict[str, Any]:
    return {
        "policy_version": REJECTION_POLICY_VERSION,
        "rules": [
            {
                "reason_code": "execution_incomplete",
                "condition": (
                    "Any planned execution result is missing "
                    "or does not have status='succeeded'."
                ),
            },
            {
                "reason_code": "short_trade_detected",
                "condition": (
                    "Any execution reports short_trade_count > 0."
                ),
            },
            {
                "reason_code": "minimum_total_trades_not_met",
                "condition": (
                    "Combined train and validation trade count "
                    "is below minimum_total_trades."
                ),
                "threshold_field": "minimum_total_trades",
            },
            {
                "reason_code": (
                    "minimum_validation_trades_per_split_not_met"
                ),
                "condition": (
                    "Any base-cost validation split has fewer "
                    "trades than "
                    "minimum_validation_trades_per_split."
                ),
                "threshold_field": (
                    "minimum_validation_trades_per_split"
                ),
            },
            {
                "reason_code": (
                    "non_positive_total_validation_pnl"
                ),
                "condition": (
                    "Combined base-cost validation PnL is "
                    "less than or equal to zero."
                ),
            },
            {
                "reason_code": (
                    "non_positive_worst_validation_fold_pnl"
                ),
                "condition": (
                    "Worst base-cost validation-fold PnL is "
                    "less than or equal to zero."
                ),
            },
            {
                "reason_code": "cost_stress_failure",
                "condition": (
                    "Any configured non-base cost scenario "
                    "fails its validation requirements."
                ),
            },
        ],
    }


def ranking_policy_definition() -> dict[str, Any]:
    return {
        "policy_version": RANKING_POLICY_VERSION,
        "eligible_candidates_only": True,
        "ordering": [
            {
                "field": "worst_validation_fold_pnl_usd",
                "direction": "descending",
            },
            {
                "field": "total_validation_pnl_usd",
                "direction": "descending",
            },
            {
                "field": "validation_return_to_drawdown",
                "direction": "descending",
            },
            {
                "field": "positive_validation_fold_count",
                "direction": "descending",
            },
            {
                "field": "total_validation_trades",
                "direction": "descending",
            },
            {
                "field": "validation_pnl_concentration",
                "direction": "ascending",
            },
            {
                "field": "trial_id",
                "direction": "ascending",
            },
        ],
    }

_COST_SCENARIO_ID_RE = re.compile(
    r"^[a-z][a-z0-9_]*$"
)


class CampaignSpecificationError(RuntimeError):
    """Raised when a campaign specification is invalid."""


@dataclass(frozen=True)
class GitIdentity:
    git_commit: str
    git_branch: str
    working_tree_clean: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CostScenario:
    cost_scenario_id: str
    fee_bps: float
    slippage_bps: float

    def __post_init__(self) -> None:
        scenario_id = self.cost_scenario_id.strip()

        if not _COST_SCENARIO_ID_RE.fullmatch(
            scenario_id
        ):
            raise CampaignSpecificationError(
                "cost_scenario_id must contain only lowercase "
                "letters, digits, and underscores, and must begin "
                f"with a letter: {self.cost_scenario_id!r}"
            )

        if float(self.fee_bps) < 0.0:
            raise CampaignSpecificationError(
                "fee_bps must be non-negative."
            )

        if float(self.slippage_bps) < 0.0:
            raise CampaignSpecificationError(
                "slippage_bps must be non-negative."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cost_scenario_id": self.cost_scenario_id,
            "fee_bps": float(self.fee_bps),
            "slippage_bps": float(self.slippage_bps),
        }


@dataclass(frozen=True)
class CampaignSpecification:
    source_contract: str
    data_tag: str
    symbol: str
    timeframe: str

    trial_count: int
    random_seed: int

    minimum_total_trades: int
    minimum_validation_trades_per_split: int

    min_bars: int
    cooldown_bars: int
    max_order_size: float

    cost_scenarios: tuple[CostScenario, ...]

    campaign_schema_version: int = (
        CAMPAIGN_SCHEMA_VERSION
    )
    trial_space_version: str = (
        TRIAL_SPACE_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.source_contract
            != MANIFEST_BACKED_SOURCE_CONTRACT
        ):
            raise CampaignSpecificationError(
                "Campaign source_contract must be "
                f"{MANIFEST_BACKED_SOURCE_CONTRACT!r}; "
                f"got {self.source_contract!r}."
            )

        for name, value in (
            ("data_tag", self.data_tag),
            ("symbol", self.symbol),
            ("timeframe", self.timeframe),
            ("trial_space_version", self.trial_space_version),
        ):
            if not str(value).strip():
                raise CampaignSpecificationError(
                    f"{name} must be non-empty."
                )

        if int(self.trial_count) <= 0:
            raise CampaignSpecificationError(
                "trial_count must be positive."
            )

        if int(self.minimum_total_trades) < 0:
            raise CampaignSpecificationError(
                "minimum_total_trades must be non-negative."
            )

        if (
            int(
                self.minimum_validation_trades_per_split
            )
            < 0
        ):
            raise CampaignSpecificationError(
                "minimum_validation_trades_per_split "
                "must be non-negative."
            )

        if int(self.min_bars) < 50:
            raise CampaignSpecificationError(
                "min_bars must be at least 50."
            )

        if int(self.cooldown_bars) < 0:
            raise CampaignSpecificationError(
                "cooldown_bars must be non-negative."
            )

        if float(self.max_order_size) < 0.0:
            raise CampaignSpecificationError(
                "max_order_size must be non-negative."
            )

        if not self.cost_scenarios:
            raise CampaignSpecificationError(
                "At least one cost scenario is required."
            )

        scenario_ids = [
            scenario.cost_scenario_id
            for scenario in self.cost_scenarios
        ]

        if len(scenario_ids) != len(set(scenario_ids)):
            raise CampaignSpecificationError(
                "cost_scenario_id values must be unique."
            )

        if scenario_ids[0] != "base":
            raise CampaignSpecificationError(
                "The first cost scenario must be 'base'."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "campaign_schema_version": int(
                self.campaign_schema_version
            ),
            "source_contract": self.source_contract,
            "data_tag": self.data_tag,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "trial_space_version": (
                self.trial_space_version
            ),
            "execution_artifact_contract_version": (
                EXECUTION_ARTIFACT_CONTRACT_VERSION
            ),
            "trial_count": int(self.trial_count),
            "random_seed": int(self.random_seed),
            "minimum_total_trades": int(
                self.minimum_total_trades
            ),
            "minimum_validation_trades_per_split": int(
                self.minimum_validation_trades_per_split
            ),
            "min_bars": int(self.min_bars),
            "cooldown_bars": int(
                self.cooldown_bars
            ),
            "max_order_size": float(
                self.max_order_size
            ),
            "fixed_strategy_settings": asdict(
                FIXED_SETTINGS
            ),
            "cost_scenarios": [
                scenario.as_dict()
                for scenario in self.cost_scenarios
            ],
            "rejection_policy": (
                rejection_policy_definition()
            ),
            "ranking_policy": (
                ranking_policy_definition()
            ),
        }


def load_clean_git_identity() -> GitIdentity:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise CampaignSpecificationError(
            "Unable to resolve Git identity."
        ) from exc

    if not commit:
        raise CampaignSpecificationError(
            "Git commit could not be resolved."
        )

    if not branch:
        raise CampaignSpecificationError(
            "Git branch could not be resolved."
        )

    if status.strip():
        raise CampaignSpecificationError(
            "Campaign execution requires a clean working tree."
        )

    return GitIdentity(
        git_commit=commit,
        git_branch=branch,
        working_tree_clean=True,
    )



def load_deployed_git_identity(
    path: str | Path = (
        "files/research/contracts/"
        ".deployed_git_identity.json"
    ),
) -> GitIdentity:
    identity_path = Path(path)

    try:
        payload = json.loads(
            identity_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise CampaignSpecificationError(
            "Unable to load deployed Git identity: "
            f"{identity_path}"
        ) from exc

    commit = str(payload.get("git_commit", "")).strip()
    branch = str(payload.get("git_branch", "")).strip()
    clean = payload.get("working_tree_clean")

    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise CampaignSpecificationError(
            "Deployed Git commit must be a lowercase "
            "40-character SHA-1 digest."
        )

    if not branch:
        raise CampaignSpecificationError(
            "Deployed Git branch must be non-empty."
        )

    if clean is not True:
        raise CampaignSpecificationError(
            "Deployed Git identity must record a clean tree."
        )

    return GitIdentity(
        git_commit=commit,
        git_branch=branch,
        working_tree_clean=True,
    )


def load_runtime_git_identity() -> GitIdentity:
    if Path(".git").exists():
        return load_clean_git_identity()

    return load_deployed_git_identity()

def campaign_identity_payload(
    *,
    specification: CampaignSpecification,
    git_identity: GitIdentity,
    manifest_fingerprint: str,
    resolved_splits: Sequence[dict[str, Any]],
    trials: Sequence[ScorerTrial],
) -> dict[str, Any]:
    fingerprint = manifest_fingerprint.strip()

    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise CampaignSpecificationError(
            "manifest_fingerprint must be a lowercase "
            "64-character SHA-256 digest."
        )

    trial_ids = [
        trial.trial_id
        for trial in trials
    ]

    if len(trial_ids) != len(set(trial_ids)):
        raise CampaignSpecificationError(
            "Candidate trial IDs must be unique."
        )

    if len(trial_ids) != specification.trial_count:
        raise CampaignSpecificationError(
            "Candidate count does not match campaign trial_count."
        )

    return {
        "specification": specification.as_dict(),
        "git_identity": git_identity.as_dict(),
        "manifest_fingerprint": fingerprint,
        "resolved_walk_forward_splits": list(
            resolved_splits
        ),
        "candidates": [
            trial.as_dict()
            for trial in trials
        ],
    }


def campaign_id_for_payload(
    payload: dict[str, Any],
) -> str:
    digest = hashlib.sha256(
        canonical_json_text(payload).encode("utf-8")
    ).hexdigest()

    return f"scorer_campaign_{digest[:16]}"


def default_campaign_specification(
    *,
    data_tag: str,
    symbol: str,
    timeframe: str,
    min_bars: int,
    cooldown_bars: int,
    max_order_size: float,
    fee_bps: float,
    slippage_bps: float,
    trial_count: int | None = None,
    random_seed: int | None = None,
) -> CampaignSpecification:
    return CampaignSpecification(
        source_contract=(
            MANIFEST_BACKED_SOURCE_CONTRACT
        ),
        data_tag=data_tag,
        symbol=symbol,
        timeframe=timeframe,
        trial_count=(
            SEARCH_CONTROLS.trial_count
            if trial_count is None
            else int(trial_count)
        ),
        random_seed=(
            SEARCH_CONTROLS.random_seed
            if random_seed is None
            else int(random_seed)
        ),
        minimum_total_trades=(
            SEARCH_CONTROLS.minimum_total_trades
        ),
        minimum_validation_trades_per_split=(
            SEARCH_CONTROLS
            .minimum_validation_trades_per_split
        ),
        min_bars=int(min_bars),
        cooldown_bars=int(cooldown_bars),
        max_order_size=float(max_order_size),
        cost_scenarios=(
            CostScenario(
                cost_scenario_id="base",
                fee_bps=float(fee_bps),
                slippage_bps=float(slippage_bps),
            ),
        ),
    )
