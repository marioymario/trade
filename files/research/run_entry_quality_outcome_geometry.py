from __future__ import annotations

import argparse
import json

from files.research.entry_quality_outcome_geometry import (
    build_entry_quality_outcome_geometry,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source-dataset-id",
        required=True,
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
    )

    args = parser.parse_args()

    manifest = (
        build_entry_quality_outcome_geometry(
            source_dataset_id=(
                args.source_dataset_id
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
