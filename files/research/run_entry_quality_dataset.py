from __future__ import annotations

import argparse
import json
from pathlib import Path

from files.research.entry_quality_dataset import (
    build_entry_quality_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build or verify the deterministic entry-quality "
            "signal-structure research dataset."
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
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help=(
            "Build and validate the complete dataset in memory "
            "without writing research artifacts. Intended for "
            "pre-commit OLD-BOX verification."
        ),
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    campaign_root = (
        Path("data/processed/research/scorer_campaigns")
        / args.campaign_id
    )

    manifest = build_entry_quality_dataset(
        campaign_root=campaign_root,
        trial_id=args.trial_id,
        write_artifacts=not args.verify_only,
    )

    print(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
