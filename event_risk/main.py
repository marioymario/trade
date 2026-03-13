from __future__ import annotations

from event_risk.service import build_event_risk_payload, get_current_event_risk_status
from event_risk.writer import write_current_event_risk


def main() -> int:
    payload = build_event_risk_payload()
    path = write_current_event_risk(payload)
    status = get_current_event_risk_status()

    print(path)
    print(
        "event_risk"
        f" status={status}"
        f" level={payload['event_risk_level']}"
        f" regime={payload['news_regime']}"
        f" score={payload['event_risk_score']}"
        f" reasons={len(payload['reason_codes'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
