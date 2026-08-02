from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Mapping

from files.data.paths import (
    research_execution_events_csv_path,
)


RESEARCH_EXECUTION_EVENT_FIELDS = (
    "event_id",
    "event_sequence",
    "run_id",
    "event_ts_ms",
    "event_type",
    "segment_id",
    "gap_id",
    "boundary_type",
    "position_side",
    "reference_price",
    "related_exit_reason",
)


class ResearchExecutionEventError(RuntimeError):
    """Raised when a research execution event artifact is invalid."""


_WS_RE = re.compile(r"\s+")


def _sanitize_csv_value(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(value, str):
        text = value.replace("\r", " ").replace("\n", " ")
        return _WS_RE.sub(" ", text).strip()

    return value


def _require_non_empty_text(
    value: Any,
    *,
    name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchExecutionEventError(
            f"{name} must be a non-empty string."
        )

    return value.strip()


def _require_positive_int(
    value: Any,
    *,
    name: str,
) -> int:
    if isinstance(value, bool):
        raise ResearchExecutionEventError(
            f"{name} must be a positive integer."
        )

    try:
        parsed = int(value)
    except Exception as exc:
        raise ResearchExecutionEventError(
            f"{name} must be a positive integer."
        ) from exc

    if parsed <= 0:
        raise ResearchExecutionEventError(
            f"{name} must be a positive integer."
        )

    return parsed


@dataclass(frozen=True)
class ResearchExecutionEvent:
    event_id: str
    event_sequence: int
    run_id: str
    event_ts_ms: int
    event_type: str
    segment_id: str
    gap_id: str = ""
    boundary_type: str = ""
    position_side: str = ""
    reference_price: float | str = ""
    related_exit_reason: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_sequence": self.event_sequence,
            "run_id": self.run_id,
            "event_ts_ms": self.event_ts_ms,
            "event_type": self.event_type,
            "segment_id": self.segment_id,
            "gap_id": self.gap_id,
            "boundary_type": self.boundary_type,
            "position_side": self.position_side,
            "reference_price": self.reference_price,
            "related_exit_reason": self.related_exit_reason,
        }


class ResearchExecutionEventWriter:
    def __init__(
        self,
        *,
        exchange: str,
        symbol: str,
        timeframe: str,
        run_id: str,
    ) -> None:
        self.exchange = _require_non_empty_text(
            exchange,
            name="exchange",
        )
        self.symbol = _require_non_empty_text(
            symbol,
            name="symbol",
        )
        self.timeframe = _require_non_empty_text(
            timeframe,
            name="timeframe",
        )
        self.run_id = _require_non_empty_text(
            run_id,
            name="run_id",
        )

        self.path = research_execution_events_csv_path(
            exchange=self.exchange,
            symbol=self.symbol,
            timeframe=self.timeframe,
        )

        if self.path.exists() and self.path.stat().st_size > 0:
            raise ResearchExecutionEventError(
                "Research execution event artifact already exists "
                "and is non-empty: "
                f"{self.path}"
            )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._last_event_sequence = 0
        self._seen_event_ids: set[str] = set()

        with self.path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=RESEARCH_EXECUTION_EVENT_FIELDS,
            )
            writer.writeheader()

    def append(
        self,
        event: ResearchExecutionEvent
        | Mapping[str, Any],
    ) -> str:
        raw = (
            event.as_row()
            if isinstance(event, ResearchExecutionEvent)
            else dict(event)
        )

        unknown_fields = sorted(
            set(raw) - set(RESEARCH_EXECUTION_EVENT_FIELDS)
        )

        if unknown_fields:
            raise ResearchExecutionEventError(
                "Research execution event contains unsupported "
                f"fields: {unknown_fields}"
            )

        event_id = _require_non_empty_text(
            raw.get("event_id"),
            name="event_id",
        )

        event_sequence = _require_positive_int(
            raw.get("event_sequence"),
            name="event_sequence",
        )

        run_id = _require_non_empty_text(
            raw.get("run_id"),
            name="run_id",
        )

        event_ts_ms = _require_positive_int(
            raw.get("event_ts_ms"),
            name="event_ts_ms",
        )

        event_type = _require_non_empty_text(
            raw.get("event_type"),
            name="event_type",
        )

        segment_id = _require_non_empty_text(
            raw.get("segment_id"),
            name="segment_id",
        )

        if run_id != self.run_id:
            raise ResearchExecutionEventError(
                "Research execution event run_id does not match "
                "the writer run_id: "
                f"event={run_id!r} writer={self.run_id!r}"
            )

        if event_sequence != self._last_event_sequence + 1:
            raise ResearchExecutionEventError(
                "Research execution event_sequence must increase "
                "by exactly one: "
                f"last={self._last_event_sequence} "
                f"new={event_sequence}"
            )

        if event_id in self._seen_event_ids:
            raise ResearchExecutionEventError(
                f"Duplicate research execution event_id: {event_id!r}"
            )

        row: dict[str, Any] = {
            field: ""
            for field in RESEARCH_EXECUTION_EVENT_FIELDS
        }

        row.update(
            {
                "event_id": event_id,
                "event_sequence": event_sequence,
                "run_id": run_id,
                "event_ts_ms": event_ts_ms,
                "event_type": event_type,
                "segment_id": segment_id,
            }
        )

        for field in (
            "gap_id",
            "boundary_type",
            "position_side",
            "reference_price",
            "related_exit_reason",
        ):
            row[field] = _sanitize_csv_value(
                raw.get(field, "")
            )

        with self.path.open(
            "a",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=RESEARCH_EXECUTION_EVENT_FIELDS,
            )
            writer.writerow(row)

        self._last_event_sequence = event_sequence
        self._seen_event_ids.add(event_id)

        return str(self.path)
