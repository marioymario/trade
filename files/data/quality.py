# files/data/quality.py
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class DataQualityReport:
    rows: int
    tz_aware: bool
    monotonic: bool
    duplicates: int
    median_step_s: float | None
    min_step_s: float | None
    max_step_s: float | None


def assess_ohlcv(df: pd.DataFrame) -> DataQualityReport:
    if df is None or len(df) == 0:
        return DataQualityReport(
            rows=0,
            tz_aware=False,
            monotonic=False,
            duplicates=0,
            median_step_s=None,
            min_step_s=None,
            max_step_s=None,
        )

    ts = pd.to_datetime(df["timestamp"], utc=True)
    tz_aware = ts.dt.tz is not None
    monotonic = ts.is_monotonic_increasing
    duplicates = int(ts.duplicated().sum())

    diffs = ts.diff().dt.total_seconds().dropna()
    if len(diffs) == 0:
        median_s = min_s = max_s = None
    else:
        median_s = float(diffs.median())
        min_s = float(diffs.min())
        max_s = float(diffs.max())

    return DataQualityReport(
        rows=int(len(df)),
        tz_aware=tz_aware,
        monotonic=bool(monotonic),
        duplicates=duplicates,
        median_step_s=median_s,
        min_step_s=min_s,
        max_step_s=max_s,
    )

