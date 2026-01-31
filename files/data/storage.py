# files/data/storage.py
from __future__ import annotations

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
    """
    df = _ensure_schema(df)
    if len(df) == 0:
        logger.warning(
            "No bars to persist",
            extra={"exchange": exchange, "symbol": symbol, "timeframe": timeframe},
        )
        return

    root: Path = raw_symbol_dir(exchange=exchange, symbol=symbol, timeframe=timeframe)
    root.mkdir(parents=True, exist_ok=True)

    df = df.copy()
    df["date"] = df["timestamp"].dt.date.astype(str)

    for date, chunk in df.groupby("date", sort=True):
        part_dir = root / f"date={date}"
        part_dir.mkdir(parents=True, exist_ok=True)
        path = part_dir / "bars.parquet"

        chunk = chunk.drop(columns=["date"]).sort_values("timestamp")

        if path.exists():
            existing = pd.read_parquet(path)
            existing = _ensure_schema(existing)
            merged = pd.concat([existing, chunk], ignore_index=True)
            merged = merged.drop_duplicates(subset=["timestamp"], keep="last")
            merged = merged.sort_values("timestamp").reset_index(drop=True)
        else:
            merged = chunk.drop_duplicates(subset=["timestamp"], keep="last").reset_index(drop=True)

        merged.to_parquet(path, index=False)

    logger.info(
        "Persisted bars",
        extra={"exchange": exchange, "symbol": symbol, "timeframe": timeframe, "rows_in": len(df)},
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

    if len(out) > tail_n:
        out = out.tail(tail_n).reset_index(drop=True)

    return out

