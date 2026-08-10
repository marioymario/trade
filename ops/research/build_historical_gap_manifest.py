from __future__ import annotations

import argparse
import json
from pathlib import Path

from files.research.historical_manifest_builder import (
    build_historical_gap_manifest,
    canonical_manifest_path,
    write_historical_gap_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a stored historical OHLCV dataset, verify "
            "missing timeframe intervals against the 1m source "
            "feed, and build its gap manifest."
        )
    )

    parser.add_argument("--source-exchange", required=True)
    parser.add_argument("--data-tag", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)

    parser.add_argument(
        "--data-root",
        default="/work/data",
    )

    parser.add_argument(
        "--write",
        action="store_true",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    manifest = build_historical_gap_manifest(
        source_exchange=args.source_exchange,
        data_tag=args.data_tag,
        symbol=args.symbol,
        timeframe=args.timeframe,
        dataset_start_utc=args.start,
        dataset_end_utc_exclusive=args.end,
        data_root=Path(args.data_root),
    )

    output = canonical_manifest_path(
        data_tag=args.data_tag
    )

    if args.write:
        write_historical_gap_manifest(
            manifest=manifest,
            output_path=output,
        )

    print(
        json.dumps(
            {
                "status": "ok",
                "mode": "write" if args.write else "dry-run",
                "output_path": str(output),
                "schema_version": manifest["schema_version"],
                "stored_bar_count": manifest["stored_bar_count"],
                "missing_bar_count": manifest["missing_bar_count"],
                "partition_count": manifest["partition_count"],
                "gap_count": len(manifest["gaps"]),
                "classification_counts": {
                    classification: sum(
                        1
                        for gap in manifest["gaps"]
                        if gap["classification"] == classification
                    )
                    for classification in sorted(
                        {
                            gap["classification"]
                            for gap in manifest["gaps"]
                        }
                    )
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
