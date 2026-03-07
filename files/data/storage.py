# files/data/storage.py
from __future__ import annotations

import os
import time
import secrets
from pathlib import Path

import pandas as pd

from files.data.paths import raw_symbol_dir
from files.utils.logger import get_logger

logger = get_logger(__name__)


def _ensure_utc_ts(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"])
    return out


def _ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")
    out = df[cols].copy()
    out = _ensure_utc_ts(out)
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out


def _atomic_write_parquet(df: pd.DataFrame, path: Path) -> None:
    """
    Write parquet atomically:
      - write to a uniquely-named temp file in the same directory
      - os.replace(temp, path) for atomic swap
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    token = secrets.token_hex(6)
    tmp = Path(str(path) + f".tmp.{os.getpid()}.{int(time.time() * 1000)}.{token}")

    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _payload_cols() -> list[str]:
    return ["open", "high", "low", "close", "volume"]


def _warn_if_replayed_adjacent_bars(
    df: pd.DataFrame,
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    context: str,
) -> None:
    """
    Warn if adjacent rows have different timestamps but identical OHLCV payload.
    This is observability-first only; we do not mutate/drop rows here.
    """
    if df is None or len(df) < 2:
        return

    out = _ensure_schema(df)
    payload = _payload_cols()

    prev_ts = out["timestamp"].shift(1)
    same_payload = pd.Series(True, index=out.index)
    for c in payload:
        same_payload = same_payload & (out[c] == out[c].shift(1))

    suspicious = same_payload & prev_ts.notna() & (out["timestamp"] != prev_ts)

    count = int(suspicious.sum())
    if count <= 0:
        return

    hits = out.loc[suspicious, ["timestamp"] + payload].copy()
    sample = []
    for _, row in hits.tail(3).iterrows():
        sample.append(
            {
                "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )

    logger.warning(
        "Suspicious replayed adjacent bars detected",
        extra={
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "context": context,
            "count": count,
            "sample_tail": sample,
        },
    )


def append_ohlcv_parquet(
    *,
    df: pd.DataFrame,
    exchange: str,
    symbol: str,
    timeframe: str,
) -> None:
    """
    Layout (canonical):
      data/raw/{exchange}/{SYMBOL}/{timeframe}/date=YYYY-MM-DD/bars.parquet

    Atomicity:
      - each partition write is atomic via os.replace
    """
    df = _ensure_schema(df)
    if len(df) == 0:
        logger.warning(
            "No bars to persist",
            extra={"exchange": exchange, "symbol": symbol, "timeframe": timeframe},
        )
        return

    _warn_if_replayed_adjacent_bars(
        df,
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        context="append_input",
    )

    root: Path = raw_symbol_dir(exchange=exchange, symbol=symbol, timeframe=timeframe)
    root.mkdir(parents=True, exist_ok=True)

    df = df.copy()
    df["date"] = df["timestamp"].dt.date.astype(str)

    partitions_written = 0
    partitions: list[str] = []

    for date, chunk in df.groupby("date", sort=True):
        part_dir = root / f"date={date}"
        path = part_dir / "bars.parquet"

        chunk = chunk.drop(columns=["date"]).sort_values("timestamp")
        chunk = chunk.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

        if path.exists():
            existing = pd.read_parquet(path)
            existing = _ensure_schema(existing)

            merged = pd.concat([existing, chunk], ignore_index=True)
            merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
            merged = merged.sort_values("timestamp").reset_index(drop=True)
        else:
            merged = chunk

        _warn_if_replayed_adjacent_bars(
            merged,
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            context=f"partition_merge:{date}",
        )

        _atomic_write_parquet(merged, path)
        partitions_written += 1
        partitions.append(str(part_dir.name))

    logger.info(
        "Persisted bars",
        extra={
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "rows_in": int(len(df)),
            "partitions_written": int(partitions_written),
            "partitions": partitions[-5:],
        },
    )


def load_recent_ohlcv_parquet(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    tail_n: int,
) -> pd.DataFrame:
    if tail_n <= 0:
        raise ValueError("tail_n must be > 0")

    root = raw_symbol_dir(exchange=exchange, symbol=symbol, timeframe=timeframe)
    if not root.exists():
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    files = sorted(root.glob("date=*/bars.parquet"))
    if not files:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    dfs: list[pd.DataFrame] = []
    for p in files:
        try:
            dfs.append(pd.read_parquet(p))
        except Exception:
            logger.exception("Failed reading parquet partition", extra={"path": str(p)})

    if not dfs:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    out = pd.concat(dfs, ignore_index=True)
    out = _ensure_schema(out)
    out = out.drop_duplicates(subset=["timestamp"], keep="last")
    out = out.sort_values("timestamp").reset_index(drop=True)

    _warn_if_replayed_adjacent_bars(
        out,
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        context="load_recent",
    )

    if len(out) > tail_n:
        out = out.tail(tail_n).reset_index(drop=True)

    return out
