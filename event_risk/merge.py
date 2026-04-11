from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_EVENT_RISK_LEVEL_RANK = {
    "normal": 0,
    "elevated": 1,
    "extreme": 2,
}

_NEWS_REGIME_RANK = {
    "calm": 0,
    "headline_driven": 1,
    "disorderly": 2,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _best_event_risk_level(levels: list[str]) -> str:
    if not levels:
        return "normal"
    return max(levels, key=lambda x: _EVENT_RISK_LEVEL_RANK.get(str(x), -1))


def _best_news_regime(regimes: list[str]) -> str:
    if not regimes:
        return "calm"
    return max(regimes, key=lambda x: _NEWS_REGIME_RANK.get(str(x), -1))


def _merge_reason_codes(payloads: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []

    for payload in payloads:
        for code in payload.get("reason_codes", []) or []:
            s = str(code).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            merged.append(s)

    return merged


def _merged_status(payloads: list[dict[str, Any]]) -> str:
    ok_payloads = [p for p in payloads if str(p.get("status", "")).strip().lower() == "ok"]
    if ok_payloads:
        return "ok"
    return "error"


def merge_event_risk_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Merge already-normalized event-risk payloads into one final payload.

    Current semantics:
    - status: ok if any source is ok, else error
    - event_risk_level: highest severity wins
    - news_regime: highest severity wins
    - event_risk_score: max score wins
    - ttl_seconds: minimum positive ttl wins
    - reason_codes: stable union, first-seen order
    - source_count: sum of source_count from ok payloads only
    - as_of_utc: merge time in UTC
    """
    if not payloads:
        return {
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "event_risk_level": "normal",
            "news_regime": "calm",
            "event_risk_score": 0.0,
            "ttl_seconds": 3600,
            "reason_codes": ["merge_no_sources"],
            "source_count": 0,
        }

    ok_payloads = [p for p in payloads if str(p.get("status", "")).strip().lower() == "ok"]
    merge_base = ok_payloads if ok_payloads else payloads

    levels = [str(p.get("event_risk_level", "normal")).strip().lower() for p in merge_base]
    regimes = [str(p.get("news_regime", "calm")).strip().lower() for p in merge_base]
    scores = [_safe_float(p.get("event_risk_score", 0.0), 0.0) for p in merge_base]
    ttls = [_safe_int(p.get("ttl_seconds", 0), 0) for p in merge_base if _safe_int(p.get("ttl_seconds", 0), 0) > 0]

    merged = {
        "as_of_utc": datetime.now(timezone.utc).isoformat(),
        "status": _merged_status(payloads),
        "event_risk_level": _best_event_risk_level(levels),
        "news_regime": _best_news_regime(regimes),
        "event_risk_score": max(scores) if scores else 0.0,
        "ttl_seconds": min(ttls) if ttls else 3600,
        "reason_codes": _merge_reason_codes(merge_base),
        "source_count": sum(_safe_int(p.get("source_count", 0), 0) for p in ok_payloads),
    }

    if merged["status"] != "ok" and not merged["reason_codes"]:
        merged["reason_codes"] = ["merge_all_sources_error"]

    return merged
