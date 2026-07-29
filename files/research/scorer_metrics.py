from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrialMetrics:
    trades_csv: str
    trades_csv_exists: bool

    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int

    win_rate: float

    total_pnl_usd: float
    average_pnl_usd: float
    best_trade_pnl_usd: float
    worst_trade_pnl_usd: float

    maximum_drawdown_usd: float

    stop_hit_count: int
    stop_hit_rate: float
    time_stop_count: int

    long_trade_count: int
    short_trade_count: int

    first_exit_ts_ms: int | None
    last_exit_ts_ms: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_float(
    value: Any,
    *,
    default: float = 0.0,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)

    if parsed != parsed:
        return float(default)

    return float(parsed)


def _as_int(
    value: Any,
    *,
    default: int = 0,
) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _maximum_drawdown(
    pnl_values: list[float],
) -> float:
    cumulative = 0.0
    peak = 0.0
    maximum_drawdown = 0.0

    for pnl in pnl_values:
        cumulative += float(pnl)
        peak = max(peak, cumulative)

        drawdown = peak - cumulative
        maximum_drawdown = max(
            maximum_drawdown,
            drawdown,
        )

    return float(maximum_drawdown)


def empty_trial_metrics(
    *,
    trades_csv: Path,
    trades_csv_exists: bool,
) -> TrialMetrics:
    return TrialMetrics(
        trades_csv=str(trades_csv),
        trades_csv_exists=trades_csv_exists,
        trade_count=0,
        winning_trades=0,
        losing_trades=0,
        breakeven_trades=0,
        win_rate=0.0,
        total_pnl_usd=0.0,
        average_pnl_usd=0.0,
        best_trade_pnl_usd=0.0,
        worst_trade_pnl_usd=0.0,
        maximum_drawdown_usd=0.0,
        stop_hit_count=0,
        stop_hit_rate=0.0,
        time_stop_count=0,
        long_trade_count=0,
        short_trade_count=0,
        first_exit_ts_ms=None,
        last_exit_ts_ms=None,
    )


def calculate_trial_metrics(
    *,
    trades_csv: str | Path,
) -> TrialMetrics:
    path = Path(trades_csv)

    if not path.exists():
        return empty_trial_metrics(
            trades_csv=path,
            trades_csv_exists=False,
        )

    with path.open(
        "r",
        newline="",
        encoding="utf-8",
    ) as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        return empty_trial_metrics(
            trades_csv=path,
            trades_csv_exists=True,
        )

    pnl_values = [
        _as_float(row.get("realized_pnl_usd"))
        for row in rows
    ]

    winning_trades = sum(
        1 for pnl in pnl_values
        if pnl > 0.0
    )

    losing_trades = sum(
        1 for pnl in pnl_values
        if pnl < 0.0
    )

    breakeven_trades = sum(
        1 for pnl in pnl_values
        if pnl == 0.0
    )

    trade_count = len(rows)
    total_pnl_usd = float(sum(pnl_values))

    average_pnl_usd = (
        total_pnl_usd / trade_count
        if trade_count > 0
        else 0.0
    )

    exit_reasons = [
        str(row.get("exit_reason", "")).strip()
        for row in rows
    ]

    stop_hit_count = sum(
        1 for reason in exit_reasons
        if reason == "stop_hit"
    )

    time_stop_count = sum(
        1 for reason in exit_reasons
        if reason == "time_stop"
    )

    sides = [
        str(row.get("side", "")).strip().upper()
        for row in rows
    ]

    long_trade_count = sum(
        1 for side in sides
        if side == "LONG"
    )

    short_trade_count = sum(
        1 for side in sides
        if side == "SHORT"
    )

    exit_timestamps = sorted(
        timestamp
        for timestamp in (
            _as_int(row.get("exit_ts_ms"))
            for row in rows
        )
        if timestamp > 0
    )

    return TrialMetrics(
        trades_csv=str(path),
        trades_csv_exists=True,
        trade_count=trade_count,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        breakeven_trades=breakeven_trades,
        win_rate=(
            winning_trades / trade_count
            if trade_count > 0
            else 0.0
        ),
        total_pnl_usd=total_pnl_usd,
        average_pnl_usd=average_pnl_usd,
        best_trade_pnl_usd=max(pnl_values),
        worst_trade_pnl_usd=min(pnl_values),
        maximum_drawdown_usd=_maximum_drawdown(
            pnl_values
        ),
        stop_hit_count=stop_hit_count,
        stop_hit_rate=(
            stop_hit_count / trade_count
            if trade_count > 0
            else 0.0
        ),
        time_stop_count=time_stop_count,
        long_trade_count=long_trade_count,
        short_trade_count=short_trade_count,
        first_exit_ts_ms=(
            exit_timestamps[0]
            if exit_timestamps
            else None
        ),
        last_exit_ts_ms=(
            exit_timestamps[-1]
            if exit_timestamps
            else None
        ),
    )
