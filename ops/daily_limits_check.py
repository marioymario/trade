#!/usr/bin/env python3
"""
ops/daily_limits_check.py

Checks "today" trade count and realized PnL from a trades.csv file.

Exit codes:
  0 = OK (limits not exceeded OR limits disabled OR file missing)
  2 = LIMITS EXCEEDED
  3 = ERROR (bad input)
"""

from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None  # type: ignore


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--trades-csv", required=True)
    p.add_argument("--max-trades-per-day", type=float, default=0.0)
    p.add_argument("--max-daily-loss-usd", type=float, default=0.0)
    p.add_argument("--tz", default="America/Los_Angeles")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args()


def pick_ts_ms(row: dict) -> int | None:
    for k in ("exit_ts_ms", "entry_ts_ms", "ts_ms"):
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            return int(float(v))
        except Exception:
            continue
    return None


def pick_pnl_usd(row: dict) -> float:
    for k in ("realized_pnl_usd", "pnl_usd", "realized_pnl"):
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except Exception:
            continue
    return 0.0


def main() -> int:
    a = parse_args()

    max_trades = float(a.max_trades_per_day)
    max_loss = float(a.max_daily_loss_usd)

    # Disabled => OK
    if max_trades <= 0 and max_loss <= 0:
        return 0

    trades_csv = a.trades_csv
    if not trades_csv or not os.path.exists(trades_csv):
        # No file yet => OK
        return 0

    tz = None
    if ZoneInfo is not None:
        try:
            tz = ZoneInfo(a.tz)
        except Exception:
            tz = None

    now = datetime.now(tz or timezone.utc)
    start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start_day.timestamp() * 1000)

    trades_today = 0
    pnl_today = 0.0

    try:
        with open(trades_csv, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                ts = pick_ts_ms(row)
                if ts is None or ts < start_ms:
                    continue
                trades_today += 1
                pnl_today += pick_pnl_usd(row)
    except Exception as e:
        if not a.quiet:
            print(f"ERROR reading trades csv: {e}")
        return 3

    if not a.quiet:
        print(f"daily_check: trades_today={trades_today}, pnl_today_usd={pnl_today:.2f}")

    exceeded = False
    if max_trades > 0 and trades_today >= max_trades:
        exceeded = True
        if not a.quiet:
            print(f"DAILY_LIMIT: trades_today {trades_today} >= {int(max_trades)}")
    if max_loss > 0 and pnl_today <= -max_loss:
        exceeded = True
        if not a.quiet:
            print(f"DAILY_LIMIT: pnl_today {pnl_today:.2f} <= -{max_loss:.2f}")

    return 2 if exceeded else 0


if __name__ == "__main__":
    raise SystemExit(main())
