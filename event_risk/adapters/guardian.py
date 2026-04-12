from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def _get_guardian_api_key() -> str:
    api_key = os.environ.get("GUARDIAN_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GUARDIAN_API_KEY is required for EVENT_RISK_SOURCE=guardian")
    return api_key


def _get_guardian_base_url() -> str:
    return os.environ.get(
        "EVENT_RISK_GUARDIAN_BASE_URL",
        "https://content.guardianapis.com/search",
    ).strip()


def _get_guardian_query() -> str:
    return os.environ.get(
        "EVENT_RISK_GUARDIAN_QUERY",
        "geopolitics OR war OR conflict OR sanctions OR oil",
    ).strip()


def _get_guardian_page_size() -> int:
    raw = os.environ.get("EVENT_RISK_GUARDIAN_PAGE_SIZE", "10").strip()
    try:
        value = int(raw)
    except Exception:
        value = 10
    if value < 1:
        value = 1
    if value > 50:
        value = 50
    return value


def _get_guardian_lookback_hours() -> int:
    raw = os.environ.get("EVENT_RISK_GUARDIAN_LOOKBACK_HOURS", "24").strip()
    try:
        value = int(raw)
    except Exception:
        value = 24
    if value < 1:
        value = 1
    if value > 168:
        value = 168
    return value


def _get_guardian_ttl_seconds() -> int:
    raw = os.environ.get("EVENT_RISK_GUARDIAN_TTL_SECONDS", "3600").strip()
    try:
        value = int(raw)
    except Exception:
        value = 3600
    if value <= 0:
        value = 3600
    return value


def _parse_web_publication_date(value: str) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fetch_guardian_results() -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    from_date = (now_utc - timedelta(hours=_get_guardian_lookback_hours())).date().isoformat()

    params = {
        "api-key": _get_guardian_api_key(),
        "q": _get_guardian_query(),
        "page-size": str(_get_guardian_page_size()),
        "order-by": "newest",
        "from-date": from_date,
    }

    url = f"{_get_guardian_base_url()}?{urlencode(params)}"

    with urlopen(url, timeout=20) as resp:
        body = resp.read().decode("utf-8")

    payload = json.loads(body)
    response = payload.get("response", {})
    results = response.get("results", [])

    if not isinstance(results, list):
        return []

    return [item for item in results if isinstance(item, dict)]


def _classify_guardian_results(results: list[dict[str, Any]]) -> tuple[str, str, float, list[str], int]:
    now_utc = datetime.now(timezone.utc)
    recent_count = 0

    for item in results:
        published = _parse_web_publication_date(str(item.get("webPublicationDate", "")))
        if published is None:
            continue
        age_hours = (now_utc - published).total_seconds() / 3600.0
        if age_hours <= 24.0:
            recent_count += 1

    if recent_count >= 5:
        return (
            "extreme",
            "disorderly",
            0.8,
            ["geopolitical_conflict", "headline_cluster"],
            len(results),
        )

    if recent_count >= 2:
        return (
            "elevated",
            "headline_driven",
            0.4,
            ["geopolitical_conflict"],
            len(results),
        )

    return (
        "normal",
        "calm",
        0.1,
        [],
        len(results),
    )


def _guardian_error_payload(reason_code: str) -> dict[str, Any]:
    return {
        "source_name": "guardian",
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "event_risk_level": "normal",
        "news_regime": "calm",
        "event_risk_score": 0.0,
        "ttl_seconds": _get_guardian_ttl_seconds(),
        "reason_codes": [reason_code],
        "source_count": 0,
    }


def _map_guardian_http_error(code: int) -> str:
    if code in (401, 403):
        return "guardian_auth_error"
    if code == 429:
        return "guardian_rate_limited"
    if 500 <= code <= 599:
        return "guardian_upstream_error"
    return "guardian_http_error"


def get_guardian_event_risk_payload() -> dict[str, Any]:
    try:
        results = _fetch_guardian_results()
        level, regime, score, reason_codes, source_count = _classify_guardian_results(results)

        return {
            "source_name": "guardian",
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
            "event_risk_level": level,
            "news_regime": regime,
            "event_risk_score": score,
            "ttl_seconds": _get_guardian_ttl_seconds(),
            "reason_codes": reason_codes,
            "source_count": source_count,
        }
    except ValueError:
        return _guardian_error_payload("guardian_config_error")
    except HTTPError as e:
        return _guardian_error_payload(_map_guardian_http_error(int(getattr(e, "code", 0) or 0)))
    except URLError:
        return _guardian_error_payload("guardian_network_error")
    except Exception:
        return _guardian_error_payload("guardian_fetch_error")
