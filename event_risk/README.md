# Event-Risk Service

## Purpose

The Event-Risk Service is a separate modular producer that writes a normalized event-risk artifact for future consumers.

Current scope:
- mock source only
- writes `data/processed/event_risk/current.json`
- runs standalone
- runs in Docker
- does not touch `paper`
- does not change trading behavior

This is a contract-first, artifact-first component.

---

## Current artifact

Canonical current artifact path:

`data/processed/event_risk/current.json`

Current V1 fields:

- `as_of_utc`
- `status`
- `event_risk_level`
- `news_regime`
- `event_risk_score`
- `ttl_seconds`
- `reason_codes`
- `source_count`

---

## Current package files

- `event_risk/main.py`
- `event_risk/service.py`
- `event_risk/schema.py`
- `event_risk/writer.py`
- `event_risk/adapters/mock.py`

---

## Current behavior

The current implementation uses a mock adapter.

It:
- builds a normalized payload
- validates schema
- writes `current.json`
- prints the written path
- prints a compact summary line

No external provider integration exists yet.

---

## Local run

From repo root:

```bash
python3 -m event_risk.main
