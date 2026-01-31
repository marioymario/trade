# files/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable


def _get_env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    return val if val is not None and val.strip() != "" else default


def _parse_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    v = val.strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(
        f"Invalid boolean value {val!r} (expected 1/0 true/false yes/no on/off)"
    )


def _parse_int(
    val: str | None,
    *,
    default: int,
    name: str,
    min_value: int | None = None,
) -> int:
    if val is None:
        out = default
    else:
        try:
            out = int(val)
        except Exception as e:
            raise ValueError(f"{name} must be an int, got {val!r}") from e

    if min_value is not None and out < min_value:
        raise ValueError(f"{name} must be >= {min_value}, got {out}")
    return out


def _parse_float(
    val: str | None,
    *,
    default: float,
    name: str,
    min_value: float | None = None,
) -> float:
    if val is None:
        out = default
    else:
        try:
            out = float(val)
        except Exception as e:
            raise ValueError(f"{name} must be a float, got {val!r}") from e

    if min_value is not None and out < min_value:
        raise ValueError(f"{name} must be >= {min_value}, got {out}")
    return out


def _parse_csv(val: str | None) -> list[str]:
    if val is None or val.strip() == "":
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


def _validate_timeframe(timeframe: str) -> None:
    tf = timeframe.strip().lower()
    if len(tf) < 2:
        raise ValueError(f"TIMEFRAME invalid: {timeframe!r}")

    unit = tf[-1]
    num = tf[:-1]

    if unit not in {"m", "h", "d"}:
        raise ValueError(f"TIMEFRAME invalid: {timeframe!r} (expected suffix m/h/d)")
    try:
        n = int(num)
    except Exception as e:
        raise ValueError(
            f"TIMEFRAME invalid: {timeframe!r} (expected leading int)"
        ) from e
    if n <= 0:
        raise ValueError(f"TIMEFRAME invalid: {timeframe!r} (must be positive)")


def _validate_symbol(symbol: str) -> None:
    s = symbol.strip()
    if not s:
        raise ValueError("SYMBOL must be non-empty")
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_/.:")
    if any(ch not in allowed for ch in s):
        raise ValueError(f"SYMBOL contains unsupported characters: {symbol!r}")


def _require_in_allowlist(symbol: str, allowlist: Iterable[str]) -> None:
    allow = {s.strip() for s in allowlist if s.strip()}
    if allow and symbol not in allow:
        raise ValueError(
            f"SYMBOL {symbol!r} not in SYMBOL_ALLOWLIST={sorted(allow)!r}. "
            "Add it or clear SYMBOL_ALLOWLIST."
        )


@dataclass(frozen=True)
class TradingConfig:
    symbol: str
    timeframe: str
    loop_sleep_seconds: int
    dry_run: bool

    # Data source
    ccxt_exchange: str

    # Safety knobs
    max_order_size: float
    symbol_allowlist: tuple[str, ...]
    min_bars: int

    # Execution cost model (applied in paper broker)
    fee_bps: float
    slippage_bps: float

    # Strategy hygiene
    cooldown_bars: int


@dataclass(frozen=True)
class AlpacaConfig:
    api_key: str
    secret_key: str
    base_url: str


def load_trading_config() -> TradingConfig:
    """
    Env vars:
      SYMBOL=BTC/USD
      TIMEFRAME=5m
      LOOP_SLEEP_SECONDS=30
      DRY_RUN=1
      CCXT_EXCHANGE=coinbase

      MAX_ORDER_SIZE=1.0
      SYMBOL_ALLOWLIST=BTC/USD,ETH/USD
      MIN_BARS=200

      FEE_BPS=8.5
      SLIPPAGE_BPS=2.25

      COOLDOWN_BARS=3
    """
    symbol = str(_get_env("SYMBOL", "BTC/USD"))
    timeframe = str(_get_env("TIMEFRAME", "5m"))
    dry_run = _parse_bool(_get_env("DRY_RUN"), default=False)

    loop_sleep_seconds = _parse_int(
        _get_env("LOOP_SLEEP_SECONDS", "30"),
        default=30,
        name="LOOP_SLEEP_SECONDS",
        min_value=1,
    )

    max_order_size = _parse_float(
        _get_env("MAX_ORDER_SIZE", "1.0"),
        default=1.0,
        name="MAX_ORDER_SIZE",
        min_value=0.0,
    )

    min_bars = _parse_int(
        _get_env("MIN_BARS", "200"),
        default=200,
        name="MIN_BARS",
        min_value=50,
    )

    ccxt_exchange = str(_get_env("CCXT_EXCHANGE", "coinbase")).strip().lower()
    if not ccxt_exchange:
        raise ValueError("CCXT_EXCHANGE must be non-empty")

    fee_bps = _parse_float(
        _get_env("FEE_BPS", "8.5"),
        default=8.5,
        name="FEE_BPS",
        min_value=0.0,
    )
    slippage_bps = _parse_float(
        _get_env("SLIPPAGE_BPS", "2.25"),
        default=2.25,
        name="SLIPPAGE_BPS",
        min_value=0.0,
    )

    cooldown_bars = _parse_int(
        _get_env("COOLDOWN_BARS", "3"),
        default=3,
        name="COOLDOWN_BARS",
        min_value=0,
    )

    allowlist = tuple(_parse_csv(_get_env("SYMBOL_ALLOWLIST")))

    _validate_symbol(symbol)
    _validate_timeframe(timeframe)
    _require_in_allowlist(symbol, allowlist)

    return TradingConfig(
        symbol=symbol,
        timeframe=timeframe,
        loop_sleep_seconds=loop_sleep_seconds,
        dry_run=dry_run,
        ccxt_exchange=ccxt_exchange,
        max_order_size=max_order_size,
        symbol_allowlist=allowlist,
        min_bars=min_bars,
        fee_bps=float(fee_bps),
        slippage_bps=float(slippage_bps),
        cooldown_bars=int(cooldown_bars),
    )


def load_alpaca_config() -> AlpacaConfig:
    api_key = _get_env("ALPACA_API_KEY")
    secret_key = _get_env("ALPACA_SECRET_KEY")
    base_url = _get_env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not api_key or not secret_key:
        raise RuntimeError(
            "Missing Alpaca API credentials. "
            "Set ALPACA_API_KEY and ALPACA_SECRET_KEY in .env"
        )

    return AlpacaConfig(api_key=api_key, secret_key=secret_key, base_url=str(base_url))
