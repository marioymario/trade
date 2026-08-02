from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from files.backtest.replay import ReplaySegment
from files.broker.paper import PaperBroker
from files.config import TradingConfig
from files.core.types import Position


DecisionWriter = Callable[[dict], str | None]


@dataclass(frozen=True)
class SegmentBoundaryPolicy:
    """
    Explicit run-level policy supplied by the backtest engine.

    The segment executor must not inspect manifests or infer why a
    segment ended. It only applies this resolved policy.
    """

    boundary_type: str
    following_gap_id: str | None

    allow_next_bar_entry: bool
    force_flat_at_end: bool
    unresolved_position_allowed: bool


@dataclass(frozen=True)
class SegmentWriterContext:
    """
    Artifact identity and writer ownership for one backtest run.
    """

    bt_exchange: str
    storage_symbol: str
    timeframe: str
    write_decision: DecisionWriter


@dataclass(frozen=True)
class SegmentExecutionRequest:
    """
    Complete input required to execute exactly one replay segment.
    """

    segment: ReplaySegment
    boundary_policy: SegmentBoundaryPolicy

    cfg: TradingConfig
    broker: PaperBroker

    ccxt_symbol: str
    expected_step_s: int

    writers: SegmentWriterContext


@dataclass(frozen=True)
class SegmentBoundaryActionFact:
    """
    Boundary action produced while executing one segment.

    This is an execution-domain fact only. It contains no CSV artifact
    identity, event sequencing, or research serializer concerns.
    """

    event_type: str
    event_ts_ms: int
    position_side: str
    reference_price: float
    related_exit_reason: str


@dataclass(frozen=True)
class SegmentExecutionResult:
    """
    Facts produced by executing one segment.

    Run-level aggregation and state-transition enforcement remain the
    responsibility of the backtest engine.
    """

    segment_id: str

    bars_total: int
    bars_processed: int
    decisions_written: int
    trades_closed: int

    last_processed_ts_ms: int | None
    last_decisions_path: str
    last_trades_path: str

    final_position: Position | None

    cancelled_entry_count: int
    forced_exit_count: int

    boundary_action_facts: tuple[
        SegmentBoundaryActionFact,
        ...,
    ]

    unresolved_position: bool



def _entry_cancellation_reason(
    *,
    boundary_policy: SegmentBoundaryPolicy,
) -> str:
    if boundary_policy.boundary_type == "gap_boundary":
        return "entry_cancelled_gap_boundary"

    if (
        boundary_policy.boundary_type
        == "requested_range_end"
    ):
        return "entry_cancelled_requested_range_end"

    if boundary_policy.boundary_type == "dataset_end":
        return "entry_cancelled_dataset_end"

    raise RuntimeError(
        "Unsupported boundary type for final-bar entry "
        "cancellation: "
        f"{boundary_policy.boundary_type!r}"
    )

def _fill_position_fields(
    decision_row: dict,
    position: Position | None,
) -> None:
    if position is None:
        decision_row["position_side"] = ""
        decision_row["position_qty"] = ""
        decision_row["position_entry_price"] = ""
        decision_row["position_stop_price"] = ""
        decision_row["position_trailing_anchor_price"] = ""
        return

    decision_row["position_side"] = position.side
    decision_row["position_qty"] = float(position.qty)
    decision_row["position_entry_price"] = float(
        position.entry_price
    )
    decision_row["position_stop_price"] = (
        float(position.stop_price)
        if position.stop_price is not None
        else ""
    )
    decision_row["position_trailing_anchor_price"] = (
        float(position.trailing_anchor_price)
        if position.trailing_anchor_price is not None
        else ""
    )


def execute_backtest_segment(
    request: SegmentExecutionRequest,
) -> SegmentExecutionResult:
    """
    Execute exactly one supplied replay segment.

    This initial extraction intentionally preserves the existing legacy
    backtest behavior. Boundary-policy semantics are added only after
    exact artifact equivalence passes.
    """
    from files.data.features import (
        compute_features,
        validate_latest_features,
    )
    from files.data.trades import append_trade_csv
    from files.strategy.filters import determine_market_state
    from files.strategy.rules import (
        ATR_MULT,
        compute_initial_stop,
        compute_trailing_stop_update,
        evaluate_entry,
        evaluate_exit,
        size_position,
    )

    segment = request.segment
    cfg = request.cfg
    broker = request.broker
    writers = request.writers

    bars = segment.bars
    tail_n = max(int(cfg.min_bars), 200)

    bars_processed = 0
    decisions_written = 0
    cancelled_entry_count = 0
    forced_exit_count = 0
    boundary_action_facts: list[
        SegmentBoundaryActionFact
    ] = []
    trades_closed_before = int(broker.trades_closed)

    last_processed_ts_ms: int | None = None
    last_decisions_path = ""
    last_trades_path = ""

    for i in range(len(bars)):
        start_i = max(0, i - tail_n + 1)
        market_data = (
            bars.iloc[start_i : i + 1]
            .reset_index(drop=True)
        )

        if len(market_data) < cfg.min_bars:
            continue

        feats = compute_features(market_data)

        try:
            validate_latest_features(feats)
        except Exception:
            continue

        market_state = determine_market_state(
            feats,
            timeframe=cfg.timeframe,
            min_bars=cfg.min_bars,
        )

        latest_row = feats.iloc[-1]
        latest_close = float(latest_row["close"])
        latest_high = float(
            latest_row.get("high", latest_close)
        )
        latest_low = float(
            latest_row.get("low", latest_close)
        )
        latest_atr = float(latest_row["atr"])

        ts = latest_row.get("timestamp", None)
        now_ts_ms = (
            int(getattr(ts, "value", 0) // 1_000_000)
            if ts is not None
            else 0
        )
        now_iso = (
            ts.isoformat()
            if hasattr(ts, "isoformat")
            else ""
        )

        if now_ts_ms > 0:
            last_processed_ts_ms = now_ts_ms

        allow_trading = True
        if (
            now_ts_ms > 0
            and int(now_ts_ms)
            < int(segment.tradable_start_ts_ms)
        ):
            allow_trading = False

        position = broker.get_tracked_position(
            symbol=request.ccxt_symbol,
            latest_close=latest_close,
            latest_atr=latest_atr,
            atr_mult=float(ATR_MULT),
        )

        decision_row = {
            "ts_ms": now_ts_ms,
            "timestamp": now_iso,
            "bar_high": latest_high,
            "bar_low": latest_low,
            "tradable": bool(market_state.tradable),
            "trend": market_state.trend,
            "volatility": market_state.volatility,
            "market_reason": market_state.reason,
            "cooldown_remaining_bars": "",
            "position_side": "",
            "position_qty": "",
            "position_entry_price": "",
            "position_stop_price": "",
            "position_trailing_anchor_price": "",
            "unrealized_pnl_usd": "",
            "unrealized_pnl_pct": "",
            "trail_reason": "",
            "trail_new_stop": "",
            "trail_new_anchor": "",
            "entry_should_enter": "",
            "entry_side": "",
            "entry_confidence": "",
            "entry_reason": "",
            "entry_blocked_reason": "",
            "exit_should_exit": "",
            "exit_reason": "",
        }

        if not allow_trading:
            _fill_position_fields(decision_row, None)

            path = writers.write_decision(decision_row)
            if path:
                last_decisions_path = path
                decisions_written += 1

            bars_processed += 1
            continue

        pending_entry = False
        if (
            position is not None
            and position.entry_ts_ms is not None
            and now_ts_ms > 0
            and int(now_ts_ms)
            < int(position.entry_ts_ms)
        ):
            pending_entry = True

        _fill_position_fields(
            decision_row,
            position,
        )

        if pending_entry:
            path = writers.write_decision(decision_row)
            if path:
                last_decisions_path = path
                decisions_written += 1

            bars_processed += 1
            continue

        if position is not None:
            unrealized_usd, unrealized_pct = (
                broker.get_unrealized_pnl(
                    symbol=request.ccxt_symbol,
                    last_price=latest_close,
                )
            )

            decision_row["unrealized_pnl_usd"] = float(
                unrealized_usd
            )
            decision_row["unrealized_pnl_pct"] = float(
                unrealized_pct
            )

            new_stop, new_anchor, trail_reason = (
                compute_trailing_stop_update(
                    position=position,
                    latest_close=latest_close,
                    latest_high=latest_high,
                    latest_low=latest_low,
                    atr=latest_atr,
                )
            )

            decision_row["trail_reason"] = trail_reason
            decision_row["trail_new_stop"] = (
                float(new_stop)
                if new_stop is not None
                else ""
            )
            decision_row["trail_new_anchor"] = (
                float(new_anchor)
                if new_anchor is not None
                else ""
            )

            if new_stop is not None and (
                position.stop_price is None
                or float(new_stop)
                != float(position.stop_price)
            ):
                updated = broker.update_stop(
                    symbol=request.ccxt_symbol,
                    new_stop_price=float(new_stop),
                    new_trailing_anchor_price=(
                        float(new_anchor)
                        if new_anchor is not None
                        else None
                    ),
                )

                if updated is not None:
                    position = updated
                    _fill_position_fields(
                        decision_row,
                        position,
                    )

            exit_signal = evaluate_exit(
                position=position,
                latest_features_row=latest_row,
                market_state=market_state,
                expected_step_s=int(
                    request.expected_step_s
                ),
            )

            decision_row["exit_should_exit"] = bool(
                exit_signal.should_exit
            )
            decision_row["exit_reason"] = (
                exit_signal.reason or ""
            )

            if exit_signal.should_exit:
                exit_reason = (
                    exit_signal.reason or "exit"
                )

                exit_price = latest_close

                if (
                    exit_reason == "stop_hit"
                    and position.stop_price is not None
                ):
                    bar_open = float(
                        market_data.iloc[-1].get(
                            "open",
                            latest_close,
                        )
                    )
                    stop_price = float(
                        position.stop_price
                    )

                    exit_price = (
                        min(bar_open, stop_price)
                        if position.side == "LONG"
                        else max(bar_open, stop_price)
                    )

                trade = broker.realize_and_close(
                    symbol=request.ccxt_symbol,
                    exit_price=float(exit_price),
                    reason=exit_reason,
                    exit_ts_ms=(
                        now_ts_ms
                        if now_ts_ms > 0
                        else None
                    ),
                )

                last_trades_path = append_trade_csv(
                    trade=trade,
                    exchange=writers.bt_exchange,
                    symbol=writers.storage_symbol,
                    timeframe=writers.timeframe,
                    market_reason=market_state.reason,
                )

                path = writers.write_decision(
                    decision_row
                )
                if path:
                    last_decisions_path = path
                    decisions_written += 1

                bars_processed += 1
                continue

            is_final_available_bar = (
                i + 1 >= len(bars)
            )

            if (
                is_final_available_bar
                and request.boundary_policy.force_flat_at_end
            ):
                decision_row["exit_should_exit"] = True
                decision_row["exit_reason"] = (
                    "segment_end_forced_exit"
                )

                trade = broker.realize_and_close(
                    symbol=request.ccxt_symbol,
                    exit_price=float(latest_close),
                    reason="segment_end_forced_exit",
                    exit_ts_ms=(
                        now_ts_ms
                        if now_ts_ms > 0
                        else None
                    ),
                )

                last_trades_path = append_trade_csv(
                    trade=trade,
                    exchange=writers.bt_exchange,
                    symbol=writers.storage_symbol,
                    timeframe=writers.timeframe,
                    market_reason=market_state.reason,
                )

                forced_exit_count += 1
                boundary_action_facts.append(
                    SegmentBoundaryActionFact(
                        event_type="position_forced_exit",
                        event_ts_ms=now_ts_ms,
                        position_side=position.side,
                        reference_price=float(
                            latest_close
                        ),
                        related_exit_reason=(
                            "segment_end_forced_exit"
                        ),
                    )
                )

                path = writers.write_decision(
                    decision_row
                )
                if path:
                    last_decisions_path = path
                    decisions_written += 1

                bars_processed += 1
                continue

        if position is None:
            remaining = broker.cooldown_remaining_bars(
                symbol=request.ccxt_symbol,
                now_ts_ms=now_ts_ms,
                expected_step_s=int(
                    request.expected_step_s
                ),
                cooldown_bars=int(
                    getattr(
                        cfg,
                        "cooldown_bars",
                        0,
                    )
                ),
            )

            decision_row[
                "cooldown_remaining_bars"
            ] = int(remaining)

            if remaining <= 0:
                entry_signal = evaluate_entry(
                    features=feats,
                    market_state=market_state,
                )

                decision_row[
                    "entry_should_enter"
                ] = bool(entry_signal.should_enter)
                decision_row["entry_side"] = (
                    entry_signal.side
                )
                decision_row[
                    "entry_confidence"
                ] = float(entry_signal.confidence)
                decision_row["entry_reason"] = (
                    entry_signal.reason
                )

                if entry_signal.should_enter:
                    is_final_available_bar = (
                        i + 1 >= len(bars)
                    )

                    if (
                        is_final_available_bar
                        and not request.boundary_policy
                        .allow_next_bar_entry
                    ):
                        decision_row[
                            "entry_blocked_reason"
                        ] = _entry_cancellation_reason(
                            boundary_policy=(
                                request.boundary_policy
                            ),
                        )
                        cancelled_entry_count += 1
                        boundary_action_facts.append(
                            SegmentBoundaryActionFact(
                                event_type="entry_cancelled",
                                event_ts_ms=now_ts_ms,
                                position_side=(
                                    entry_signal.side
                                ),
                                reference_price=float(
                                    latest_close
                                ),
                                related_exit_reason=(
                                    decision_row[
                                        "entry_blocked_reason"
                                    ]
                                ),
                            )
                        )

                    else:
                        size = min(
                            size_position(
                                signal=entry_signal,
                                market_state=market_state,
                            ),
                            cfg.max_order_size,
                        )

                        if i + 1 < len(bars):
                            next_timestamp = bars.iloc[
                                i + 1
                            ]["timestamp"]

                            next_ts_ms = int(
                                getattr(
                                    next_timestamp,
                                    "value",
                                    0,
                                )
                                // 1_000_000
                            )

                            entry_ts_ms = (
                                next_ts_ms
                                if next_ts_ms > 0
                                else (
                                    now_ts_ms
                                    + int(
                                        request.expected_step_s
                                        * 1000
                                    )
                                )
                            )
                        else:
                            entry_ts_ms = (
                                now_ts_ms
                                + int(
                                    request.expected_step_s
                                    * 1000
                                )
                            )

                        stop_price = compute_initial_stop(
                            side=entry_signal.side,
                            entry_price=latest_close,
                            atr=latest_atr,
                        )

                        broker.open_position(
                            symbol=request.ccxt_symbol,
                            side=entry_signal.side,
                            size=size,
                            entry_price=latest_close,
                            entry_ts_ms=entry_ts_ms,
                            stop_price=stop_price,
                            trailing_anchor_price=(
                                latest_high
                                if entry_signal.side == "LONG"
                                else latest_low
                            ),
                        )

                        position = (
                            broker.get_tracked_position(
                                symbol=request.ccxt_symbol,
                                latest_close=latest_close,
                                latest_atr=latest_atr,
                                atr_mult=float(ATR_MULT),
                            )
                        )

                        _fill_position_fields(
                            decision_row,
                            position,
                        )

        path = writers.write_decision(decision_row)
        if path:
            last_decisions_path = path
            decisions_written += 1

        bars_processed += 1

    final_position = broker.get_tracked_position(
        symbol=request.ccxt_symbol,
    )

    return SegmentExecutionResult(
        segment_id=segment.segment_id,
        bars_total=segment.bar_count,
        bars_processed=bars_processed,
        decisions_written=decisions_written,
        trades_closed=(
            int(broker.trades_closed)
            - trades_closed_before
        ),
        last_processed_ts_ms=last_processed_ts_ms,
        last_decisions_path=last_decisions_path,
        last_trades_path=last_trades_path,
        final_position=final_position,
        cancelled_entry_count=cancelled_entry_count,
        forced_exit_count=forced_exit_count,
        boundary_action_facts=tuple(
            boundary_action_facts
        ),
        unresolved_position=(
            final_position is not None
        ),
    )
