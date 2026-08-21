from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from files.research.run_adaptive_range_confirmation import (
    BASELINE_POLICY_ID,
    CONFIRMATION_END_EXCLUSIVE,
    CONFIRMATION_START,
    EXPECTED_2025_POLICY,
    PRIMARY_SYMBOLS,
    RANGE_POLICY_ID,
    load_confirmation_contract,
    load_universe_contract,
    resolve_primary_members,
    run_execution,
)


EXPERIMENT_ID = "range_factor_2025_counterfactual_completion_v1"

OUTPUT_ROOT = (
    Path("data/processed/research/experiments")
    / EXPERIMENT_ID
)

MISSING_RANGE_SYMBOLS = (
    "ETH/USD",
    "DOGE/USD",
    "LTC/USD",
)


class CompletionError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Complete the missing 2025 RANGE counterfactuals needed "
            "to derive the chronological 2026 adaptive-range map."
        )
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
    )

    return parser


def validate_contract() -> None:
    load_confirmation_contract()

    if tuple(
        symbol
        for symbol in PRIMARY_SYMBOLS
        if EXPECTED_2025_POLICY[symbol]
        == BASELINE_POLICY_ID
    ) != MISSING_RANGE_SYMBOLS:
        raise CompletionError(
            "Missing-range symbol set no longer matches the frozen "
            "2025 adaptive policy."
        )

    if CONFIRMATION_START != "2025-01-01T00:00:00Z":
        raise CompletionError(
            "2025 start boundary changed."
        )

    if CONFIRMATION_END_EXCLUSIVE != "2026-01-01T00:00:00Z":
        raise CompletionError(
            "2025 end boundary changed."
        )


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.exists():
        raise CompletionError(
            f"Refusing to overwrite artifact: {path}"
        )

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    args = build_parser().parse_args()

    validate_contract()

    universe = load_universe_contract()

    members = resolve_primary_members(
        universe
    )

    member_by_symbol = {
        str(member["symbol"]): member
        for member in members
    }

    plan = {
        "experiment_id": EXPERIMENT_ID,
        "purpose": (
            "Complete missing 2025 RANGE counterfactuals before "
            "mechanically deriving the 2026 adaptive-range map."
        ),
        "start_inclusive": CONFIRMATION_START,
        "end_exclusive": CONFIRMATION_END_EXCLUSIVE,
        "policy_id": RANGE_POLICY_ID,
        "symbols": list(MISSING_RANGE_SYMBOLS),
        "execution_count": len(
            MISSING_RANGE_SYMBOLS
        ),
        "reserved_2026_outcomes_consumed": False,
    }

    if args.plan_only:
        print(
            json.dumps(
                plan,
                indent=2,
                sort_keys=True,
            )
        )
        return

    if OUTPUT_ROOT.exists():
        raise CompletionError(
            "Completion output root already exists; refusing "
            f"to overwrite: {OUTPUT_ROOT}"
        )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=False,
    )

    write_json(
        OUTPUT_ROOT / "execution_plan.json",
        plan,
    )

    executions = []

    for symbol in MISSING_RANGE_SYMBOLS:
        result = run_execution(
            symbol=symbol,
            member=member_by_symbol[symbol],
            role="counterfactual_range",
            use_range_gate=True,
        )

        executions.append(
            result
        )

        write_json(
            OUTPUT_ROOT
            / "executions"
            / f"{symbol.replace('/', '_')}.json",
            result,
        )

    result = {
        "experiment_id": EXPERIMENT_ID,
        "window": {
            "start_inclusive": (
                CONFIRMATION_START
            ),
            "end_exclusive": (
                CONFIRMATION_END_EXCLUSIVE
            ),
        },
        "policy_id": RANGE_POLICY_ID,
        "execution_count": len(
            executions
        ),
        "executions": executions,
        "reserved_2026_outcomes_consumed": False,
    }

    write_json(
        OUTPUT_ROOT / "result.json",
        result,
    )

    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
