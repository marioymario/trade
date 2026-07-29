from __future__ import annotations

import json

from files.config import load_trading_config
from files.research.scorer_walk_forward import (
    resolve_walk_forward_splits,
)


def main() -> None:
    trading_config = load_trading_config()

    resolved, data_min, data_max, bar_count = (
        resolve_walk_forward_splits(
            trading_config=trading_config,
        )
    )

    payload = {
        "data": {
            "data_tag": trading_config.data_tag,
            "symbol": trading_config.symbol,
            "timeframe": trading_config.timeframe,
            "bar_count": bar_count,
            "minimum_timestamp": data_min.isoformat(),
            "maximum_timestamp": data_max.isoformat(),
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
