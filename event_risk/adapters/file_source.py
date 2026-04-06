from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from event_risk.schema import validate_event_risk_payload


def _get_manual_source_path() -> Path:
    raw = os.environ.get(
        "EVENT_RISK_MANUAL_SOURCE_PATH",
        "data/processed/event_risk/manual_current.json",
    ).strip()
    return Path(raw)


def _should_refresh_manual_as_of_utc() -> bool:
    raw = os.environ.get("EVENT_RISK_FILE_SOURCE_REFRESH_AS_OF_UTC", "").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")


def get_file_event_risk_payload() -> dict[str, Any]:
    path = _get_manual_source_path()

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if _should_refresh_manual_as_of_utc():
        payload["as_of_utc"] = datetime.now(timezone.utc).isoformat()

    return validate_event_risk_payload(payload)
