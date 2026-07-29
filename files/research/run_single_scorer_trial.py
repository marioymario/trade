from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone

from files.config import load_trading_config
from files.research.scorer_parameter_space import generate_trials
from files.research.scorer_trial import TrialRunRequest, run_single_trial


def parse_utc_ts_ms(value: str | None) -> int | None:
    if value is None:
        return None

    text = value.strip()

    if not text:
        return None

    parsed = datetime.fromisoformat(
        text.replace("Z", "+00:00")
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    parsed = parsed.astimezone(timezone.utc)

    return int(parsed.timestamp() * 1000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one deterministic scorer research trial."
    )

    parser.add_argument(
        "--trial-index",
        type=int,
        default=0,
        help="Zero-based index from the deterministic trial sequence.",
    )

    parser.add_argument(
        "--start",
        required=True,
        help="UTC ISO-8601 trade-window start.",
    )

    parser.add_argument(
        "--end",
        required=True,
        help="UTC ISO-8601 replay end.",
    )

    parser.add_argument(
        "--runid",
        default=None,
        help="Optional explicit isolated backtest run ID.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    trials = generate_trials()

    if args.trial_index < 0 or args.trial_index >= len(trials):
        raise SystemExit(
            f"trial-index must be between 0 and {len(trials) - 1}"
        )

    trial = trials[args.trial_index]

    start_ts_ms = parse_utc_ts_ms(args.start)
    end_ts_ms = parse_utc_ts_ms(args.end)

    if start_ts_ms is None or end_ts_ms is None:
        raise SystemExit("Both --start and --end are required.")

    if end_ts_ms < start_ts_ms:
        raise SystemExit("--end must be >= --start.")

    runid = args.runid or (
        f"research_{trial.trial_id}_"
        f"{start_ts_ms}_{end_ts_ms}"
    )

    result = run_single_trial(
        TrialRunRequest(
            trial=trial,
            runid=runid,
            trading_config=load_trading_config(),
            start_ts_ms=start_ts_ms,
            end_ts_ms=end_ts_ms,
        )
    )

    print(
        json.dumps(
            result.as_dict(),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
