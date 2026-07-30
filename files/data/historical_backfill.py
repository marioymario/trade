from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

import pandas as pd

from files.data.storage import append_ohlcv_parquet
from files.utils.logger import get_logger


logger = get_logger(__name__)


OHLCV_COLUMNS = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
]


class HistoricalBackfillError(RuntimeError):
    """Raised when historical OHLCV acquisition or validation fails."""


@dataclass(frozen=True)
class HistoricalBackfillRequest:
    ccxt_exchange: str
    data_tag: str
    symbol: str
    timeframe: str
    start_utc: pd.Timestamp
    end_utc_exclusive: pd.Timestamp
    page_limit: int = 300

    def __post_init__(self) -> None:
        start = normalize_utc_timestamp(
            self.start_utc,
            name="start_utc",
        )
        end = normalize_utc_timestamp(
            self.end_utc_exclusive,
            name="end_utc_exclusive",
        )

        if end <= start:
            raise ValueError(
                "end_utc_exclusive must be later than start_utc"
            )

        if not self.ccxt_exchange.strip():
            raise ValueError("ccxt_exchange must not be empty")

        if not self.data_tag.strip():
            raise ValueError("data_tag must not be empty")

        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")

        if not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")

        if self.page_limit <= 0:
            raise ValueError("page_limit must be greater than zero")

        object.__setattr__(self, "start_utc", start)
        object.__setattr__(self, "end_utc_exclusive", end)


@dataclass(frozen=True)
class HistoricalBackfillResult:
    request: HistoricalBackfillRequest
    bars: pd.DataFrame
    pages_fetched: int
    raw_rows_received: int
    out_of_window_rows_filtered: int
    duplicate_rows_removed: int
    expected_rows: int

    @property
    def row_count(self) -> int:
        return int(len(self.bars))

    @property
    def first_timestamp(self) -> Optional[pd.Timestamp]:
        if self.bars.empty:
            return None
        return pd.Timestamp(self.bars["timestamp"].iloc[0])

    @property
    def last_timestamp(self) -> Optional[pd.Timestamp]:
        if self.bars.empty:
            return None
        return pd.Timestamp(self.bars["timestamp"].iloc[-1])


def normalize_utc_timestamp(
    value: Any,
    *,
    name: str,
) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")

    if pd.isna(timestamp):
        raise ValueError(f"{name} is not a valid timestamp")

    return timestamp


def timeframe_to_timedelta(timeframe: str) -> pd.Timedelta:
    normalized = timeframe.strip().lower()

    if len(normalized) < 2:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")

    try:
        count = int(normalized[:-1])
    except ValueError as exc:
        raise ValueError(
            f"Unsupported timeframe: {timeframe!r}"
        ) from exc

    if count <= 0:
        raise ValueError(
            f"Timeframe count must be positive: {timeframe!r}"
        )

    unit = normalized[-1]

    if unit == "m":
        return pd.Timedelta(minutes=count)

    if unit == "h":
        return pd.Timedelta(hours=count)

    if unit == "d":
        return pd.Timedelta(days=count)

    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def timestamp_to_milliseconds(timestamp: pd.Timestamp) -> int:
    normalized = normalize_utc_timestamp(
        timestamp,
        name="timestamp",
    )
    return int(normalized.timestamp() * 1000)


def build_ccxt_exchange(exchange_id: str) -> Any:
    import ccxt  # type: ignore

    normalized = exchange_id.strip().lower()

    try:
        exchange_class = getattr(ccxt, normalized)
    except AttributeError as exc:
        raise HistoricalBackfillError(
            f"Unsupported CCXT exchange: {exchange_id!r}"
        ) from exc

    exchange = exchange_class(
        {
            "enableRateLimit": True,
        }
    )

    exchange.load_markets()

    if not exchange.has.get("fetchOHLCV"):
        raise HistoricalBackfillError(
            f"{exchange_id!r} does not support fetchOHLCV"
        )

    return exchange


def normalize_ohlcv_rows(
    rows: Iterable[list[Any]],
    *,
    start_ms: int,
    end_ms_exclusive: int,
) -> list[list[float | int]]:
    normalized: list[list[float | int]] = []

    for row in rows:
        if len(row) < 6:
            raise HistoricalBackfillError(
                f"Malformed OHLCV row: {row!r}"
            )

        timestamp_ms = int(row[0])

        if timestamp_ms < start_ms:
            continue

        if timestamp_ms >= end_ms_exclusive:
            continue

        normalized.append(
            [
                timestamp_ms,
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            ]
        )

    return normalized


def rows_to_frame(
    rows_by_timestamp: dict[int, list[float | int]],
) -> pd.DataFrame:
    if not rows_by_timestamp:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    ordered_rows = [
        rows_by_timestamp[timestamp_ms]
        for timestamp_ms in sorted(rows_by_timestamp)
    ]

    frame = pd.DataFrame(
        ordered_rows,
        columns=[
            "timestamp_ms",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    )

    frame["timestamp"] = pd.to_datetime(
        frame["timestamp_ms"],
        unit="ms",
        utc=True,
        errors="raise",
    )

    frame = (
        frame.drop(columns=["timestamp_ms"])
        [OHLCV_COLUMNS]
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    return frame


def validate_complete_history(
    frame: pd.DataFrame,
    *,
    request: HistoricalBackfillRequest,
) -> int:
    if frame.empty:
        raise HistoricalBackfillError(
            "Historical fetch returned no in-window bars"
        )

    step = timeframe_to_timedelta(
        request.timeframe
    )

    expected_rows = int(
        (
            request.end_utc_exclusive
            - request.start_utc
        )
        / step
    )

    expected_last_timestamp = (
        request.end_utc_exclusive
        - step
    )

    first_timestamp = pd.Timestamp(
        frame["timestamp"].iloc[0]
    )

    last_timestamp = pd.Timestamp(
        frame["timestamp"].iloc[-1]
    )

    duplicate_count = int(
        frame["timestamp"].duplicated().sum()
    )

    if duplicate_count:
        raise HistoricalBackfillError(
            "Duplicate timestamps remain after pagination: "
            f"{duplicate_count}"
        )

    if not frame["timestamp"].is_monotonic_increasing:
        raise HistoricalBackfillError(
            "Historical timestamps are not monotonic"
        )

    if first_timestamp != request.start_utc:
        raise HistoricalBackfillError(
            "Historical range does not begin at the requested "
            f"timestamp: expected {request.start_utc}, "
            f"found {first_timestamp}"
        )

    if last_timestamp != expected_last_timestamp:
        raise HistoricalBackfillError(
            "Historical range does not end at the expected "
            f"closed bar: expected {expected_last_timestamp}, "
            f"found {last_timestamp}"
        )

    differences = (
        frame["timestamp"]
        .diff()
        .dropna()
    )

    irregular = differences.loc[
        differences.ne(step)
    ]

    if not irregular.empty:
        raise HistoricalBackfillError(
            "Historical range contains irregular cadence: "
            f"{len(irregular)} interval(s)"
        )

    if len(frame) != expected_rows:
        raise HistoricalBackfillError(
            "Historical row count differs from expectation: "
            f"{len(frame)}/{expected_rows}"
        )

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    if frame[numeric_columns].isna().any().any():
        raise HistoricalBackfillError(
            "Historical OHLCV data contains null numeric values"
        )

    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise HistoricalBackfillError(
            "Historical OHLC prices must be positive"
        )

    if (frame["volume"] < 0).any():
        raise HistoricalBackfillError(
            "Historical volume must not be negative"
        )

    invalid_high = (
        frame["high"]
        < frame[
            [
                "open",
                "low",
                "close",
            ]
        ].max(axis=1)
    )

    invalid_low = (
        frame["low"]
        > frame[
            [
                "open",
                "high",
                "close",
            ]
        ].min(axis=1)
    )

    if invalid_high.any() or invalid_low.any():
        raise HistoricalBackfillError(
            "Historical OHLC relationships are invalid"
        )

    return expected_rows


def fetch_historical_ohlcv(
    *,
    request: HistoricalBackfillRequest,
    exchange: Any | None = None,
    progress_callback: Optional[
        Callable[[dict[str, Any]], None]
    ] = None,
) -> HistoricalBackfillResult:
    exchange = exchange or build_ccxt_exchange(
        request.ccxt_exchange
    )

    if request.symbol not in exchange.markets:
        raise HistoricalBackfillError(
            f"Symbol {request.symbol!r} is not available "
            f"on {request.ccxt_exchange!r}"
        )

    if (
        exchange.timeframes
        and request.timeframe
        not in exchange.timeframes
    ):
        raise HistoricalBackfillError(
            f"Timeframe {request.timeframe!r} is not supported "
            f"by {request.ccxt_exchange!r}"
        )

    step = timeframe_to_timedelta(
        request.timeframe
    )

    step_ms = int(
        step.total_seconds()
        * 1000
    )

    start_ms = timestamp_to_milliseconds(
        request.start_utc
    )

    end_ms_exclusive = timestamp_to_milliseconds(
        request.end_utc_exclusive
    )

    rows_by_timestamp: dict[
        int,
        list[float | int],
    ] = {}

    next_since_ms = start_ms
    previous_raw_last_ms: Optional[int] = None
    pages_fetched = 0
    raw_rows_received = 0
    in_window_rows_received = 0

    while next_since_ms < end_ms_exclusive:
        pages_fetched += 1

        raw_page = exchange.fetch_ohlcv(
            request.symbol,
            timeframe=request.timeframe,
            since=next_since_ms,
            limit=request.page_limit,
        )

        if not raw_page:
            raise HistoricalBackfillError(
                "Exchange returned an empty page before the "
                "requested range was complete: "
                f"since={exchange.iso8601(next_since_ms)}"
            )

        raw_rows_received += len(raw_page)

        raw_first_ms = int(raw_page[0][0])
        raw_last_ms = int(raw_page[-1][0])

        if raw_first_ms < next_since_ms:
            logger.warning(
                "Historical page began before requested since",
                extra={
                    "requested_since_ms": next_since_ms,
                    "raw_first_ms": raw_first_ms,
                },
            )

        if raw_last_ms < next_since_ms:
            raise HistoricalBackfillError(
                "Exchange returned a final timestamp earlier "
                "than the requested since timestamp"
            )

        if (
            previous_raw_last_ms is not None
            and raw_last_ms <= previous_raw_last_ms
        ):
            raise HistoricalBackfillError(
                "Historical pagination did not advance"
            )

        normalized_page = normalize_ohlcv_rows(
            raw_page,
            start_ms=start_ms,
            end_ms_exclusive=end_ms_exclusive,
        )

        in_window_rows_received += len(normalized_page)

        for row in normalized_page:
            rows_by_timestamp[int(row[0])] = row

        if progress_callback is not None:
            progress_callback(
                {
                    "page_number": pages_fetched,
                    "requested_since_ms": next_since_ms,
                    "raw_rows": len(raw_page),
                    "in_window_rows": len(normalized_page),
                    "raw_first_ms": raw_first_ms,
                    "raw_last_ms": raw_last_ms,
                    "unique_rows": len(rows_by_timestamp),
                }
            )

        previous_raw_last_ms = raw_last_ms
        next_since_ms = raw_last_ms + step_ms

        if raw_last_ms >= end_ms_exclusive - step_ms:
            break

    frame = rows_to_frame(
        rows_by_timestamp
    )

    expected_rows = validate_complete_history(
        frame,
        request=request,
    )

    out_of_window_rows_filtered = (
        raw_rows_received
        - in_window_rows_received
    )

    duplicate_rows_removed = (
        in_window_rows_received
        - len(rows_by_timestamp)
    )

    return HistoricalBackfillResult(
        request=request,
        bars=frame,
        pages_fetched=pages_fetched,
        raw_rows_received=raw_rows_received,
        out_of_window_rows_filtered=max(
            0,
            out_of_window_rows_filtered,
        ),
        duplicate_rows_removed=max(
            0,
            duplicate_rows_removed,
        ),
        expected_rows=expected_rows,
    )


def persist_historical_ohlcv(
    result: HistoricalBackfillResult,
) -> None:
    append_ohlcv_parquet(
        df=result.bars,
        exchange=result.request.data_tag,
        symbol=result.request.symbol,
        timeframe=result.request.timeframe,
    )


def fetch_and_persist_historical_ohlcv(
    *,
    request: HistoricalBackfillRequest,
    exchange: Any | None = None,
    progress_callback: Optional[
        Callable[[dict[str, Any]], None]
    ] = None,
) -> HistoricalBackfillResult:
    result = fetch_historical_ohlcv(
        request=request,
        exchange=exchange,
        progress_callback=progress_callback,
    )

    persist_historical_ohlcv(
        result
    )

    return result
