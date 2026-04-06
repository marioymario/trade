# Event-Risk Service

## Purpose

The Event-Risk Service is a separate modular producer that writes a normalized event-risk artifact for future consumers.

Current scope:
- mock source
- local file source
- writes data/processed/event_risk/current.json
- runs standalone
- runs in Docker
- does not touch paper
- does not change trading behavior

This is a contract-first, artifact-first component.

--------------------------------------------------
1) CURRENT ARTIFACT
--------------------------------------------------

Canonical current artifact path:

data/processed/event_risk/current.json

Current V1 fields:

- as_of_utc
- status
- event_risk_level
- news_regime
- event_risk_score
- ttl_seconds
- reason_codes
- source_count

--------------------------------------------------
2) CURRENT PACKAGE FILES
--------------------------------------------------

- event_risk/main.py
- event_risk/service.py
- event_risk/schema.py
- event_risk/writer.py
- event_risk/adapters/mock.py
- event_risk/adapters/file_source.py

--------------------------------------------------
3) CURRENT BEHAVIOR
--------------------------------------------------

The current implementation supports two sources:

- mock
- file

It:
- builds a normalized payload
- validates schema
- writes current.json
- prints the written path
- prints a compact summary line

No external network/provider integration exists yet.

--------------------------------------------------
4) LOCAL RUN
--------------------------------------------------

From repo root:

python3 -m event_risk.main

Expected output shape:

data/processed/event_risk/current.json
event_risk source=mock status=ok level=normal regime=calm score=0.1 reasons=0

--------------------------------------------------
5) DOCKER RUN
--------------------------------------------------

From repo root:

docker compose -f docker-compose.event_risk.yml up --build --force-recreate

--------------------------------------------------
6) SUPPORTED SOURCES
--------------------------------------------------

Mock source

Default source:

EVENT_RISK_SOURCE=mock python3 -m event_risk.main

Supported mock environment variables:

- EVENT_RISK_SOURCE
- EVENT_RISK_STATUS
- EVENT_RISK_LEVEL
- EVENT_RISK_NEWS_REGIME
- EVENT_RISK_SCORE
- EVENT_RISK_TTL_SECONDS
- EVENT_RISK_REASON_CODES
- EVENT_RISK_SOURCE_COUNT

Example:

EVENT_RISK_SOURCE=mock \
EVENT_RISK_LEVEL=elevated \
EVENT_RISK_NEWS_REGIME=headline_driven \
EVENT_RISK_REASON_CODES=geopolitical_conflict,cross_asset_volatility \
python3 -m event_risk.main

File source

The file source reads a prebuilt normalized payload from:

data/processed/event_risk/manual_current.json

Default local run:

EVENT_RISK_SOURCE=file python3 -m event_risk.main

Default compose run:

EVENT_RISK_SOURCE=file docker compose -f docker-compose.event_risk.yml up --build --force-recreate

Optional file-source environment variables:

- EVENT_RISK_MANUAL_SOURCE_PATH
- EVENT_RISK_FILE_SOURCE_REFRESH_AS_OF_UTC

EVENT_RISK_FILE_SOURCE_REFRESH_AS_OF_UTC is useful for testing.
When enabled, the file source keeps the manual payload fields but refreshes as_of_utc to current UTC before validation.

Example:

EVENT_RISK_SOURCE=file \
EVENT_RISK_FILE_SOURCE_REFRESH_AS_OF_UTC=1 \
python3 -m event_risk.main

Example manual file:

{
  "as_of_utc": "2026-03-13T21:30:00+00:00",
  "status": "ok",
  "event_risk_level": "elevated",
  "news_regime": "headline_driven",
  "event_risk_score": 0.4,
  "ttl_seconds": 900,
  "reason_codes": [
    "geopolitical_conflict"
  ],
  "source_count": 1
}

--------------------------------------------------
7) CURRENT STATUS
--------------------------------------------------

This is an ER.2-style skeleton pass.

What is done:
- canonical path helpers exist
- artifact writer exists
- schema validator exists
- read/fresh/status helpers exist
- Docker path works
- compose path works
- mock source works
- file source works
- source boundary exists

What is not done yet:
- external provider adapters
- history writing
- dashboard integration
- trading-system consumer integration
- policy mapping

--------------------------------------------------
8) GUARDRAILS
--------------------------------------------------

- keep paper untouched unless explicitly entering consumer work
- keep top-level runtime data/ operator-owned
- keep Event-Risk modular
- keep contract stable and boring
- producer owns normalized data
- future consumer owns policy mapping
