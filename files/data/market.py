# files/data/market.py
from __future__ import annotations

from typing import Literal, Optional

import pandas as pd

from files.utils.logger import get_logger

logger = get_logger(__name__)

AssetClass = Literal["crypto", "stocks"]


def _normalize_crypto_symbol_for_ccxt(symbol: str) -> str:
    """
    CCXT expects 'BASE/QUOTE' like 'BTC/USD' or 'BTC/USDT'.

    Accept:
      - 'BTC/USD' (kept)
      - 'BTCUSDT' -> 'BTC/USDT'
      - 'BTCUSD'  -> 'BTC/USD'
    """
    s = symbol.strip().upper()
    if "/" in s:
        return s

    for quote in ("USDT", "USD"):
        if s.endswith(quote) and len(s) > len(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"

    return s


def _parse_timeframe_seconds(timeframe: str) -> int:
    """
    Accepts '1m', '5m', '15m', '1h', '1d' and returns seconds.
    """
    tf = timeframe.strip().lower()
    if len(tf) < 2:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")

    unit = tf[-1]
    n = int(tf[:-1])

    if n <= 0:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")

    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 60 * 60
    if unit == "d":
        return n * 60 * 60 * 24

    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def _ensure_ohlcv_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforce stable schema:
      timestamp (tz-aware UTC), open, high, low, close, volume
    """
    needed = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Market DF missing columns: {missing}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerse")
    out = out.dropna(subset=["timestamp"])
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out[needed]


def _fetch_crypto_ccxt(
    *,
    symbol: str,
    timeframe: str,
    limit: int,
    exchange_id: str,
) -> pd.DataFrame:
    import ccxt  # type: ignore

    ex_class = getattr(ccxt, exchange_id)
    exchange = ex_class({"enableRateLimit": True})

    sym = _normalize_crypto_symbol_for_ccxt(symbol)

    ohlcv = exchange.fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp_ms", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp_ms"])
    return _ensure_ohlcv_schema(df)


def fetch_market_data(
    *,
    symbol: str,
    timeframe: str,
    asset_class: AssetClass = "crypto",
    limit: int = 200,
    ccxt_exchange: str = "coinbase",
    min_bars_warn: Optional[int] = None,
    enforce_regular_cadence: bool = True,
) -> pd.DataFrame:
    """
    Market data entrypoint (CCXT-only for now).

    - ccxt_exchange: 'coinbase' or 'kraken' are good defaults.
    - min_bars_warn: logs warning if fewer than this returned
    - enforce_regular_cadence: warn if bars spacing is way larger than expected
    """
    if asset_class != "crypto":
        raise NotImplementedError("Only crypto implemented right now")

    if limit <= 0:
        raise ValueError("limit must be > 0")

    expected_s = _parse_timeframe_seconds(timeframe)

    df = _fetch_crypto_ccxt(
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        exchange_id=ccxt_exchange,
    )

    rows = len(df)

    if min_bars_warn is not None and rows < min_bars_warn:
        logger.warning(
            "Too few bars returned",
            extra={"symbol": symbol, "timeframe": timeframe, "rows": rows, "min_bars": min_bars_warn, "source": "ccxt", "exchange": ccxt_exchange},
        )

    if enforce_regular_cadence and rows >= 3:
        diffs = df["timestamp"].diff().dt.total_seconds().dropna()
        if len(diffs) > 0:
            med = float(diffs.median())
            # if median spacing is > 2.5x expected, this is not the timeframe you think it is
            if med > expected_s * 2.5:
                logger.warning(
                    "Bars appear sparse for requested timeframe",
                    extra={"symbol": symbol, "timeframe": timeframe, "median_spacing_s": med, "expected_s": expected_s, "rows": rows, "source": "ccxt", "exchange": ccxt_exchange},
                )

    logger.info(
        "Fetched market data",
        extra={"symbol": symbol, "timeframe": timeframe, "rows": rows, "source": "ccxt", "exchange": ccxt_exchange},
    )
    return df

