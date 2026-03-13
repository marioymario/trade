# EVENT RISK SERVICE SPEC — CURRENT PROPOSED V1

Purpose

The Event-Risk Service is a separate modular producer that converts external event/news conditions into a small, structured, normalized event-risk artifact.

Its job is not to predict trades.

Its job is to produce a boring, inspectable current-state artifact that a future consumer may use as an external regime/risk input.

This service must remain useful even if no trading-system integration happens yet.

--------------------------------------------------
1) STATUS
--------------------------------------------------

This document defines the proposed V1 contract and semantics for the Event-Risk Service.

This is a contract-first spec.

Initial implementation should follow this spec rather than inventing behavior ad hoc.

--------------------------------------------------
2) NON-GOALS
--------------------------------------------------

The Event-Risk Service is not:

- an AI trader
- a direct buy/sell recommendation engine
- a direct live internet dependency inside main.py
- a replacement for price/feature-based strategy logic
- a provider payload mirror
- a free-form sentiment text generator
- a hidden sidecar with undocumented output

The first useful version should stay small, explicit, and machine-readable.

--------------------------------------------------
3) DESIGN PRINCIPLES
--------------------------------------------------

The Event-Risk Service must follow these principles:

- modular
- Dockerized
- inspectable
- file-contract first
- normalized output
- minimal schema
- stable machine-readable reason codes
- UTC-explicit time semantics
- fail-safe behavior defined up front
- reusable outside this repo
- no direct invasive integration into trading runtime during initial build

The service should feel like a native processed-artifact producer, not a bolt-on app feature.

--------------------------------------------------
4) ARCHITECTURAL BOUNDARY
--------------------------------------------------

Producer

The Event-Risk producer is a separate service/process/container.

Producer responsibilities:

- read trusted external inputs
- normalize provider-specific details
- reduce them to the official contract
- write the canonical current-state artifact
- expose freshness and status explicitly
- fail in a predictable way

Consumer

A future consumer may be:

- the trading system
- the dashboard
- an alerting tool
- offline analytics
- another repo

Consumer responsibilities:

- read the local normalized artifact
- validate freshness/status/schema
- decide what action, if any, to take

The producer owns normalized event-risk data.

The consumer owns policy mapping.

--------------------------------------------------
5) INITIAL INTEGRATION RULE
--------------------------------------------------

The Event-Risk Service must not directly modify the current live trading runtime during initial build.

Specifically, initial work must not:

- change strategy logic
- change entry thresholds
- change cooldown behavior
- change trailing behavior
- add direct network dependency to main.py
- wire event-risk into paper yet

Initial build must remain parallel-safe and non-invasive.

--------------------------------------------------
6) CANONICAL ARTIFACT PATHS
--------------------------------------------------

Required V1 path:

data/processed/event_risk/current.json

This is the canonical current-state artifact.

It must represent the latest normalized usable event-risk state.

It is not a raw provider dump.
It is not a log stream.
It is not a mirror of external payloads.

Optional later path:

data/processed/event_risk/history.csv

This may be added later for historical analysis.

History is explicitly secondary.

History must not delay the first useful version.

--------------------------------------------------
7) ARTIFACT ROLE AND SEMANTICS
--------------------------------------------------

Event-Risk is a processed artifact.

It is conceptually similar to other processed artifacts in that it has explicit semantics and canonical location, but it serves a different role.

Event-Risk answers:

- what is the current normalized event-risk state?
- when was that state produced?
- is it usable?
- how long is it valid for?
- what stable reason codes explain it?
- how many sources contributed to it?

Event-Risk does not answer:

- whether the system should buy now
- whether the system should sell now
- whether an entry must be blocked
- what threshold the strategy should use
- what exact provider payload was received

Those decisions belong to future consumers or future analysis layers.

--------------------------------------------------
8) REQUIRED V1 SCHEMA
--------------------------------------------------

Canonical example:

{
  "as_of_utc": "2026-03-12T15:00:00+00:00",
  "status": "ok",
  "event_risk_level": "elevated",
  "news_regime": "headline_driven",
  "event_risk_score": 0.72,
  "ttl_seconds": 900,
  "reason_codes": [
    "geopolitical_conflict",
    "oil_shock_risk",
    "cross_asset_volatility"
  ],
  "source_count": 3
}

--------------------------------------------------
9) FIELD DEFINITIONS
--------------------------------------------------

as_of_utc
- type: string
- required: yes
- meaning: UTC timestamp representing when the normalized current-state artifact was produced
- rules:
  - must be timezone-aware
  - must use UTC explicitly
  - should be ISO 8601 / RFC 3339 compatible

status
- type: string enum
- required: yes
- allowed values:
  - ok
  - stale
  - error
- meaning:
  - top-level service judgment about artifact usability
- rules:
  - ok means artifact is currently intended to be usable
  - stale means artifact exists but is no longer fresh enough for normal trust
  - error means producer encountered a failure or could not produce valid normalized state
- important:
  - future consumers must still validate freshness independently using as_of_utc and ttl_seconds
  - status is part of the contract, not a replacement for deterministic freshness checking

event_risk_level
- type: string enum
- required: yes
- allowed values:
  - normal
  - elevated
  - extreme
- meaning:
  - normalized categorical risk state
- rules:
  - low-dimensional and stable
  - must not be provider-specific
  - must not contain prose

news_regime
- type: string enum
- required: yes
- allowed values:
  - calm
  - headline_driven
  - disorderly
- meaning:
  - normalized description of the current event/news environment
- interpretation guidance:
  - calm = no unusual current event/news pressure detected
  - headline_driven = event/news flow appears materially relevant to current conditions
  - disorderly = event/news environment appears unusually unstable, discontinuous, or shock-like
- this is a normalized regime label, not a direct trading command

event_risk_score
- type: number
- required: yes
- expected range:
  - 0.0 to 1.0
- meaning:
  - normalized scalar event-risk score
- rules:
  - higher means higher event risk
  - must be bounded and interpretable
  - must be documented as normalized service output, not raw provider confidence
  - must not be labeled as AI confidence
- interpretation:
  - score supports machine consumption and future policy mapping
  - score does not by itself imply any direct trade action

ttl_seconds
- type: integer
- required: yes
- meaning:
  - maximum age in seconds for which this artifact should be treated as fresh
- rules:
  - must be positive
  - must be explicit in every valid artifact
  - freshness is determined relative to as_of_utc

reason_codes
- type: array of strings
- required: yes
- meaning:
  - stable machine-readable reasons contributing to the current normalized event-risk state
- rules:
  - must use short stable identifiers
  - must not use long prose explanations
  - should be low-cardinality and reusable
  - should not leak provider-specific implementation details unless intentionally standardized
- preferred style examples:
  - geopolitical_conflict
  - oil_shock_risk
  - cross_asset_volatility
  - major_macro_event
  - exchange_incident
- bad style examples:
  - The market is reacting to scary war headlines
  - ProviderA says sentiment is negative
  - multi-sentence human explanation text
- an empty list is allowed only if the artifact is valid and the normalized state truly has no active reasons worth recording

source_count
- type: integer
- required: yes
- meaning:
  - number of source inputs used to produce the normalized current-state artifact
- rules:
  - must be zero or positive
  - intended for observability, not policy
  - does not require provider detail disclosure

--------------------------------------------------
10) OPTIONAL FUTURE FIELDS
--------------------------------------------------

The following fields are intentionally not required in V1 core contract:

- size_multiplier
- block_new_entries

Reason:
these begin to blur the boundary between producer-owned normalized risk data and consumer-owned policy mapping.

These may be revisited later only if the project explicitly chooses to let the producer emit advisory policy hints.

Current preferred boundary:
producer returns normalized event-risk state;
consumer decides policy mapping.

--------------------------------------------------
11) FRESHNESS SEMANTICS
--------------------------------------------------

Freshness semantics are part of the contract and must be deterministic.

Freshness rule:

An artifact is considered fresh if:

current_utc <= as_of_utc + ttl_seconds

An artifact is considered stale if:

current_utc > as_of_utc + ttl_seconds

Important rule:

Future consumers must not rely on status alone.

Consumers should determine effective freshness from:

- as_of_utc
- ttl_seconds

and then use status as an additional signal.

Producer expectation:

The producer should attempt to write status=ok only when it believes the artifact is valid and usable at write time.

If the producer knows the artifact is already stale or unusable at write time, it should write the most truthful status available.

--------------------------------------------------
12) FAIL-SAFE SEMANTICS
--------------------------------------------------

Fail-safe behavior must be deterministic.

Missing file

If data/processed/event_risk/current.json does not exist:
- treat event-risk as unavailable
- do not invent state
- do not assume provider access
- future consumer should follow its documented safe fallback behavior

Malformed file

If the file exists but is not valid JSON or does not match required schema:
- treat artifact as invalid
- treat event-risk as unavailable
- future consumer should follow safe fallback behavior

status=stale

If artifact status is stale, or freshness check shows it is stale:
- treat artifact as not fresh for normal decision use
- future consumer should follow its defined stale fallback behavior

status=error

If artifact status is error:
- treat artifact as unusable for normal decision use
- future consumer should follow its defined error fallback behavior

Safe fallback principle

This spec does not hardcode future trading behavior.

However, it requires that future consumers have explicit documented behavior for:
- missing artifact
- malformed artifact
- stale artifact
- error artifact

The future trading consumer must be able to behave deterministically from spec + consumer policy, without guessing.

--------------------------------------------------
13) TIME SEMANTICS
--------------------------------------------------

UTC must be explicit everywhere in this component.

Required UTC-explicit fields:
- as_of_utc
- ttl_seconds

Rules:
- do not use naive local timestamps in artifact contract
- do not rely on local timezone interpretation
- do not make freshness dependent on ambiguous local time

If future source windows are added, those should also be UTC-explicit.

--------------------------------------------------
14) CURRENT.JSON SEMANTICS
--------------------------------------------------

current.json must represent the latest normalized usable service state.

It should contain:
- one current object
- normalized fields only
- the official contract state

It should not contain:
- raw provider payloads
- large source excerpts
- free-form essays
- provider-specific nested blobs unless intentionally added to the official schema later

The service boundary exists to hide provider-specific complexity behind a small stable contract.

--------------------------------------------------
15) REASON CODE DESIGN RULES
--------------------------------------------------

Reason codes must be:
- machine-readable
- short
- stable
- reusable
- implementation-light

Reason codes should be nouns or compact identifiers, not prose.

Preferred style:
- geopolitical_conflict
- major_macro_event
- oil_shock_risk
- cross_asset_volatility
- exchange_incident

Avoid:
- paragraphs
- provider names unless standardized intentionally
- unstable one-off strings
- raw headline text
- natural-language explanations embedded in the artifact contract

Human-readable explanation may exist elsewhere, such as:
- logs
- dashboards
- documentation

The artifact contract should stay boring.

--------------------------------------------------
16) REUSABILITY REQUIREMENT
--------------------------------------------------

The Event-Risk Service must remain useful outside this repo.

That means:
- service can run alone
- artifact can be inspected alone
- no trading integration is required for usefulness
- another dashboard or repo could read the same normalized artifact
- provider details remain behind the service boundary

This requirement protects the design from becoming prematurely overfit to one trading loop.

--------------------------------------------------
17) DOCKER REQUIREMENT
--------------------------------------------------

Docker is required from the start.

The Event-Risk Service should run in its own container and write to the mounted canonical artifact path.

The trading system should not need to know:
- how providers are queried
- how normalization works internally
- what dependencies the service uses

The trading system should only care whether a valid fresh artifact exists.

--------------------------------------------------
18) REPO INTEGRATION DIRECTION
--------------------------------------------------

The preferred first repo integration style is:
- define the spec
- define canonical paths
- build separate producer
- write current.json
- validate freshness/staleness/error behavior
- only later consider optional consumers

The service must not begin as a hidden special-case script or undocumented helper output.

It should feel like a native processed artifact from day one.

--------------------------------------------------
19) EXPECTED INITIAL IMPLEMENTATION SEQUENCE
--------------------------------------------------

ER.1
Contract and semantics only

Deliverables:
- this spec
- canonical path decision

ER.2
Dockerized producer skeleton

Deliverables:
- separate service/container
- mock or placeholder source handling
- writes valid current.json
- proves schema and freshness behavior

ER.3
Source adapters

Deliverables:
- trusted external inputs
- normalization behind contract boundary
- no change to trading runtime yet

ER.4
Optional read-only consumer prototype

Deliverables:
- local artifact read only
- optional observability/logging only
- no trading behavior change yet

ER.5
Policy experiments

Deliverables:
- explicit consumer-owned mapping experiments
- only after baseline and contract are stable

--------------------------------------------------
20) CONSUMER EXPECTATIONS FOR FUTURE PHASES
--------------------------------------------------

A future consumer should:
1. read local artifact only
2. validate JSON/schema
3. validate freshness using as_of_utc + ttl_seconds
4. inspect status
5. decide consumer-specific fallback or policy action

A future trading consumer must not depend on direct external network access for event-risk.

That boundary is intentional and must be preserved.

--------------------------------------------------
21) CURRENT V1 RECOMMENDATION
--------------------------------------------------

The recommended V1 core contract is:
- as_of_utc
- status
- event_risk_level
- news_regime
- event_risk_score
- ttl_seconds
- reason_codes
- source_count

This is enough for a first useful version.

It is small, explicit, inspectable, and stable enough to support later consumers without turning the project into soup.

--------------------------------------------------
22) DOCUMENT RULE
--------------------------------------------------

This is a current-state spec for the Event-Risk Service contract.

Update this file when:
- required schema changes
- canonical artifact paths change
- freshness semantics change
- fail-safe semantics change
- producer/consumer boundary changes materially

Do not turn this file into a mission archive.

Keep it current, explicit, and operational.
