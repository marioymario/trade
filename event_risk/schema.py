from __future__ import annotations

from datetime import datetime
from typing import Any


REQUIRED_KEYS = [
    "as_of_utc",
    "status",
    "event_risk_level",
    "news_regime",
    "event_risk_score",
    "ttl_seconds",
    "reason_codes",
    "source_count",
]

ALLOWED_STATUS = {"ok", "stale", "error"}
ALLOWED_EVENT_RISK_LEVEL = {"normal", "elevated", "extreme"}
ALLOWED_NEWS_REGIME = {"calm", "headline_driven", "disorderly"}


def _require_keys(payload: dict[str, Any]) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in payload]
    if missing:
        raise ValueError(f"Missing required event-risk keys: {missing}")


def _validate_as_of_utc(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("as_of_utc must be a non-empty string")
    try:
        dt = datetime.fromisoformat(value)
    except Exception as e:
        raise ValueError(f"as_of_utc must be ISO-8601 compatible: {value!r}") from e
    if dt.tzinfo is None:
        raise ValueError("as_of_utc must include timezone information")


def _validate_status(value: Any) -> None:
    if value not in ALLOWED_STATUS:
        raise ValueError(f"status must be one of {sorted(ALLOWED_STATUS)}")


def _validate_event_risk_level(value: Any) -> None:
    if value not in ALLOWED_EVENT_RISK_LEVEL:
        raise ValueError(
            f"event_risk_level must be one of {sorted(ALLOWED_EVENT_RISK_LEVEL)}"
        )


def _validate_news_regime(value: Any) -> None:
    if value not in ALLOWED_NEWS_REGIME:
        raise ValueError(f"news_regime must be one of {sorted(ALLOWED_NEWS_REGIME)}")


def _validate_event_risk_score(value: Any) -> None:
    if not isinstance(value, (int, float)):
        raise ValueError("event_risk_score must be numeric")
    if float(value) < 0.0 or float(value) > 1.0:
        raise ValueError("event_risk_score must be between 0.0 and 1.0")


def _validate_ttl_seconds(value: Any) -> None:
    if not isinstance(value, int):
        raise ValueError("ttl_seconds must be an integer")
    if value <= 0:
        raise ValueError("ttl_seconds must be > 0")


def _validate_reason_codes(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError("reason_codes must be a list")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("reason_codes must contain non-empty strings")


def _validate_source_count(value: Any) -> None:
    if not isinstance(value, int):
        raise ValueError("source_count must be an integer")
    if value < 0:
        raise ValueError("source_count must be >= 0")


def validate_event_risk_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("event-risk payload must be a dict")

    _require_keys(payload)
    _validate_as_of_utc(payload["as_of_utc"])
    _validate_status(payload["status"])
    _validate_event_risk_level(payload["event_risk_level"])
    _validate_news_regime(payload["news_regime"])
    _validate_event_risk_score(payload["event_risk_score"])
    _validate_ttl_seconds(payload["ttl_seconds"])
    _validate_reason_codes(payload["reason_codes"])
    _validate_source_count(payload["source_count"])

    return payload
