# files/data/trades.py
from __future__ import annotations

import csv
import os
from typing import Any, Dict

from files.data.paths import trades_csv_path as _trades_csv_path


TRADE_FIELDS = [
    "exchange",
    "symbol",
    "timeframe",
    "entry_ts_ms",
    "exit_ts_ms",
    "side",
    "qty",
    "entry_price",
    "exit_price",
    "exit_reason",
    "fee_bps",
    "slippage_bps",
    "cost_usd",
    "realized_pnl_usd",
    "realized_pnl_pct",
    "cum_realized_pnl_usd",
    "trades_closed",
    "stop_price",
    "market_reason",
]


def trades_csv_path(*, exchange: str, symbol: str, timeframe: str) -> str:
    return str(_trades_csv_path(exchange=exchange, symbol=symbol, timeframe=timeframe))


def append_trade_csv(
    *,
    trade: Dict[str, Any],
    exchange: str,
    symbol: str,
    timeframe: str,
    market_reason: str | None = None,
) -> str:
    """
    Append one closed trade to CSV.
    Creates directories and header if needed.

    Returns the path written to.
    """
    path = trades_csv_path(exchange=exchange, symbol=symbol, timeframe=timeframe)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    row: Dict[str, Any] = {k: "" for k in TRADE_FIELDS}
    row["exchange"] = exchange
    row["symbol"] = symbol
    row["timeframe"] = timeframe
    row["market_reason"] = market_reason or ""

    for k in TRADE_FIELDS:
        if k in ("exchange", "symbol", "timeframe", "market_reason"):
            continue
        if k in trade:
            row[k] = trade[k]

    file_exists = os.path.exists(path)
    write_header = (not file_exists) or (os.path.getsize(path) == 0)

    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRADE_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)

    return path
