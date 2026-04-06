from __future__ import annotations

import os

from event_risk.service import build_event_risk_payload, get_current_event_risk_status
from event_risk.writer import append_event_risk_history, write_current_event_risk


def _get_event_risk_source() -> str:
    return os.environ.get("EVENT_RISK_SOURCE", "mock").strip().lower() or "mock"


def main() -> int:
    source = _get_event_risk_source()
    payload = build_event_risk_payload()

    current_path = write_current_event_risk(payload)
    history_path = append_event_risk_history(payload)
    status = get_current_event_risk_status()

    print(current_path)
    print(history_path)
    print(
        "event_risk"
        f" source={source}"
        f" status={status}"
        f" level={payload['event_risk_level']}"
        f" regime={payload['news_regime']}"
        f" score={payload['event_risk_score']}"
        f" reasons={len(payload['reason_codes'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
