# files/data/decisions.py
from __future__ import annotations

import csv
import os
import re
from typing import Any, Dict, Optional

from files.data.paths import decisions_csv_path as _decisions_csv_path


DECISION_FIELDS = [
    # identity
    "exchange",
    "symbol",
    "timeframe",

    # bar timing + OHLC debug
    "ts_ms",
    "timestamp",
    "bar_high",
    "bar_low",

    # market state
    "tradable",
    "trend",
    "volatility",
    "market_reason",
    "cooldown_remaining_bars",

    # position snapshot
    "position_side",
    "position_qty",
    "position_entry_price",
    "position_stop_price",
    "position_trailing_anchor_price",
    "unrealized_pnl_usd",
    "unrealized_pnl_pct",

    # trailing stop debug
    "trail_reason",
    "trail_new_stop",
    "trail_new_anchor",

    # entry decision
    "entry_should_enter",
    "entry_side",
    "entry_confidence",
    "entry_reason",
    "entry_blocked_reason",

    # exit decision
    "exit_should_exit",
    "exit_reason",
]


def decisions_csv_path(*, exchange: str, symbol: str, timeframe: str) -> str:
    """
    NOTE: `exchange` is a DATA TAG used in the filesystem layout.
    It may match CCXT exchange id (e.g. coinbase) but does not have to.
    """
    return str(_decisions_csv_path(exchange=exchange, symbol=symbol, timeframe=timeframe))


def _env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    s = str(v).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "on")


def _safe_int(x) -> Optional[int]:
    try:
        if x in (None, "", "nan"):
            return None
        return int(float(x))
    except Exception:
        return None


_WS_RE = re.compile(r"\s+")


def _sanitize_csv_value(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, str):
        s = v.replace("\r", " ").replace("\n", " ")
        s = _WS_RE.sub(" ", s).strip()
        return s
    return v


def _read_last_ts_ms_from_decisions_csv(path: str) -> Optional[int]:
    try:
        if (not os.path.exists(path)) or os.path.getsize(path) == 0:
            return None

        last: Optional[int] = None
        with open(path, "r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                ts = _safe_int((row or {}).get("ts_ms"))
                if ts is not None and ts > 0:
                    last = ts
        return last
    except Exception:
        return None


def append_decision_csv(
    *,
    decision: Dict[str, Any],
    exchange: str,
    symbol: str,
    timeframe: str,
) -> str:
    path = decisions_csv_path(exchange=exchange, symbol=symbol, timeframe=timeframe)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    enforce_monotonic = _env_flag("ENFORCE_DECISION_MONOTONIC", default=False)
    if enforce_monotonic:
        new_ts = _safe_int(decision.get("ts_ms"))
        if new_ts is None or new_ts <= 0:
            raise ValueError(
                f"[decisions] ENFORCE_DECISION_MONOTONIC=1 but decision.ts_ms is invalid: {decision.get('ts_ms')!r}"
            )

        last_ts = _read_last_ts_ms_from_decisions_csv(path)
        if last_ts is not None and new_ts <= int(last_ts):
            raise ValueError(
                f"[decisions] Monotonicity violation for {path}: new_ts_ms={new_ts} <= last_ts_ms={last_ts}"
            )

    if _env_flag("WARN_DECISION_SCHEMA_DRIFT", default=False):
        extra_keys = sorted(set(decision.keys()) - set(DECISION_FIELDS))
        if extra_keys:
            print(f"[decisions] WARNING: decision has extra keys not in DECISION_FIELDS (dropped): {extra_keys}")

    row: Dict[str, Any] = {k: "" for k in DECISION_FIELDS}
    row["exchange"] = exchange
    row["symbol"] = symbol
    row["timeframe"] = timeframe

    for k in DECISION_FIELDS:
        if k in ("exchange", "symbol", "timeframe"):
            continue
        if k in decision:
            row[k] = _sanitize_csv_value(decision[k])

    file_exists = os.path.exists(path)
    write_header = (not file_exists) or (os.path.getsize(path) == 0)

    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DECISION_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)

    return path
