# files/main_smoke.py
from __future__ import annotations

import os

from files.config import load_trading_config, load_alpaca_config
from files.data.market import fetch_market_data
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.features import compute_features, validate_latest_features
from files.utils.logger import get_logger

logger = get_logger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "t", "yes", "y", "on")


def main() -> None:
    """
    Smoke test:
      - loads TradingConfig
      - optionally validates Alpaca env keys (if REQUIRE_ALPACA=1)
      - fetches market data via CCXT (cfg.ccxt_exchange)
      - persists bars (to cfg.data_tag)
      - computes features and validates latest row has no NaNs
    """
    cfg = load_trading_config()

    if _env_flag("REQUIRE_ALPACA", default=False):
        _ = load_alpaca_config()
        logger.info("✅ Alpaca env OK (REQUIRE_ALPACA=1)")
    else:
        logger.info("Skipping Alpaca env check (set REQUIRE_ALPACA=1 to enforce)")

    df = fetch_market_data(
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        limit=max(cfg.min_bars, 200) + 5,
        min_bars_warn=cfg.min_bars,
        ccxt_exchange=cfg.ccxt_exchange,  # fetch source
    )

    append_ohlcv_parquet(
        df=df,
        exchange=cfg.data_tag,  # storage tag
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
    )
    tail = load_recent_ohlcv_parquet(
        exchange=cfg.data_tag,  # storage tag
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        tail_n=10,
    )

    feats = compute_features(tail)
    validate_latest_features(feats)

    logger.info(
        "✅ smoke OK",
        extra={
            "ccxt_exchange": cfg.ccxt_exchange,
            "data_tag": cfg.data_tag,
        },
    )


if __name__ == "__main__":
    main()
