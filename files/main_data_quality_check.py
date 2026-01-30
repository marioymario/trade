# files/main_data_quality_check.py
from __future__ import annotations

from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.quality import assess_ohlcv
from files.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    cfg = load_trading_config()

    df = fetch_market_data(
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        limit=max(cfg.min_bars, 200),
        ccxt_exchange=cfg.ccxt_exchange,
        min_bars_warn=cfg.min_bars,
    )

    rep = assess_ohlcv(df)

    logger.info(
        "Data quality report",
        extra={
            "exchange": cfg.ccxt_exchange,
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "rows": rep.rows,
            "tz_aware": rep.tz_aware,
            "monotonic": rep.monotonic,
            "duplicates": rep.duplicates,
            "median_step_s": rep.median_step_s,
            "min_step_s": rep.min_step_s,
            "max_step_s": rep.max_step_s,
        },
    )

    tail = df[["timestamp", "open", "high", "low", "close", "volume"]].tail(5)
    logger.info("Tail bars:\n%s", tail.to_string(index=False))


if __name__ == "__main__":
    main()


