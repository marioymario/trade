from __future__ import annotations

import argparse
import json

from files.research.entry_quality_structural_search import (
    run_entry_quality_structural_search,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--btc-feature-dataset-id",
        required=True,
    )

    parser.add_argument(
        "--btc-outcome-dataset-id",
        required=True,
    )

    parser.add_argument(
        "--eth-feature-dataset-id",
        required=True,
    )

    parser.add_argument(
        "--eth-outcome-dataset-id",
        required=True,
    )

    parser.add_argument(
        "--permutations",
        type=int,
        default=10_000,
    )

    parser.add_argument(
        "--random-seed",
        type=int,
        default=20260811,
    )

    parser.add_argument(
        "--verify-only",
        action="store_true",
    )

    args = parser.parse_args()

    manifest = (
        run_entry_quality_structural_search(
            btc_feature_dataset_id=(
                args.btc_feature_dataset_id
            ),
            btc_outcome_dataset_id=(
                args.btc_outcome_dataset_id
            ),
            eth_feature_dataset_id=(
                args.eth_feature_dataset_id
            ),
            eth_outcome_dataset_id=(
                args.eth_outcome_dataset_id
            ),
            permutation_count=(
                args.permutations
            ),
            random_seed=(
                args.random_seed
            ),
            write_artifacts=(
                not args.verify_only
            ),
        )
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
