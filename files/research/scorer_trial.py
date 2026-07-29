from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from typing import Any, Iterator

from files.backtest.engine import BacktestResult, run_backtest
from files.config import TradingConfig
from files.models.entry_model import EntryModel, EntryModelConfig
from files.research.scorer_parameter_space import ScorerTrial
from files.research.scorer_search_config import FIXED_SETTINGS
import files.strategy.rules as strategy_rules


ENTRY_MODEL_CONFIG_FIELDS: frozenset[str] = frozenset(
    field.name
    for field in fields(EntryModelConfig)
)


@dataclass(frozen=True)
class TrialRunRequest:
    trial: ScorerTrial
    runid: str
    trading_config: TradingConfig

    start_ts_ms: int | None = None
    end_ts_ms: int | None = None


@dataclass(frozen=True)
class TrialRunResult:
    trial_id: str
    runid: str

    scorer_config: dict[str, float]
    confidence_enter: float

    start_ts_ms: int | None
    end_ts_ms: int | None

    backtest: BacktestResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "runid": self.runid,
            "scorer_config": dict(self.scorer_config),
            "confidence_enter": self.confidence_enter,
            "start_ts_ms": self.start_ts_ms,
            "end_ts_ms": self.end_ts_ms,
            "backtest": asdict(self.backtest),
        }


def scorer_config_from_parameters(
    parameters: dict[str, float],
) -> EntryModelConfig:
    unknown_model_parameters = sorted(
        name
        for name in parameters
        if (
            name != "confidence_enter"
            and name not in ENTRY_MODEL_CONFIG_FIELDS
        )
    )

    if unknown_model_parameters:
        raise ValueError(
            "Trial contains unsupported scorer parameters: "
            f"{unknown_model_parameters}"
        )

    missing_model_parameters = sorted(
        name
        for name in ENTRY_MODEL_CONFIG_FIELDS
        if (
            name not in {"min_confidence", "max_confidence"}
            and name not in parameters
        )
    )

    if missing_model_parameters:
        raise ValueError(
            "Trial is missing scorer parameters: "
            f"{missing_model_parameters}"
        )

    config_values = {
        name: float(parameters[name])
        for name in ENTRY_MODEL_CONFIG_FIELDS
        if name in parameters
    }

    return EntryModelConfig(**config_values)


def confidence_enter_from_parameters(
    parameters: dict[str, float],
) -> float:
    if "confidence_enter" not in parameters:
        raise ValueError(
            "Trial is missing confidence_enter."
        )

    confidence_enter = float(
        parameters["confidence_enter"]
    )

    if not 0.0 <= confidence_enter <= 1.0:
        raise ValueError(
            "confidence_enter must be between 0.0 and 1.0."
        )

    return confidence_enter


def verify_fixed_strategy_contract() -> None:
    mismatches: list[str] = []

    if bool(strategy_rules.ENABLE_LONG) != FIXED_SETTINGS.enable_long:
        mismatches.append(
            "ENABLE_LONG "
            f"expected={FIXED_SETTINGS.enable_long!r} "
            f"actual={strategy_rules.ENABLE_LONG!r}"
        )

    if bool(strategy_rules.ENABLE_SHORT) != FIXED_SETTINGS.enable_short:
        mismatches.append(
            "ENABLE_SHORT "
            f"expected={FIXED_SETTINGS.enable_short!r} "
            f"actual={strategy_rules.ENABLE_SHORT!r}"
        )

    if float(strategy_rules.ATR_MULT) != FIXED_SETTINGS.atr_mult:
        mismatches.append(
            "ATR_MULT "
            f"expected={FIXED_SETTINGS.atr_mult!r} "
            f"actual={strategy_rules.ATR_MULT!r}"
        )

    if (
        float(strategy_rules.TRAIL_ATR_MULT)
        != FIXED_SETTINGS.trail_atr_mult
    ):
        mismatches.append(
            "TRAIL_ATR_MULT "
            f"expected={FIXED_SETTINGS.trail_atr_mult!r} "
            f"actual={strategy_rules.TRAIL_ATR_MULT!r}"
        )

    if (
        int(strategy_rules.MAX_HOLD_BARS)
        != FIXED_SETTINGS.max_hold_bars
    ):
        mismatches.append(
            "MAX_HOLD_BARS "
            f"expected={FIXED_SETTINGS.max_hold_bars!r} "
            f"actual={strategy_rules.MAX_HOLD_BARS!r}"
        )

    if FIXED_SETTINGS.event_risk_enabled:
        mismatches.append(
            "Phase 1 requires event_risk_enabled=False."
        )

    if mismatches:
        details = "\n".join(
            f"- {message}"
            for message in mismatches
        )

        raise RuntimeError(
            "Fixed strategy contract mismatch:\n"
            f"{details}"
        )


@contextmanager
def temporary_scorer_configuration(
    *,
    scorer_config: EntryModelConfig,
    confidence_enter: float,
) -> Iterator[None]:
    original_model = strategy_rules._model
    original_confidence_enter = (
        strategy_rules.CONFIDENCE_ENTER
    )

    try:
        strategy_rules._model = EntryModel(
            cfg=scorer_config
        )

        strategy_rules.CONFIDENCE_ENTER = float(
            confidence_enter
        )

        yield

    finally:
        strategy_rules._model = original_model
        strategy_rules.CONFIDENCE_ENTER = (
            original_confidence_enter
        )


def run_single_trial(
    request: TrialRunRequest,
) -> TrialRunResult:
    verify_fixed_strategy_contract()

    scorer_config = scorer_config_from_parameters(
        request.trial.parameters
    )

    confidence_enter = (
        confidence_enter_from_parameters(
            request.trial.parameters
        )
    )

    with temporary_scorer_configuration(
        scorer_config=scorer_config,
        confidence_enter=confidence_enter,
    ):
        backtest_result = run_backtest(
            runid=request.runid,
            cfg=request.trading_config,
            start_ts_ms=request.start_ts_ms,
            end_ts_ms=request.end_ts_ms,
        )

    return TrialRunResult(
        trial_id=request.trial.trial_id,
        runid=request.runid,
        scorer_config={
            key: float(value)
            for key, value in asdict(
                scorer_config
            ).items()
        },
        confidence_enter=confidence_enter,
        start_ts_ms=request.start_ts_ms,
        end_ts_ms=request.end_ts_ms,
        backtest=backtest_result,
    )
