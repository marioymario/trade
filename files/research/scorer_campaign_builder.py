from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from files.config import TradingConfig
from files.research.historical_dataset import (
    HistoricalResearchSource,
    load_and_resolve_historical_research_source,
)
from files.research.scorer_campaign_artifacts import (
    CampaignArtifactPaths,
    campaign_artifact_paths,
)
from files.research.scorer_campaign_io import (
    write_json_immutable,
)
from files.research.scorer_campaign_plan import (
    CampaignExecutionPlan,
    build_campaign_execution_plan,
)
from files.research.scorer_campaign_spec import (
    CampaignSpecification,
    GitIdentity,
    campaign_id_for_payload,
    campaign_identity_payload,
    default_campaign_specification,
)
from files.research.scorer_parameter_space import (
    ScorerTrial,
    generate_trials,
)
from files.research.scorer_trial import (
    verify_fixed_strategy_contract,
)
from files.research.scorer_walk_forward import (
    ResolvedWalkForwardSplit,
    resolve_walk_forward_splits_for_source,
)


@dataclass(frozen=True)
class InitializedScorerCampaign:
    campaign_id: str
    specification: CampaignSpecification
    source: HistoricalResearchSource
    resolved_splits: tuple[
        ResolvedWalkForwardSplit, ...
    ]
    trials: tuple[ScorerTrial, ...]
    execution_plan: CampaignExecutionPlan
    artifacts: CampaignArtifactPaths
    manifest_payload: dict[str, Any]


def build_default_campaign_specification(
    *,
    trading_config: TradingConfig,
    trial_count: int | None = None,
    random_seed: int | None = None,
) -> CampaignSpecification:
    return default_campaign_specification(
        data_tag=trading_config.data_tag,
        symbol=trading_config.symbol,
        timeframe=trading_config.timeframe,
        min_bars=trading_config.min_bars,
        cooldown_bars=trading_config.cooldown_bars,
        max_order_size=trading_config.max_order_size,
        fee_bps=trading_config.fee_bps,
        slippage_bps=trading_config.slippage_bps,
        trial_count=trial_count,
        random_seed=random_seed,
    )


def initialize_scorer_campaign(
    *,
    trading_config: TradingConfig,
    git_identity: GitIdentity,
    trial_count: int | None = None,
    random_seed: int | None = None,
    write_artifacts: bool = True,
) -> InitializedScorerCampaign:
    specification = build_default_campaign_specification(
        trading_config=trading_config,
        trial_count=trial_count,
        random_seed=random_seed,
    )

    source = load_and_resolve_historical_research_source(
        data_tag=specification.data_tag,
        expected_symbol=specification.symbol,
        expected_timeframe=specification.timeframe,
    )

    resolved_splits = (
        resolve_walk_forward_splits_for_source(
            source=source,
            min_bars=specification.min_bars,
        )
    )

    trials = generate_trials(
        trial_count=specification.trial_count,
        random_seed=specification.random_seed,
    )

    manifest_payload = campaign_identity_payload(
        specification=specification,
        git_identity=git_identity,
        manifest_fingerprint=(
            source.manifest_fingerprint
        ),
        resolved_splits=tuple(
            split.as_dict()
            for split in resolved_splits
        ),
        trials=trials,
    )

    campaign_id = campaign_id_for_payload(
        manifest_payload
    )

    execution_plan = build_campaign_execution_plan(
        campaign_id=campaign_id,
        specification=specification,
        trials=trials,
        resolved_splits=resolved_splits,
        timeframe_step_ms=source.timeframe_step_ms,
    )

    artifacts = campaign_artifact_paths(
        campaign_id=campaign_id,
    )

    if write_artifacts:
        write_json_immutable(
            path=artifacts.campaign_manifest_json,
            value={
                "campaign_id": campaign_id,
                **manifest_payload,
            },
        )

        write_json_immutable(
            path=artifacts.execution_plan_json,
            value=execution_plan.as_dict(),
        )

    return InitializedScorerCampaign(
        campaign_id=campaign_id,
        specification=specification,
        source=source,
        resolved_splits=resolved_splits,
        trials=trials,
        execution_plan=execution_plan,
        artifacts=artifacts,
        manifest_payload=manifest_payload,
    )
