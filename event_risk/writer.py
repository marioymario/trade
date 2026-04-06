from __future__ import annotations

import csv
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from files.data.paths import event_risk_current_json_path, event_risk_history_csv_path


EVENT_RISK_HISTORY_FIELDS = [
    "as_of_utc",
    "status",
    "event_risk_level",
    "news_regime",
    "event_risk_score",
    "ttl_seconds",
    "reason_codes",
    "source_count",
]


def _atomic_write_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    token = secrets.token_hex(6)
    tmp = Path(str(path) + f".tmp.{os.getpid()}.{int(time.time() * 1000)}.{token}")

    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def write_current_event_risk(payload: dict[str, Any]) -> Path:
    path = event_risk_current_json_path()
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(text, path)
    return path


def append_event_risk_history(payload: dict[str, Any]) -> Path:
    """
    Append one normalized event-risk snapshot row to history.csv.

    Semantics:
    - one row per write call
    - append-only
    - latest row is the newest appended snapshot
    - reason_codes are stored as a compact JSON string for stable round-trip
    """
    path = event_risk_history_csv_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    row: dict[str, Any] = {k: "" for k in EVENT_RISK_HISTORY_FIELDS}
    for key in EVENT_RISK_HISTORY_FIELDS:
        if key == "reason_codes":
            row[key] = json.dumps(payload.get("reason_codes", []), separators=(",", ":"))
        else:
            row[key] = payload.get(key, "")

    file_exists = path.exists()
    write_header = (not file_exists) or (path.stat().st_size == 0)

    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_RISK_HISTORY_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)

    return path
