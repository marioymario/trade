from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from files.data.paths import event_risk_current_json_path


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
