from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from files.data.features import compute_features
from files.models.entry_model import EntryModel
from files.research.historical_dataset import (
    load_and_resolve_historical_research_source,
)
from files.research.scorer_campaign_io import (
    write_csv_atomic,
    write_json_atomic,
)
from files.research.scorer_trial import (
    confidence_enter_from_parameters,
    scorer_config_from_parameters,
)
from files.strategy.filters import determine_market_state


DIAGNOSTIC_SCHEMA_VERSION = 2
CHECKPOINTS = (1, 2, 3, 4, 6)

OUTCOME_REACHED_1R = "reached_1r"
OUTCOME_NOT_REACHED_1R = "not_reached_1r"

TRADE_IDENTITY_FIELDS = (
    "campaign_id",
    "trial_id",
    "execution_id",
    "split_name",
    "entry_ts_ms",
    "exit_ts_ms",
)

TRADE_BASE_FIELDS = (
    *TRADE_IDENTITY_FIELDS,
    "side",
    "entry_price",
    "exit_price",
    "qty",
    "exit_reason",
    "realized_pnl_usd",
    "realized_pnl_pct",
    "bars_held",
    "initial_stop_price",
    "initial_risk_price",
    "initial_risk_pct",
    "outcome_group",
    "reached_initial_025r",
    "reached_initial_050r",
    "reached_initial_075r",
    "reached_initial_100r",
    "reached_initial_150r",
    "reached_initial_200r",
    "full_mfe_r",
    "full_mae_r",
)

ENTRY_FIELDS = (
    "signal_ts_ms",
    "signal_decision_confidence",
    "signal_recomputed_confidence",
    "signal_confidence_difference",
    "confidence_enter",
    "signal_tradable",
    "signal_trend",
    "signal_volatility",
    "signal_market_reason",
    "signal_entry_reason",
    "signal_open",
    "signal_high",
    "signal_low",
    "signal_close",
    "signal_volume",
    "signal_close_ratio",
    "signal_rvol_20",
    "signal_ret_1",
    "signal_ret_3",
    "signal_ret_6",
    "signal_ret_12",
    "signal_ema_fast",
    "signal_ema_slow",
    "signal_ema_spread",
    "signal_ema_slow_slope",
    "signal_atr",
    "signal_atr_pct",
    "signal_rsi",
    "signal_vol_z",
    "signal_dollar_vol",
    "signal_dollar_vol_z",
    "signal_close_vs_ema_fast_pct",
    "signal_close_vs_ema_slow_pct",
    "signal_distance_from_prior_20_high_pct",
)

CHECKPOINT_FIELD_SUFFIXES = (
    "available",
    "ts_ms",
    "close",
    "close_progress_pct",
    "close_progress_r",
    "mfe_pct",
    "mfe_r",
    "mae_pct",
    "mae_r",
    "close_ratio",
    "average_close_ratio",
    "minimum_close_ratio",
    "low_close_ratio_count",
    "high_close_ratio_count",
    "closes_above_entry_count",
    "closes_below_entry_count",
    "consecutive_closes_below_entry",
    "rvol_20",
    "average_rvol_20",
    "maximum_rvol_20",
    "confidence",
    "confidence_change",
    "confidence_above_entry_threshold",
    "tradable",
    "trend",
    "volatility",
    "market_reason",
    "long_condition_supported",
    "ema_spread",
    "ema_spread_change",
    "ema_slow_slope",
    "ema_slow_slope_change",
    "ret_1",
    "rsi",
    "rsi_change",
    "atr_pct",
    "atr_pct_change",
    "gross_mark_pnl_usd",
)


class EntryProgressDiagnosticError(RuntimeError):
    """Raised when diagnostic evidence cannot be reconstructed safely."""


def _checkpoint_fields() -> tuple[str, ...]:
    return tuple(
        f"cp{checkpoint}_{suffix}"
        for checkpoint in CHECKPOINTS
        for suffix in CHECKPOINT_FIELD_SUFFIXES
    )


TRADE_FIELDS = (
    *TRADE_BASE_FIELDS,
    *ENTRY_FIELDS,
    *_checkpoint_fields(),
)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EntryProgressDiagnosticError(
            f"Unable to read JSON artifact: {path}"
        ) from exc

    if not isinstance(value, dict):
        raise EntryProgressDiagnosticError(
            f"JSON artifact must contain an object: {path}"
        )

    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(
            mode="r",
            newline="",
            encoding="utf-8",
        ) as handle:
            return list(csv.DictReader(handle))
    except Exception as exc:
        raise EntryProgressDiagnosticError(
            f"Unable to read CSV artifact: {path}"
        ) from exc


def _as_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)

    if not math.isfinite(parsed):
        return float(default)

    return float(parsed)


def _as_optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(parsed):
        return None

    return float(parsed)


def _as_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
    }


def _percentile(
    values: Sequence[float],
    fraction: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(float(value) for value in values)
    index = round((len(ordered) - 1) * fraction)

    return float(ordered[index])


def _find_first_key(
    value: Any,
    key: str,
) -> Any:
    if isinstance(value, Mapping):
        if key in value:
            return value[key]

        for child in value.values():
            found = _find_first_key(child, key)

            if found is not None:
                return found

    if isinstance(value, list):
        for child in value:
            found = _find_first_key(child, key)

            if found is not None:
                return found

    return None


def _find_trial_parameters(
    value: Any,
    trial_id: str,
) -> dict[str, float] | None:
    if isinstance(value, Mapping):
        if (
            str(value.get("trial_id", "")) == trial_id
            and isinstance(value.get("parameters"), Mapping)
        ):
            return {
                str(key): float(raw)
                for key, raw in value["parameters"].items()
            }

        for child in value.values():
            found = _find_trial_parameters(
                child,
                trial_id,
            )

            if found is not None:
                return found

    if isinstance(value, list):
        for child in value:
            found = _find_trial_parameters(
                child,
                trial_id,
            )

            if found is not None:
                return found

    return None


def _close_ratio(
    *,
    high: float,
    low: float,
    close: float,
) -> float | None:
    width = float(high) - float(low)

    if width <= 0.0:
        return None

    return float(
        (float(close) - float(low)) / width
    )


def _prepare_audited_bars(
    *,
    source: Any,
) -> tuple[pd.DataFrame, dict[str, tuple[int, int]]]:
    bars = source.audit.bars.copy()

    required = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing = sorted(required - set(bars.columns))

    if missing:
        raise EntryProgressDiagnosticError(
            f"Audited bars are missing columns: {missing}"
        )

    bars["timestamp"] = pd.to_datetime(
        bars["timestamp"],
        utc=True,
        errors="raise",
    )

    bars = bars.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)

    bars["ts_ms"] = (
        bars["timestamp"].astype("int64")
        // 1_000_000
    )

    bars["physical_segment_id"] = ""

    segment_bounds: dict[str, tuple[int, int]] = {}

    for physical in source.physical_segments:
        mask = (
            (
                bars["timestamp"]
                >= physical.physical_start_utc
            )
            & (
                bars["timestamp"]
                < physical.physical_end_utc_exclusive
            )
        )

        indices = bars.index[mask].tolist()

        if not indices:
            raise EntryProgressDiagnosticError(
                f"{physical.segment_id} has no audited bars."
            )

        start_index = int(indices[0])
        end_index = int(indices[-1])

        bars.loc[
            start_index:end_index,
            "physical_segment_id",
        ] = physical.segment_id

        segment_bounds[physical.segment_id] = (
            start_index,
            end_index,
        )

    if (bars["physical_segment_id"] == "").any():
        raise EntryProgressDiagnosticError(
            "Some audited bars were not assigned to a physical segment."
        )

    prior_20_mean = (
        bars.groupby(
            "physical_segment_id",
            sort=False,
        )["volume"]
        .transform(
            lambda series: (
                series.shift(1)
                .rolling(
                    window=20,
                    min_periods=20,
                )
                .mean()
            )
        )
    )

    bars["rvol_20"] = (
        bars["volume"] / prior_20_mean
    )

    bars["close_ratio"] = [
        _close_ratio(
            high=float(high),
            low=float(low),
            close=float(close),
        )
        for high, low, close in zip(
            bars["high"],
            bars["low"],
            bars["close"],
        )
    ]

    return bars, segment_bounds


def _timestamp_index(
    bars: pd.DataFrame,
) -> dict[int, int]:
    return {
        int(ts_ms): int(index)
        for index, ts_ms in zip(
            bars.index,
            bars["ts_ms"],
        )
    }


def _feature_frame_at_index(
    *,
    bars: pd.DataFrame,
    bar_index: int,
    segment_start_index: int,
    tail_n: int,
) -> pd.DataFrame:
    start_index = max(
        int(segment_start_index),
        int(bar_index) - int(tail_n) + 1,
    )

    market_data = (
        bars.loc[
            start_index:bar_index,
            [
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ],
        ]
        .reset_index(drop=True)
    )

    return compute_features(market_data)


def _decision_for_trade(
    *,
    decisions: list[dict[str, str]],
    entry_ts_ms: int,
    entry_price: float,
    step_ms: int,
) -> dict[str, str]:
    expected_signal_ts_ms = (
        int(entry_ts_ms) - int(step_ms)
    )

    exact = [
        row
        for row in decisions
        if (
            _as_int(row.get("ts_ms"))
            == expected_signal_ts_ms
        )
    ]

    tolerance = max(abs(entry_price) * 1e-9, 1e-9)

    for row in exact:
        position_entry_price = _as_optional_float(
            row.get("position_entry_price")
        )

        if (
            position_entry_price is not None
            and abs(
                position_entry_price - entry_price
            )
            <= tolerance
        ):
            return row

    candidates: list[dict[str, str]] = []

    for row in decisions:
        ts_ms = _as_int(row.get("ts_ms"))

        if not (
            expected_signal_ts_ms - step_ms
            <= ts_ms
            < entry_ts_ms
        ):
            continue

        position_entry_price = _as_optional_float(
            row.get("position_entry_price")
        )

        if position_entry_price is None:
            continue

        if (
            abs(position_entry_price - entry_price)
            <= tolerance
        ):
            candidates.append(row)

    if not candidates:
        raise EntryProgressDiagnosticError(
            "Unable to identify signal decision for trade: "
            f"entry_ts_ms={entry_ts_ms} "
            f"entry_price={entry_price}"
        )

    candidates.sort(
        key=lambda row: _as_int(row.get("ts_ms"))
    )

    return candidates[-1]


def _trade_key(
    *,
    split_name: str,
    entry_ts_ms: int,
    exit_ts_ms: int,
) -> tuple[str, int, int]:
    return (
        str(split_name),
        int(entry_ts_ms),
        int(exit_ts_ms),
    )


def _checkpoint_values(
    *,
    checkpoint: int,
    row: dict[str, Any],
    bars: pd.DataFrame,
    entry_index: int,
    exit_index: int,
    segment_start_index: int,
    segment_end_index: int,
    tail_n: int,
    min_bars: int,
    timeframe: str,
    model: EntryModel,
    confidence_enter: float,
    entry_price: float,
    initial_risk_price: float,
    qty: float,
    signal_features: pd.Series,
) -> None:
    prefix = f"cp{checkpoint}_"

    for suffix in CHECKPOINT_FIELD_SUFFIXES:
        row[f"{prefix}{suffix}"] = ""

    checkpoint_index = (
        int(entry_index) + int(checkpoint) - 1
    )

    if checkpoint_index >= int(exit_index):
        row[f"{prefix}available"] = False
        return

    if checkpoint_index > int(segment_end_index):
        row[f"{prefix}available"] = False
        return

    checkpoint_bars = bars.loc[
        entry_index:checkpoint_index
    ]

    if len(checkpoint_bars) != checkpoint:
        raise EntryProgressDiagnosticError(
            "Checkpoint bar count mismatch: "
            f"checkpoint={checkpoint} "
            f"actual={len(checkpoint_bars)}"
        )

    feats = _feature_frame_at_index(
        bars=bars,
        bar_index=checkpoint_index,
        segment_start_index=segment_start_index,
        tail_n=tail_n,
    )

    latest = feats.iloc[-1]

    market_state = determine_market_state(
        feats,
        timeframe=timeframe,
        min_bars=min_bars,
    )

    confidence = float(
        model.predict_confidence(
            feats,
            side="LONG",
        )
    )

    checkpoint_close = float(latest["close"])
    highest = float(checkpoint_bars["high"].max())
    lowest = float(checkpoint_bars["low"].min())

    close_progress_price = (
        checkpoint_close - entry_price
    )
    mfe_price = max(
        highest - entry_price,
        0.0,
    )
    mae_price = max(
        entry_price - lowest,
        0.0,
    )

    close_ratios = [
        float(value)
        for value in checkpoint_bars["close_ratio"]
        if pd.notna(value)
    ]

    rvol_values = [
        float(value)
        for value in checkpoint_bars["rvol_20"]
        if pd.notna(value)
    ]

    checkpoint_closes = [
        float(value)
        for value in checkpoint_bars["close"]
    ]

    consecutive_below = 0

    for close in reversed(checkpoint_closes):
        if close < entry_price:
            consecutive_below += 1
        else:
            break

    signal_confidence = _as_float(
        row["signal_recomputed_confidence"]
    )

    signal_ema_spread = float(
        signal_features["ema_spread"]
    )
    signal_ema_slow_slope = float(
        signal_features["ema_slow_slope"]
    )
    signal_rsi = float(signal_features["rsi"])
    signal_atr_pct = float(
        signal_features["atr_pct"]
    )

    row[f"{prefix}available"] = True
    row[f"{prefix}ts_ms"] = int(
        bars.loc[checkpoint_index, "ts_ms"]
    )
    row[f"{prefix}close"] = checkpoint_close
    row[f"{prefix}close_progress_pct"] = (
        close_progress_price / entry_price
    )
    row[f"{prefix}close_progress_r"] = (
        close_progress_price / initial_risk_price
    )
    row[f"{prefix}mfe_pct"] = (
        mfe_price / entry_price
    )
    row[f"{prefix}mfe_r"] = (
        mfe_price / initial_risk_price
    )
    row[f"{prefix}mae_pct"] = (
        mae_price / entry_price
    )
    row[f"{prefix}mae_r"] = (
        mae_price / initial_risk_price
    )
    row[f"{prefix}close_ratio"] = (
        bars.loc[checkpoint_index, "close_ratio"]
        if pd.notna(
            bars.loc[
                checkpoint_index,
                "close_ratio",
            ]
        )
        else ""
    )
    row[f"{prefix}average_close_ratio"] = (
        sum(close_ratios) / len(close_ratios)
        if close_ratios
        else ""
    )
    row[f"{prefix}minimum_close_ratio"] = (
        min(close_ratios)
        if close_ratios
        else ""
    )
    row[f"{prefix}low_close_ratio_count"] = sum(
        value < 0.30
        for value in close_ratios
    )
    row[f"{prefix}high_close_ratio_count"] = sum(
        value > 0.70
        for value in close_ratios
    )
    row[f"{prefix}closes_above_entry_count"] = sum(
        close > entry_price
        for close in checkpoint_closes
    )
    row[f"{prefix}closes_below_entry_count"] = sum(
        close < entry_price
        for close in checkpoint_closes
    )
    row[
        f"{prefix}consecutive_closes_below_entry"
    ] = consecutive_below
    row[f"{prefix}rvol_20"] = (
        bars.loc[checkpoint_index, "rvol_20"]
        if pd.notna(
            bars.loc[
                checkpoint_index,
                "rvol_20",
            ]
        )
        else ""
    )
    row[f"{prefix}average_rvol_20"] = (
        sum(rvol_values) / len(rvol_values)
        if rvol_values
        else ""
    )
    row[f"{prefix}maximum_rvol_20"] = (
        max(rvol_values)
        if rvol_values
        else ""
    )
    row[f"{prefix}confidence"] = confidence
    row[f"{prefix}confidence_change"] = (
        confidence - signal_confidence
    )
    row[
        f"{prefix}confidence_above_entry_threshold"
    ] = confidence >= confidence_enter
    row[f"{prefix}tradable"] = bool(
        market_state.tradable
    )
    row[f"{prefix}trend"] = market_state.trend
    row[f"{prefix}volatility"] = (
        market_state.volatility
    )
    row[f"{prefix}market_reason"] = (
        market_state.reason or ""
    )
    row[f"{prefix}long_condition_supported"] = bool(
        market_state.tradable
        and market_state.trend == "up"
        and confidence >= confidence_enter
    )
    row[f"{prefix}ema_spread"] = float(
        latest["ema_spread"]
    )
    row[f"{prefix}ema_spread_change"] = (
        float(latest["ema_spread"])
        - signal_ema_spread
    )
    row[f"{prefix}ema_slow_slope"] = float(
        latest["ema_slow_slope"]
    )
    row[f"{prefix}ema_slow_slope_change"] = (
        float(latest["ema_slow_slope"])
        - signal_ema_slow_slope
    )
    row[f"{prefix}ret_1"] = float(
        latest["ret_1"]
    )
    row[f"{prefix}rsi"] = float(
        latest["rsi"]
    )
    row[f"{prefix}rsi_change"] = (
        float(latest["rsi"]) - signal_rsi
    )
    row[f"{prefix}atr_pct"] = float(
        latest["atr_pct"]
    )
    row[f"{prefix}atr_pct_change"] = (
        float(latest["atr_pct"])
        - signal_atr_pct
    )
    row[f"{prefix}gross_mark_pnl_usd"] = (
        qty * close_progress_price
    )


def _build_trade_row(
    *,
    campaign_id: str,
    trial_id: str,
    execution: Mapping[str, Any],
    trade: Mapping[str, str],
    stop_row: Mapping[str, str],
    decision: Mapping[str, str],
    bars: pd.DataFrame,
    timestamp_to_index: Mapping[int, int],
    segment_bounds: Mapping[str, tuple[int, int]],
    step_ms: int,
    tail_n: int,
    min_bars: int,
    timeframe: str,
    model: EntryModel,
    confidence_enter: float,
) -> dict[str, Any]:
    side = str(trade.get("side", "")).upper()

    if side != "LONG":
        raise EntryProgressDiagnosticError(
            f"Non-LONG trade encountered: {side!r}"
        )

    entry_ts_ms = _as_int(trade.get("entry_ts_ms"))
    exit_ts_ms = _as_int(trade.get("exit_ts_ms"))
    entry_price = _as_float(trade.get("entry_price"))
    exit_price = _as_float(trade.get("exit_price"))
    qty = _as_float(trade.get("qty"))

    initial_stop_price = _as_float(
        stop_row.get("initial_stop_price")
    )

    initial_risk_price = (
        entry_price - initial_stop_price
    )

    if initial_risk_price <= 0.0:
        raise EntryProgressDiagnosticError(
            "Invalid initial risk for LONG trade: "
            f"entry={entry_price} "
            f"initial_stop={initial_stop_price}"
        )

    entry_index = timestamp_to_index.get(entry_ts_ms)
    exit_index = timestamp_to_index.get(exit_ts_ms)

    if entry_index is None or exit_index is None:
        raise EntryProgressDiagnosticError(
            "Trade timestamps are absent from audited bars: "
            f"entry={entry_ts_ms} exit={exit_ts_ms}"
        )

    segment_id = str(
        bars.loc[entry_index, "physical_segment_id"]
    )

    if (
        str(
            bars.loc[
                exit_index,
                "physical_segment_id",
            ]
        )
        != segment_id
    ):
        raise EntryProgressDiagnosticError(
            "Trade crosses a physical source gap."
        )

    segment_start_index, segment_end_index = (
        segment_bounds[segment_id]
    )

    signal_ts_ms = _as_int(decision.get("ts_ms"))

    signal_index = timestamp_to_index.get(
        signal_ts_ms
    )

    if signal_index is None:
        raise EntryProgressDiagnosticError(
            f"Signal timestamp absent from audited bars: {signal_ts_ms}"
        )

    if signal_index + 1 != entry_index:
        raise EntryProgressDiagnosticError(
            "Signal and entry bars are not adjacent: "
            f"signal={signal_ts_ms} "
            f"entry={entry_ts_ms}"
        )

    signal_feats = _feature_frame_at_index(
        bars=bars,
        bar_index=signal_index,
        segment_start_index=segment_start_index,
        tail_n=tail_n,
    )

    signal_latest = signal_feats.iloc[-1]

    recomputed_confidence = float(
        model.predict_confidence(
            signal_feats,
            side="LONG",
        )
    )

    decision_confidence = _as_float(
        decision.get("entry_confidence")
    )

    full_trade_bars = bars.loc[
        entry_index:exit_index
    ]

    full_mfe_price = max(
        float(full_trade_bars["high"].max())
        - entry_price,
        0.0,
    )
    full_mae_price = max(
        entry_price
        - float(full_trade_bars["low"].min()),
        0.0,
    )

    full_mfe_r = (
        full_mfe_price / initial_risk_price
    )
    full_mae_r = (
        full_mae_price / initial_risk_price
    )

    prior_20_start = max(
        segment_start_index,
        signal_index - 20,
    )

    prior_20 = bars.loc[
        prior_20_start:signal_index - 1
    ]

    prior_20_high = (
        float(prior_20["high"].max())
        if not prior_20.empty
        else float(signal_latest["high"])
    )

    signal_close = float(signal_latest["close"])

    row: dict[str, Any] = {
        "campaign_id": campaign_id,
        "trial_id": trial_id,
        "execution_id": execution["execution_id"],
        "split_name": execution["split_name"],
        "entry_ts_ms": entry_ts_ms,
        "exit_ts_ms": exit_ts_ms,
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "qty": qty,
        "exit_reason": str(
            trade.get("exit_reason", "")
        ),
        "realized_pnl_usd": _as_float(
            trade.get("realized_pnl_usd")
        ),
        "realized_pnl_pct": _as_float(
            trade.get("realized_pnl_pct")
        ),
        "bars_held": _as_int(
            stop_row.get("bars_held")
        ),
        "initial_stop_price": initial_stop_price,
        "initial_risk_price": initial_risk_price,
        "initial_risk_pct": (
            initial_risk_price / entry_price
        ),
        "outcome_group": (
            OUTCOME_REACHED_1R
            if full_mfe_r >= 1.0
            else OUTCOME_NOT_REACHED_1R
        ),
        "reached_initial_025r": (
            full_mfe_r >= 0.25
        ),
        "reached_initial_050r": (
            full_mfe_r >= 0.50
        ),
        "reached_initial_075r": (
            full_mfe_r >= 0.75
        ),
        "reached_initial_100r": (
            full_mfe_r >= 1.00
        ),
        "reached_initial_150r": (
            full_mfe_r >= 1.50
        ),
        "reached_initial_200r": (
            full_mfe_r >= 2.00
        ),
        "full_mfe_r": full_mfe_r,
        "full_mae_r": full_mae_r,
        "signal_ts_ms": signal_ts_ms,
        "signal_decision_confidence": (
            decision_confidence
        ),
        "signal_recomputed_confidence": (
            recomputed_confidence
        ),
        "signal_confidence_difference": (
            recomputed_confidence
            - decision_confidence
        ),
        "confidence_enter": confidence_enter,
        "signal_tradable": _as_bool(
            decision.get("tradable")
        ),
        "signal_trend": str(
            decision.get("trend", "")
        ),
        "signal_volatility": str(
            decision.get("volatility", "")
        ),
        "signal_market_reason": str(
            decision.get("market_reason", "")
        ),
        "signal_entry_reason": str(
            decision.get("entry_reason", "")
        ),
        "signal_open": float(
            signal_latest["open"]
        ),
        "signal_high": float(
            signal_latest["high"]
        ),
        "signal_low": float(
            signal_latest["low"]
        ),
        "signal_close": signal_close,
        "signal_volume": float(
            signal_latest["volume"]
        ),
        "signal_close_ratio": (
            bars.loc[signal_index, "close_ratio"]
            if pd.notna(
                bars.loc[
                    signal_index,
                    "close_ratio",
                ]
            )
            else ""
        ),
        "signal_rvol_20": (
            bars.loc[signal_index, "rvol_20"]
            if pd.notna(
                bars.loc[
                    signal_index,
                    "rvol_20",
                ]
            )
            else ""
        ),
        "signal_ret_1": float(
            signal_latest["ret_1"]
        ),
        "signal_ret_3": (
            signal_close
            / float(
                bars.loc[
                    max(
                        segment_start_index,
                        signal_index - 3,
                    ),
                    "close",
                ]
            )
            - 1.0
        ),
        "signal_ret_6": (
            signal_close
            / float(
                bars.loc[
                    max(
                        segment_start_index,
                        signal_index - 6,
                    ),
                    "close",
                ]
            )
            - 1.0
        ),
        "signal_ret_12": (
            signal_close
            / float(
                bars.loc[
                    max(
                        segment_start_index,
                        signal_index - 12,
                    ),
                    "close",
                ]
            )
            - 1.0
        ),
        "signal_ema_fast": float(
            signal_latest["ema_fast"]
        ),
        "signal_ema_slow": float(
            signal_latest["ema_slow"]
        ),
        "signal_ema_spread": float(
            signal_latest["ema_spread"]
        ),
        "signal_ema_slow_slope": float(
            signal_latest["ema_slow_slope"]
        ),
        "signal_atr": float(
            signal_latest["atr"]
        ),
        "signal_atr_pct": float(
            signal_latest["atr_pct"]
        ),
        "signal_rsi": float(
            signal_latest["rsi"]
        ),
        "signal_vol_z": float(
            signal_latest["vol_z"]
        ),
        "signal_dollar_vol": float(
            signal_latest["dollar_vol"]
        ),
        "signal_dollar_vol_z": float(
            signal_latest["dollar_vol_z"]
        ),
        "signal_close_vs_ema_fast_pct": (
            signal_close
            / float(signal_latest["ema_fast"])
            - 1.0
        ),
        "signal_close_vs_ema_slow_pct": (
            signal_close
            / float(signal_latest["ema_slow"])
            - 1.0
        ),
        "signal_distance_from_prior_20_high_pct": (
            signal_close / prior_20_high - 1.0
        ),
    }

    for checkpoint in CHECKPOINTS:
        _checkpoint_values(
            checkpoint=checkpoint,
            row=row,
            bars=bars,
            entry_index=entry_index,
            exit_index=exit_index,
            segment_start_index=segment_start_index,
            segment_end_index=segment_end_index,
            tail_n=tail_n,
            min_bars=min_bars,
            timeframe=timeframe,
            model=model,
            confidence_enter=confidence_enter,
            entry_price=entry_price,
            initial_risk_price=initial_risk_price,
            qty=qty,
            signal_features=signal_latest,
        )

    return row


def _numeric_feature_names() -> tuple[str, ...]:
    fields = [
        "initial_risk_pct",
        "full_mfe_r",
        "full_mae_r",
        "signal_decision_confidence",
        "signal_recomputed_confidence",
        "signal_close_ratio",
        "signal_rvol_20",
        "signal_ret_1",
        "signal_ret_3",
        "signal_ret_6",
        "signal_ret_12",
        "signal_ema_spread",
        "signal_ema_slow_slope",
        "signal_atr_pct",
        "signal_rsi",
        "signal_vol_z",
        "signal_dollar_vol_z",
        "signal_close_vs_ema_fast_pct",
        "signal_close_vs_ema_slow_pct",
        "signal_distance_from_prior_20_high_pct",
    ]

    for checkpoint in CHECKPOINTS:
        prefix = f"cp{checkpoint}_"

        fields.extend(
            [
                f"{prefix}close_progress_r",
                f"{prefix}mfe_r",
                f"{prefix}mae_r",
                f"{prefix}close_ratio",
                f"{prefix}average_close_ratio",
                f"{prefix}minimum_close_ratio",
                f"{prefix}low_close_ratio_count",
                f"{prefix}high_close_ratio_count",
                f"{prefix}rvol_20",
                f"{prefix}average_rvol_20",
                f"{prefix}maximum_rvol_20",
                f"{prefix}confidence",
                f"{prefix}confidence_change",
                f"{prefix}ema_spread_change",
                f"{prefix}ema_slow_slope_change",
                f"{prefix}ret_1",
                f"{prefix}rsi_change",
                f"{prefix}atr_pct_change",
            ]
        )

    return tuple(fields)


def _feature_group_summary(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    split_names = sorted(
        {
            str(row["split_name"])
            for row in rows
        }
    )

    scopes = [("all_validation", list(rows))]

    scopes.extend(
        (
            split_name,
            [
                row
                for row in rows
                if row["split_name"] == split_name
            ],
        )
        for split_name in split_names
    )

    for scope_name, scope_rows in scopes:
        for outcome_group in (
            OUTCOME_REACHED_1R,
            OUTCOME_NOT_REACHED_1R,
        ):
            group_rows = [
                row
                for row in scope_rows
                if row["outcome_group"]
                == outcome_group
            ]

            for feature_name in _numeric_feature_names():
                values = [
                    parsed
                    for row in group_rows
                    if (
                        parsed := _as_optional_float(
                            row.get(feature_name)
                        )
                    )
                    is not None
                ]

                output.append(
                    {
                        "scope": scope_name,
                        "outcome_group": outcome_group,
                        "feature_name": feature_name,
                        "available_count": len(values),
                        "missing_count": (
                            len(group_rows) - len(values)
                        ),
                        "mean": (
                            sum(values) / len(values)
                            if values
                            else ""
                        ),
                        "median": (
                            median(values)
                            if values
                            else ""
                        ),
                        "p25": (
                            _percentile(values, 0.25)
                            if values
                            else ""
                        ),
                        "p75": (
                            _percentile(values, 0.75)
                            if values
                            else ""
                        ),
                    }
                )

    return output


def _fold_summary(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

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

        for outcome_group in (
            "all",
            OUTCOME_REACHED_1R,
            OUTCOME_NOT_REACHED_1R,
        ):
            group_rows = (
                split_rows
                if outcome_group == "all"
                else [
                    row
                    for row in split_rows
                    if row["outcome_group"]
                    == outcome_group
                ]
            )

            pnl_values = [
                _as_float(
                    row["realized_pnl_usd"]
                )
                for row in group_rows
            ]

            bars_values = [
                _as_int(row["bars_held"])
                for row in group_rows
            ]

            output.append(
                {
                    "split_name": split_name,
                    "outcome_group": outcome_group,
                    "trade_count": len(group_rows),
                    "total_pnl_usd": sum(pnl_values),
                    "average_pnl_usd": (
                        sum(pnl_values)
                        / len(pnl_values)
                        if pnl_values
                        else 0.0
                    ),
                    "median_bars_held": (
                        median(bars_values)
                        if bars_values
                        else 0.0
                    ),
                    "positive_trade_count": sum(
                        pnl > 0.0
                        for pnl in pnl_values
                    ),
                    "negative_trade_count": sum(
                        pnl < 0.0
                        for pnl in pnl_values
                    ),
                }
            )

    return output


def _threshold_definitions() -> tuple[
    tuple[int, str, str, tuple[float, ...]],
    ...
]:
    return (
        (
            3,
            "close_progress_r",
            "below",
            (-0.50, -0.25, 0.00, 0.10, 0.25),
        ),
        (
            3,
            "mfe_r",
            "below",
            (0.10, 0.25, 0.50, 0.75),
        ),
        (
            3,
            "average_close_ratio",
            "below",
            (0.30, 0.40, 0.50),
        ),
        (
            3,
            "low_close_ratio_count",
            "at_least",
            (1.0, 2.0, 3.0),
        ),
        (
            3,
            "confidence_change",
            "below",
            (-0.20, -0.10, -0.05, 0.00),
        ),
        (
            6,
            "close_progress_r",
            "below",
            (-0.50, -0.25, 0.00, 0.10, 0.25),
        ),
        (
            6,
            "mfe_r",
            "below",
            (0.10, 0.25, 0.50, 0.75),
        ),
        (
            6,
            "average_close_ratio",
            "below",
            (0.30, 0.40, 0.50),
        ),
        (
            6,
            "low_close_ratio_count",
            "at_least",
            (2.0, 3.0, 4.0),
        ),
        (
            6,
            "confidence_change",
            "below",
            (-0.20, -0.10, -0.05, 0.00),
        ),
    )


def _threshold_analysis(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []

    split_names = sorted(
        {
            str(row["split_name"])
            for row in rows
        }
    )

    scopes = [("all_validation", list(rows))]

    scopes.extend(
        (
            split_name,
            [
                row
                for row in rows
                if row["split_name"] == split_name
            ],
        )
        for split_name in split_names
    )

    for scope_name, scope_rows in scopes:
        for (
            checkpoint,
            feature_suffix,
            operator,
            thresholds,
        ) in _threshold_definitions():
            feature_name = (
                f"cp{checkpoint}_{feature_suffix}"
            )
            availability_name = (
                f"cp{checkpoint}_available"
            )

            available_rows = [
                row
                for row in scope_rows
                if _as_bool(
                    row.get(availability_name)
                )
                and _as_optional_float(
                    row.get(feature_name)
                )
                is not None
            ]

            for threshold in thresholds:
                if operator == "below":
                    flagged = [
                        row
                        for row in available_rows
                        if _as_float(
                            row[feature_name]
                        )
                        < threshold
                    ]
                elif operator == "at_least":
                    flagged = [
                        row
                        for row in available_rows
                        if _as_float(
                            row[feature_name]
                        )
                        >= threshold
                    ]
                else:
                    raise EntryProgressDiagnosticError(
                        f"Unsupported threshold operator: {operator}"
                    )

                failed_available = [
                    row
                    for row in available_rows
                    if row["outcome_group"]
                    == OUTCOME_NOT_REACHED_1R
                ]
                successful_available = [
                    row
                    for row in available_rows
                    if row["outcome_group"]
                    == OUTCOME_REACHED_1R
                ]
                failed_flagged = [
                    row
                    for row in flagged
                    if row["outcome_group"]
                    == OUTCOME_NOT_REACHED_1R
                ]
                successful_flagged = [
                    row
                    for row in flagged
                    if row["outcome_group"]
                    == OUTCOME_REACHED_1R
                ]

                loss_potentially_avoided = sum(
                    max(
                        -_as_float(
                            row["realized_pnl_usd"]
                        ),
                        0.0,
                    )
                    for row in failed_flagged
                )

                profit_potentially_sacrificed = sum(
                    max(
                        _as_float(
                            row["realized_pnl_usd"]
                        ),
                        0.0,
                    )
                    for row in successful_flagged
                )

                gross_checkpoint_mark_pnl = sum(
                    _as_float(
                        row.get(
                            f"cp{checkpoint}_gross_mark_pnl_usd"
                        )
                    )
                    for row in flagged
                )

                output.append(
                    {
                        "scope": scope_name,
                        "checkpoint": checkpoint,
                        "feature_name": feature_name,
                        "operator": operator,
                        "threshold": threshold,
                        "available_trade_count": len(
                            available_rows
                        ),
                        "flagged_trade_count": len(flagged),
                        "failed_available_count": len(
                            failed_available
                        ),
                        "failed_flagged_count": len(
                            failed_flagged
                        ),
                        "failed_capture_rate": (
                            len(failed_flagged)
                            / len(failed_available)
                            if failed_available
                            else 0.0
                        ),
                        "reached_1r_available_count": len(
                            successful_available
                        ),
                        "reached_1r_flagged_count": len(
                            successful_flagged
                        ),
                        "reached_1r_false_positive_rate": (
                            len(successful_flagged)
                            / len(successful_available)
                            if successful_available
                            else 0.0
                        ),
                        "loss_potentially_avoided_usd": (
                            loss_potentially_avoided
                        ),
                        "profit_potentially_sacrificed_usd": (
                            profit_potentially_sacrificed
                        ),
                        "diagnostic_net_upper_bound_usd": (
                            loss_potentially_avoided
                            - profit_potentially_sacrificed
                        ),
                        "flagged_gross_checkpoint_mark_pnl_usd": (
                            gross_checkpoint_mark_pnl
                        ),
                    }
                )

    return output


def _winner_concentration(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    def summarize(
        scope_rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        pnl = sorted(
            (
                _as_float(
                    row["realized_pnl_usd"]
                )
                for row in scope_rows
            ),
            reverse=True,
        )

        gross_profit = sum(
            value for value in pnl if value > 0.0
        )
        gross_loss = sum(
            value for value in pnl if value < 0.0
        )
        total = sum(pnl)

        def top_sum(count: int) -> float:
            return sum(pnl[: min(count, len(pnl))])

        trimmed = pnl[1:-1] if len(pnl) > 2 else pnl

        return {
            "trade_count": len(pnl),
            "total_pnl_usd": total,
            "gross_profit_usd": gross_profit,
            "gross_loss_usd": gross_loss,
            "profit_factor": (
                gross_profit / abs(gross_loss)
                if gross_loss < 0.0
                else 0.0
            ),
            "best_trade_pnl_usd": (
                pnl[0] if pnl else 0.0
            ),
            "top_1_trade_pnl_usd": top_sum(1),
            "top_3_trade_pnl_usd": top_sum(3),
            "top_5_trade_pnl_usd": top_sum(5),
            "top_10_trade_pnl_usd": top_sum(10),
            "pnl_without_best_trade_usd": (
                total - top_sum(1)
            ),
            "pnl_without_top_3_trades_usd": (
                total - top_sum(3)
            ),
            "pnl_without_top_5_trades_usd": (
                total - top_sum(5)
            ),
            "median_trade_pnl_usd": (
                median(pnl) if pnl else 0.0
            ),
            "trimmed_mean_pnl_usd": (
                sum(trimmed) / len(trimmed)
                if trimmed
                else 0.0
            ),
        }

    result = {
        "all_validation": summarize(rows),
        "validation_splits": {},
    }

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

        result["validation_splits"][
            split_name
        ] = summarize(split_rows)

    return result


def build_entry_progress_diagnostic(
    *,
    campaign_root: Path,
    trial_id: str,
) -> dict[str, Any]:
    campaign_manifest = _load_json_object(
        campaign_root / "campaign_manifest.json"
    )
    execution_plan = _load_json_object(
        campaign_root / "execution_plan.json"
    )

    campaign_id = str(
        campaign_manifest.get("campaign_id", "")
    )

    if campaign_id != campaign_root.name:
        raise EntryProgressDiagnosticError(
            "Campaign root and manifest identity differ."
        )

    parameters = _find_trial_parameters(
        campaign_manifest,
        trial_id,
    )

    if parameters is None:
        parameters = _find_trial_parameters(
            execution_plan,
            trial_id,
        )

    if parameters is None:
        raise EntryProgressDiagnosticError(
            f"Trial parameters not found: {trial_id}"
        )

    scorer_config = scorer_config_from_parameters(
        parameters
    )
    confidence_enter = (
        confidence_enter_from_parameters(parameters)
    )
    model = EntryModel(cfg=scorer_config)

    data_tag = str(
        _find_first_key(
            campaign_manifest,
            "data_tag",
        )
    )
    symbol = str(
        _find_first_key(
            campaign_manifest,
            "symbol",
        )
    )
    timeframe = str(
        _find_first_key(
            campaign_manifest,
            "timeframe",
        )
    )

    min_bars_value = _find_first_key(
        campaign_manifest,
        "min_bars",
    )
    min_bars = (
        int(min_bars_value)
        if min_bars_value is not None
        else 200
    )
    tail_n = max(min_bars, 200)

    source = load_and_resolve_historical_research_source(
        data_tag=data_tag,
        expected_symbol=symbol,
        expected_timeframe=timeframe,
    )

    expected_fingerprint = str(
        _find_first_key(
            campaign_manifest,
            "manifest_fingerprint",
        )
    )

    if (
        source.manifest_fingerprint
        != expected_fingerprint
    ):
        raise EntryProgressDiagnosticError(
            "Historical source fingerprint mismatch: "
            f"expected={expected_fingerprint} "
            f"actual={source.manifest_fingerprint}"
        )

    bars, segment_bounds = (
        _prepare_audited_bars(source=source)
    )
    timestamp_to_index = _timestamp_index(bars)

    stop_diagnostic_path = (
        campaign_root
        / "diagnostics"
        / "stop_behavior"
        / trial_id
        / "trades.csv"
    )

    stop_rows = _read_csv(
        stop_diagnostic_path
    )

    stop_by_key = {
        _trade_key(
            split_name=row["split_name"],
            entry_ts_ms=_as_int(
                row["entry_ts_ms"]
            ),
            exit_ts_ms=_as_int(
                row["exit_ts_ms"]
            ),
        ): row
        for row in stop_rows
    }

    executions = [
        execution
        for execution in execution_plan["executions"]
        if (
            execution["trial_id"] == trial_id
            and execution["window_role"]
            == "validation"
            and execution["cost_scenario_id"]
            == "base"
        )
    ]

    if not executions:
        raise EntryProgressDiagnosticError(
            "No base validation executions found."
        )

    trade_rows: list[dict[str, Any]] = []

    for execution in executions:
        result = _load_json_object(
            Path(execution["result_json"])
        )

        if result.get("status") != "succeeded":
            raise EntryProgressDiagnosticError(
                "Execution did not succeed: "
                f"{execution['execution_id']}"
            )

        backtest = result.get(
            "backtest",
            {},
        ).get(
            "backtest",
            {},
        )

        trades_path = Path(
            str(backtest["trades_csv"])
        )
        decisions_path = Path(
            str(backtest["decisions_csv"])
        )

        trades = _read_csv(trades_path)
        decisions = _read_csv(decisions_path)

        for trade in trades:
            entry_ts_ms = _as_int(
                trade.get("entry_ts_ms")
            )
            exit_ts_ms = _as_int(
                trade.get("exit_ts_ms")
            )
            entry_price = _as_float(
                trade.get("entry_price")
            )

            key = _trade_key(
                split_name=execution["split_name"],
                entry_ts_ms=entry_ts_ms,
                exit_ts_ms=exit_ts_ms,
            )

            stop_row = stop_by_key.get(key)

            if stop_row is None:
                raise EntryProgressDiagnosticError(
                    "Stop diagnostic row not found: "
                    f"{key}"
                )

            decision = _decision_for_trade(
                decisions=decisions,
                entry_ts_ms=entry_ts_ms,
                entry_price=entry_price,
                step_ms=source.timeframe_step_ms,
            )

            trade_rows.append(
                _build_trade_row(
                    campaign_id=campaign_id,
                    trial_id=trial_id,
                    execution=execution,
                    trade=trade,
                    stop_row=stop_row,
                    decision=decision,
                    bars=bars,
                    timestamp_to_index=(
                        timestamp_to_index
                    ),
                    segment_bounds=segment_bounds,
                    step_ms=source.timeframe_step_ms,
                    tail_n=tail_n,
                    min_bars=min_bars,
                    timeframe=timeframe,
                    model=model,
                    confidence_enter=confidence_enter,
                )
            )

    trade_rows.sort(
        key=lambda row: (
            row["split_name"],
            int(row["entry_ts_ms"]),
        )
    )

    confidence_differences = [
        abs(
            _as_float(
                row[
                    "signal_confidence_difference"
                ]
            )
        )
        for row in trade_rows
    ]

    maximum_confidence_difference = max(
        confidence_differences,
        default=0.0,
    )

    if maximum_confidence_difference > 1e-9:
        raise EntryProgressDiagnosticError(
            "Recomputed signal confidence differs from "
            "the campaign decision artifact: "
            f"maximum_difference="
            f"{maximum_confidence_difference}"
        )

    feature_summary = _feature_group_summary(
        trade_rows
    )
    threshold_rows = _threshold_analysis(
        trade_rows
    )
    fold_rows = _fold_summary(trade_rows)
    winner_concentration = _winner_concentration(
        trade_rows
    )

    output_dir = (
        campaign_root
        / "diagnostics"
        / "entry_early_progress"
        / trial_id
    )

    trades_path = (
        output_dir
        / "entry_early_progress_trades.csv"
    )
    feature_summary_path = (
        output_dir
        / "feature_group_summary.csv"
    )
    threshold_path = (
        output_dir
        / "threshold_analysis.csv"
    )
    fold_path = (
        output_dir
        / "fold_summary.csv"
    )
    winner_path = (
        output_dir
        / "winner_concentration.json"
    )
    summary_path = (
        output_dir
        / "diagnostic_summary.json"
    )

    write_csv_atomic(
        path=trades_path,
        fieldnames=TRADE_FIELDS,
        rows=trade_rows,
    )

    write_csv_atomic(
        path=feature_summary_path,
        fieldnames=(
            "scope",
            "outcome_group",
            "feature_name",
            "available_count",
            "missing_count",
            "mean",
            "median",
            "p25",
            "p75",
        ),
        rows=feature_summary,
    )

    write_csv_atomic(
        path=threshold_path,
        fieldnames=(
            "scope",
            "checkpoint",
            "feature_name",
            "operator",
            "threshold",
            "available_trade_count",
            "flagged_trade_count",
            "failed_available_count",
            "failed_flagged_count",
            "failed_capture_rate",
            "reached_1r_available_count",
            "reached_1r_flagged_count",
            "reached_1r_false_positive_rate",
            "loss_potentially_avoided_usd",
            "profit_potentially_sacrificed_usd",
            "diagnostic_net_upper_bound_usd",
            "flagged_gross_checkpoint_mark_pnl_usd",
        ),
        rows=threshold_rows,
    )

    write_csv_atomic(
        path=fold_path,
        fieldnames=(
            "split_name",
            "outcome_group",
            "trade_count",
            "total_pnl_usd",
            "average_pnl_usd",
            "median_bars_held",
            "positive_trade_count",
            "negative_trade_count",
        ),
        rows=fold_rows,
    )

    write_json_atomic(
        path=winner_path,
        value=winner_concentration,
    )

    summary = {
        "diagnostic_schema_version": (
            DIAGNOSTIC_SCHEMA_VERSION
        ),
        "diagnostic_type": (
            "read_only_entry_early_progress_v2"
        ),
        "campaign_id": campaign_id,
        "trial_id": trial_id,
        "source_manifest_fingerprint": (
            source.manifest_fingerprint
        ),
        "timeframe": timeframe,
        "min_bars": min_bars,
        "feature_tail_bars": tail_n,
        "checkpoint_bars": list(CHECKPOINTS),
        "trade_count": len(trade_rows),
        "reached_1r_count": sum(
            row["outcome_group"]
            == OUTCOME_REACHED_1R
            for row in trade_rows
        ),
        "not_reached_1r_count": sum(
            row["outcome_group"]
            == OUTCOME_NOT_REACHED_1R
            for row in trade_rows
        ),
        "maximum_signal_confidence_reconstruction_difference": (
            maximum_confidence_difference
        ),
        "rvol_contract": {
            "window_bars": 20,
            "current_bar_excluded": True,
            "physical_segment_scoped": True,
            "crosses_confirmed_gap": False,
        },
        "anti_leakage_contract": {
            "checkpoint_features_use_future_bars": False,
            "outcome_labels_joined_after_features": True,
            "unavailable_checkpoint_carried_forward": False,
            "exit_bar_checkpoint_features_used": False,
            "threshold_results_are_diagnostic_only": True,
            "strategy_or_backtest_replayed": False,
        },
        "counterfactual_warning": (
            "Threshold results are descriptive upper bounds. "
            "Any policy must be replayed through the full engine."
        ),
        "artifacts": {
            "trades_csv": str(trades_path),
            "feature_group_summary_csv": str(
                feature_summary_path
            ),
            "threshold_analysis_csv": str(
                threshold_path
            ),
            "fold_summary_csv": str(fold_path),
            "winner_concentration_json": str(
                winner_path
            ),
            "diagnostic_summary_json": str(
                summary_path
            ),
        },
    }

    write_json_atomic(
        path=summary_path,
        value=summary,
    )

    return summary
