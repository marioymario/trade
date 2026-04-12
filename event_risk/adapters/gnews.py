from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


def _get_gnews_api_key() -> str:
    api_key = os.environ.get("GNEWS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GNEWS_API_KEY is required for EVENT_RISK_SOURCE=gnews")
    return api_key


def _get_gnews_base_url() -> str:
    return os.environ.get(
        "EVENT_RISK_GNEWS_BASE_URL",
        "https://gnews.io/api/v4/search",
    ).strip()


def _get_gnews_query() -> str:
    return os.environ.get(
        "EVENT_RISK_GNEWS_QUERY",
        "geopolitics OR war OR conflict OR sanctions OR oil",
    ).strip()


def _get_gnews_language() -> str:
    return os.environ.get("EVENT_RISK_GNEWS_LANGUAGE", "en").strip() or "en"


def _get_gnews_page_size() -> int:
    raw = os.environ.get("EVENT_RISK_GNEWS_PAGE_SIZE", "10").strip()
    try:
        value = int(raw)
    except Exception:
        value = 10
    if value < 1:
        value = 1
    if value > 100:
        value = 100
    return value


def _get_gnews_lookback_hours() -> int:
    raw = os.environ.get("EVENT_RISK_GNEWS_LOOKBACK_HOURS", "24").strip()
    try:
        value = int(raw)
    except Exception:
        value = 24
    if value < 1:
        value = 1
    if value > 168:
        value = 168
    return value


def _get_gnews_ttl_seconds() -> int:
    raw = os.environ.get("EVENT_RISK_GNEWS_TTL_SECONDS", "3600").strip()
    try:
        value = int(raw)
    except Exception:
        value = 3600
    if value <= 0:
        value = 3600
    return value


def _parse_gnews_published_at(value: str) -> datetime | None:
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


def _fetch_gnews_articles() -> list[dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    from_ts = (now_utc - timedelta(hours=_get_gnews_lookback_hours())).isoformat().replace("+00:00", "Z")

    params = {
        "apikey": _get_gnews_api_key(),
        "q": _get_gnews_query(),
        "lang": _get_gnews_language(),
        "max": str(_get_gnews_page_size()),
        "from": from_ts,
        "sortby": "publishedAt",
    }

    url = f"{_get_gnews_base_url()}?{urlencode(params)}"

    with urlopen(url, timeout=20) as resp:
        body = resp.read().decode("utf-8")

    payload = json.loads(body)
    articles = payload.get("articles", [])

    if not isinstance(articles, list):
        return []

    return [item for item in articles if isinstance(item, dict)]


def _classify_gnews_articles(articles: list[dict[str, Any]]) -> tuple[str, str, float, list[str], int]:
    now_utc = datetime.now(timezone.utc)
    recent_count = 0
    lookback_hours = float(_get_gnews_lookback_hours())

    for item in articles:
        published = _parse_gnews_published_at(str(item.get("publishedAt", "")))
        if published is None:
            continue
        age_hours = (now_utc - published).total_seconds() / 3600.0
        if age_hours <= lookback_hours:
            recent_count += 1

    if recent_count >= 5:
        return (
            "extreme",
            "disorderly",
            0.8,
            ["geopolitical_conflict", "headline_cluster"],
            len(articles),
        )

    if recent_count >= 2:
        return (
            "elevated",
            "headline_driven",
            0.4,
            ["geopolitical_conflict"],
            len(articles),
        )

    return (
        "normal",
        "calm",
        0.1,
        [],
        len(articles),
    )


def _gnews_error_payload(reason_code: str) -> dict[str, Any]:
    return {
        "source_name": "gnews",
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "event_risk_level": "normal",
        "news_regime": "calm",
        "event_risk_score": 0.0,
        "ttl_seconds": _get_gnews_ttl_seconds(),
        "reason_codes": [reason_code],
        "source_count": 0,
    }


def _map_gnews_http_error(code: int) -> str:
    if code in (401, 403):
        return "gnews_auth_error"
    if code == 429:
        return "gnews_rate_limited"
    if 500 <= code <= 599:
        return "gnews_upstream_error"
    return "gnews_http_error"


def get_gnews_event_risk_payload() -> dict[str, Any]:
    try:
        articles = _fetch_gnews_articles()
        level, regime, score, reason_codes, source_count = _classify_gnews_articles(articles)

        return {
            "source_name": "gnews",
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
            "event_risk_level": level,
            "news_regime": regime,
            "event_risk_score": score,
            "ttl_seconds": _get_gnews_ttl_seconds(),
            "reason_codes": reason_codes,
            "source_count": source_count,
        }
    except ValueError:
        return _gnews_error_payload("gnews_config_error")
    except HTTPError as e:
        return _gnews_error_payload(_map_gnews_http_error(int(getattr(e, "code", 0) or 0)))
    except TimeoutError:
        return _gnews_error_payload("gnews_timeout")
    except URLError:
        return _gnews_error_payload("gnews_network_error")
    except Exception:
        return _gnews_error_payload("gnews_fetch_error")
