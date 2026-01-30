# files/main_correctness_check.py
from __future__ import annotations

from files.broker.paper import _map_strategy_side_to_alpaca


def main() -> None:
    assert _map_strategy_side_to_alpaca("LONG") == "buy"
    assert _map_strategy_side_to_alpaca("SHORT") == "sell"
    print("✅ Correctness OK: side mapping")


if __name__ == "__main__":
    main()

