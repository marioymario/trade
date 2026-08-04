# files/backtest/engine.py
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from files.backtest.replay import (
    ReplayPlan,
    ReplaySegment,
    build_legacy_replay_plan,
    build_research_replay_plan,
)
from files.backtest.segment_executor import (
    SegmentBoundaryPolicy,
    SegmentExecutionRequest,
    SegmentWriterContext,
    execute_backtest_segment,
)
from files.broker.paper import PaperBroker
from files.config import TradingConfig, load_trading_config
from files.data.decisions import append_decision_csv, decisions_csv_path
from files.data.features import compute_features, validate_latest_features
from files.data.paths import (
    historical_gap_manifest_path,
    raw_symbol_dir,
    trades_csv_path,
)
from files.data.trades import append_trade_csv
from files.research.execution_events import (
    ResearchExecutionEvent,
    ResearchExecutionEventWriter,
)
from files.research.historical_dataset import (
    PHYSICAL_DATASET_END,
    PHYSICAL_GAP_BOUNDARY,
    build_historical_research_dataset,
    load_and_audit_historical_dataset,
)
from files.strategy.filters import determine_market_state
from files.strategy.rules import (
    ATR_MULT,
    compute_initial_stop,
    compute_trailing_stop_update,
    evaluate_entry,
    evaluate_exit,
    size_position,
)
from files.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BacktestResult:
    bt_exchange: str
    symbol: str
    timeframe: str
    bars_total: int
    bars_processed: int
    decisions_csv: str
    trades_csv: str
    research_execution_events_csv: str


def _timeframe_to_seconds(timeframe: str) -> int:
    tf = timeframe.strip().lower()
    unit = tf[-1]
    n = int(tf[:-1])
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 60 * 60
    if unit == "d":
        return n * 60 * 60 * 24
    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def _storage_symbol(symbol: str) -> str:
    """
    Normalize symbol for filesystem + processed CSV identity:
      - BTC/USD -> BTC_USD
    """
    return symbol.strip().upper().replace("/", "_")


def _fill_position_fields(decision_row: dict, position) -> None:
    """Mutates decision_row to include position data if available."""
    if position is None:
        decision_row["position_side"] = ""
        decision_row["position_qty"] = ""
        decision_row["position_entry_price"] = ""
        decision_row["position_stop_price"] = ""
        decision_row["position_trailing_anchor_price"] = ""
        return

    decision_row["position_side"] = position.side
    decision_row["position_qty"] = float(position.qty)
    decision_row["position_entry_price"] = float(position.entry_price)
    decision_row["position_stop_price"] = (
        float(position.stop_price) if position.stop_price is not None else ""
    )
    decision_row["position_trailing_anchor_price"] = (
        float(position.trailing_anchor_price)
        if getattr(position, "trailing_anchor_price", None) is not None
        else ""
    )


def _read_last_ts_ms_from_decisions_csv(path: str) -> int | None:
    """Return the last ts_ms found in an existing decisions CSV, or None."""
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return None

        last: int | None = None
        with open(path, "r", newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                v = row.get("ts_ms", "") if row else ""
                try:
                    ts_ms = int(float(v)) if v not in (None, "", "nan") else 0
                except Exception:
                    ts_ms = 0
                if ts_ms > 0:
                    last = ts_ms
        return last
    except Exception as e:
        logger.warning(
            "Failed to read last ts_ms from decisions CSV",
            extra={"path": path, "error": repr(e)},
        )
        return None


def _load_all_ohlcv_parquet(*, exchange: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Layout (canonical):
      data/raw/{exchange}/{SYMBOL}/{timeframe}/date=YYYY-MM-DD/bars.parquet
    """
    root: Path = raw_symbol_dir(exchange=exchange, symbol=symbol, timeframe=timeframe)
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

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV missing columns: {missing}")

    out = out[required].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out = out.dropna(subset=["timestamp"])
    out = out.drop_duplicates(subset=["timestamp"], keep="last")
    out = out.sort_values("timestamp").reset_index(drop=True)
    return out



def _resolve_backtest_replay_plan(
    *,
    cfg: TradingConfig,
    storage_symbol: str,
    start_ts_ms: int | None,
    end_ts_ms: int | None,
) -> ReplayPlan:
    """
    Resolve the authoritative replay plan for a backtest run.

    Ownership:
    - engine selects and loads the data source
    - historical_dataset validates manifest-backed data
    - replay transforms already-resolved data into execution units
    """
    warmup_bars = max(int(cfg.min_bars), 50) + 5

    manifest_path = historical_gap_manifest_path(
        data_tag=cfg.data_tag,
    )

    if manifest_path.is_file():
        audit = load_and_audit_historical_dataset(
            data_tag=cfg.data_tag,
            expected_symbol=cfg.symbol,
            expected_timeframe=cfg.timeframe,
            manifest_path=manifest_path,
        )

        dataset = build_historical_research_dataset(
            audit=audit,
            start_ts_ms=start_ts_ms,
            end_ts_ms=end_ts_ms,
            warmup_bars=warmup_bars,
        )

        return build_research_replay_plan(
            dataset=dataset,
        )

    source_bars = _load_all_ohlcv_parquet(
        exchange=cfg.data_tag,
        symbol=storage_symbol,
        timeframe=cfg.timeframe,
    )

    if len(source_bars) == 0:
        raise RuntimeError(
            f"No bars found under "
            f"data/raw/{cfg.data_tag}/"
            f"{storage_symbol}/{cfg.timeframe} "
            f"(DATA_TAG={cfg.data_tag}, "
            f"CCXT_EXCHANGE={cfg.ccxt_exchange})"
        )

    return build_legacy_replay_plan(
        bars=source_bars,
        start_ts_ms=start_ts_ms,
        end_ts_ms=end_ts_ms,
        warmup_bars=warmup_bars,
    )


def _build_research_segment_boundary_policy(
    *,
    segment: ReplaySegment,
) -> SegmentBoundaryPolicy:
    """
    Classify why a manifest-backed research segment ends.

    The engine owns this run-level policy decision. The segment executor
    receives only the resolved policy and does not inspect manifests.

    Priority:
    1. An applied requested end terminates the requested run range.
    2. A physical gap boundary requires the broker to finish flat.
    3. A physical dataset end may expose unresolved final state.
    """
    if segment.requested_end_applied:
        return SegmentBoundaryPolicy(
            boundary_type="requested_range_end",
            following_gap_id=None,
            allow_next_bar_entry=False,
            force_flat_at_end=False,
            unresolved_position_allowed=True,
        )

    if (
        segment.physical_end_boundary_type
        == PHYSICAL_GAP_BOUNDARY
    ):
        if not segment.following_gap_id:
            raise RuntimeError(
                "Gap-boundary replay segment is missing "
                "following_gap_id: "
                f"segment_id={segment.segment_id!r}"
            )

        return SegmentBoundaryPolicy(
            boundary_type="gap_boundary",
            following_gap_id=segment.following_gap_id,
            allow_next_bar_entry=False,
            force_flat_at_end=True,
            unresolved_position_allowed=False,
        )

    if (
        segment.physical_end_boundary_type
        == PHYSICAL_DATASET_END
    ):
        return SegmentBoundaryPolicy(
            boundary_type="dataset_end",
            following_gap_id=None,
            allow_next_bar_entry=False,
            force_flat_at_end=False,
            unresolved_position_allowed=True,
        )

    raise RuntimeError(
        "Unsupported research segment end boundary: "
        f"segment_id={segment.segment_id!r} "
        "physical_end_boundary_type="
        f"{segment.physical_end_boundary_type!r} "
        "requested_end_applied="
        f"{segment.requested_end_applied!r}"
    )

def run_backtest(
    *,
    runid: str,
    cfg: Optional[TradingConfig] = None,
    start_ts_ms: Optional[int] = None,
    end_ts_ms: Optional[int] = None,
    replay_plan: ReplayPlan | None = None,
) -> BacktestResult:
    """
    Deterministic offline replay:
    - loads OHLCV from local parquet (data/raw/...)
    - reuses same strategy/broker/CSV writers as main.py
    - does NOT fetch, does NOT sleep
    - reads from storage namespace: cfg.data_tag
    - writes to exchange namespace: "{data_tag}_bt_{runid}"

    IMPORTANT behavior for equivalence:
    - If start_ts_ms is provided, we keep the broker FLAT until now_ts_ms >= start_ts_ms.
      (We still load warmup bars prior to start_ts_ms so indicators/features are valid.)
      This prevents backtest from carrying a pre-window position into the overlap.
    """
    cfg = cfg or load_trading_config()
    data_tag = cfg.data_tag

    ccxt_symbol = cfg.symbol
    storage_symbol = _storage_symbol(cfg.symbol)

    expected_step_s = _timeframe_to_seconds(cfg.timeframe)

    # Backtest output namespace is derived from storage tag (NOT fetch source)
    bt_exchange = f"{data_tag}_bt_{runid}"

    trade_start_ts_ms: Optional[int] = int(start_ts_ms) if start_ts_ms is not None else None

    logger.info(
        "Backtest starting",
        extra={
            "runid": runid,
            "ccxt_exchange": cfg.ccxt_exchange,  # fetch source (metadata)
            "data_tag": data_tag,  # storage namespace (read root)
            "bt_exchange": bt_exchange,  # backtest output namespace
            "symbol": ccxt_symbol,
            "storage_symbol": storage_symbol,
            "timeframe": cfg.timeframe,
            "min_bars": cfg.min_bars,
            "trade_start_ts_ms": trade_start_ts_ms,
            "end_ts_ms": int(end_ts_ms) if end_ts_ms is not None else None,
        },
    )

    broker = PaperBroker(
        dry_run=cfg.dry_run,
        fee_bps=getattr(cfg, "fee_bps", 0.0),
        slippage_bps=getattr(cfg, "slippage_bps", 0.0),
    )

    resolved_replay_plan = (
        replay_plan
        if replay_plan is not None
        else _resolve_backtest_replay_plan(
            cfg=cfg,
            storage_symbol=storage_symbol,
            start_ts_ms=trade_start_ts_ms,
            end_ts_ms=(
                int(end_ts_ms)
                if end_ts_ms is not None
                else None
            ),
        )
    )

    # Restart-safe decision dedupe for bt output namespace
    dpath_existing = decisions_csv_path(exchange=bt_exchange, symbol=storage_symbol, timeframe=cfg.timeframe)
    last_decision_ts_ms: int | None = _read_last_ts_ms_from_decisions_csv(dpath_existing)
    if last_decision_ts_ms is not None:
        logger.info(
            "Decision dedupe initialized from existing CSV",
            extra={"csv_path": dpath_existing, "last_decision_ts_ms": int(last_decision_ts_ms)},
        )

    def _write_decision_once_per_bar(decision_row: dict) -> str | None:
        nonlocal last_decision_ts_ms

        ts_ms = decision_row.get("ts_ms", 0) or 0
        try:
            ts_ms = int(ts_ms)
        except Exception:
            ts_ms = 0

        if ts_ms <= 0:
            return None

        if last_decision_ts_ms is not None and ts_ms <= last_decision_ts_ms:
            return None

        dpath = append_decision_csv(
            decision=decision_row,
            exchange=bt_exchange,
            symbol=storage_symbol,   # STORAGE SYMBOL (e.g. BTC_USD)
            timeframe=cfg.timeframe,
        )
        last_decision_ts_ms = ts_ms
        return dpath

    bars_processed = 0
    last_decisions_path = ""
    last_trades_path = ""

    cancelled_entry_count = 0
    forced_exit_count = 0

    research_event_writer = (
        ResearchExecutionEventWriter(
            exchange=bt_exchange,
            symbol=storage_symbol,
            timeframe=cfg.timeframe,
            run_id=runid,
        )
        if resolved_replay_plan.gap_aware
        else None
    )
    research_event_sequence = 0
    research_execution_events_path = ""

    for segment_index, replay_segment in enumerate(
        resolved_replay_plan.segments
    ):
        is_final_segment = (
            segment_index
            == len(resolved_replay_plan.segments) - 1
        )

        if resolved_replay_plan.gap_aware:
            boundary_policy = (
                _build_research_segment_boundary_policy(
                    segment=replay_segment,
                )
            )
        else:
            boundary_policy = SegmentBoundaryPolicy(
                boundary_type=(
                    replay_segment
                    .physical_end_boundary_type
                ),
                following_gap_id=(
                    replay_segment.following_gap_id
                ),
                allow_next_bar_entry=True,
                force_flat_at_end=False,
                unresolved_position_allowed=True,
            )

        segment_result = execute_backtest_segment(
            SegmentExecutionRequest(
                segment=replay_segment,
                boundary_policy=boundary_policy,
                cfg=cfg,
                broker=broker,
                ccxt_symbol=ccxt_symbol,
                expected_step_s=int(expected_step_s),
                writers=SegmentWriterContext(
                    bt_exchange=bt_exchange,
                    storage_symbol=storage_symbol,
                    timeframe=cfg.timeframe,
                    write_decision=(
                        _write_decision_once_per_bar
                    ),
                ),
            )
        )

        bars_processed += int(
            segment_result.bars_processed
        )
        cancelled_entry_count += int(
            segment_result.cancelled_entry_count
        )
        forced_exit_count += int(
            segment_result.forced_exit_count
        )

        if segment_result.last_decisions_path:
            last_decisions_path = (
                segment_result.last_decisions_path
            )

        if segment_result.last_trades_path:
            last_trades_path = (
                segment_result.last_trades_path
            )

        if research_event_writer is not None:
            final_timestamp = pd.to_datetime(
                replay_segment.bars.iloc[-1]["timestamp"],
                utc=True,
                errors="raise",
            )
            final_ts_ms = int(
                final_timestamp.value // 1_000_000
            )
            final_reference_price = float(
                replay_segment.bars.iloc[-1]["close"]
            )

            for action_fact in (
                segment_result.boundary_action_facts
            ):
                research_event_sequence += 1

                research_execution_events_path = (
                    research_event_writer.append(
                        ResearchExecutionEvent(
                            event_id=(
                                f"{runid}:"
                                f"{research_event_sequence:06d}:"
                                f"{action_fact.event_type}"
                            ),
                            event_sequence=(
                                research_event_sequence
                            ),
                            run_id=runid,
                            event_ts_ms=(
                                action_fact.event_ts_ms
                            ),
                            event_type=(
                                action_fact.event_type
                            ),
                            segment_id=(
                                replay_segment.segment_id
                            ),
                            gap_id=(
                                boundary_policy.following_gap_id
                                or ""
                            ),
                            boundary_type=(
                                boundary_policy.boundary_type
                            ),
                            position_side=(
                                action_fact.position_side
                            ),
                            reference_price=(
                                action_fact.reference_price
                            ),
                            related_exit_reason=(
                                action_fact
                                .related_exit_reason
                            ),
                        )
                    )
                )

            research_event_sequence += 1

            research_execution_events_path = (
                research_event_writer.append(
                    ResearchExecutionEvent(
                        event_id=(
                            f"{runid}:"
                            f"{research_event_sequence:06d}:"
                            "segment_boundary_reached"
                        ),
                        event_sequence=(
                            research_event_sequence
                        ),
                        run_id=runid,
                        event_ts_ms=final_ts_ms,
                        event_type=(
                            "segment_boundary_reached"
                        ),
                        segment_id=(
                            replay_segment.segment_id
                        ),
                        gap_id=(
                            boundary_policy.following_gap_id
                            or ""
                        ),
                        boundary_type=(
                            boundary_policy.boundary_type
                        ),
                        position_side=(
                            segment_result.final_position.side
                            if segment_result.final_position
                            is not None
                            else ""
                        ),
                        reference_price=(
                            final_reference_price
                        ),
                        related_exit_reason="",
                    )
                )
            )

        if (
            segment_result.final_position is not None
            and not boundary_policy
            .unresolved_position_allowed
        ):
            raise RuntimeError(
                "Segment ended with unresolved broker state "
                "where the boundary policy requires flat: "
                f"segment_id={replay_segment.segment_id!r} "
                f"boundary_type="
                f"{boundary_policy.boundary_type!r} "
                f"position_side="
                f"{segment_result.final_position.side!r} "
                f"entry_ts_ms="
                f"{segment_result.final_position.entry_ts_ms!r}"
            )

        if not is_final_segment:
            if segment_result.final_position is not None:
                raise RuntimeError(
                    "Broker state cannot cross into the next "
                    "historical replay segment: "
                    f"segment_id={replay_segment.segment_id!r}"
                )

            broker.reset_segment_state(
                symbol=ccxt_symbol,
            )

    decisions_out = decisions_csv_path(exchange=bt_exchange, symbol=storage_symbol, timeframe=cfg.timeframe)
    trades_out = str(trades_csv_path(exchange=bt_exchange, symbol=storage_symbol, timeframe=cfg.timeframe))

    logger.info(
        "Backtest complete",
        extra={
            "runid": runid,
            "ccxt_exchange": cfg.ccxt_exchange,
            "data_tag": data_tag,
            "bt_exchange": bt_exchange,
            "decisions_csv": decisions_out,
            "trades_csv": trades_out,
            "bars_total": replay_plan.bars_total,
            "bars_processed": bars_processed,
            "segment_count": len(replay_plan.segments),
            "cancelled_entry_count": cancelled_entry_count,
            "forced_exit_count": forced_exit_count,
            "research_execution_event_count": (
                research_event_sequence
            ),
            "research_execution_events_csv": (
                research_execution_events_path
            ),
            "broker_realized_pnl_usd_total": float(
                broker.realized_pnl_usd_total
            ),
            "broker_trades_closed": int(
                broker.trades_closed
            ),
            "last_decisions_path": last_decisions_path,
            "last_trades_path": last_trades_path,
        },
    )

    return BacktestResult(
        bt_exchange=bt_exchange,
        symbol=ccxt_symbol,
        timeframe=cfg.timeframe,
        bars_total=replay_plan.bars_total,
        bars_processed=bars_processed,
        decisions_csv=decisions_out,
        trades_csv=trades_out,
        research_execution_events_csv=(
            research_execution_events_path
        ),
    )

