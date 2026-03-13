from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def _parse_reason_codes() -> list[str]:
    raw = os.environ.get("EVENT_RISK_REASON_CODES", "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def get_mock_event_risk_payload() -> dict[str, Any]:
    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "status": os.environ.get("EVENT_RISK_STATUS", "ok").strip() or "ok",
        "event_risk_level": os.environ.get("EVENT_RISK_LEVEL", "normal").strip() or "normal",
        "news_regime": os.environ.get("EVENT_RISK_NEWS_REGIME", "calm").strip() or "calm",
        "event_risk_score": float(os.environ.get("EVENT_RISK_SCORE", "0.1")),
        "ttl_seconds": int(os.environ.get("EVENT_RISK_TTL_SECONDS", "900")),
        "reason_codes": _parse_reason_codes(),
        "source_count": int(os.environ.get("EVENT_RISK_SOURCE_COUNT", "1")),
    }
