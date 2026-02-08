# files/main_data_quality_check.py
from __future__ import annotations

from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    cfg = load_trading_config()

    df = fetch_market_data(
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        limit=max(cfg.min_bars, 200) + 5,
        min_bars_warn=cfg.min_bars,
        ccxt_exchange=cfg.ccxt_exchange,  # fetch source
    )

    # This check is about fetch quality only; no storage writes.
    logger.info(
        "✅ main_data_quality_check OK",
        extra={
            "rows": len(df),
            "ccxt_exchange": cfg.ccxt_exchange,
            "data_tag": cfg.data_tag,
        },
    )


if __name__ == "__main__":
    main()
