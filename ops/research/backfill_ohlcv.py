from __future__ import annotations

import argparse
import json
from typing import Any

import pandas as pd

from files.data.historical_backfill import (
    HistoricalBackfillRequest,
    fetch_historical_ohlcv,
    persist_historical_ohlcv,
)


DEFAULT_DATA_TAG = "coinbase_history_2022_20260209"


def parse_utc_timestamp(
    value: str,
    *,
    argument_name: str,
) -> pd.Timestamp:
    text = value.strip()

    if not text:
        raise argparse.ArgumentTypeError(
            f"{argument_name} must not be empty"
        )

    try:
        timestamp = pd.Timestamp(text)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            f"{argument_name} must be a valid ISO-8601 timestamp"
        ) from exc

    if pd.isna(timestamp):
        raise argparse.ArgumentTypeError(
            f"{argument_name} must be a valid ISO-8601 timestamp"
        )

    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    return timestamp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch, validate, and optionally persist a bounded "
            "historical OHLCV range into an isolated data namespace."
        )
    )

    parser.add_argument(
        "--ccxt-exchange",
        default="coinbase",
        help="CCXT exchange identifier. Default: coinbase.",
    )

    parser.add_argument(
        "--data-tag",
        default=DEFAULT_DATA_TAG,
        help=(
            "Isolated storage namespace used under data/raw. "
            f"Default: {DEFAULT_DATA_TAG}."
        ),
    )

    parser.add_argument(
        "--symbol",
        default="BTC/USD",
        help="CCXT market symbol. Default: BTC/USD.",
    )

    parser.add_argument(
        "--timeframe",
        default="5m",
        help="OHLCV timeframe. Default: 5m.",
    )

    parser.add_argument(
        "--start",
        required=True,
        help=(
            "Inclusive UTC ISO-8601 start timestamp aligned "
            "to the requested timeframe."
        ),
    )

    parser.add_argument(
        "--end",
        required=True,
        help=(
            "Exclusive UTC ISO-8601 end timestamp aligned "
            "to the requested timeframe."
        ),
    )

    parser.add_argument(
        "--page-limit",
        type=int,
        default=300,
        help="Maximum OHLCV rows requested per page. Default: 300.",
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Persist validated bars using the canonical atomic "
            "Parquet writer. Without this flag, the command is read-only."
        ),
    )

    return parser


def progress_line(progress: dict[str, Any]) -> None:
    raw_first = pd.to_datetime(
        progress["raw_first_ms"],
        unit="ms",
        utc=True,
    )

    raw_last = pd.to_datetime(
        progress["raw_last_ms"],
        unit="ms",
        utc=True,
    )

    print(
        "page="
        f"{progress['page_number']} "
        "raw_rows="
        f"{progress['raw_rows']} "
        "in_window_rows="
        f"{progress['in_window_rows']} "
        "unique_rows="
        f"{progress['unique_rows']} "
        "first="
        f"{raw_first.isoformat()} "
        "last="
        f"{raw_last.isoformat()}",
        flush=True,
    )


def main() -> None:
    args = build_parser().parse_args()

    start_utc = parse_utc_timestamp(
        args.start,
        argument_name="--start",
    )

    end_utc_exclusive = parse_utc_timestamp(
        args.end,
        argument_name="--end",
    )

    request = HistoricalBackfillRequest(
        ccxt_exchange=args.ccxt_exchange,
        data_tag=args.data_tag,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_utc=start_utc,
        end_utc_exclusive=end_utc_exclusive,
        page_limit=args.page_limit,
    )

    print()
    print("=== HISTORICAL OHLCV BACKFILL ===")
    print(f"mode={'write' if args.write else 'dry-run'}")
    print(f"ccxt_exchange={request.ccxt_exchange}")
    print(f"data_tag={request.data_tag}")
    print(f"symbol={request.symbol}")
    print(f"timeframe={request.timeframe}")
    print(f"start_utc={request.start_utc.isoformat()}")
    print(
        "end_utc_exclusive="
        f"{request.end_utc_exclusive.isoformat()}"
    )
    print(f"page_limit={request.page_limit}")
    print("=================================")
    print()

    result = fetch_historical_ohlcv(
        request=request,
        progress_callback=progress_line,
    )

    if args.write:
        persist_historical_ohlcv(result)

    summary = {
        "status": "ok",
        "mode": "write" if args.write else "dry-run",
        "ccxt_exchange": request.ccxt_exchange,
        "data_tag": request.data_tag,
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "start_utc": request.start_utc.isoformat(),
        "end_utc_exclusive": (
            request.end_utc_exclusive.isoformat()
        ),
        "pages_fetched": result.pages_fetched,
        "raw_rows_received": result.raw_rows_received,
        "out_of_window_rows_filtered": (
            result.out_of_window_rows_filtered
        ),
        "duplicate_rows_removed": result.duplicate_rows_removed,
        "expected_rows": result.expected_rows,
        "validated_rows": result.row_count,
        "first_timestamp": (
            result.first_timestamp.isoformat()
            if result.first_timestamp is not None
            else None
        ),
        "last_timestamp": (
            result.last_timestamp.isoformat()
            if result.last_timestamp is not None
            else None
        ),
        "persisted": bool(args.write),
    }

    print()
    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
