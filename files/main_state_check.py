# files/main_state_check.py
from __future__ import annotations

from files.config import load_trading_config
from files.data.market import fetch_market_data
from files.data.storage import append_ohlcv_parquet, load_recent_ohlcv_parquet
from files.data.features import compute_features, validate_latest_features
from files.strategy.filters import determine_market_state
from files.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    cfg = load_trading_config()

    logger.info(
        "State check config",
        extra={
            "symbol": cfg.symbol,
            "timeframe": cfg.timeframe,
            "ccxt_exchange": cfg.ccxt_exchange,  # fetch source
            "data_tag": cfg.data_tag,            # storage tag
        },
    )

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
    out = load_recent_ohlcv_parquet(
        exchange=cfg.data_tag,  # storage tag
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        tail_n=cfg.min_bars,
    )

    feats = compute_features(out)
    validate_latest_features(feats)

    st = determine_market_state(
        feats,
        timeframe=cfg.timeframe,
        min_bars=cfg.min_bars,
    )
    logger.info(
        "✅ main_state_check OK",
        extra={
            "tradable": st.tradable,
            "trend": st.trend,
            "volatility": st.volatility,
            "reason": st.reason,
        },
    )


if __name__ == "__main__":
    main()
