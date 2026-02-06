# files/data/market.py
from __future__ import annotations

from typing import Literal, Optional, Dict, Any
import os
import time

import pandas as pd

from files.utils.logger import get_logger

logger = get_logger(__name__)

AssetClass = Literal["crypto", "stocks"]

_CCXT_EXCHANGE_CACHE: Dict[str, Any] = {}


class MarketFetchError(RuntimeError):
    """Raised when market data cannot be fetched after retry policy (if enabled)."""


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


def _normalize_crypto_symbol_for_ccxt(symbol: str) -> str:
    """
    CCXT expects 'BASE/QUOTE' like 'BTC/USD' or 'BTC/USDT'.

    Accept common variants:
      - 'BTC/USD' (kept)
      - 'BTCUSDT' -> 'BTC/USDT'
      - 'BTCUSD'  -> 'BTC/USD'
      - 'BTC_USD' -> 'BTC/USD'
      - 'BTC-USD' -> 'BTC/USD'
    """
    s = symbol.strip().upper()

    # already normalized
    if "/" in s:
        return s

    # tolerate common separators
    s = s.replace("_", "").replace("-", "")

    for quote in ("USDT", "USD"):
        if s.endswith(quote) and len(s) > len(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"

    return s


def _parse_timeframe_seconds(timeframe: str) -> int:
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
    needed = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"Market DF missing columns: {missing}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"])
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out[needed]


def _get_ccxt_exchange(exchange_id: str):
    import ccxt  # type: ignore

    key = (exchange_id or "").strip().lower()
    if not key:
        raise ValueError("ccxt_exchange must be non-empty")

    if key in _CCXT_EXCHANGE_CACHE:
        return _CCXT_EXCHANGE_CACHE[key]

    ex_class = getattr(ccxt, key)
    exchange = ex_class({"enableRateLimit": True})
    _CCXT_EXCHANGE_CACHE[key] = exchange
    return exchange


def _fetch_crypto_ccxt(
    *,
    symbol: str,
    timeframe: str,
    limit: int,
    exchange_id: str,
) -> pd.DataFrame:
    exchange = _get_ccxt_exchange(exchange_id)

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
    if asset_class != "crypto":
        raise NotImplementedError("Only crypto implemented right now")

    if limit <= 0:
        raise ValueError("limit must be > 0")

    expected_s = _parse_timeframe_seconds(timeframe)

    retries = max(0, _env_int("MARKET_FETCH_RETRIES", 0))
    backoff_s = max(0.0, _env_float("MARKET_FETCH_BACKOFF_S", 0.0))

    last_err: Optional[BaseException] = None
    attempt_total = 1 + retries

    for attempt in range(1, attempt_total + 1):
        try:
            df = _fetch_crypto_ccxt(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
                exchange_id=ccxt_exchange,
            )
            break
        except Exception as e:
            last_err = e
            logger.warning(
                "Market fetch failed",
                extra={
                    "attempt": attempt,
                    "attempt_total": attempt_total,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "limit": int(limit),
                    "exchange": ccxt_exchange,
                    "error": repr(e),
                },
            )
            if attempt >= attempt_total:
                raise MarketFetchError(
                    f"fetch_market_data failed after {attempt_total} attempt(s): {repr(last_err)}"
                ) from last_err
            if backoff_s > 0:
                time.sleep(backoff_s)

    rows = len(df)

    if min_bars_warn is not None and rows < min_bars_warn:
        logger.warning(
            "Too few bars returned",
            extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": int(rows),
                "min_bars": int(min_bars_warn),
                "source": "ccxt",
                "exchange": ccxt_exchange,
            },
        )

    if enforce_regular_cadence and rows >= 3:
        diffs = df["timestamp"].diff().dt.total_seconds().dropna()
        if len(diffs) > 0:
            med = float(diffs.median())
            if med > expected_s * 2.5:
                logger.warning(
                    "Bars appear sparse for requested timeframe",
                    extra={
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "median_spacing_s": med,
                        "expected_s": int(expected_s),
                        "rows": int(rows),
                        "source": "ccxt",
                        "exchange": ccxt_exchange,
                    },
                )

    logger.info(
        "Fetched market data",
        extra={
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": int(rows),
            "source": "ccxt",
            "exchange": ccxt_exchange,
        },
    )
    return df


