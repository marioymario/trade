from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
import random
from typing import Any

from files.research.scorer_search_config import (
    PARAMETER_RANGES,
    SEARCH_CONTROLS,
    RangeSpec,
)


WEIGHT_NAMES: tuple[str, ...] = (
    "weight_trend_strength",
    "weight_trend_slope",
    "weight_recent_return",
    "weight_rsi_quality",
)


@dataclass(frozen=True)
class ScorerTrial:
    trial_id: str
    parameters: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "parameters": dict(self.parameters),
        }


def stepped_values(spec: RangeSpec) -> tuple[float, ...]:
    minimum = Decimal(str(spec.minimum))
    maximum = Decimal(str(spec.maximum))
    step = Decimal(str(spec.step))

    if step <= 0:
        raise ValueError("Range step must be positive.")

    if maximum < minimum:
        raise ValueError("Range maximum must be >= minimum.")

    values: list[float] = []
    current = minimum

    while current <= maximum:
        values.append(float(current))
        current += step

    return tuple(values)


def parameter_value_space() -> dict[str, tuple[float, ...]]:
    return {
        name: stepped_values(spec)
        for name, spec in PARAMETER_RANGES.items()
    }


def normalize_weights(
    raw_parameters: dict[str, float],
) -> dict[str, float]:
    total = sum(
        float(raw_parameters[name])
        for name in WEIGHT_NAMES
    )

    if total <= 0.0:
        raise ValueError("Component-weight total must be positive.")

    normalized = dict(raw_parameters)

    for name in WEIGHT_NAMES:
        normalized[name] = (
            float(raw_parameters[name]) / total
        )

    return normalized


def add_symmetric_parameters(
    parameters: dict[str, float],
) -> dict[str, float]:
    completed = dict(parameters)

    completed["short_rsi_center"] = (
        100.0 - completed["long_rsi_center"]
    )

    completed["short_rsi_oversold"] = (
        100.0 - completed["long_rsi_overbought"]
    )

    return completed


def parameters_are_valid(
    parameters: dict[str, float],
) -> bool:
    tolerance = 1e-12

    weight_sum = sum(
        parameters[name]
        for name in WEIGHT_NAMES
    )

    if abs(weight_sum - 1.0) > tolerance:
        return False

    if (
        parameters["weight_rsi_quality"]
        > parameters["weight_recent_return"]
    ):
        return False

    if (
        parameters["weight_rsi_quality"]
        > parameters["weight_trend_slope"]
    ):
        return False

    if (
        parameters["atr_pct_full_penalty"]
        <= parameters["atr_pct_soft_penalty_start"]
    ):
        return False

    expected_short_center = (
        100.0 - parameters["long_rsi_center"]
    )

    if (
        abs(
            parameters["short_rsi_center"]
            - expected_short_center
        )
        > tolerance
    ):
        return False

    expected_short_oversold = (
        100.0 - parameters["long_rsi_overbought"]
    )

    if (
        abs(
            parameters["short_rsi_oversold"]
            - expected_short_oversold
        )
        > tolerance
    ):
        return False

    return True


def canonical_parameter_json(
    parameters: dict[str, float],
) -> str:
    return json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def trial_id_for_parameters(
    parameters: dict[str, float],
) -> str:
    payload = canonical_parameter_json(parameters)

    digest = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()

    return f"trial_{digest[:16]}"


def generate_trials(
    *,
    trial_count: int | None = None,
    random_seed: int | None = None,
) -> tuple[ScorerTrial, ...]:
    count = (
        SEARCH_CONTROLS.trial_count
        if trial_count is None
        else int(trial_count)
    )

    seed = (
        SEARCH_CONTROLS.random_seed
        if random_seed is None
        else int(random_seed)
    )

    if count <= 0:
        raise ValueError("trial_count must be positive.")

    value_space = parameter_value_space()
    parameter_names = tuple(value_space.keys())
    rng = random.Random(seed)

    trials: list[ScorerTrial] = []
    seen_ids: set[str] = set()

    max_attempts = max(count * 1000, 10000)
    attempts = 0

    while len(trials) < count:
        attempts += 1

        if attempts > max_attempts:
            raise RuntimeError(
                "Unable to generate enough unique valid trials."
            )

        raw = {
            name: rng.choice(value_space[name])
            for name in parameter_names
        }

        normalized = normalize_weights(raw)
        completed = add_symmetric_parameters(normalized)

        if not parameters_are_valid(completed):
            continue

        trial_id = trial_id_for_parameters(completed)

        if trial_id in seen_ids:
            continue

        seen_ids.add(trial_id)

        trials.append(
            ScorerTrial(
                trial_id=trial_id,
                parameters=completed,
            )
        )

    return tuple(trials)


def trials_as_dicts(
    trials: tuple[ScorerTrial, ...],
) -> list[dict[str, Any]]:
    return [
        trial.as_dict()
        for trial in trials
    ]
