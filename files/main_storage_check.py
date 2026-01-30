# files/main_storage_check.py
from __future__ import annotations

from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
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

    append_ohlcv_parquet(df=df, exchange=cfg.ccxt_exchange, symbol=cfg.symbol, timeframe=cfg.timeframe)

    out = load_recent_ohlcv_parquet(exchange=cfg.ccxt_exchange, symbol=cfg.symbol, timeframe=cfg.timeframe, tail_n=cfg.min_bars)
    logger.info("✅ Storage OK", extra={"rows": len(out)})
    logger.info("Tail:\n%s", out.tail(5).to_string(index=False))

if __name__ == "__main__":
    main()

