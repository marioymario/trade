# files/backtest/__main__.py
from __future__ import annotations

import argparse
from datetime import datetime

from files.backtest.engine import run_backtest


def _default_runid() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def main() -> None:
    p = argparse.ArgumentParser(description="Deterministic offline backtest (parquet replay).")
    p.add_argument("--runid", default=_default_runid(), help="Run id (default YYYYMMDD_HHMMSS).")
    p.add_argument("--start-ts-ms", type=int, default=None)
    p.add_argument("--end-ts-ms", type=int, default=None)
    args = p.parse_args()

    res = run_backtest(runid=args.runid, start_ts_ms=args.start_ts_ms, end_ts_ms=args.end_ts_ms)
    print(res)


if __name__ == "__main__":
    main()

