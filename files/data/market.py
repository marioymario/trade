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
    s = symbol.strip().upper()

    if "/" in s:
        return s

    s = s.replace("_", "").replace("-", "")

    for quote in ("USDT", "USD"):
        if s.endswith(quote) and len(s) > len(quote):
            base = s[: -len(quote)]
            return f"{base}/{quote}"

    return s


def _parse_timeframe_seconds(timeframe: str) -> int:
    tf = timeframe.strip().lower()
    unit = tf[-1]
    n = int(tf[:-1])

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
    import ccxt

    key = exchange_id.strip().lower()

    if key in _CCXT_EXCHANGE_CACHE:
        return _CCXT_EXCHANGE_CACHE[key]

    ex_class = getattr(ccxt, key)

    exchange = ex_class(
        {
            "enableRateLimit": True,
        }
    )

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

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp_ms", "open", "high", "low", "close", "volume"],
    )

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

    # TEST HOOK — deterministic cadence failure
    if os.environ.get("TEST_HOOKS_ENABLED") == "1":
        try:
            n = int(os.environ.get("FORCE_CADENCE_FAIL_N", "0"))
        except Exception:
            n = 0

        if n > 0 and rows > 15:
            os.environ["FORCE_CADENCE_FAIL_N"] = str(n - 1)

            # shift HALF the timestamps to break median cadence
            half = rows // 2

            for i in range(1, half + 1):
                idx = df.index[-i]
                df.loc[idx, "timestamp"] = (
                    df.loc[idx, "timestamp"]
                    + pd.Timedelta(seconds=expected_s * 4)
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
