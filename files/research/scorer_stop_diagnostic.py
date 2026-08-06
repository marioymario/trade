from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from files.research.historical_dataset import (
    load_and_resolve_historical_research_source,
)
from files.research.scorer_campaign_io import (
    write_csv_atomic,
    write_json_atomic,
)


STOP_DIAGNOSTIC_FIELDS = (
    "campaign_id",
    "trial_id",
    "execution_id",
    "split_name",
    "entry_ts_ms",
    "exit_ts_ms",
    "exit_reason",
    "bars_held",
    "entry_price",
    "exit_price",
    "realized_pnl_usd",
    "realized_pnl_pct",
    "initial_stop_price",
    "final_stop_price",
    "initial_risk_pct",
    "mfe_before_exit_bar_pct",
    "mfe_including_exit_bar_pct",
    "mae_including_exit_bar_pct",
    "reached_initial_1r_before_exit",
    "favorable_before_stop",
)


class StopDiagnosticError(RuntimeError):
    """Raised when stop diagnostics cannot be reconstructed safely."""


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise StopDiagnosticError(
            f"Unable to read JSON artifact: {path}"
        ) from exc

    if not isinstance(payload, dict):
        raise StopDiagnosticError(
            f"JSON artifact must contain an object: {path}"
        )

    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(
            newline="",
            encoding="utf-8",
        ) as handle:
            return list(csv.DictReader(handle))
    except Exception as exc:
        raise StopDiagnosticError(
            f"Unable to read CSV artifact: {path}"
        ) from exc


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0

    if parsed != parsed:
        return 0.0

    return parsed


def _initial_stop_for_trade(
    *,
    decisions: list[dict[str, str]],
    entry_ts_ms: int,
    exit_ts_ms: int,
    entry_price: float,
    timeframe_step_ms: int,
) -> float | None:
    search_start = entry_ts_ms - timeframe_step_ms

    candidates: list[tuple[int, float]] = []

    for row in decisions:
        ts_ms = _as_int(row.get("ts_ms"))

        if ts_ms < search_start or ts_ms > exit_ts_ms:
            continue

        if str(row.get("position_side", "")).upper() != "LONG":
            continue

        row_entry_price = _as_float(
            row.get("position_entry_price")
        )

        if row_entry_price <= 0.0:
            continue

        tolerance = max(abs(entry_price) * 1e-9, 1e-9)

        if abs(row_entry_price - entry_price) > tolerance:
            continue

        stop_price = _as_float(
            row.get("position_stop_price")
        )

        if stop_price > 0.0:
            candidates.append((ts_ms, stop_price))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    return float(candidates[0][1])


def _prepare_bars(
    bars: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
    }

    missing = sorted(required - set(bars.columns))

    if missing:
        raise StopDiagnosticError(
            f"Historical bars are missing columns: {missing}"
        )

    prepared = bars.loc[
        :,
        ["timestamp", "open", "high", "low", "close"],
    ].copy()

    prepared["timestamp"] = pd.to_datetime(
        prepared["timestamp"],
        utc=True,
        errors="raise",
    )

    prepared["ts_ms"] = (
        prepared["timestamp"].astype("int64")
        // 1_000_000
    )

    prepared = prepared.sort_values(
        "ts_ms",
        kind="stable",
    ).reset_index(drop=True)

    return prepared


def _trade_diagnostic_row(
    *,
    campaign_id: str,
    trial_id: str,
    execution: dict[str, Any],
    trade: dict[str, str],
    decisions: list[dict[str, str]],
    bars: pd.DataFrame,
    timeframe_step_ms: int,
) -> dict[str, Any]:
    entry_ts_ms = _as_int(trade.get("entry_ts_ms"))
    exit_ts_ms = _as_int(trade.get("exit_ts_ms"))
    entry_price = _as_float(trade.get("entry_price"))
    exit_price = _as_float(trade.get("exit_price"))

    if (
        entry_ts_ms <= 0
        or exit_ts_ms < entry_ts_ms
        or entry_price <= 0.0
    ):
        raise StopDiagnosticError(
            "Trade contains invalid entry/exit identity: "
            f"{trade}"
        )

    trade_bars = bars.loc[
        (bars["ts_ms"] >= entry_ts_ms)
        & (bars["ts_ms"] <= exit_ts_ms)
    ]

    if trade_bars.empty:
        raise StopDiagnosticError(
            "No historical bars found for trade window: "
            f"entry={entry_ts_ms} exit={exit_ts_ms}"
        )

    before_exit = trade_bars.loc[
        trade_bars["ts_ms"] < exit_ts_ms
    ]

    highest_including_exit = float(
        trade_bars["high"].max()
    )
    lowest_including_exit = float(
        trade_bars["low"].min()
    )

    highest_before_exit = (
        float(before_exit["high"].max())
        if not before_exit.empty
        else entry_price
    )

    mfe_before_exit_pct = (
        highest_before_exit / entry_price - 1.0
    )
    mfe_including_exit_pct = (
        highest_including_exit / entry_price - 1.0
    )
    mae_including_exit_pct = (
        lowest_including_exit / entry_price - 1.0
    )

    initial_stop = _initial_stop_for_trade(
        decisions=decisions,
        entry_ts_ms=entry_ts_ms,
        exit_ts_ms=exit_ts_ms,
        entry_price=entry_price,
        timeframe_step_ms=timeframe_step_ms,
    )

    final_stop = _as_float(trade.get("stop_price"))
    initial_risk_pct = 0.0

    if initial_stop is not None:
        initial_risk_pct = max(
            (entry_price - initial_stop) / entry_price,
            0.0,
        )

    reached_1r = (
        initial_risk_pct > 0.0
        and mfe_before_exit_pct >= initial_risk_pct
    )

    exit_reason = str(
        trade.get("exit_reason", "")
    )

    return {
        "campaign_id": campaign_id,
        "trial_id": trial_id,
        "execution_id": execution["execution_id"],
        "split_name": execution["split_name"],
        "entry_ts_ms": entry_ts_ms,
        "exit_ts_ms": exit_ts_ms,
        "exit_reason": exit_reason,
        "bars_held": int(len(trade_bars)),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "realized_pnl_usd": _as_float(
            trade.get("realized_pnl_usd")
        ),
        "realized_pnl_pct": _as_float(
            trade.get("realized_pnl_pct")
        ),
        "initial_stop_price": (
            initial_stop
            if initial_stop is not None
            else ""
        ),
        "final_stop_price": (
            final_stop
            if final_stop > 0.0
            else ""
        ),
        "initial_risk_pct": initial_risk_pct,
        "mfe_before_exit_bar_pct": (
            mfe_before_exit_pct
        ),
        "mfe_including_exit_bar_pct": (
            mfe_including_exit_pct
        ),
        "mae_including_exit_bar_pct": (
            mae_including_exit_pct
        ),
        "reached_initial_1r_before_exit": (
            reached_1r
        ),
        "favorable_before_stop": (
            exit_reason == "stop_hit"
            and mfe_before_exit_pct > 0.0
        ),
    }


def _summary_for_rows(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if not rows:
        return {
            "trade_count": 0,
            "stop_hit_count": 0,
            "stop_hit_rate": 0.0,
            "total_pnl_usd": 0.0,
            "average_bars_held": 0.0,
            "median_bars_held": 0.0,
            "average_mfe_before_exit_bar_pct": 0.0,
            "average_mae_including_exit_bar_pct": 0.0,
            "stopped_with_favorable_excursion_count": 0,
            "stopped_reaching_initial_1r_count": 0,
        }

    stop_rows = [
        row
        for row in rows
        if row["exit_reason"] == "stop_hit"
    ]

    favorable_stops = [
        row
        for row in stop_rows
        if row["favorable_before_stop"]
    ]

    one_r_stops = [
        row
        for row in stop_rows
        if row["reached_initial_1r_before_exit"]
    ]

    bars_held = [
        int(row["bars_held"])
        for row in rows
    ]

    return {
        "trade_count": len(rows),
        "stop_hit_count": len(stop_rows),
        "stop_hit_rate": (
            len(stop_rows) / len(rows)
        ),
        "total_pnl_usd": sum(
            float(row["realized_pnl_usd"])
            for row in rows
        ),
        "average_bars_held": (
            sum(bars_held) / len(bars_held)
        ),
        "median_bars_held": float(
            median(bars_held)
        ),
        "average_mfe_before_exit_bar_pct": (
            sum(
                float(
                    row["mfe_before_exit_bar_pct"]
                )
                for row in rows
            )
            / len(rows)
        ),
        "average_mae_including_exit_bar_pct": (
            sum(
                float(
                    row["mae_including_exit_bar_pct"]
                )
                for row in rows
            )
            / len(rows)
        ),
        "stopped_with_favorable_excursion_count": len(
            favorable_stops
        ),
        "stopped_reaching_initial_1r_count": len(
            one_r_stops
        ),
    }


def build_stop_diagnostic(
    *,
    campaign_root: Path,
    trial_id: str,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    manifest = _load_json_object(
        campaign_root / "campaign_manifest.json"
    )
    execution_plan = _load_json_object(
        campaign_root / "execution_plan.json"
    )

    campaign_id = str(manifest.get("campaign_id", ""))

    if campaign_id != campaign_root.name:
        raise StopDiagnosticError(
            "Campaign root and manifest identity differ."
        )

    source_info = manifest.get("specification", {})

    source = load_and_resolve_historical_research_source(
        data_tag=str(source_info["data_tag"]),
        expected_symbol=str(source_info["symbol"]),
        expected_timeframe=str(source_info["timeframe"]),
        manifest_path=Path(
            str(
                manifest[
                    "resolved_walk_forward_splits"
                ]
                and manifest.get(
                    "manifest_path",
                    source_info.get("manifest_path", ""),
                )
            )
        )
        if manifest.get("manifest_path")
        else None,
    )

    expected_fingerprint = str(
        manifest.get("manifest_fingerprint", "")
    )

    if (
        source.manifest_fingerprint
        != expected_fingerprint
    ):
        raise StopDiagnosticError(
            "Historical source fingerprint mismatch."
        )

    bars = _prepare_bars(source.audit.bars)

    executions = [
        item
        for item in execution_plan["executions"]
        if item["trial_id"] == trial_id
        and item["window_role"] == "validation"
        and item["cost_scenario_id"] == "base"
    ]

    if not executions:
        raise StopDiagnosticError(
            f"No base validation executions found for {trial_id}."
        )

    rows: list[dict[str, Any]] = []

    for execution in executions:
        result_path = Path(
            execution["result_json"]
        )

        result = _load_json_object(result_path)

        if result.get("status") != "succeeded":
            raise StopDiagnosticError(
                f"Execution is not successful: {result_path}"
            )

        backtest = result.get("backtest", {}).get(
            "backtest",
            {},
        )

        trades_path = Path(
            str(backtest.get("trades_csv", ""))
        )
        decisions_path = Path(
            str(backtest.get("decisions_csv", ""))
        )

        trades = _read_csv(trades_path)
        decisions = _read_csv(decisions_path)

        for trade in trades:
            if str(trade.get("side", "")).upper() != "LONG":
                raise StopDiagnosticError(
                    "Non-LONG trade encountered."
                )

            rows.append(
                _trade_diagnostic_row(
                    campaign_id=campaign_id,
                    trial_id=trial_id,
                    execution=execution,
                    trade=trade,
                    decisions=decisions,
                    bars=bars,
                    timeframe_step_ms=(
                        source.timeframe_step_ms
                    ),
                )
            )

    rows.sort(
        key=lambda row: (
            row["split_name"],
            int(row["entry_ts_ms"]),
        )
    )

    by_split: dict[str, Any] = {}

    for split_name in sorted(
        {
            str(row["split_name"])
            for row in rows
        }
    ):
        split_rows = [
            row
            for row in rows
            if row["split_name"] == split_name
        ]

        by_split[split_name] = _summary_for_rows(
            split_rows
        )

    summary = {
        "campaign_id": campaign_id,
        "trial_id": trial_id,
        "source_manifest_fingerprint": (
            source.manifest_fingerprint
        ),
        "overall": _summary_for_rows(rows),
        "validation_splits": by_split,
    }

    if write_artifacts:
        output_dir = (
            campaign_root
            / "diagnostics"
            / "stop_behavior"
            / trial_id
        )

        write_csv_atomic(
            path=output_dir / "trades.csv",
            fieldnames=STOP_DIAGNOSTIC_FIELDS,
            rows=rows,
        )

        write_json_atomic(
            path=output_dir / "summary.json",
            value=summary,
        )

        summary["trades_csv"] = str(
            output_dir / "trades.csv"
        )
        summary["summary_json"] = str(
            output_dir / "summary.json"
        )

    return summary
