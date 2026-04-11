## event_risk/adapters/service.py
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from event_risk.adapters.file_source import get_file_event_risk_payload
from event_risk.adapters.gnews import get_gnews_event_risk_payload
from event_risk.adapters.guardian import get_guardian_event_risk_payload
from event_risk.adapters.mock import get_mock_event_risk_payload
from event_risk.adapters.newsapi import get_newsapi_event_risk_payload
from event_risk.adapters.newsdata import get_newsdata_event_risk_payload
from event_risk.merge import merge_event_risk_payloads
from event_risk.schema import validate_event_risk_payload
from event_risk.writer import EVENT_RISK_HISTORY_FIELDS
from files.data.paths import event_risk_current_json_path, event_risk_history_csv_path


def _get_event_risk_source() -> str:
    return os.environ.get("EVENT_RISK_SOURCE", "mock").strip().lower() or "mock"


def _load_single_source_event_risk_payload(source: str) -> dict[str, Any]:
    if source == "mock":
        return get_mock_event_risk_payload()

    if source == "file":
        return get_file_event_risk_payload()

    if source == "guardian":
        return get_guardian_event_risk_payload()

    if source == "newsdata":
        return get_newsdata_event_risk_payload()

    if source == "gnews":
        return get_gnews_event_risk_payload()

    if source == "newsapi":
        return get_newsapi_event_risk_payload()

    raise ValueError(f"Unsupported EVENT_RISK_SOURCE: {source!r}")


def _get_merge_sources() -> list[str]:
    raw = os.environ.get("EVENT_RISK_MERGE_SOURCES", "").strip()
    if not raw:
        return ["guardian", "newsdata", "gnews", "newsapi"]

    out: list[str] = []
    for part in raw.split(","):
        s = part.strip().lower()
        if not s:
            continue
        if s not in out:
            out.append(s)
    return out


def _load_event_risk_payload_from_source() -> dict[str, Any]:
    source = _get_event_risk_source()

    if source == "merge":
        payloads: list[dict[str, Any]] = []
        for merge_source in _get_merge_sources():
            payloads.append(_load_single_source_event_risk_payload(merge_source))
        return merge_event_risk_payloads(payloads)

    return _load_single_source_event_risk_payload(source)


def build_event_risk_payload() -> dict[str, Any]:
    payload = _load_event_risk_payload_from_source()
    return validate_event_risk_payload(payload)


def read_current_event_risk() -> dict[str, Any]:
    path: Path = event_risk_current_json_path()
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return validate_event_risk_payload(payload)


def read_event_risk_history_tail(limit: int = 5) -> list[dict[str, Any]]:
    if limit <= 0:
        raise ValueError("limit must be > 0")

    path: Path = event_risk_history_csv_path()
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed: dict[str, Any] = {}
            for key in EVENT_RISK_HISTORY_FIELDS:
                value = row.get(key, "")
                if key == "event_risk_score":
                    parsed[key] = float(value)
                elif key == "ttl_seconds":
                    parsed[key] = int(value)
                elif key == "source_count":
                    parsed[key] = int(value)
                elif key == "reason_codes":
                    parsed[key] = json.loads(value) if value else []
                else:
                    parsed[key] = value
            rows.append(validate_event_risk_payload(parsed))

    if len(rows) <= limit:
        return rows

    return rows[-limit:]


def read_latest_event_risk_history() -> dict[str, Any] | None:
    rows = read_event_risk_history_tail(limit=1)
    if not rows:
        return None
    return rows[0]


def is_current_event_risk_fresh(now_utc: datetime | None = None) -> bool:
    payload = read_current_event_risk()

    as_of_utc = datetime.fromisoformat(payload["as_of_utc"])
    ttl_seconds = int(payload["ttl_seconds"])

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    return now_utc <= (as_of_utc + timedelta(seconds=ttl_seconds))


def get_current_event_risk_status(now_utc: datetime | None = None) -> str:
    try:
        payload = read_current_event_risk()
    except Exception:
        return "error"

    if payload.get("status") == "error":
        return "error"

    if is_current_event_risk_fresh(now_utc=now_utc):
        return "ok"

    return "stale"


def get_event_risk_dashboard_summary() -> dict[str, Any]:
    current = read_current_event_risk()
    latest_history = read_latest_event_risk_history()

    return {
        "status": get_current_event_risk_status(),
        "current": current,
        "latest_history": latest_history,
        "history_rows_available": len(read_event_risk_history_tail(limit=1)),
    }
