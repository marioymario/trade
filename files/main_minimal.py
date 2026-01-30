# files/main_minimal.py
from __future__ import annotations

from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.features import compute_features
from files.strategy.filters import determine_market_state
from files.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    cfg = load_trading_config()
    logger.info("Minimal run starting")

    data = fetch_market_data(symbol=cfg.symbol, timeframe=cfg.timeframe)
    if data is None:
        logger.warning("No data returned")
        return

    feats = compute_features(data)
    market_state = determine_market_state(feats)

    logger.info(f"Market state: {market_state}")


if __name__ == "__main__":
    main()


