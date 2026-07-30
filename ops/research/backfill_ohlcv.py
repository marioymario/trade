from __future__ import annotations

import argparse
import json
from typing import Any

import pandas as pd

from files.data.historical_backfill import (
    HistoricalBackfillRequest,
    build_ccxt_exchange,
    fetch_historical_ohlcv,
    persist_historical_ohlcv,
)


DEFAULT_DATA_TAG = "coinbase_history_2022_20260209"
DEFAULT_CHUNK_DAYS = 30
DEFAULT_MAX_PAGE_ATTEMPTS = 5
DEFAULT_INITIAL_BACKOFF_SECONDS = 2.0


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


def positive_int(value: str) -> int:
    parsed = int(value)

    if parsed <= 0:
        raise argparse.ArgumentTypeError(
            "value must be greater than zero"
        )

    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)

    if parsed < 0:
        raise argparse.ArgumentTypeError(
            "value must not be negative"
        )

    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch, validate, and optionally persist historical "
            "OHLCV in independently committed bounded chunks."
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
        type=positive_int,
        default=300,
        help="Maximum OHLCV rows requested per page. Default: 300.",
    )

    parser.add_argument(
        "--chunk-days",
        type=positive_int,
        default=DEFAULT_CHUNK_DAYS,
        help=(
            "Maximum calendar days fetched and validated before "
            f"each independent commit. Default: {DEFAULT_CHUNK_DAYS}."
        ),
    )

    parser.add_argument(
        "--max-page-attempts",
        type=positive_int,
        default=DEFAULT_MAX_PAGE_ATTEMPTS,
        help=(
            "Maximum attempts for each exchange page request. "
            f"Default: {DEFAULT_MAX_PAGE_ATTEMPTS}."
        ),
    )

    parser.add_argument(
        "--initial-backoff-seconds",
        type=nonnegative_float,
        default=DEFAULT_INITIAL_BACKOFF_SECONDS,
        help=(
            "Initial retry delay; subsequent delays use exponential "
            f"backoff. Default: {DEFAULT_INITIAL_BACKOFF_SECONDS}."
        ),
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Persist every successfully validated chunk through the "
            "canonical atomic Parquet writer. Without this flag, the "
            "command is read-only."
        ),
    )

    return parser


def progress_line(
    chunk_number: int,
    progress: dict[str, Any],
) -> None:
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
        "chunk="
        f"{chunk_number} "
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


def build_chunk_ranges(
    *,
    start_utc: pd.Timestamp,
    end_utc_exclusive: pd.Timestamp,
    chunk_days: int,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if end_utc_exclusive <= start_utc:
        raise ValueError("--end must be later than --start")

    chunk_size = pd.Timedelta(days=chunk_days)
    ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    chunk_start = start_utc

    while chunk_start < end_utc_exclusive:
        chunk_end = min(
            chunk_start + chunk_size,
            end_utc_exclusive,
        )

        ranges.append(
            (
                chunk_start,
                chunk_end,
            )
        )

        chunk_start = chunk_end

    return ranges


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

    try:
        chunk_ranges = build_chunk_ranges(
            start_utc=start_utc,
            end_utc_exclusive=end_utc_exclusive,
            chunk_days=args.chunk_days,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    print()
    print("=== HISTORICAL OHLCV BACKFILL ===")
    print(f"mode={'write' if args.write else 'dry-run'}")
    print(f"ccxt_exchange={args.ccxt_exchange}")
    print(f"data_tag={args.data_tag}")
    print(f"symbol={args.symbol}")
    print(f"timeframe={args.timeframe}")
    print(f"start_utc={start_utc.isoformat()}")
    print(
        "end_utc_exclusive="
        f"{end_utc_exclusive.isoformat()}"
    )
    print(f"page_limit={args.page_limit}")
    print(f"chunk_days={args.chunk_days}")
    print(f"chunk_count={len(chunk_ranges)}")
    print(f"max_page_attempts={args.max_page_attempts}")
    print(
        "initial_backoff_seconds="
        f"{args.initial_backoff_seconds}"
    )
    print("=================================")
    print()

    exchange = build_ccxt_exchange(
        args.ccxt_exchange
    )

    totals = {
        "pages_fetched": 0,
        "raw_rows_received": 0,
        "out_of_window_rows_filtered": 0,
        "duplicate_rows_removed": 0,
        "expected_rows": 0,
        "validated_rows": 0,
    }

    chunk_summaries: list[dict[str, Any]] = []

    for chunk_number, (
        chunk_start,
        chunk_end,
    ) in enumerate(
        chunk_ranges,
        start=1,
    ):
        print(
            f"--- chunk {chunk_number}/{len(chunk_ranges)} "
            f"[{chunk_start.isoformat()}, "
            f"{chunk_end.isoformat()}) ---",
            flush=True,
        )

        request = HistoricalBackfillRequest(
            ccxt_exchange=args.ccxt_exchange,
            data_tag=args.data_tag,
            symbol=args.symbol,
            timeframe=args.timeframe,
            start_utc=chunk_start,
            end_utc_exclusive=chunk_end,
            page_limit=args.page_limit,
        )

        result = fetch_historical_ohlcv(
            request=request,
            exchange=exchange,
            progress_callback=lambda progress, number=chunk_number: (
                progress_line(number, progress)
            ),
            max_page_attempts=args.max_page_attempts,
            initial_backoff_seconds=(
                args.initial_backoff_seconds
            ),
        )

        if args.write:
            persist_historical_ohlcv(
                result
            )

        chunk_summary = {
            "chunk_number": chunk_number,
            "start_utc": chunk_start.isoformat(),
            "end_utc_exclusive": chunk_end.isoformat(),
            "pages_fetched": result.pages_fetched,
            "raw_rows_received": result.raw_rows_received,
            "out_of_window_rows_filtered": (
                result.out_of_window_rows_filtered
            ),
            "duplicate_rows_removed": (
                result.duplicate_rows_removed
            ),
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

        chunk_summaries.append(
            chunk_summary
        )

        for field in totals:
            totals[field] += int(
                chunk_summary[field]
            )

        print(
            json.dumps(
                chunk_summary,
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )

    summary = {
        "status": "ok",
        "mode": "write" if args.write else "dry-run",
        "ccxt_exchange": args.ccxt_exchange,
        "data_tag": args.data_tag,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "start_utc": start_utc.isoformat(),
        "end_utc_exclusive": (
            end_utc_exclusive.isoformat()
        ),
        "page_limit": args.page_limit,
        "chunk_days": args.chunk_days,
        "chunks_completed": len(chunk_summaries),
        "persisted": bool(args.write),
        **totals,
    }

    print()
    print("=== BACKFILL SUMMARY ===")
    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
