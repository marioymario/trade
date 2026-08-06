from __future__ import annotations

import argparse
import json
from pathlib import Path

from files.research.scorer_stop_diagnostic import (
    build_stop_diagnostic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruct read-only stop behavior from completed "
            "scorer campaign artifacts."
        )
    )

    parser.add_argument(
        "--campaign-id",
        required=True,
    )

    parser.add_argument(
        "--trial-id",
        required=True,
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    campaign_root = Path(
        "data/processed/research/scorer_campaigns"
    ) / args.campaign_id

    summary = build_stop_diagnostic(
        campaign_root=campaign_root,
        trial_id=args.trial_id,
        write_artifacts=True,
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
