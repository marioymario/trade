from __future__ import annotations

import json

from files.config import load_trading_config
from files.research.scorer_walk_forward import (
    resolve_walk_forward_splits,
)


def main() -> None:
    trading_config = load_trading_config()

    resolved, source = resolve_walk_forward_splits(
        trading_config=trading_config,
    )

    payload = {
        "source": {
            "data_tag": source.data_tag,
            "symbol": source.symbol,
            "timeframe": source.timeframe,
            "timeframe_step_ms": source.timeframe_step_ms,
            "stored_bar_count": source.stored_bar_count,
            "gap_count": source.gap_count,
            "physical_segment_count": (
                source.physical_segment_count
            ),
            "dataset_start_ts_ms": (
                source.dataset_start_ts_ms
            ),
            "dataset_end_ts_ms_exclusive": (
                source.dataset_end_ts_ms_exclusive
            ),
            "first_available_ts_ms": (
                source.first_available_ts_ms
            ),
            "last_available_ts_ms": (
                source.last_available_ts_ms
            ),
            "manifest_path": str(source.manifest_path),
            "manifest_fingerprint": (
                source.manifest_fingerprint
            ),
        },
        "walk_forward_splits": [
            split.as_dict()
            for split in resolved
        ],
    }

    print()
    print("=== RESOLVED WALK-FORWARD SPLITS ===")
    print(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
    )
    print("====================================")
    print()


if __name__ == "__main__":
    main()
