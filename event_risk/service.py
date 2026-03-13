from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from event_risk.adapters.mock import get_mock_event_risk_payload
from event_risk.schema import validate_event_risk_payload
from files.data.paths import event_risk_current_json_path


def build_event_risk_payload() -> dict[str, Any]:
    payload = get_mock_event_risk_payload()
    return validate_event_risk_payload(payload)


def read_current_event_risk() -> dict[str, Any]:
    path: Path = event_risk_current_json_path()
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return validate_event_risk_payload(payload)


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
