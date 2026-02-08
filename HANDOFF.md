### Decision monotonicity invariant

### Restart-safe ≠ catch-up-safe

### Explicit non-goals
---

# HANDOFF — v0.2.1 (ops-hardened)

**Date:** 2026-02-06  
**Status:** Correctness anchor + operational hardening complete  
**Baseline tag:** v0.2-equivalence-pass  
**Delta:** v0.2.1-ops-hardened  

---

## 0) What this milestone proves (the headline)

This system now has a **verified, restart-safe trading loop** where:

- **LIVE** emits exactly one decision per closed bar (including explicit skips).
- **BACKTEST** replays deterministically from on-disk market data.
- **Equivalence validation** confirms decision and trade lifecycle behavior matches across LIVE and BACKTEST for overlapping windows (sync-at-flat).
- **Operational failures** (restarts, container crashes, filesystem quirks) no longer corrupt data or break invariants.

This milestone is a **correctness anchor**.  
All future changes must preserve the contracts defined below.

---

## 1) Final contracts (LOCKED)

### 1.1 `ts_ms` invariant (hard)

- `ts_ms` is the **bar close timestamp**, aligned to the timeframe boundary.
- Identical meaning in LIVE and BACKTEST.
- Every decision and trade row is keyed to `ts_ms`.

Example (5m):
ts_ms = bar_start_ts + 300_000

---

### 1.2 Closed-bar processing rule (structural)

Bars are treated as closed by construction:

1. Fetch or load recent bars.
2. Drop the most recent bar (assumed possibly in-progress).
3. Operate only on the remaining bars.

No reliance on:
- Wall-clock timing
- Exchange “is_closed” flags
- Local clock alignment

---

### 1.3 Decision monotonicity invariant (explicit)

Decisions **must be emitted in strictly increasing `ts_ms` order**.

- A LIVE or BACKTEST run must never append a decision with  
  `ts_ms <= last_written_ts_ms` for the same `(exchange, symbol, timeframe)`.
- Decision logs are **append-only time series**.

An optional guard is available:
ENFORCE_DECISION_MONOTONIC=1

When enabled, non-monotonic writes fail fast.

---

### 1.4 One decision per closed bar

For every closed bar, exactly one decision row is emitted, even if the system skips:

- `not_enough_bars`
- `cadence_failed`
- `features_invalid`
- `fetch_failed` (future)
- `persist_failed` (future)

This prevents silent timeline gaps.

---

## 2) Execution semantics

### 2.1 LIVE execution

Defined in `files/main.py`.

Guarantees:
- Restart-safe (no duplicate decisions)
- Timeline-safe (monotonic `ts_ms`)
- Stateless across restarts except for persisted CSV state

Mechanism:
- Last decision timestamp is seeded from existing CSV.
- Decisions are deduplicated by `(exchange, symbol, timeframe, ts_ms)`.

**Important:**  
Restart-safe ≠ catch-up-safe (see Section 4).

---

### 2.2 BACKTEST execution

Defined in `files/backtest/engine.py`.

Guarantees:
- Deterministic replay from disk
- Warmup bars loaded for indicator validity
- Output rows emitted **only inside requested window**

Warmup bars:
- Update internal state
- Must never emit decisions or trades

---

### 2.3 Phase 2A stop-through modeling (BACKTEST only)

In BACKTEST only:

- LONG: if bar opens below stop → fill at open
- SHORT: if bar opens above stop → fill at open

LIVE fills stops at the stop price.

**Expected result:**
- Lifecycle equivalence preserved
- PnL divergence allowed (by design)

---

## 3) Data integrity & storage guarantees

### 3.1 Market data (`data/raw/`)

- Partitioned by `exchange / symbol / timeframe / date`
- Written atomically (temp file + replace)
- UTC timestamps enforced
- Duplicate timestamps deduped (last-write-wins)

This is the **ground truth** for historical replay.

---

### 3.2 Decisions & trades (`data/processed/`)

- Append-only CSVs
- Strict `ts_ms` ordering
- LIVE and BACKTEST write to separate run-specific directories
- No in-place mutation

---

## 4) Explicit limitations (by design)

The following are **not guaranteed** at this milestone:

- LIVE and BACKTEST PnL equality
- Market realism (latency, slippage, fills)
- Catch-up of missed bars after extended LIVE downtime
- Indicator numerical stability across code revisions
- Strategy profitability or trade optimality
- Multi-symbol or multi-timeframe isolation

These are **outside the v0.2 correctness boundary**.

---

## 5) Correctness boundary (named)

This milestone guarantees:

> **Behavioral equivalence of decision and trade lifecycle transitions for identical bar data.**

Out of scope:
- Execution quality
- Market microstructure
- Exchange-specific quirks

---

## 6) Operational guarantees (v0.2.1)

- Containers run as host-aligned UID:GID (no root-owned artifacts).
- Atomic parquet writes use collision-proof temp filenames.
- LIVE containers auto-restart (`restart: unless-stopped`).
- Filesystem and restart failures no longer corrupt state.

---

## 7) Canonical files (source of truth)

- `files/main.py` — LIVE loop
- `files/backtest/engine.py` — deterministic replay
- `files/main_live_vs_backtest_equivalence.py` — validator
- `files/data/storage.py` — atomic persistence
- `files/data/decisions.py` — decision contract enforcement

---

## 8) Next milestones (not implemented yet)

- v0.3: missed-bar catch-up logic
- LIVE degraded-mode skip decisions
- Stronger equivalence assertions
- Resilience tests (kill/restart mid-loop)

---

**Mjölnir principle:** correctness first, speed second.


--- 

# HANDSOFF — 2026-02-07 (after v0.2.1 docs + Tier 2/healthcheck upgrades)

## Current status
- LIVE ↔ BACKTEST lifecycle equivalence is the correctness anchor (v0.2-equivalence-pass).
- Tier 2 hardening added:
  - decision monotonicity enforcement option (`ENFORCE_DECISION_MONOTONIC=1`) in decisions append path
  - resilience behaviors for forced failure tests (fetch/persist failures record skip decisions)
- Healthcheck implemented and working:
  - `files/main_healthcheck.py` supports operator mode vs strict
  - includes decision staleness + raw parquet staleness checks
  - includes cadence grace window after restart/downtime
  - supports `--json 1` for monitoring pipelines
- Docs added:
  - HANDOFF.md v0.2.1
  - DATA_LAYOUT.md based on current tree
  - healthcheck semantics documented (operator vs strict)

## What happened today (evidence)
- Verified forced-failure behaviors:
  - `FORCE_FETCH_FAIL=1` → healthcheck shows decisions stale (expected) when paper stopped; when running, records skip decisions
  - `FORCE_PERSIST_FAIL=1` → records `persist_failed` decisions; these show up as historical markers in tail (warning-only after hardening)
- Healthcheck now returns WARN after downtime until cadence window is clean again:
  - `clean_trailing_cadence_diffs` climbs over time; OK once >= grace bars

## Overnight plan (recommended)
Goal: collect uninterrupted clean cadence so health becomes OK with no grace warnings.

1) Start LIVE paper:
```bash
docker compose up -d paper
docker compose logs -f --tail=50 paper

