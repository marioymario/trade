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

---

HANDOVER FEB 7, 7:57

New Rules for HANDSOFF 

1) Drop-in section for HANDOFF.md

Copy/paste this whole block into your HANDOFF.md (near the top).

# SYNC GATE (must do before proposing changes)

**Rule:** Before suggesting fixes, we sync on reality.

## Step A — Reproduce in one command
Run:

```bash
DATA_TAG=<tag> make eqflat


Expected output includes:

[decisions] PASS/FAIL

[trades] PASS/FAIL

If FAIL: mismatch block showing first mismatch.

Step B — Report in this exact format

Paste:

Result: PASS/FAIL
DATA_TAG=...
RUNID=...
Layer: decisions|trades
Window overlap: [start_ts, end_ts]
First mismatch (ts_ms or trade index):
Hypothesis (1 sentence, no solution yet):
Next check I will run (1 command):


Only after this report is posted do we propose code changes.

Quick commands (operator cheatsheet)
Run LIVE paper loop
DATA_TAG=<tag> make live-up
make live-logs

Stop LIVE paper loop
make live-down

Run equivalence from the first LIVE bar (recommended)
DATA_TAG=<tag> make eqflat

Run plain equivalence against an existing backtest runid
DATA_TAG=<tag> RUNID=<runid> make eq

Run a windowed backtest manually
DATA_TAG=<tag> RUNID=<runid> START_TS_MS=<ts> END_TS_MS=<ts> make backtest

Troubleshooting Index (pick ONE, run it, paste output)
T1 — Confirm LIVE decisions file exists and has data
DATA_TAG=<tag>
ls -la data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv
tail -n 3 data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv

T2 — Extract START_TS_MS from LIVE (first data row)
LIVE="data/processed/decisions/<tag>/BTC_USD/5m/decisions.csv"
awk -F, 'NR==2{print $4; exit}' "$LIVE"

T3 — Show the decision row at a specific ts_ms
CSV="data/processed/decisions/<tag>/BTC_USD/5m/decisions.csv"
TS=1770508500000
awk -F, -v ts="$TS" '$4==ts {print; exit}' "$CSV"

T4 — Trades mismatch debug (show both trade files)
LIVE_T="data/processed/trades/<live_tag>/BTC_USD/5m/trades.csv"
BT_T="data/processed/trades/<bt_tag>/BTC_USD/5m/trades.csv"
echo "LIVE trades:"; tail -n +1 "$LIVE_T" | tail -n 5
echo "BT trades:";   tail -n +1 "$BT_T" | tail -n 5

Change proposal format (required)

Before coding, write:

Intent: (one sentence)

Constraints: (what must not change; list invariants)

Files touched: (explicit list)

Test plan: (exact command(s), no vagueness)

Risk: (what could break; how we’d notice)

Example test command:

DATA_TAG=paper_local_check make eqflat


---

## 2) How to run the “new files.sh” (your `scripts/eqflat.sh` + Makefile target)

You now have **two equivalent ways**:

### Option A (recommended): Make target
```bash
DATA_TAG=paper_local_check make eqflat

Option B: Run the script directly
./scripts/eqflat.sh paper_local_check


What eqflat does (in plain English):

reads START_TS_MS from row 2 of LIVE decisions.csv

runs make backtest windowed from that ts

runs make eq against that backtest run

3) Git plan (no noise, no surprises)

Right now you have:

✅ 1 commit already created locally (ahead of origin by 1)

🔶 a set of modified files still uncommitted (HANDOFF.md, engine.py, config/main/check scripts, docker-compose.yml, etc.)

You asked: “are we going to commit all changes we did?”
Answer: yes — but we do it safely: review → stage → commit → push.

Step 1 — Review what you’re about to publish

This is the “quality control” step. No staging yet.

git diff


If that’s too big, do it file by file:

git diff HANDOFF.md
git diff files/backtest/engine.py
git diff files/main.py
git diff docker-compose.yml

Step 2 — Stage everything you intend to ship

If you want to commit all modified tracked files (not ignored stuff), do:

git add HANDOFF.md docker-compose.yml \
  files/backtest/engine.py files/config.py files/main.py \
  files/main_data_quality_check.py files/main_features_check.py \
  files/main_healthcheck.py files/main_sanity_check.py \
  files/main_smoke.py files/main_state_check.py files/main_storage_check.py


(That stages exactly what git status -sb showed.)

Step 3 — Confirm staged set is correct
git diff --staged

Step 4 — Commit with a clear message
git commit -m "Wire DATA_TAG/RUN_ENV; stabilize eq workflow"

Step 5 — Run one check before pushing
DATA_TAG=paper_local_check make eqflat

Step 6 — Push
git push


That’s it.

Important: your .gitignore already protects requestedfiles.sh and requestedfiles.txt, and it ignores data/, so those won’t get committed unless you force-add them (don’t).

4) About the FAIL you saw (trades mismatch)

You just hit a real signal:

decisions PASS

trades FAIL because BT had an extra trade: LONG stop_hit after the first one

That means: lifecycle decision stream aligns, but execution/trade logging diverged in that window.

When you’re ready, the debug path is:

re-run eqflat (save runid)

compare trades.csv LIVE vs BT for that runid

inspect why BT generated a second stop-hit trade

But since you explicitly want to focus on commits/push first: ignore this until your repo state is clean and pushed.

5) “Next chat starter” (minimal, high signal)

Paste this at the top of your next chat and you’ll avoid the whole “meat to the grill” problem:

Goal: keep LIVE↔BT behavioral equivalence (ts-keyed, sync-at-flat).
Current DATA_TAG: paper_local_check
Command used: DATA_TAG=paper_local_check make eqflat
Latest result: PASS/FAIL (paste only summary + mismatch block if FAIL)
Repo state:
- last pushed commit: <hash>
- local unpushed commits: <count>
What I want to do next: <one sentence>
Constraints: do not change closed-bar rule / ts_ms semantics / warmup gating.


If you want the cleanest workflow long-term, the only “hard rule” I’d enforce is:
no one proposes changes until they run make eqflat and paste the sync report format.

When you’re ready, paste git diff --staged (or just the filenames you’re unsure about), and I’ll tell you exactly whether it’s safe/clean to commit that batch.

---

HANDOVER — 2026-02-07 — EQFLAT runner + LIVE↔BT equivalence workflow
0) Context and goal

We are building a trading system where LIVE and BACKTEST must match in lifecycle behavior (position open/close + reasons) when comparing over an overlapped time window, synced at flat.

We just added a one-command operator workflow:

make eqflat runs:

a windowed backtest that starts exactly at the first LIVE decision timestamp (row 2)

the equivalence check against LIVE

The intended outcome is fast, repeatable verification of LIVE↔BT equivalence with minimal operator steps.

1) What changed (high-level)
1.1 New operator command

Command (example):

DATA_TAG=paper_local_check make eqflat


What it does:

Reads LIVE decisions CSV:
data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv

Extracts START_TS_MS from the first data row (NR==2, column 4)

Creates a new RUNID=eqflat_YYYYmmdd_HHMMSS

Runs:

make backtest using that START_TS_MS

make eq using that RUNID (so it compares LIVE tag vs ${DATA_TAG}_bt_${RUNID})

1.2 New script

File:

scripts/eqflat.sh

Purpose:

Provide a reliable wrapper so you don’t have to type long env-chains.

Important:

This script intentionally does not use set -euo pipefail to avoid “unwanted behavior” you’ve hit before.

It does explicit return-code checks for make backtest and make eq.

1.3 Makefile improvements

The Makefile was updated to:

Standardize env-forwarding into docker containers via RUN_ENV:

--env DATA_TAG --env CCXT_EXCHANGE --env SYMBOL --env TIMEFRAME ...

Make DATA_TAG the storage namespace default (if not provided)

Update eq to use:

--live-tag "$(DATA_TAG)"

--bt-tag "$(DATA_TAG)_bt_$${RUNID}"

Add eqflat: target which calls:

./scripts/eqflat.sh "$(DATA_TAG)"

1.4 .gitignore updates

We explicitly do NOT commit local sharing helpers:

requestedfiles.sh

requestedfiles.txt

Also data/ is ignored (raw/processed/cache etc).

2) Current operator workflow (the “one-liner” way)
Run eqflat (recommended)
DATA_TAG=paper_local_check make eqflat


Expected:

backtest runs inside docker, creates:

data/processed/decisions/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/decisions.csv

data/processed/trades/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/trades.csv

equivalence tool runs and prints PASS/FAIL

Run manual (fallback)

If you want to do it step-by-step without the script:

Get first live ts:

LIVE="data/processed/decisions/paper_local_check/BTC_USD/5m/decisions.csv"
START_TS_MS="$(awk -F, 'NR==2{print $4; exit}' "$LIVE")"
echo "$START_TS_MS"


Run backtest:

DATA_TAG=paper_local_check RUNID="eqflat_$(date -u +%Y%m%d_%H%M%S)" START_TS_MS="$START_TS_MS" make backtest


Run equivalence:

DATA_TAG=paper_local_check RUNID="$RUNID" make eq

3) Known behavior and known risk
3.1 “PASS can become FAIL later” is possible

Because LIVE continues generating decisions/trades over time, the overlap window grows, and new divergences can appear.

Example we observed:

decisions: PASS

trades: FAIL because BT had 2 trades in window while LIVE had 1

This means:

The system is stable enough to compare, but lifecycle may still diverge under some conditions.

3.2 What to check when trades mismatch

When you see:

[trades] length mismatch: LIVE=1 BT=2

Do:

Inspect live trades:

LIVE_TRADES="data/processed/trades/${DATA_TAG}/BTC_USD/5m/trades.csv"
tail -n 20 "$LIVE_TRADES"


Inspect bt trades (from the run shown in output):

BT_TRADES="data/processed/trades/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/trades.csv"
tail -n 40 "$BT_TRADES"


Find the “extra” trade’s entry/exit ts_ms and then look up decisions around it:

LIVE_DEC="data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv"
BT_DEC="data/processed/decisions/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/decisions.csv"

# Example: check a specific ts_ms
awk -F, '$4==1770517500000 {print; exit}' "$LIVE_DEC"
awk -F, '$4==1770517500000 {print; exit}' "$BT_DEC"


Interpretation:

If LIVE is flat/no trade while BT opens/closes, it’s a real divergence (not a window/sync artifact).

4) Repo hygiene rules (no noise, no surprises)
4.1 “No changes before looking”

Before editing anything:

Always run:

git status -sb


If code-related:

git diff

4.2 “No patches”

Do not use git add -p during normal work unless explicitly required.
We stage whole coherent changesets.

4.3 “Quality work only”

Every change must satisfy:

reproducible command path (documented)

no new scripts written into the wrong directory

no accidental new untracked files unless intentional

commit messages reflect real scope

5) Git plan (commit & push) — clean and repeatable
5.1 What we commit vs don’t commit

Commit:

tracked code/docs changes (M ... files)

scripts under scripts/

Do NOT commit:

anything under data/ (ignored)

requestedfiles.sh, requestedfiles.txt (ignored)

5.2 Current state summary

You are:

ahead 1 commit already (you pushed nothing yet)

have additional modified tracked files:

HANDOFF.md

docker-compose.yml

files/... (multiple)

etc.

5.3 Recommended commit structure (2 commits total)

You already have:

Commit #1: “Add eqflat script and Makefile target”

Now do:

Commit #2: “Backtest/live plumbing and behavior changes” (the remaining modified tracked files)

Exact commands:

Stage all modified tracked files (only tracked ones):

git add -u


Verify staging:

git status -sb
git diff --staged


Commit:

git commit -m "Backtest/live plumbing and behavior fixes"


Push both commits:

git push

6) Files list (what matters)

New:

scripts/eqflat.sh

scripts/preflight.sh (currently empty; decide if we keep or delete later)

Modified (tracked):

.gitignore

Makefile

plus your current list from git status -sb (engine/config/main/check scripts etc.)

7) Next actions (practical)

Decide what to do with scripts/preflight.sh:

It’s empty right now. Either:

keep it as placeholder with TODO + basic checks

or delete it (cleaner)

If eqflat produces trade mismatches again:

capture the mismatch lines

inspect the “extra” trade in BT and find corresponding decision rows at entry/exit ts_ms

identify which rule or state difference caused the extra open/close

8) Operator quick reference

Run full check:

DATA_TAG=paper_local_check make eqflat


Just run equivalence (if you already know RUNID):

DATA_TAG=paper_local_check RUNID="..." make eq


Just run backtest windowed:

DATA_TAG=paper_local_check RUNID="..." START_TS_MS="..." make backtest

End HANDOVER

--- 

HANDOFF — 2026-02-08 — old-box (Pop!_OS) live paper loop + cron + GPU + 8888 lockdown + rsync deploy
0) What we achieved (truth)

We now have old-box running the trading repo under Docker Compose with:

paper service running the live paper loop (writes decisions/trades to disk)

trade service for tooling/Jupyter/tests

cron @reboot auto-starts the stack reliably after host reboot (GPU-first, CPU fallback)

GPU in containers works (TensorFlow sees GPU; runtime verified)

Port 8888 is locked down to localhost (127.0.0.1) instead of being publicly exposed

We established an rsync-based deploy flow (local → target) that preserves target-only state

1) Current known-good target state
1.1 Repo location (target)

Repo path on old-box:

/home/kk7wus/Projects/trade

1.2 Containers

docker compose ps shows both services up:

paper (live loop)

trade (tooling / Jupyter)

1.3 “Win condition” for 8888 lockdown

docker compose ps for trade shows:

127.0.0.1:8888->8888/tcp

If it shows 0.0.0.0:8888->8888, then 8888 is exposed and needs fix (see §5).

2) Contracts / invariants (LOCKED)
2.1 Target vs repo differences must be operator state only

On old-box, the intended differences vs the “source repo” are not code:

Allowed target-only:

Local-only .env (NOT committed), e.g. DATA_TAG, SYMBOL, TIMEFRAME, DRY_RUN, optional JUPYTER_BIND_ADDR

data/ contents (raw/processed decisions/trades) — runtime state, not committed

Installed crontab (scheduler state)

Logs in home directory (e.g. ~/trade_reboot.log, ~/trade_heartbeat.log)

Docker runtime state / container lifecycle

Not allowed:

“Just this one edit” on target in repo files.
All repo edits happen locally, then deployed.

2.2 Deployment discipline

Local is source of truth

Target is deploy + run only

We use rsync to push updates to target (no git pull needed)

3) Ops automation (cron + scripts)
3.1 Repo scripts (target has ops/)

/home/kk7wus/Projects/trade/ops/ contains:

cron_reboot.sh — boot start, GPU-first, verify GPU usability, fallback CPU, logs to ~/trade_reboot.log

cron_heartbeat.sh — periodic health proof, logs to ~/trade_heartbeat.log

crontab.example, README.md

3.2 Crontab (target)

Target user’s crontab includes:

@reboot /bin/bash -lc '/home/kk7wus/Projects/trade/ops/cron_reboot.sh'

Heartbeat every 10 minutes (if enabled): cron_heartbeat.sh

Old reboot line exists but is commented out:

#@reboot /bin/bash -lc '/home/kk7wus/trade_boot.sh'

3.3 Logs (target)

Logs are in the target user’s home directory:

/home/kk7wus/trade_reboot.log

/home/kk7wus/trade_heartbeat.log

4) 8888 lockdown (Jupyter exposure)
4.1 What changed (compose)

In docker-compose.yml under the trade service:

ports:
  - "${JUPYTER_BIND_ADDR:-127.0.0.1}:8888:8888"


This makes host publishing default to 127.0.0.1.
Even though Jupyter runs --ip=0.0.0.0 inside the container, the host bind address controls exposure.

4.2 Verify on target
cd /home/kk7wus/Projects/trade
docker compose ps


Expected:

127.0.0.1:8888->8888/tcp

4.3 Safe remote access pattern

Use an SSH tunnel instead of exposing 8888:

ssh -p <SSH_PORT> -L 8888:127.0.0.1:8888 kk7wus@10.0.0.82


Then open http://localhost:8888 on your local machine.

5) Troubleshooting quick hits
5.1 If 8888 shows as exposed (0.0.0.0:8888)

Most common causes:

Target is still running old container config → needs recreate

Target .env sets JUPYTER_BIND_ADDR=0.0.0.0

Fix/re-apply (target):

cd /home/kk7wus/Projects/trade
docker compose up -d --force-recreate trade
docker compose ps


Check env override:

grep -n '^JUPYTER_BIND_ADDR=' .env || true

5.2 Paper loop alive proof (target)
cd /home/kk7wus/Projects/trade
tail -n 3 data/processed/decisions/*/*/*/decisions.csv 2>/dev/null | tail -n 20
docker compose logs --since=15m --tail=120 paper

5.3 Cron proof (target)
crontab -l
tail -n 120 ~/trade_reboot.log
tail -n 120 ~/trade_heartbeat.log

6) Rsync deploy flow (local → target) — no deletes
6.1 Goal

Push repo changes from local to target without overwriting:

.env (target-only)

data/ (target-only)

6.2 Dry-run command (local)

Replace <SSH_PORT> with the correct SSH port (we hit “wrong port” once; confirm before running).

rsync -av --dry-run --itemize-changes --stats \
  -e "ssh -p <SSH_PORT>" \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='data/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='ops/logs/' \
  ~/Projects/trade/ \
  kk7wus@10.0.0.82:~/Projects/trade/

6.3 Real sync (local)

Same command without --dry-run.

6.4 Apply changes on target (recreate trade when ports change)
ssh -p <SSH_PORT> kk7wus@10.0.0.82 \
  'cd ~/Projects/trade && docker compose up -d --force-recreate trade && docker compose ps'

7) GPU status (summary)

Host has NVIDIA GPU (nvidia-smi works)

Docker GPU integration works

TensorFlow in container can see GPU (previously validated)

cron boot script uses GPU compose if present and falls back to CPU if GPU isn’t usable

8) Next missions (queued)

Stop target drift: keep target as “deploy + run,” no repo edits

Optional: remove local-only helper scripts from target if they appear (target doesn’t need deploy helpers)

Optional hardening: risk controls / kill switch (shortest “real-trade safety” upgrade)

Optional: log rotation (prevent ~/trade_*.log growth)

9) Current “done / not done” truth

✅ Reboot resilience: working
✅ Cron auto-start: working
✅ GPU-first + CPU fallback: working
✅ 8888 locked to localhost: verified working
✅ Rsync deploy approach: working (dry-run + correct port + sync + recreate trade)
⚠️ Real-money readiness: not the current goal; next step would be risk controls + reconciliation later


# HANDOFF — 2026-03-06 — Mission 4 Enforcement + Runtime Proof State

## Mission

Finish **Mission 4 — Enforcement at Submit Boundary**.

Goal:

Ensure entry blocks for broker-facing safety controls are enforced at the submit boundary and recorded in `decisions.csv` with canonical reason codes.

Required canonical submit-boundary codes:

- `STOP_BLOCK`
- `HALT_BLOCK`
- `ARM_BLOCK`
- `DAILY_LIMIT_BLOCK`

Exits must remain allowed.

---

## Why this mission matters

This is the main remaining safety-hardening gap between:

- a system that can run unattended
- and a system that is safe enough to even think about real money

The key principle is:

**`files/broker/guarded.py` must be the authoritative submit-boundary blocker.**

`main.py` may still block for orchestration/runtime reasons like degraded mode or cooldown, but not for broker-facing control-plane policy.

---

## Files changed in this session

### Trading-system files changed

- `files/broker/guarded.py`
- `files/main.py`
- `files/data/features.py`
- `files/data/storage.py`

### Files inspected but not changed

- `files/data/decisions.py`
- `files/broker/paper.py`
- `files/data/market.py`

---

## What changed

### 1) `files/broker/guarded.py`

Moved submit-boundary broker policy into `GuardedBroker`.

Current responsibilities there:

- `STOP_BLOCK(...)`
- `HALT_BLOCK(...)`
- `ARM_BLOCK(...)`
- `DAILY_LIMIT_BLOCK(...)`
- `DRY_RUN_BLOCK` for real-broker path
- `BAD_INPUTS`
- `MAX_ORDER_USD_BLOCK(...)`
- `MAX_POSITION_USD_BLOCK(...)`

Important fix:
- renamed old `HALT_ENTRY_BLOCK` style to canonical `HALT_BLOCK`

### 2) `files/main.py`

Removed duplicate broker-facing policy from `main.py`.

`main.py` now keeps orchestration/runtime blocks only:

- `COOLDOWN_BLOCK(...)`
- `DEGRADED_BLOCK(...)`
- `SIZE_BLOCK(...)`

It still handles:

- market fetch / feature compute loop
- degraded mode logic
- trailing freeze behavior
- decision writing
- exit handling

Important split now:

- `main.py` decides whether it wants to enter
- `GuardedBroker` decides whether entry is allowed to hit the inner broker

### 3) `files/data/features.py`

Hardened latest-row feature validation.

Old behavior:
- any NaN in latest row killed the loop

New behavior:
- execution-critical fields still fail hard
- optional derived fields warn instead of halting

This reduced brittleness but did **not** remove all upstream data issues.

### 4) `files/data/storage.py`

Added observability for suspicious replayed adjacent OHLCV bars.

Current behavior:
- warn if adjacent rows have different timestamps but identical OHLCV payload
- do **not** mutate/drop rows yet
- observability-first only

---

## What was proven

### Proven in `decisions.csv`

Observed real rows showing:

- `ARM_BLOCK(...)`
- `DEGRADED_BLOCK(...)`
- `COOLDOWN_BLOCK(...)`

Observed forced-entry proof rows with:

- `entry_should_enter=True`
- `entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE`

This proves:

- forced-entry test hook works
- fresh eligible bar path works
- decision writing path works
- blocked entry reasons are landing in `entry_blocked_reason`
- Mission 4 submit-boundary plumbing is working at least for `ARM_BLOCK`

### Proven operationally

- restart-safe idempotency is working
- in-progress last-bar dropping is working
- loop survives restarts
- `.env` cleanup fixed stale test-fault config issues
- duplicate/dirty runtime env was a real source of confusion and has been cleaned

---

## What is **not** fully proven yet

Still not directly observed in `decisions.csv` during this session:

- `STOP_BLOCK(...)`
- `HALT_BLOCK(...)`
- `DAILY_LIMIT_BLOCK(...)`

This is the remaining proof gap.

Important nuance:

This is **not** because the submit-boundary architecture failed.

It is because entry attempts were intercepted earlier by higher-precedence runtime/orchestration blockers during testing:

- `COOLDOWN_BLOCK(...)`
- then later
- `DEGRADED_BLOCK(...)`

So STOP/HALT were not reached on those proof attempts.

---

## Current blocker

### Main remaining blocker to full Mission 4 PASS

**Degraded-mode precedence during proof runs.**

Observed fresh proof row:

- `entry_should_enter=True`
- `entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE`
- `entry_blocked_reason=DEGRADED_BLOCK(features_invalid_x4_in_last6)`

So the system is still correctly blocking, but the block reason is degraded-mode, not STOP/HALT.

### What caused degraded mode

Two things contributed during this session:

1. stale test-fault env left on in `.env`
   - `FORCE_FEATURES_INVALID_N=2`
   - this intentionally poisoned features until cleaned up

2. bar-freshness / replay weirdness in live data path
   - not conclusively fatal now
   - but previously contributed to `features_invalid` rows

---

## Important runtime findings

### `.env` was dirty and duplicated

Found stale test settings in runtime `.env`, including:

- `FORCE_FEATURES_INVALID_N=2`
- duplicate `TEST_HOOKS_ENABLED`
- duplicate `FORCE_ENTRY_SIGNAL_ONCE`

This was cleaned by overwriting `.env` with a single boring source of truth.

### Repeated `SKIP: already-processed bar` was not necessarily a bug

This turned out to be expected behavior when:

- the latest fetched bar was still the in-progress bar
- `main.py` dropped the in-progress last bar
- newest eligible closed candle was already present in `decisions.csv`

So repeated skip behavior during a live 5m window can be correct.

---

## Current runtime truth

At the end of this session:

- Mission 4 architecture is much cleaner than before
- `GuardedBroker` now owns submit-boundary entry policy
- `main.py` is cleaner and no longer duplicates STOP/HALT/ARM/daily-limit entry policy
- test hooks are available and working
- degraded state still needs to clear before STOP/HALT proof can land cleanly

---

## Recommended next mission

### Immediate next mission

**Complete deterministic proof for `STOP_BLOCK` and `HALT_BLOCK` after degraded mode clears.**

Suggested method:

1. wait until market_reason is no longer `DEGRADED(...)`
2. keep:
   - `TEST_HOOKS_ENABLED=1`
   - `FORCE_ENTRY_SIGNAL_ONCE=1`
3. set:
   - STOP present, HALT absent
4. recreate paper
5. capture next fresh eligible row in `decisions.csv`

Expected proof row:

- `entry_should_enter=True`
- `entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE`
- `entry_blocked_reason=STOP_BLOCK(...)`

Then repeat with:

- STOP absent
- HALT present

Expected:

- `entry_blocked_reason=HALT_BLOCK(...)`

### After that

Do a controlled `DAILY_LIMIT_BLOCK(...)` proof with a deterministic low limit.

---

## Suggested PASS condition for Mission 4

Mission 4 should be marked PASS only when all of the following are observed:

1. `ARM_BLOCK(...)` observed in `entry_blocked_reason`
2. `STOP_BLOCK(...)` observed in `entry_blocked_reason`
3. `HALT_BLOCK(...)` observed in `entry_blocked_reason`
4. `DAILY_LIMIT_BLOCK(...)` observed in `entry_blocked_reason`
5. exits remain allowed under STOP/HALT
6. no broker-facing policy for STOP/HALT/ARM/daily-limit remains duplicated in `main.py`

Current status:
- items 1 and 6 are effectively proven
- items 2–5 still need explicit proof

---

## Commands that were useful in this session

### Check runtime env inside paper
```bash
cd ~/Projects/trade && docker compose exec -T paper sh -lc 'env | egrep "^(TEST_HOOKS_ENABLED|FORCE_FEATURES_INVALID_N|FORCE_CADENCE_FAIL_N|FORCE_ENTRY_SIGNAL_ONCE|FORCE_COOLDOWN_BLOCK_ONCE|FORCE_COOLDOWN_BARS|ARM_FILE|KILL_SWITCH_FILE|HALT_ORDERS_FILE|DATA_TAG|TIMEFRAME|BROKER)="'

Tail live decisions
cd ~/Projects/trade && tail -f data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv
Search proof rows
cd ~/Projects/trade && grep -n 'TEST_FORCE_ENTRY_SIGNAL_ONCE\|STOP_BLOCK\|HALT_BLOCK\|ARM_BLOCK\|DAILY_LIMIT_BLOCK\|DEGRADED_BLOCK\|COOLDOWN_BLOCK' data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv | tail -n 20
Watch proof logs
cd ~/Projects/trade && docker compose logs -f paper | egrep 'TEST: forcing entry signal once|Blocked entry at broker guard|Decision recorded|SKIP: already-processed|Latest features invalid'
Recommended operator notes

Keep runtime .env boring and deduplicated

Do not leave fault-injection knobs on after a proof

Distinguish:

orchestration/runtime blockers

submit-boundary broker blockers

repeated already-processed skips can be normal during the current in-progress candle window

do not call Mission 4 PASS until STOP/HALT/daily-limit are observed directly in decisions.csv

----
HANDOFF — 2026-03-07 — Mission 4 Enforcement + Overnight Runtime State

Mission
Finish Mission 4 — Enforcement at Submit Boundary.

Goal:
Ensure broker-facing entry safety controls are enforced at the submit boundary and recorded in decisions.csv with canonical reason codes.

Required canonical submit-boundary codes:
- STOP_BLOCK
- HALT_BLOCK
- ARM_BLOCK
- DAILY_LIMIT_BLOCK

Exits must remain allowed.

================================================================
WHY THIS MISSION MATTERS
================================================================

This is the key remaining safety-hardening gap between:
- a system that can run unattended
and
- a system that is safe enough to seriously approach real-money readiness.

The main principle is now clear:

files/broker/guarded.py must be the authoritative submit-boundary blocker.

main.py may still block for orchestration/runtime reasons like:
- degraded mode
- cooldown
- size <= 0

But broker-facing control-plane policy should not be duplicated there.

================================================================
FILES CHANGED IN THIS SESSION
================================================================

Trading-system files changed:
- files/broker/guarded.py
- files/main.py
- files/data/features.py
- files/data/storage.py

Files inspected but not changed:
- files/data/decisions.py
- files/broker/paper.py
- files/data/market.py

Other repo state still present locally and should be reviewed separately before commit:
- docker-compose.yml
- files/data/market.py
- ops/cron_heartbeat.sh
- ops/deploy_oldbox.sh
- ops/rsync_exclude.txt

Do not blindly commit unrelated ops/deploy changes with the Mission 4 batch.

================================================================
WHAT CHANGED
================================================================

1) files/broker/guarded.py

Submit-boundary broker policy was consolidated into GuardedBroker.

Current responsibilities there:
- STOP_BLOCK(...)
- HALT_BLOCK(...)
- ARM_BLOCK(...)
- DAILY_LIMIT_BLOCK(...)
- DRY_RUN_BLOCK for real-broker path
- BAD_INPUTS
- MAX_ORDER_USD_BLOCK(...)
- MAX_POSITION_USD_BLOCK(...)

Important fix:
- old HALT_ENTRY_BLOCK naming was aligned to canonical HALT_BLOCK

2) files/main.py

Removed duplicate broker-facing control-plane blocking from main.py.

main.py now keeps orchestration/runtime blocks only:
- COOLDOWN_BLOCK(...)
- DEGRADED_BLOCK(...)
- SIZE_BLOCK(...)

main.py still owns:
- market fetch / loop orchestration
- degraded-mode logic
- trailing freeze logic
- decision writing
- exit handling

Current intended split:
- main.py decides whether it wants to enter
- GuardedBroker decides whether entry may reach the inner broker

3) files/data/features.py

Hardened latest-row feature validation.

Old behavior:
- any NaN in latest feature row killed the loop

New behavior:
- execution-critical fields still fail hard
- optional derived fields warn instead of halting

This reduced brittleness, but stale test-fault env and prior degraded state still affected proof runs.

4) files/data/storage.py

Added observability for suspicious replayed adjacent OHLCV bars.

Current behavior:
- warns if adjacent rows have different timestamps but identical OHLCV payload
- does not mutate/drop rows yet
- observability-first only

================================================================
WHAT WAS PROVEN
================================================================

Proven in decisions.csv:
- ARM_BLOCK(...)
- DEGRADED_BLOCK(...)
- COOLDOWN_BLOCK(...)
- MAX_ORDER_USD_BLOCK(...)

Observed forced-entry proof rows with:
- entry_should_enter=True
- entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE

This proves:
- forced-entry hook works
- fresh eligible bar path works
- decision writing works
- blocked entry reasons are landing in entry_blocked_reason
- submit-boundary blocking flow is functioning for real entry attempts

Overnight healthy-loop evidence:
paper container repeatedly showed:
- Fetched market data
- Persisted bars
- Decision recorded on fresh closed bars
- SKIP: already-processed bar (restart-safe idempotency) during already-seen/in-progress windows

That is expected and healthy behavior.

================================================================
WHAT IS NOT FULLY PROVEN YET
================================================================

Still not directly observed in decisions.csv during this mission:
- STOP_BLOCK(...)
- HALT_BLOCK(...)
- DAILY_LIMIT_BLOCK(...)
- exits still allowed under STOP/HALT

This is the remaining proof gap.

Important nuance:
This is not because the submit-boundary architecture failed.

It is because proof attempts were intercepted earlier by higher-precedence runtime/orchestration blockers during testing:
- COOLDOWN_BLOCK(...)
- then DEGRADED_BLOCK(...)

So STOP/HALT were not reached on those specific proof attempts.

================================================================
MAIN BLOCKER TO FULL MISSION 4 PASS
================================================================

The remaining blocker is proof completion, not architecture.

During deterministic proof attempts, fresh forced-entry rows were blocked by:
- COOLDOWN_BLOCK(remaining=3)
and later by:
- DEGRADED_BLOCK(features_invalid_x4_in_last6)
- DEGRADED_BLOCK(features_invalid_x5_in_last6)

Therefore:
STOP/HALT proof did not fail due to GuardedBroker.
STOP/HALT proof did not land because runtime-state precedence intercepted entry first.

================================================================
IMPORTANT RUNTIME FINDINGS
================================================================

1) .env had stale test-fault settings

A major source of confusion during proofing was dirty runtime env.
Found earlier in .env:
- FORCE_FEATURES_INVALID_N=2
- duplicate TEST_HOOKS_ENABLED
- duplicate FORCE_ENTRY_SIGNAL_ONCE

This intentionally poisoned features until cleaned.

The fix was to overwrite .env with a single boring source of truth.

2) Repeated SKIP: already-processed bar was not a bug

This was expected behavior when:
- latest fetched bar was still the in-progress candle
- main.py dropped the in-progress last bar
- newest eligible closed bar was already present in decisions.csv

So repeated skip behavior during a live 5m window can be normal and safe.

3) Overnight run showed healthy stabilization

By the overnight check:
- no recurring features_invalid churn in the active runtime tail
- no replay warning fired from storage.py
- loop showed normal cadence and stable decision writing
- system now behaves much more like an operationally boring service

4) Submit-boundary MAX_ORDER_USD proof appeared naturally

Overnight decisions.csv contained repeated rows like:
- MAX_ORDER_USD_BLOCK(order_usd=50.00 cap=25.00)

This is strong evidence that:
- strategy wanted to enter
- main.py called broker.open_position(...)
- GuardedBroker blocked at submit boundary
- the returned reason landed correctly in decisions.csv

This is a very important proof of architecture correctness.

================================================================
CURRENT RUNTIME TRUTH
================================================================

At the end of this session / overnight run:
- Mission 4 architecture is much cleaner than before
- GuardedBroker now owns broker-facing submit-boundary policy
- main.py is cleaner and no longer duplicates STOP/HALT/ARM/daily-limit entry policy
- runtime env is cleaner and less polluted by old fault-injection state
- overnight loop behavior looks healthy
- submit-boundary reasons are definitely landing in decisions.csv
- remaining work is mainly proof matrix completion, not structural redesign

================================================================
UPDATED MATURITY SNAPSHOT
================================================================

Trading system

Self-running unattended system readiness:
~93–94%

Why:
- loop runs continuously
- docker/systemd/runtime behavior is stable
- observability chain works
- healthy overnight cadence observed
- restart-safe idempotency works

Safe-to-connect-real-money readiness:
~69–72%

Why it improved:
- submit-boundary architecture is cleaner
- ARM_BLOCK proved
- MAX_ORDER_USD_BLOCK proved
- overnight operation looked healthy
- runtime env/test pollution issue was identified and corrected

Why it is not higher:
- STOP_BLOCK / HALT_BLOCK / DAILY_LIMIT_BLOCK still need explicit proof
- exits-under-STOP/HALT still need explicit proof
- there is still some proof debt around the control-plane matrix

Mission 4 specifically

Architecture completion:
~92–94%

Proof completion:
~68–72%

Why:
- multiple real block reasons are proven in decisions.csv
- but the exact canonical control-plane proof set is still incomplete

Repo RAG Assistant

Useful/trustworthy teammate readiness:
~84–89%

Strong:
- refusal discipline
- source cleanliness
- eval stability
- operator usefulness

Still weaker:
- multi-hop trace capability

================================================================
SUGGESTED PASS CONDITION FOR MISSION 4
================================================================

Mission 4 should be marked PASS only when all of the following are explicitly observed:

1) ARM_BLOCK(...) observed in entry_blocked_reason
2) STOP_BLOCK(...) observed in entry_blocked_reason
3) HALT_BLOCK(...) observed in entry_blocked_reason
4) DAILY_LIMIT_BLOCK(...) observed in entry_blocked_reason
5) exits remain allowed under STOP/HALT
6) no broker-facing STOP/HALT/ARM/daily-limit entry policy remains duplicated in main.py

Current status:
- item 1 is proven
- item 6 is effectively proven by file inspection/change
- items 2–5 still need explicit proof

================================================================
BEST NEXT MISSION
================================================================

Complete the remaining proof matrix for Mission 4.

Recommended order:

1) STOP_BLOCK proof
- ensure degraded mode is not active
- keep TEST_HOOKS_ENABLED=1
- set FORCE_ENTRY_SIGNAL_ONCE=1
- create STOP file
- ensure HALT absent
- recreate paper
- capture next fresh eligible decision row

Expected proof row:
- entry_should_enter=True
- entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE
- entry_blocked_reason=STOP_BLOCK(...)

2) HALT_BLOCK proof
- remove STOP
- create HALT
- keep FORCE_ENTRY_SIGNAL_ONCE=1
- recreate paper
- capture next fresh eligible decision row

Expected:
- entry_blocked_reason=HALT_BLOCK(...)

3) DAILY_LIMIT_BLOCK proof
- set deterministic low daily limit
- trigger one qualifying trade/day state
- attempt another entry
- capture daily-limit block in decisions.csv

Expected:
- entry_blocked_reason=DAILY_LIMIT_BLOCK(...)

4) Exit-under-STOP/HALT proof
- force or wait for open position
- activate STOP or HALT
- confirm exit path still functions
- confirm no new entry allowed

================================================================
USEFUL COMMANDS
================================================================

Check runtime env inside paper:
cd ~/Projects/trade && docker compose exec -T paper sh -lc 'env | egrep "^(TEST_HOOKS_ENABLED|FORCE_FEATURES_INVALID_N|FORCE_CADENCE_FAIL_N|FORCE_ENTRY_SIGNAL_ONCE|FORCE_COOLDOWN_BLOCK_ONCE|FORCE_COOLDOWN_BARS|ARM_FILE|KILL_SWITCH_FILE|HALT_ORDERS_FILE|DATA_TAG|TIMEFRAME|BROKER)="'

Tail live decisions:
cd ~/Projects/trade && tail -f data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv

Search proof rows:
cd ~/Projects/trade && grep -n 'TEST_FORCE_ENTRY_SIGNAL_ONCE\|STOP_BLOCK\|HALT_BLOCK\|ARM_BLOCK\|DAILY_LIMIT_BLOCK\|DEGRADED_BLOCK\|COOLDOWN_BLOCK\|MAX_ORDER_USD_BLOCK' data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv | tail -n 30

Watch proof logs:
cd ~/Projects/trade && docker compose logs -f paper | egrep 'TEST: forcing entry signal once|Blocked entry at broker guard|Decision recorded|SKIP: already-processed|Latest features invalid'

================================================================
OPERATOR NOTES
================================================================

- Keep runtime .env boring and deduplicated
- Do not leave fault-injection knobs on after proofs
- Distinguish:
  - orchestration/runtime blockers
  - submit-boundary broker blockers
- repeated already-processed skips can be normal during the current in-progress candle window
- do not mark Mission 4 PASS until STOP/HALT/daily-limit/exits-under-halt are explicitly observed

================================================================
HONEST SUMMARY
================================================================

This session made real progress.

The architecture is better.
The submit-boundary model is cleaner.
The overnight loop looked healthy.
The proof plumbing works.
Real submit-boundary block reasons are landing in decisions.csv.

But Mission 4 is not fully closed yet.

Best current label:

Mission 4 — strong progress, healthy overnight runtime, partial proof complete, explicit STOP/HALT/DAILY_LIMIT and exit-under-halt proofs still pendin:> [!WARNING]

=================================================================

HANDOFF — 2026-03-08 — Mission 4 PASS + Mission 5A PASS + Next Mission

================================================================
MISSION STATUS
================================================================

Mission 4
PASS

Mission 5A
PASS

Current overall state:
- submit-boundary entry matrix proven
- STOP semantics proven during a live position
- realistic paper runtime proven with natural entries, holds, trailing, exits, and trade recording
- next work should move from semantics proofing into runtime quality / safety re-balancing / performance truth

================================================================
EXECUTIVE SUMMARY
================================================================

This cycle closed Mission 4 for real.

We proved from old-box runtime evidence that:
- STOP blocks new entries
- STOP freezes trailing during a live open position
- the live open position can still exit and record a trade while STOP is present

We also proved Mission 5A:
- the system can run in a realistic paper configuration
- natural positions can open without proof hooks
- positions can hold across bars
- trailing ratchets in normal runtime
- exits are recorded cleanly
- old-box runtime truth matches intended configuration

This is a major step up in system honesty.

We are no longer mainly asking:
- “are the guardrails wired?”
We are now mainly asking:
- “how well does the system behave in realistic paper runtime?”
- “what should be tuned next without breaking the proven semantics?”

================================================================
CURRENT TRUTH
================================================================

Repo / runtime discipline

Re-confirmed:
- local repo truth is not enough
- old-box runtime truth is what counts

For any serious claim, verify all four:
1) file truth
2) deploy truth
3) container env truth
4) runtime-state truth

Current architecture / ownership

- files/main.py owns orchestration/runtime behavior
- files/broker/guarded.py owns submit-boundary entry blocking
- PaperBroker handles paper position lifecycle
- operator flag files affect runtime immediately through mounted flags dir

Current proven submit-boundary blockers:
- ARM_BLOCK(...)
- STOP_BLOCK(...)
- HALT_BLOCK(...)
- DAILY_LIMIT_BLOCK(...)
- MAX_ORDER_USD_BLOCK(...)
- MAX_POSITION_USD_BLOCK(...)

Current runtime behavior:
- STOP/HALT block entries at submit boundary
- exits still go through realize_and_close(...)
- trailing freezes under STOP/HALT in main.py
- proof hooks exist but are now OFF in Mission 5A runtime

================================================================
WHAT WE PROVED THIS CYCLE
================================================================

A) Mission 5A realistic paper runtime proof

Runtime config was moved out of proof-junk mode and into realistic paper mode:
- proof hooks OFF
- MAX_ORDER_USD raised
- MAX_POSITION_USD raised
- daily loss guard kept on
- ARM active
- STOP/HALT absent during normal observation
- current runtime env confirmed inside running paper container

Observed from real runtime:
- natural entries occurred
- positions held across multiple 5m bars
- trailing stop updated with trail_reason=ratchet
- exits were recorded as trades
- repeated real paper activity occurred without proof hooks
- no degraded/cadence/features noise interfered

Mission 5A result:
PASS

B) Mission 4 final remainder proof

Goal:
prove that under STOP during a live position:
- trailing freezes
- new entries are blocked
- open position can still close and record a trade

A dedicated proof runner was created:
- ops/mission4_stop_exit_proof.sh

What it did:
1) wait for a live open position
2) create STOP automatically at the correct time
3) hold STOP in place during the live position
4) capture decision rows, logs, and trades
5) remove STOP after proof capture

Observed runtime evidence:

1. Entry blocked under STOP
Observed in decisions.csv:
- entry_should_enter=True
- entry_reason=trend_down_and_confident
- entry_blocked_reason=STOP_BLOCK(kill_switch=/home/kk7wus/trade_flags/STOP)

Examples captured:
- 2026-03-08T16:40:00+00:00
- 2026-03-08T16:45:00+00:00
- 2026-03-08T16:50:00+00:00
- 2026-03-08T16:55:00+00:00
- 2026-03-08T17:00:00+00:00
- 2026-03-08T18:45:00+00:00

2. Trailing froze under STOP during a live open position
Observed in decisions.csv for live SHORT position:
- trail_reason=halted_freeze_trailing(STOP_BLOCK(kill_switch=/home/kk7wus/trade_flags/STOP))

Also observed:
- position_stop_price remained fixed at 67041.87056700776 across multiple bars
- position remained open while STOP was present
- loop continued writing decision rows

Captured examples:
- 2026-03-08T18:55:00+00:00
- 2026-03-08T19:00:00+00:00
- 2026-03-08T19:05:00+00:00
- 2026-03-08T19:10:00+00:00
- 2026-03-08T19:15:00+00:00

3. Exit still completed under STOP
Observed:
- live SHORT position remained open under STOP
- exit_should_exit=True with exit_reason=stop_hit while STOP still present
- trade was recorded
- trades.csv captured:
  entry_ts_ms=1772996100000
  exit_ts_ms=1772997300000
  side=SHORT
  qty=0.01
  entry_price=66830.24
  exit_price=67041.87056700776
  reason=stop_hit

Log evidence also showed:
- Trade recorded

Mission 4 final remainder result:
PASS

================================================================
STRONGEST EVIDENCE TO REMEMBER
================================================================

From decisions.csv:
- STOP_BLOCK(...) rows exist for attempted fresh entries
- halted_freeze_trailing(STOP_BLOCK(...)) rows exist during live position
- exit_should_exit=True and exit_reason=stop_hit occurred while STOP remained present

From trades.csv:
- the STOP-window live SHORT did close and record correctly

From proof runner lifecycle:
- STOP was created automatically only after live position appeared
- STOP was removed automatically after proof capture
- proof packet saved at:
  /home/kk7wus/Projects/trade/ops/proofs/mission4_stop_exit_20260308T185914Z.log

================================================================
IMPORTANT FILES NOW IN PLAY
================================================================

Core runtime files
- files/main.py
- files/broker/guarded.py
- files/config.py
- ops/daily_limits_check.py

Proof tooling
- ops/mission4_stop_exit_proof.sh

Compose/runtime
- docker-compose.yml
- .env

Evidence locations
- data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv
- data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv
- ops/proofs/mission4_stop_exit_20260308T185914Z.log

================================================================
CURRENT MISSION 5A CONFIG TRUTH
================================================================

Mission 5A runtime mode was confirmed inside the running paper container:

- DATA_TAG=paper_oldbox_live
- SYMBOL=BTC/USD
- TIMEFRAME=5m
- BROKER=paper
- DRY_RUN=1
- COOLDOWN_BARS=1
- MAX_ORDER_SIZE=0.01
- MAX_ORDER_USD=1000
- MAX_POSITION_USD=1000
- MAX_TRADES_PER_DAY=0
- MAX_DAILY_LOSS_USD=25
- TEST_HOOKS_ENABLED=0
- FORCE_ENTRY_SIGNAL_ONCE=0
- FORCE_EXIT_SIGNAL_ONCE=0
- FORCE_COOLDOWN_BLOCK_ONCE=0
- FORCE_COOLDOWN_BARS=0
- FORCE_FEATURES_INVALID_N=0
- FORCE_CADENCE_FAIL_N=0
- BYPASS_FEATURE_VALIDATION=0
- ARM_FILE=/home/kk7wus/trade_flags/ARM
- KILL_SWITCH_FILE=/home/kk7wus/trade_flags/STOP
- HALT_ORDERS_FILE=/home/kk7wus/trade_flags/HALT
- TZ_LOCAL=America/Los_Angeles

Flags truth during normal runtime:
- ARM exists
- STOP absent except when intentionally used for proof
- HALT absent except when intentionally used for proof

================================================================
MAIN PITFALLS WE HIT
================================================================

1) Local truth != old-box truth
Still the biggest source of false confidence.

2) Proof timing matters
For STOP live-position proof, order matters:
- live position exists
- apply STOP
- observe freeze + exit
Not:
- apply STOP while flat
- hope later evidence still means the same thing

3) Manual proof timing is noisy
A dedicated proof runner was much better than human polling.

4) Historical decision rows can confuse current truth
Old proof rows stayed in decisions.csv, so always anchor to timestamps and current runtime state.

5) Safety semantics proof and strategy quality proof are different
The system can be semantically correct and still perform poorly.
Do not confuse those categories.

================================================================
WORKING CONTRACT — HOW WE WORK
================================================================

Purpose

We work in a way that is:
- safe
- grounded
- reproducible
- proof-driven
- low-noise

Core rules

1) One mission at a time
Stay on one mission until:
- proven
- cleanly blocked
- or intentionally parked

2) File-first discipline
Before proposing changes, identify the exact file(s).

3) Full-file replacements preferred
Avoid speculative patch fragments when possible.

4) Old-box runtime truth wins
Never trust local assumptions over running truth.

5) Proof over theory
A change is not done because it sounds right.
It is done when runtime evidence proves it.

6) Honest labels only
Use:
- PASS
- partial proof
- blocked
- failed
- deferred remainder

7) Clean proof state
When a proof is done, clean:
- STOP / HALT / ARM test state
- .env proof knobs
- seeded test data if used

8) Prefer proof tools over manual babysitting
If timing sensitivity is high, create a dedicated proof runner instead of relying on human polling.

================================================================
USEFUL COMMANDS
================================================================

Runtime env truth
cd ~/Projects/trade && docker compose exec -T paper sh -lc 'env | egrep "^(DATA_TAG|SYMBOL|TIMEFRAME|DRY_RUN|BROKER|COOLDOWN_BARS|MAX_ORDER_SIZE|MAX_ORDER_USD|MAX_POSITION_USD|MAX_TRADES_PER_DAY|MAX_DAILY_LOSS_USD|TEST_HOOKS_ENABLED|FORCE_ENTRY_SIGNAL_ONCE|FORCE_EXIT_SIGNAL_ONCE|FORCE_COOLDOWN_BLOCK_ONCE|FORCE_COOLDOWN_BARS|FORCE_FEATURES_INVALID_N|FORCE_CADENCE_FAIL_N|BYPASS_FEATURE_VALIDATION|ARM_FILE|KILL_SWITCH_FILE|HALT_ORDERS_FILE|TZ_LOCAL)="'

Latest decisions
cd ~/Projects/trade && tail -n 40 data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv

Latest trades
cd ~/Projects/trade && tail -n 20 data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv

Recent paper events
cd ~/Projects/trade && docker compose logs --since=12h paper | egrep 'Opened paper position|Updated stop|Trade recorded|Closed paper position|Blocked entry at broker guard|DEGRADED|Cadence check failed|Latest features invalid'

Proof log tail
cd ~/Projects/trade && tail -n 120 ops/proofs/mission4_stop_exit_20260308T185914Z.log

Run Mission 4 STOP/exit proof tool again
cd ~/Projects/trade && ./ops/mission4_stop_exit_proof.sh

Deploy to old-box safely
cd ~/Projects/trade && OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh

Important deploy note
Do not use:
- OLD_BOX_DIR=~/Projects/trade
Use:
- OLD_BOX_DIR=/home/kk7wus/Projects/trade

================================================================
RECOMMENDED STATUS LABEL NOW
================================================================

Mission 4
PASS

Expanded label:
- submit-boundary entry matrix proven
- STOP during live position freezes trailing
- STOP blocks fresh entries
- open position can still exit and record under STOP
- proven from old-box runtime evidence

Mission 5A
PASS

Expanded label:
- realistic paper runtime observed
- natural open / hold / trail / exit cycle(s) observed
- proof hooks off
- rails still active

================================================================
NEXT MISSION
================================================================

Mission 5B — Runtime Quality, Safety Re-Balancing, and Honest Paper Performance

Goal

Move from “semantics are proven” into:
- how well the system behaves in realistic paper runtime
- whether current sizing / stops / trailing / filters are sensible
- how to rebalance safety caps now that proof mode is over
- what the real next bottleneck is: strategy quality, runtime safety, or observability

Why this is the right next mission

- Mission 4 is now closed
- Mission 5A proved realistic runtime operation
- the next unanswered questions are quality questions, not wiring questions
- current paper trades show repeated stop_hit exits and cumulative drawdown
- now is the right time to analyze behavior honestly before changing architecture again

Mission 5B suggested targets

1) Quantify paper runtime performance
Look at:
- win/loss count
- average pnl
- cumulative pnl
- average hold duration
- stop_hit frequency
- time_stop frequency
- LONG vs SHORT behavior
- behavior by market_reason / trend / volatility

2) Assess whether current safety caps are still appropriate
Now that 0.01 positions are real:
- is MAX_DAILY_LOSS_USD=25 right?
- should MAX_TRADES_PER_DAY remain 0 or be restored to a real cap?
- should MAX_POSITION_USD stay at 1000 or be reduced to a more boring paper cap?

3) Inspect strategy/runtime quality
Questions:
- are entries too frequent or too weak?
- is trailing too tight?
- are many exits just noise-stop losses?
- is cooldown too permissive?
- are filter conditions admitting poor setups?

4) Improve observability if needed
Possible next improvements:
- better dashboard visibility for current position lifecycle
- clearer logging around open/close/trail/blocked events
- small summary scripts for paper performance truth

5) Only after the above, decide whether repo changes are needed
Do not jump into code surgery until paper-runtime truth says what actually hurts.

Suggested first moves for Mission 5B

1. Build a simple runtime-performance summary from trades.csv
2. Quantify what the current paper configuration actually did overnight
3. Decide whether next step is:
   - performance analysis script
   - dashboard/operator summary improvement
   - cap rebalance
   - strategy tuning

================================================================
HONEST SUMMARY
================================================================

This was a high-value cycle.

We did not just “test things.”
We turned ambiguous behavior into proven runtime truth.

What we now know for real:
- submit-boundary guard semantics are real
- STOP behavior is proven during a live open position
- realistic paper runtime works without proof hooks
- the system can naturally open, hold, trail, and exit
- the next dragon is no longer semantics; it is runtime quality and performance truth

Best current summary:

Mission 4 is closed.
Mission 5A is passed.
Next mission should be Mission 5B:
runtime quality, safety re-balancing, and honest paper-performance analysis.


===
SIDE HANDOFF — STRATEGY LAB EXPERIMENT — 2026-03-09

PURPOSE

This sub-handoff tracks the notebook-based strategy experiment work.
It is not the canonical runtime/system handoff.
It is the research handoff for understanding strategy behavior before repo changes.

CURRENT NOTEBOOK

Notebook file:
data/notebooks/strategy_lab_experiment_01.ipynb

Notebook state verified:
- notebook exists
- notebook runs
- imports work
- features compute correctly
- current workflow is usable

Important workflow note:
- notebook output copy/paste had been a problem
- user later found a way to copy/paste
- export-to-text helper also exists in notebook and still remains useful

CURRENT NOTEBOOK STRUCTURE

Verified sections:
- strategy notes markdown
- first notebook goals markdown
- 0 imports
- 1 exports
- 2 existence check
- 3 list raw partitions
- 4 raw coverage summary
- 5 load raw bars
- 6 raw bars summary
- 7 schema and nulls
- 8 load decisions
- 9 decisions summary
- 10 load trades
- 11 trades summary
- 12 last trades
- 13 compute features from raw bars
- 14 features summary
- 15 feature distributions
- 16 classify market state
- 17 market state counts
- 18 merge trades with nearest feature/state at entry time
- 19 inspect losing trades in context
- 20 regime table
- 21 MFE/MAE table
- 22 MFE/MAE summary by side and outcome
- 23 SHORT loss filter audit
- 24 SHORT filter variant audit
- 25 ALL vs LONG_ONLY vs LONG+filtered_SHORT comparison

DATA STATUS

Raw bar data:
- tag: paper_oldbox_live
- symbol: BTC_USD
- timeframe: 5m
- raw partitions present for 17 days
- date span includes:
  2026-02-09 through 2026-03-09
- raw feature rows observed:
  about 3608

Processed runtime data:
- decisions.csv present
- trades.csv present

This is enough for:
- exploratory analysis
- side/regime analysis
- first controlled notebook experiments

This is not yet enough for:
- high-confidence broad optimization
- trusting large parameter sweeps
- claiming robustness

KEY VERIFIED FINDINGS

1) Overall strategy is losing
From notebook trades summary:
- trades: 41
- wins: 9
- losses: 32
- total_pnl_usd: -63.26
- avg_pnl_usd: -1.54

2) SHORT is much worse than LONG
Side summary:
- SHORT
  trades: 19
  wins: 2
  losses: 17
  pnl_usd: -41.57
  avg_pnl_usd: -2.19
  win_rate: 10.53%

- LONG
  trades: 22
  wins: 7
  losses: 15
  pnl_usd: -21.70
  avg_pnl_usd: -0.99
  win_rate: 31.82%

Conclusion:
- both sides lose
- SHORT is the bigger problem by far

3) Worst regime is SHORT in down regimes, especially high volatility
Side by regime findings:
- SHORT + down + normal is the biggest total damage bucket
- SHORT + down + high is the worst average-loss bucket

Conclusion:
- SHORT is not just weak in general
- it is especially damaging in the exact conditions where it was expected to help

4) MFE / MAE analysis says SHORT is mainly an entry problem
MFE/MAE summary:
- SHORT losses:
  avg_mfe_atr about 0.75
  med_mfe_atr about 0.51
  avg_mae_atr about 1.63
  med_mae_atr about 1.54

Interpretation:
- losing SHORT trades do not move enough in the favorable direction
- they move against the position too quickly and too strongly
- this argues against widening SHORT stops first
- this supports the idea that SHORT entries are poor or late

5) SHORT loss audit found two failure modes
SHORT loss clusters:
A) oversold late-entry shorts
- RSI < 30
- negative ema_slow_slope
- likely shorting into exhausted downside

B) suspicious counter-trend shorts
- RSI >= 50
- positive ema_slow_slope
- likely shorting while slow trend context is still rising

Conclusion:
- SHORT failure is not a single issue
- there are at least two bad entry patterns

6) Simple SHORT filters helped but did not save SHORT
Filter tests:
- ema_slow_slope < 0 helped
- RSI > 35 helped a bit
- combined filter helped the most among tested variants
- but all filtered SHORT variants remained negative

Conclusion:
- filtering removes garbage
- but the remaining SHORT trades still do not show enough edge

7) Final comparison confirmed LONG_ONLY is cleaner than LONG + filtered SHORT
Portfolio comparison:
- ALL: -63.26
- LONG_ONLY: -21.70
- LONG + filtered SHORT: -34.35

Conclusion:
- filtered SHORT is less bad than raw SHORT
- filtered SHORT still makes portfolio worse than LONG_ONLY
- LONG_ONLY is the current clean baseline

MAIN RESEARCH CONCLUSION

SHORT should be quarantined.

Not because we dislike SHORT in theory,
but because current notebook evidence says:

- raw SHORT is bad
- filtered SHORT is still bad
- SHORT does not currently earn its place
- LONG_ONLY is the better baseline for the next phase

RECOMMENDED REPO DIRECTION

Do not widen SHORT stops first.

Preferred next repo change:
- disable SHORT explicitly
- keep LONG enabled
- do it in a configurable and observable way
- avoid silent hidden behavior if possible
- preserve honest blocked/disabled reasoning in decisions or logs if feasible

BEST NEXT RESEARCH DIRECTION AFTER QUARANTINE

Move into LONG calibration.

Priority questions:
1) Why do LONG winners reach large MFE but total LONG performance is still negative?
2) Is trailing giving back too much?
3) Is confidence threshold too low even for LONG?
4) Do LONG losses cluster in specific volatility or volume contexts?

WORKING PRINCIPLES RECONFIRMED

- do not change repo logic before notebook evidence is strong enough
- isolate one failure mode at a time
- prefer explicit conclusions over vague optimism
- quarantine failing subsystems rather than endlessly tweaking them
- keep the strategy lab notebook as the current research notebook
- do not split into a new notebook yet unless this one becomes crowded

NEXT INTENDED STEP

After repo change to quarantine SHORT:
- run paper as LONG_ONLY baseline
- measure honestly
- then begin LONG-side calibration work
===
GENERAL HANDOFF — 2026-03-09 — MISSION 5B STRATEGY LAB UPDATE

CURRENT BIG PICTURE

System work has shifted from semantics proofing into strategy quality.

Already proven from earlier mission work:
- Mission 4 PASS
- Mission 5A PASS
- submit-boundary entry matrix proven
- STOP semantics proven during live position
- realistic paper runtime proven
- runtime observability and proof discipline improved

What changed in this cycle:
- we started serious notebook-based strategy analysis
- we stopped guessing from tails
- we moved into data-backed regime / side / MFE-MAE analysis

CURRENT STATUS

Runtime / system side:
- infrastructure and semantics remain in a good place
- paper runtime is still operating
- notebook storage under data/notebooks is working
- strategy lab notebook is now in active use

Research side:
- current notebook:
  data/notebooks/strategy_lab_experiment_01.ipynb
- notebook state verified and usable
- enough raw and processed data exists for exploratory work

MOST IMPORTANT NEW FINDING

SHORT is currently a liability.

This is not just a feeling.
Notebook evidence now supports it from multiple angles:

- side summary
- regime summary
- MFE/MAE
- SHORT loss filter audit
- filtered SHORT vs LONG_ONLY comparison

KEY STRATEGY FINDINGS

1) Strategy is losing overall
Current observed notebook summary:
- trades: 41
- wins: 9
- losses: 32
- total pnl: -63.26 USD
- avg pnl per trade: -1.54 USD

2) SHORT is much worse than LONG
- SHORT:
  19 trades
  2 wins
  17 losses
  -41.57 USD
  avg -2.19 USD/trade
- LONG:
  22 trades
  7 wins
  15 losses
  -21.70 USD
  avg -0.99 USD/trade

3) Worst strategy zone is SHORT in down regimes
Especially:
- SHORT + down + normal
- SHORT + down + high

4) MFE/MAE says SHORT is mainly an entry problem
SHORT losers:
- do not go far enough in favorable direction
- move against the trade too quickly
- widening stops would likely subsidize bad entries

5) Two distinct SHORT failure modes exist
A) late oversold shorts
B) suspicious counter-trend shorts

6) Filtering helped but did not rescue SHORT
Trend-confirmed / RSI-filtered SHORT is still negative

7) LONG_ONLY beats LONG + filtered SHORT
This is the final operationally important comparison.
Filtered SHORT still drags the portfolio below LONG_ONLY.

CURRENT BEST CONCLUSION

The cleanest next baseline is LONG_ONLY.

SHORT should be quarantined.

This is not a final philosophical claim about all SHORT logic forever.
It is the correct operational claim for the current system and current evidence.

RECOMMENDED NEXT REPO CHANGE

Make a minimal repo change to disable SHORT.

Preferred style:
- configurable
- explicit
- observable
- not a hidden silent hack if avoidable

Rationale:
- notebook evidence is now strong enough
- LONG_ONLY is the better baseline
- this reduces strategy complexity and focuses the next phase

WHAT NOT TO DO NEXT

- do not broaden optimization yet
- do not widen SHORT stops first
- do not try to rescue SHORT in production logic immediately
- do not start a new notebook unless needed
- do not bury this conclusion under future side quests

NEXT PHASE AFTER SHORT QUARANTINE

Mission direction:
LONG calibration

Key questions:
- why does LONG still lose overall despite good MFE on winners?
- is trailing giving back too much?
- should LONG confidence threshold be increased?
- do LONG losses cluster in specific volatility or volume conditions?
- can LONG_ONLY be moved from slightly negative toward break-even or positive?

CURRENT RESEARCH NOTEBOOK

Notebook:
data/notebooks/strategy_lab_experiment_01.ipynb

Verified contents include:
- raw data coverage
- trade summary
- feature distributions
- regime table
- side summary
- portfolio comparison
- MFE/MAE table
- MFE/MAE by side/outcome
- SHORT loss filter audit
- SHORT filter variant audit
- LONG_ONLY vs LONG+filtered_SHORT comparison

WORKING CONTRACT RECONFIRMED

- one mission at a time
- no guessing on notebook state
- no pretending we know what was not verified
- no repo changes before enough evidence exists
- prefer explicit, boring, observable changes
- step by step

HONEST CURRENT LABEL

Mission 5B strategy lab:
IN PROGRESS

Sub-status:
- analysis phase produced a decisive finding
- SHORT quarantine now has evidence support
- next meaningful move is repo change to establish LONG_ONLY baseline

===
MISSION LIST — NEXT ORDER

MISSION 5B.1
Quarantine SHORT in repo logic

Goal:
- establish LONG_ONLY as the new clean runtime baseline

Definition of done:
- SHORT entries are explicitly disabled
- LONG still functions normally
- behavior is configurable and observable
- runtime truth on old-box confirms new behavior

Notes:
- keep this change small
- do not mix with unrelated tuning

MISSION 5B.2
Run LONG_ONLY paper baseline

Goal:
- collect honest runtime behavior with SHORT removed

Definition of done:
- paper runtime observed under LONG_ONLY
- decisions/trades confirm only LONG entries
- new runtime snapshot captured
- new trade summary produced

MISSION 5B.3
Analyze LONG_ONLY quality

Goal:
- understand why LONG still loses overall
- isolate whether the main issue is entry selectivity, trailing, or regime mismatch

Key questions:
- what do LONG winners vs LONG losers look like?
- how much MFE is being given back?
- do LONG losses cluster by volatility, rsi, vol_z, or dollar_vol_z?
- is confidence threshold too permissive?

Definition of done:
- notebook analysis produces clear LONG-side findings
- one dominant LONG calibration hypothesis is selected

MISSION 5B.4
Choose first LONG calibration experiment

Preferred small candidates:
- raise LONG confidence threshold
- improve LONG trailing behavior
- test a simple LONG regime filter if evidence supports it

Definition of done:
- one change only
- notebook evidence justifies it
- exact file(s) identified before change

MISSION 5B.5
Apply one repo change for LONG calibration

Goal:
- implement only the chosen LONG-side change

Definition of done:
- local file truth verified
- deploy safely to old-box
- runtime truth verified
- new baseline observation starts

PARKED / DEFERRED

SHORT redesign
Status:
- deferred / quarantined

Reason:
- current evidence says SHORT does not earn its place yet
- revisit only after LONG baseline is understood

Broad parameter sweeps
Status:
- deferred

Reason:
- current data is enough for exploratory work, not broad-trust optimization

Notebook split into second notebook
Status:
- deferred

Reason:
- current notebook is still usable
- no need to fragment context yet

NON-NEGOTIABLE RULES FOR NEXT MISSIONS

- step by step
- know the exact file before proposing change
- no broad multi-change surgery
- verify old-box runtime truth
- do not hide logic silently if observability can be preserved
- keep conclusions honest
===

GENERAL HANDOFF — 2026-03-10 — MISSION 5B.2 LONG_ONLY BASELINE

CURRENT BIG PICTURE

System work is in a solid state, and strategy work has now crossed an important boundary:

SHORT has been quarantined in live runtime.

We are no longer debating whether SHORT is harmful in the current system.
That was decided by notebook evidence and then promoted into repo + runtime truth.

We are now entering the next clean phase:
observe and measure LONG_ONLY honestly before making further strategy changes.

WHAT IS ALREADY PROVEN

System / runtime proofs already established from earlier missions:
- Mission 4 PASS
- Mission 5A PASS
- submit-boundary entry matrix proven
- STOP semantics proven during live position
- realistic paper runtime proven
- restart-safe idempotency proven
- runtime observability improved
- notebook workflow established under data/notebooks

Strategy / research conclusions already established:
- overall strategy is losing
- LONG loses less than SHORT
- SHORT is the larger liability
- filtered SHORT still underperforms LONG_ONLY
- LONG_ONLY is the current cleaner baseline

MISSION 5B.1 — STATUS

PASS

What was done:
- exact side-control file identified: files/strategy/rules.py
- minimal repo change applied
- SHORT explicitly disabled via side enable flags
- LONG behavior left untouched
- no hidden threshold hack used
- no SHORT code deleted

Runtime proof:
- old-box file truth verified
- container/runtime truth verified
- mission proof script created:
  ops/mission5b1_short_quarantine_check.sh

Observed runtime evidence:
- repeated post-cutoff rows in decisions.csv show:
  should_enter=False
  side=SHORT
  reason=trend_down_but_short_disabled

Meaning:
- runtime still detects short-type opportunities
- policy explicitly blocks them
- observability is preserved
- SHORT has lost runtime privileges

CURRENT RUNTIME STATE

old-box services:
- paper up
- trade up
- dashboard up

Current runtime behavior:
- paper loop healthy
- decisions continue recording
- restart-safe idempotency still normal
- repeated SHORT-disabled evidence observed overnight

Canonical proof command for Mission 5B.1:
./ops/mission5b1_short_quarantine_check.sh 2026-03-09T20:51:00+00:00

CURRENT STRATEGY STATE

Active baseline:
- LONG_ONLY in runtime practice
- SHORT quarantined

Important note:
- this does NOT prove LONG is good
- this only proves SHORT is currently not allowed to degrade the portfolio further

We now need honest observation of LONG-only runtime behavior before any more repo strategy changes.

MISSION 5B.2 — CURRENT MISSION

Run LONG_ONLY paper baseline

Goal:
- observe runtime behavior with SHORT removed
- confirm new entries/trades are effectively LONG-only
- collect a cleaner baseline for the next round of notebook analysis

Definition of done:
- enough fresh runtime collected under SHORT quarantine
- no evidence of live SHORT entries after cutoff
- updated trades/decisions snapshot captured
- fresh trade summary available for LONG_ONLY baseline window

WHAT NOT TO DO YET

- do not re-enable SHORT
- do not tune LONG threshold yet
- do not change trailing yet
- do not widen stops
- do not mix in new strategy surgery before baseline observation is captured
- do not start broad optimization
- do not split notebooks unless needed

NEXT ANALYSIS DIRECTION AFTER BASELINE WINDOW

Mission 5B.3:
Analyze LONG_ONLY quality

Key questions:
- why does LONG still lose overall?
- are LONG entries too permissive?
- is trailing giving back too much MFE?
- do LONG losses cluster in certain volatility / volume / RSI conditions?
- is one simple LONG-side calibration hypothesis stronger than the others?

Best candidate categories later:
- raise LONG confidence threshold
- improve LONG trailing behavior
- add a simple LONG regime filter only if notebook evidence supports it

MISSION SCRIPT NOTE

Mission-scoped scripts are now considered valid when they are:
- repeatable
- read-only or narrowly scoped
- operationally important
- explicit about PASS / PENDING / FAIL
- tied clearly to one mission

Current example:
- ops/mission5b1_short_quarantine_check.sh

This is part of the project’s proof discipline and should be expanded selectively, not carelessly.

WORKING CONTRACT RECONFIRMED

- one mission at a time
- no guessing
- know exact file truth before changes
- prefer explicit and observable behavior
- verify runtime truth on old-box
- do not mix multiple strategy changes into one patch
- baseline first, calibration second

HONEST CURRENT LABEL

Mission 5B.2:
IN PROGRESS

Sub-status:
- SHORT quarantine complete and proven
- LONG_ONLY baseline now active
- current job is observation, not surgery

===

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

---

HANDOVER FEB 7, 7:57

New Rules for HANDSOFF 

1) Drop-in section for HANDOFF.md

Copy/paste this whole block into your HANDOFF.md (near the top).

# SYNC GATE (must do before proposing changes)

**Rule:** Before suggesting fixes, we sync on reality.

## Step A — Reproduce in one command
Run:

```bash
DATA_TAG=<tag> make eqflat


Expected output includes:

[decisions] PASS/FAIL

[trades] PASS/FAIL

If FAIL: mismatch block showing first mismatch.

Step B — Report in this exact format

Paste:

Result: PASS/FAIL
DATA_TAG=...
RUNID=...
Layer: decisions|trades
Window overlap: [start_ts, end_ts]
First mismatch (ts_ms or trade index):
Hypothesis (1 sentence, no solution yet):
Next check I will run (1 command):


Only after this report is posted do we propose code changes.

Quick commands (operator cheatsheet)
Run LIVE paper loop
DATA_TAG=<tag> make live-up
make live-logs

Stop LIVE paper loop
make live-down

Run equivalence from the first LIVE bar (recommended)
DATA_TAG=<tag> make eqflat

Run plain equivalence against an existing backtest runid
DATA_TAG=<tag> RUNID=<runid> make eq

Run a windowed backtest manually
DATA_TAG=<tag> RUNID=<runid> START_TS_MS=<ts> END_TS_MS=<ts> make backtest

Troubleshooting Index (pick ONE, run it, paste output)
T1 — Confirm LIVE decisions file exists and has data
DATA_TAG=<tag>
ls -la data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv
tail -n 3 data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv

T2 — Extract START_TS_MS from LIVE (first data row)
LIVE="data/processed/decisions/<tag>/BTC_USD/5m/decisions.csv"
awk -F, 'NR==2{print $4; exit}' "$LIVE"

T3 — Show the decision row at a specific ts_ms
CSV="data/processed/decisions/<tag>/BTC_USD/5m/decisions.csv"
TS=1770508500000
awk -F, -v ts="$TS" '$4==ts {print; exit}' "$CSV"

T4 — Trades mismatch debug (show both trade files)
LIVE_T="data/processed/trades/<live_tag>/BTC_USD/5m/trades.csv"
BT_T="data/processed/trades/<bt_tag>/BTC_USD/5m/trades.csv"
echo "LIVE trades:"; tail -n +1 "$LIVE_T" | tail -n 5
echo "BT trades:";   tail -n +1 "$BT_T" | tail -n 5

Change proposal format (required)

Before coding, write:

Intent: (one sentence)

Constraints: (what must not change; list invariants)

Files touched: (explicit list)

Test plan: (exact command(s), no vagueness)

Risk: (what could break; how we’d notice)

Example test command:

DATA_TAG=paper_local_check make eqflat


---

## 2) How to run the “new files.sh” (your `scripts/eqflat.sh` + Makefile target)

You now have **two equivalent ways**:

### Option A (recommended): Make target
```bash
DATA_TAG=paper_local_check make eqflat

Option B: Run the script directly
./scripts/eqflat.sh paper_local_check


What eqflat does (in plain English):

reads START_TS_MS from row 2 of LIVE decisions.csv

runs make backtest windowed from that ts

runs make eq against that backtest run

3) Git plan (no noise, no surprises)

Right now you have:

✅ 1 commit already created locally (ahead of origin by 1)

🔶 a set of modified files still uncommitted (HANDOFF.md, engine.py, config/main/check scripts, docker-compose.yml, etc.)

You asked: “are we going to commit all changes we did?”
Answer: yes — but we do it safely: review → stage → commit → push.

Step 1 — Review what you’re about to publish

This is the “quality control” step. No staging yet.

git diff


If that’s too big, do it file by file:

git diff HANDOFF.md
git diff files/backtest/engine.py
git diff files/main.py
git diff docker-compose.yml

Step 2 — Stage everything you intend to ship

If you want to commit all modified tracked files (not ignored stuff), do:

git add HANDOFF.md docker-compose.yml \
  files/backtest/engine.py files/config.py files/main.py \
  files/main_data_quality_check.py files/main_features_check.py \
  files/main_healthcheck.py files/main_sanity_check.py \
  files/main_smoke.py files/main_state_check.py files/main_storage_check.py


(That stages exactly what git status -sb showed.)

Step 3 — Confirm staged set is correct
git diff --staged

Step 4 — Commit with a clear message
git commit -m "Wire DATA_TAG/RUN_ENV; stabilize eq workflow"

Step 5 — Run one check before pushing
DATA_TAG=paper_local_check make eqflat

Step 6 — Push
git push


That’s it.

Important: your .gitignore already protects requestedfiles.sh and requestedfiles.txt, and it ignores data/, so those won’t get committed unless you force-add them (don’t).

4) About the FAIL you saw (trades mismatch)

You just hit a real signal:

decisions PASS

trades FAIL because BT had an extra trade: LONG stop_hit after the first one

That means: lifecycle decision stream aligns, but execution/trade logging diverged in that window.

When you’re ready, the debug path is:

re-run eqflat (save runid)

compare trades.csv LIVE vs BT for that runid

inspect why BT generated a second stop-hit trade

But since you explicitly want to focus on commits/push first: ignore this until your repo state is clean and pushed.

5) “Next chat starter” (minimal, high signal)

Paste this at the top of your next chat and you’ll avoid the whole “meat to the grill” problem:

Goal: keep LIVE↔BT behavioral equivalence (ts-keyed, sync-at-flat).
Current DATA_TAG: paper_local_check
Command used: DATA_TAG=paper_local_check make eqflat
Latest result: PASS/FAIL (paste only summary + mismatch block if FAIL)
Repo state:
- last pushed commit: <hash>
- local unpushed commits: <count>
What I want to do next: <one sentence>
Constraints: do not change closed-bar rule / ts_ms semantics / warmup gating.


If you want the cleanest workflow long-term, the only “hard rule” I’d enforce is:
no one proposes changes until they run make eqflat and paste the sync report format.

When you’re ready, paste git diff --staged (or just the filenames you’re unsure about), and I’ll tell you exactly whether it’s safe/clean to commit that batch.

---

HANDOVER — 2026-02-07 — EQFLAT runner + LIVE↔BT equivalence workflow
0) Context and goal

We are building a trading system where LIVE and BACKTEST must match in lifecycle behavior (position open/close + reasons) when comparing over an overlapped time window, synced at flat.

We just added a one-command operator workflow:

make eqflat runs:

a windowed backtest that starts exactly at the first LIVE decision timestamp (row 2)

the equivalence check against LIVE

The intended outcome is fast, repeatable verification of LIVE↔BT equivalence with minimal operator steps.

1) What changed (high-level)
1.1 New operator command

Command (example):

DATA_TAG=paper_local_check make eqflat


What it does:

Reads LIVE decisions CSV:
data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv

Extracts START_TS_MS from the first data row (NR==2, column 4)

Creates a new RUNID=eqflat_YYYYmmdd_HHMMSS

Runs:

make backtest using that START_TS_MS

make eq using that RUNID (so it compares LIVE tag vs ${DATA_TAG}_bt_${RUNID})

1.2 New script

File:

scripts/eqflat.sh

Purpose:

Provide a reliable wrapper so you don’t have to type long env-chains.

Important:

This script intentionally does not use set -euo pipefail to avoid “unwanted behavior” you’ve hit before.

It does explicit return-code checks for make backtest and make eq.

1.3 Makefile improvements

The Makefile was updated to:

Standardize env-forwarding into docker containers via RUN_ENV:

--env DATA_TAG --env CCXT_EXCHANGE --env SYMBOL --env TIMEFRAME ...

Make DATA_TAG the storage namespace default (if not provided)

Update eq to use:

--live-tag "$(DATA_TAG)"

--bt-tag "$(DATA_TAG)_bt_$${RUNID}"

Add eqflat: target which calls:

./scripts/eqflat.sh "$(DATA_TAG)"

1.4 .gitignore updates

We explicitly do NOT commit local sharing helpers:

requestedfiles.sh

requestedfiles.txt

Also data/ is ignored (raw/processed/cache etc).

2) Current operator workflow (the “one-liner” way)
Run eqflat (recommended)
DATA_TAG=paper_local_check make eqflat


Expected:

backtest runs inside docker, creates:

data/processed/decisions/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/decisions.csv

data/processed/trades/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/trades.csv

equivalence tool runs and prints PASS/FAIL

Run manual (fallback)

If you want to do it step-by-step without the script:

Get first live ts:

LIVE="data/processed/decisions/paper_local_check/BTC_USD/5m/decisions.csv"
START_TS_MS="$(awk -F, 'NR==2{print $4; exit}' "$LIVE")"
echo "$START_TS_MS"


Run backtest:

DATA_TAG=paper_local_check RUNID="eqflat_$(date -u +%Y%m%d_%H%M%S)" START_TS_MS="$START_TS_MS" make backtest


Run equivalence:

DATA_TAG=paper_local_check RUNID="$RUNID" make eq

3) Known behavior and known risk
3.1 “PASS can become FAIL later” is possible

Because LIVE continues generating decisions/trades over time, the overlap window grows, and new divergences can appear.

Example we observed:

decisions: PASS

trades: FAIL because BT had 2 trades in window while LIVE had 1

This means:

The system is stable enough to compare, but lifecycle may still diverge under some conditions.

3.2 What to check when trades mismatch

When you see:

[trades] length mismatch: LIVE=1 BT=2

Do:

Inspect live trades:

LIVE_TRADES="data/processed/trades/${DATA_TAG}/BTC_USD/5m/trades.csv"
tail -n 20 "$LIVE_TRADES"


Inspect bt trades (from the run shown in output):

BT_TRADES="data/processed/trades/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/trades.csv"
tail -n 40 "$BT_TRADES"


Find the “extra” trade’s entry/exit ts_ms and then look up decisions around it:

LIVE_DEC="data/processed/decisions/${DATA_TAG}/BTC_USD/5m/decisions.csv"
BT_DEC="data/processed/decisions/${DATA_TAG}_bt_${RUNID}/BTC_USD/5m/decisions.csv"

# Example: check a specific ts_ms
awk -F, '$4==1770517500000 {print; exit}' "$LIVE_DEC"
awk -F, '$4==1770517500000 {print; exit}' "$BT_DEC"


Interpretation:

If LIVE is flat/no trade while BT opens/closes, it’s a real divergence (not a window/sync artifact).

4) Repo hygiene rules (no noise, no surprises)
4.1 “No changes before looking”

Before editing anything:

Always run:

git status -sb


If code-related:

git diff

4.2 “No patches”

Do not use git add -p during normal work unless explicitly required.
We stage whole coherent changesets.

4.3 “Quality work only”

Every change must satisfy:

reproducible command path (documented)

no new scripts written into the wrong directory

no accidental new untracked files unless intentional

commit messages reflect real scope

5) Git plan (commit & push) — clean and repeatable
5.1 What we commit vs don’t commit

Commit:

tracked code/docs changes (M ... files)

scripts under scripts/

Do NOT commit:

anything under data/ (ignored)

requestedfiles.sh, requestedfiles.txt (ignored)

5.2 Current state summary

You are:

ahead 1 commit already (you pushed nothing yet)

have additional modified tracked files:

HANDOFF.md

docker-compose.yml

files/... (multiple)

etc.

5.3 Recommended commit structure (2 commits total)

You already have:

Commit #1: “Add eqflat script and Makefile target”

Now do:

Commit #2: “Backtest/live plumbing and behavior changes” (the remaining modified tracked files)

Exact commands:

Stage all modified tracked files (only tracked ones):

git add -u


Verify staging:

git status -sb
git diff --staged


Commit:

git commit -m "Backtest/live plumbing and behavior fixes"


Push both commits:

git push

6) Files list (what matters)

New:

scripts/eqflat.sh

scripts/preflight.sh (currently empty; decide if we keep or delete later)

Modified (tracked):

.gitignore

Makefile

plus your current list from git status -sb (engine/config/main/check scripts etc.)

7) Next actions (practical)

Decide what to do with scripts/preflight.sh:

It’s empty right now. Either:

keep it as placeholder with TODO + basic checks

or delete it (cleaner)

If eqflat produces trade mismatches again:

capture the mismatch lines

inspect the “extra” trade in BT and find corresponding decision rows at entry/exit ts_ms

identify which rule or state difference caused the extra open/close

8) Operator quick reference

Run full check:

DATA_TAG=paper_local_check make eqflat


Just run equivalence (if you already know RUNID):

DATA_TAG=paper_local_check RUNID="..." make eq


Just run backtest windowed:

DATA_TAG=paper_local_check RUNID="..." START_TS_MS="..." make backtest

End HANDOVER

--- 

HANDOFF — 2026-02-08 — old-box (Pop!_OS) live paper loop + cron + GPU + 8888 lockdown + rsync deploy
0) What we achieved (truth)

We now have old-box running the trading repo under Docker Compose with:

paper service running the live paper loop (writes decisions/trades to disk)

trade service for tooling/Jupyter/tests

cron @reboot auto-starts the stack reliably after host reboot (GPU-first, CPU fallback)

GPU in containers works (TensorFlow sees GPU; runtime verified)

Port 8888 is locked down to localhost (127.0.0.1) instead of being publicly exposed

We established an rsync-based deploy flow (local → target) that preserves target-only state

1) Current known-good target state
1.1 Repo location (target)

Repo path on old-box:

/home/kk7wus/Projects/trade

1.2 Containers

docker compose ps shows both services up:

paper (live loop)

trade (tooling / Jupyter)

1.3 “Win condition” for 8888 lockdown

docker compose ps for trade shows:

127.0.0.1:8888->8888/tcp

If it shows 0.0.0.0:8888->8888, then 8888 is exposed and needs fix (see §5).

2) Contracts / invariants (LOCKED)
2.1 Target vs repo differences must be operator state only

On old-box, the intended differences vs the “source repo” are not code:

Allowed target-only:

Local-only .env (NOT committed), e.g. DATA_TAG, SYMBOL, TIMEFRAME, DRY_RUN, optional JUPYTER_BIND_ADDR

data/ contents (raw/processed decisions/trades) — runtime state, not committed

Installed crontab (scheduler state)

Logs in home directory (e.g. ~/trade_reboot.log, ~/trade_heartbeat.log)

Docker runtime state / container lifecycle

Not allowed:

“Just this one edit” on target in repo files.
All repo edits happen locally, then deployed.

2.2 Deployment discipline

Local is source of truth

Target is deploy + run only

We use rsync to push updates to target (no git pull needed)

3) Ops automation (cron + scripts)
3.1 Repo scripts (target has ops/)

/home/kk7wus/Projects/trade/ops/ contains:

cron_reboot.sh — boot start, GPU-first, verify GPU usability, fallback CPU, logs to ~/trade_reboot.log

cron_heartbeat.sh — periodic health proof, logs to ~/trade_heartbeat.log

crontab.example, README.md

3.2 Crontab (target)

Target user’s crontab includes:

@reboot /bin/bash -lc '/home/kk7wus/Projects/trade/ops/cron_reboot.sh'

Heartbeat every 10 minutes (if enabled): cron_heartbeat.sh

Old reboot line exists but is commented out:

#@reboot /bin/bash -lc '/home/kk7wus/trade_boot.sh'

3.3 Logs (target)

Logs are in the target user’s home directory:

/home/kk7wus/trade_reboot.log

/home/kk7wus/trade_heartbeat.log

4) 8888 lockdown (Jupyter exposure)
4.1 What changed (compose)

In docker-compose.yml under the trade service:

ports:
  - "${JUPYTER_BIND_ADDR:-127.0.0.1}:8888:8888"


This makes host publishing default to 127.0.0.1.
Even though Jupyter runs --ip=0.0.0.0 inside the container, the host bind address controls exposure.

4.2 Verify on target
cd /home/kk7wus/Projects/trade
docker compose ps


Expected:

127.0.0.1:8888->8888/tcp

4.3 Safe remote access pattern

Use an SSH tunnel instead of exposing 8888:

ssh -p <SSH_PORT> -L 8888:127.0.0.1:8888 kk7wus@10.0.0.82


Then open http://localhost:8888 on your local machine.

5) Troubleshooting quick hits
5.1 If 8888 shows as exposed (0.0.0.0:8888)

Most common causes:

Target is still running old container config → needs recreate

Target .env sets JUPYTER_BIND_ADDR=0.0.0.0

Fix/re-apply (target):

cd /home/kk7wus/Projects/trade
docker compose up -d --force-recreate trade
docker compose ps


Check env override:

grep -n '^JUPYTER_BIND_ADDR=' .env || true

5.2 Paper loop alive proof (target)
cd /home/kk7wus/Projects/trade
tail -n 3 data/processed/decisions/*/*/*/decisions.csv 2>/dev/null | tail -n 20
docker compose logs --since=15m --tail=120 paper

5.3 Cron proof (target)
crontab -l
tail -n 120 ~/trade_reboot.log
tail -n 120 ~/trade_heartbeat.log

6) Rsync deploy flow (local → target) — no deletes
6.1 Goal

Push repo changes from local to target without overwriting:

.env (target-only)

data/ (target-only)

6.2 Dry-run command (local)

Replace <SSH_PORT> with the correct SSH port (we hit “wrong port” once; confirm before running).

rsync -av --dry-run --itemize-changes --stats \
  -e "ssh -p <SSH_PORT>" \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='data/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='ops/logs/' \
  ~/Projects/trade/ \
  kk7wus@10.0.0.82:~/Projects/trade/

6.3 Real sync (local)

Same command without --dry-run.

6.4 Apply changes on target (recreate trade when ports change)
ssh -p <SSH_PORT> kk7wus@10.0.0.82 \
  'cd ~/Projects/trade && docker compose up -d --force-recreate trade && docker compose ps'

7) GPU status (summary)

Host has NVIDIA GPU (nvidia-smi works)

Docker GPU integration works

TensorFlow in container can see GPU (previously validated)

cron boot script uses GPU compose if present and falls back to CPU if GPU isn’t usable

8) Next missions (queued)

Stop target drift: keep target as “deploy + run,” no repo edits

Optional: remove local-only helper scripts from target if they appear (target doesn’t need deploy helpers)

Optional hardening: risk controls / kill switch (shortest “real-trade safety” upgrade)

Optional: log rotation (prevent ~/trade_*.log growth)

9) Current “done / not done” truth

✅ Reboot resilience: working
✅ Cron auto-start: working
✅ GPU-first + CPU fallback: working
✅ 8888 locked to localhost: verified working
✅ Rsync deploy approach: working (dry-run + correct port + sync + recreate trade)
⚠️ Real-money readiness: not the current goal; next step would be risk controls + reconciliation later


# HANDOFF — 2026-03-06 — Mission 4 Enforcement + Runtime Proof State

## Mission

Finish **Mission 4 — Enforcement at Submit Boundary**.

Goal:

Ensure entry blocks for broker-facing safety controls are enforced at the submit boundary and recorded in `decisions.csv` with canonical reason codes.

Required canonical submit-boundary codes:

- `STOP_BLOCK`
- `HALT_BLOCK`
- `ARM_BLOCK`
- `DAILY_LIMIT_BLOCK`

Exits must remain allowed.

---

## Why this mission matters

This is the main remaining safety-hardening gap between:

- a system that can run unattended
- and a system that is safe enough to even think about real money

The key principle is:

**`files/broker/guarded.py` must be the authoritative submit-boundary blocker.**

`main.py` may still block for orchestration/runtime reasons like degraded mode or cooldown, but not for broker-facing control-plane policy.

---

## Files changed in this session

### Trading-system files changed

- `files/broker/guarded.py`
- `files/main.py`
- `files/data/features.py`
- `files/data/storage.py`

### Files inspected but not changed

- `files/data/decisions.py`
- `files/broker/paper.py`
- `files/data/market.py`

---

## What changed

### 1) `files/broker/guarded.py`

Moved submit-boundary broker policy into `GuardedBroker`.

Current responsibilities there:

- `STOP_BLOCK(...)`
- `HALT_BLOCK(...)`
- `ARM_BLOCK(...)`
- `DAILY_LIMIT_BLOCK(...)`
- `DRY_RUN_BLOCK` for real-broker path
- `BAD_INPUTS`
- `MAX_ORDER_USD_BLOCK(...)`
- `MAX_POSITION_USD_BLOCK(...)`

Important fix:
- renamed old `HALT_ENTRY_BLOCK` style to canonical `HALT_BLOCK`

### 2) `files/main.py`

Removed duplicate broker-facing policy from `main.py`.

`main.py` now keeps orchestration/runtime blocks only:

- `COOLDOWN_BLOCK(...)`
- `DEGRADED_BLOCK(...)`
- `SIZE_BLOCK(...)`

It still handles:

- market fetch / feature compute loop
- degraded mode logic
- trailing freeze behavior
- decision writing
- exit handling

Important split now:

- `main.py` decides whether it wants to enter
- `GuardedBroker` decides whether entry is allowed to hit the inner broker

### 3) `files/data/features.py`

Hardened latest-row feature validation.

Old behavior:
- any NaN in latest row killed the loop

New behavior:
- execution-critical fields still fail hard
- optional derived fields warn instead of halting

This reduced brittleness but did **not** remove all upstream data issues.

### 4) `files/data/storage.py`

Added observability for suspicious replayed adjacent OHLCV bars.

Current behavior:
- warn if adjacent rows have different timestamps but identical OHLCV payload
- do **not** mutate/drop rows yet
- observability-first only

---

## What was proven

### Proven in `decisions.csv`

Observed real rows showing:

- `ARM_BLOCK(...)`
- `DEGRADED_BLOCK(...)`
- `COOLDOWN_BLOCK(...)`

Observed forced-entry proof rows with:

- `entry_should_enter=True`
- `entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE`

This proves:

- forced-entry test hook works
- fresh eligible bar path works
- decision writing path works
- blocked entry reasons are landing in `entry_blocked_reason`
- Mission 4 submit-boundary plumbing is working at least for `ARM_BLOCK`

### Proven operationally

- restart-safe idempotency is working
- in-progress last-bar dropping is working
- loop survives restarts
- `.env` cleanup fixed stale test-fault config issues
- duplicate/dirty runtime env was a real source of confusion and has been cleaned

---

## What is **not** fully proven yet

Still not directly observed in `decisions.csv` during this session:

- `STOP_BLOCK(...)`
- `HALT_BLOCK(...)`
- `DAILY_LIMIT_BLOCK(...)`

This is the remaining proof gap.

Important nuance:

This is **not** because the submit-boundary architecture failed.

It is because entry attempts were intercepted earlier by higher-precedence runtime/orchestration blockers during testing:

- `COOLDOWN_BLOCK(...)`
- then later
- `DEGRADED_BLOCK(...)`

So STOP/HALT were not reached on those proof attempts.

---

## Current blocker

### Main remaining blocker to full Mission 4 PASS

**Degraded-mode precedence during proof runs.**

Observed fresh proof row:

- `entry_should_enter=True`
- `entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE`
- `entry_blocked_reason=DEGRADED_BLOCK(features_invalid_x4_in_last6)`

So the system is still correctly blocking, but the block reason is degraded-mode, not STOP/HALT.

### What caused degraded mode

Two things contributed during this session:

1. stale test-fault env left on in `.env`
   - `FORCE_FEATURES_INVALID_N=2`
   - this intentionally poisoned features until cleaned up

2. bar-freshness / replay weirdness in live data path
   - not conclusively fatal now
   - but previously contributed to `features_invalid` rows

---

## Important runtime findings

### `.env` was dirty and duplicated

Found stale test settings in runtime `.env`, including:

- `FORCE_FEATURES_INVALID_N=2`
- duplicate `TEST_HOOKS_ENABLED`
- duplicate `FORCE_ENTRY_SIGNAL_ONCE`

This was cleaned by overwriting `.env` with a single boring source of truth.

### Repeated `SKIP: already-processed bar` was not necessarily a bug

This turned out to be expected behavior when:

- the latest fetched bar was still the in-progress bar
- `main.py` dropped the in-progress last bar
- newest eligible closed candle was already present in `decisions.csv`

So repeated skip behavior during a live 5m window can be correct.

---

## Current runtime truth

At the end of this session:

- Mission 4 architecture is much cleaner than before
- `GuardedBroker` now owns submit-boundary entry policy
- `main.py` is cleaner and no longer duplicates STOP/HALT/ARM/daily-limit entry policy
- test hooks are available and working
- degraded state still needs to clear before STOP/HALT proof can land cleanly

---

## Recommended next mission

### Immediate next mission

**Complete deterministic proof for `STOP_BLOCK` and `HALT_BLOCK` after degraded mode clears.**

Suggested method:

1. wait until market_reason is no longer `DEGRADED(...)`
2. keep:
   - `TEST_HOOKS_ENABLED=1`
   - `FORCE_ENTRY_SIGNAL_ONCE=1`
3. set:
   - STOP present, HALT absent
4. recreate paper
5. capture next fresh eligible row in `decisions.csv`

Expected proof row:

- `entry_should_enter=True`
- `entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE`
- `entry_blocked_reason=STOP_BLOCK(...)`

Then repeat with:

- STOP absent
- HALT present

Expected:

- `entry_blocked_reason=HALT_BLOCK(...)`

### After that

Do a controlled `DAILY_LIMIT_BLOCK(...)` proof with a deterministic low limit.

---

## Suggested PASS condition for Mission 4

Mission 4 should be marked PASS only when all of the following are observed:

1. `ARM_BLOCK(...)` observed in `entry_blocked_reason`
2. `STOP_BLOCK(...)` observed in `entry_blocked_reason`
3. `HALT_BLOCK(...)` observed in `entry_blocked_reason`
4. `DAILY_LIMIT_BLOCK(...)` observed in `entry_blocked_reason`
5. exits remain allowed under STOP/HALT
6. no broker-facing policy for STOP/HALT/ARM/daily-limit remains duplicated in `main.py`

Current status:
- items 1 and 6 are effectively proven
- items 2–5 still need explicit proof

---

## Commands that were useful in this session

### Check runtime env inside paper
```bash
cd ~/Projects/trade && docker compose exec -T paper sh -lc 'env | egrep "^(TEST_HOOKS_ENABLED|FORCE_FEATURES_INVALID_N|FORCE_CADENCE_FAIL_N|FORCE_ENTRY_SIGNAL_ONCE|FORCE_COOLDOWN_BLOCK_ONCE|FORCE_COOLDOWN_BARS|ARM_FILE|KILL_SWITCH_FILE|HALT_ORDERS_FILE|DATA_TAG|TIMEFRAME|BROKER)="'

Tail live decisions
cd ~/Projects/trade && tail -f data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv
Search proof rows
cd ~/Projects/trade && grep -n 'TEST_FORCE_ENTRY_SIGNAL_ONCE\|STOP_BLOCK\|HALT_BLOCK\|ARM_BLOCK\|DAILY_LIMIT_BLOCK\|DEGRADED_BLOCK\|COOLDOWN_BLOCK' data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv | tail -n 20
Watch proof logs
cd ~/Projects/trade && docker compose logs -f paper | egrep 'TEST: forcing entry signal once|Blocked entry at broker guard|Decision recorded|SKIP: already-processed|Latest features invalid'
Recommended operator notes

Keep runtime .env boring and deduplicated

Do not leave fault-injection knobs on after a proof

Distinguish:

orchestration/runtime blockers

submit-boundary broker blockers

repeated already-processed skips can be normal during the current in-progress candle window

do not call Mission 4 PASS until STOP/HALT/daily-limit are observed directly in decisions.csv

----
HANDOFF — 2026-03-07 — Mission 4 Enforcement + Overnight Runtime State

Mission
Finish Mission 4 — Enforcement at Submit Boundary.

Goal:
Ensure broker-facing entry safety controls are enforced at the submit boundary and recorded in decisions.csv with canonical reason codes.

Required canonical submit-boundary codes:
- STOP_BLOCK
- HALT_BLOCK
- ARM_BLOCK
- DAILY_LIMIT_BLOCK

Exits must remain allowed.

================================================================
WHY THIS MISSION MATTERS
================================================================

This is the key remaining safety-hardening gap between:
- a system that can run unattended
and
- a system that is safe enough to seriously approach real-money readiness.

The main principle is now clear:

files/broker/guarded.py must be the authoritative submit-boundary blocker.

main.py may still block for orchestration/runtime reasons like:
- degraded mode
- cooldown
- size <= 0

But broker-facing control-plane policy should not be duplicated there.

================================================================
FILES CHANGED IN THIS SESSION
================================================================

Trading-system files changed:
- files/broker/guarded.py
- files/main.py
- files/data/features.py
- files/data/storage.py

Files inspected but not changed:
- files/data/decisions.py
- files/broker/paper.py
- files/data/market.py

Other repo state still present locally and should be reviewed separately before commit:
- docker-compose.yml
- files/data/market.py
- ops/cron_heartbeat.sh
- ops/deploy_oldbox.sh
- ops/rsync_exclude.txt

Do not blindly commit unrelated ops/deploy changes with the Mission 4 batch.

================================================================
WHAT CHANGED
================================================================

1) files/broker/guarded.py

Submit-boundary broker policy was consolidated into GuardedBroker.

Current responsibilities there:
- STOP_BLOCK(...)
- HALT_BLOCK(...)
- ARM_BLOCK(...)
- DAILY_LIMIT_BLOCK(...)
- DRY_RUN_BLOCK for real-broker path
- BAD_INPUTS
- MAX_ORDER_USD_BLOCK(...)
- MAX_POSITION_USD_BLOCK(...)

Important fix:
- old HALT_ENTRY_BLOCK naming was aligned to canonical HALT_BLOCK

2) files/main.py

Removed duplicate broker-facing control-plane blocking from main.py.

main.py now keeps orchestration/runtime blocks only:
- COOLDOWN_BLOCK(...)
- DEGRADED_BLOCK(...)
- SIZE_BLOCK(...)

main.py still owns:
- market fetch / loop orchestration
- degraded-mode logic
- trailing freeze logic
- decision writing
- exit handling

Current intended split:
- main.py decides whether it wants to enter
- GuardedBroker decides whether entry may reach the inner broker

3) files/data/features.py

Hardened latest-row feature validation.

Old behavior:
- any NaN in latest feature row killed the loop

New behavior:
- execution-critical fields still fail hard
- optional derived fields warn instead of halting

This reduced brittleness, but stale test-fault env and prior degraded state still affected proof runs.

4) files/data/storage.py

Added observability for suspicious replayed adjacent OHLCV bars.

Current behavior:
- warns if adjacent rows have different timestamps but identical OHLCV payload
- does not mutate/drop rows yet
- observability-first only

================================================================
WHAT WAS PROVEN
================================================================

Proven in decisions.csv:
- ARM_BLOCK(...)
- DEGRADED_BLOCK(...)
- COOLDOWN_BLOCK(...)
- MAX_ORDER_USD_BLOCK(...)

Observed forced-entry proof rows with:
- entry_should_enter=True
- entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE

This proves:
- forced-entry hook works
- fresh eligible bar path works
- decision writing works
- blocked entry reasons are landing in entry_blocked_reason
- submit-boundary blocking flow is functioning for real entry attempts

Overnight healthy-loop evidence:
paper container repeatedly showed:
- Fetched market data
- Persisted bars
- Decision recorded on fresh closed bars
- SKIP: already-processed bar (restart-safe idempotency) during already-seen/in-progress windows

That is expected and healthy behavior.

================================================================
WHAT IS NOT FULLY PROVEN YET
================================================================

Still not directly observed in decisions.csv during this mission:
- STOP_BLOCK(...)
- HALT_BLOCK(...)
- DAILY_LIMIT_BLOCK(...)
- exits still allowed under STOP/HALT

This is the remaining proof gap.

Important nuance:
This is not because the submit-boundary architecture failed.

It is because proof attempts were intercepted earlier by higher-precedence runtime/orchestration blockers during testing:
- COOLDOWN_BLOCK(...)
- then DEGRADED_BLOCK(...)

So STOP/HALT were not reached on those specific proof attempts.

================================================================
MAIN BLOCKER TO FULL MISSION 4 PASS
================================================================

The remaining blocker is proof completion, not architecture.

During deterministic proof attempts, fresh forced-entry rows were blocked by:
- COOLDOWN_BLOCK(remaining=3)
and later by:
- DEGRADED_BLOCK(features_invalid_x4_in_last6)
- DEGRADED_BLOCK(features_invalid_x5_in_last6)

Therefore:
STOP/HALT proof did not fail due to GuardedBroker.
STOP/HALT proof did not land because runtime-state precedence intercepted entry first.

================================================================
IMPORTANT RUNTIME FINDINGS
================================================================

1) .env had stale test-fault settings

A major source of confusion during proofing was dirty runtime env.
Found earlier in .env:
- FORCE_FEATURES_INVALID_N=2
- duplicate TEST_HOOKS_ENABLED
- duplicate FORCE_ENTRY_SIGNAL_ONCE

This intentionally poisoned features until cleaned.

The fix was to overwrite .env with a single boring source of truth.

2) Repeated SKIP: already-processed bar was not a bug

This was expected behavior when:
- latest fetched bar was still the in-progress candle
- main.py dropped the in-progress last bar
- newest eligible closed bar was already present in decisions.csv

So repeated skip behavior during a live 5m window can be normal and safe.

3) Overnight run showed healthy stabilization

By the overnight check:
- no recurring features_invalid churn in the active runtime tail
- no replay warning fired from storage.py
- loop showed normal cadence and stable decision writing
- system now behaves much more like an operationally boring service

4) Submit-boundary MAX_ORDER_USD proof appeared naturally

Overnight decisions.csv contained repeated rows like:
- MAX_ORDER_USD_BLOCK(order_usd=50.00 cap=25.00)

This is strong evidence that:
- strategy wanted to enter
- main.py called broker.open_position(...)
- GuardedBroker blocked at submit boundary
- the returned reason landed correctly in decisions.csv

This is a very important proof of architecture correctness.

================================================================
CURRENT RUNTIME TRUTH
================================================================

At the end of this session / overnight run:
- Mission 4 architecture is much cleaner than before
- GuardedBroker now owns broker-facing submit-boundary policy
- main.py is cleaner and no longer duplicates STOP/HALT/ARM/daily-limit entry policy
- runtime env is cleaner and less polluted by old fault-injection state
- overnight loop behavior looks healthy
- submit-boundary reasons are definitely landing in decisions.csv
- remaining work is mainly proof matrix completion, not structural redesign

================================================================
UPDATED MATURITY SNAPSHOT
================================================================

Trading system

Self-running unattended system readiness:
~93–94%

Why:
- loop runs continuously
- docker/systemd/runtime behavior is stable
- observability chain works
- healthy overnight cadence observed
- restart-safe idempotency works

Safe-to-connect-real-money readiness:
~69–72%

Why it improved:
- submit-boundary architecture is cleaner
- ARM_BLOCK proved
- MAX_ORDER_USD_BLOCK proved
- overnight operation looked healthy
- runtime env/test pollution issue was identified and corrected

Why it is not higher:
- STOP_BLOCK / HALT_BLOCK / DAILY_LIMIT_BLOCK still need explicit proof
- exits-under-STOP/HALT still need explicit proof
- there is still some proof debt around the control-plane matrix

Mission 4 specifically

Architecture completion:
~92–94%

Proof completion:
~68–72%

Why:
- multiple real block reasons are proven in decisions.csv
- but the exact canonical control-plane proof set is still incomplete

Repo RAG Assistant

Useful/trustworthy teammate readiness:
~84–89%

Strong:
- refusal discipline
- source cleanliness
- eval stability
- operator usefulness

Still weaker:
- multi-hop trace capability

================================================================
SUGGESTED PASS CONDITION FOR MISSION 4
================================================================

Mission 4 should be marked PASS only when all of the following are explicitly observed:

1) ARM_BLOCK(...) observed in entry_blocked_reason
2) STOP_BLOCK(...) observed in entry_blocked_reason
3) HALT_BLOCK(...) observed in entry_blocked_reason
4) DAILY_LIMIT_BLOCK(...) observed in entry_blocked_reason
5) exits remain allowed under STOP/HALT
6) no broker-facing STOP/HALT/ARM/daily-limit entry policy remains duplicated in main.py

Current status:
- item 1 is proven
- item 6 is effectively proven by file inspection/change
- items 2–5 still need explicit proof

================================================================
BEST NEXT MISSION
================================================================

Complete the remaining proof matrix for Mission 4.

Recommended order:

1) STOP_BLOCK proof
- ensure degraded mode is not active
- keep TEST_HOOKS_ENABLED=1
- set FORCE_ENTRY_SIGNAL_ONCE=1
- create STOP file
- ensure HALT absent
- recreate paper
- capture next fresh eligible decision row

Expected proof row:
- entry_should_enter=True
- entry_reason=TEST_FORCE_ENTRY_SIGNAL_ONCE
- entry_blocked_reason=STOP_BLOCK(...)

2) HALT_BLOCK proof
- remove STOP
- create HALT
- keep FORCE_ENTRY_SIGNAL_ONCE=1
- recreate paper
- capture next fresh eligible decision row

Expected:
- entry_blocked_reason=HALT_BLOCK(...)

3) DAILY_LIMIT_BLOCK proof
- set deterministic low daily limit
- trigger one qualifying trade/day state
- attempt another entry
- capture daily-limit block in decisions.csv

Expected:
- entry_blocked_reason=DAILY_LIMIT_BLOCK(...)

4) Exit-under-STOP/HALT proof
- force or wait for open position
- activate STOP or HALT
- confirm exit path still functions
- confirm no new entry allowed

================================================================
USEFUL COMMANDS
================================================================

Check runtime env inside paper:
cd ~/Projects/trade && docker compose exec -T paper sh -lc 'env | egrep "^(TEST_HOOKS_ENABLED|FORCE_FEATURES_INVALID_N|FORCE_CADENCE_FAIL_N|FORCE_ENTRY_SIGNAL_ONCE|FORCE_COOLDOWN_BLOCK_ONCE|FORCE_COOLDOWN_BARS|ARM_FILE|KILL_SWITCH_FILE|HALT_ORDERS_FILE|DATA_TAG|TIMEFRAME|BROKER)="'

Tail live decisions:
cd ~/Projects/trade && tail -f data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv

Search proof rows:
cd ~/Projects/trade && grep -n 'TEST_FORCE_ENTRY_SIGNAL_ONCE\|STOP_BLOCK\|HALT_BLOCK\|ARM_BLOCK\|DAILY_LIMIT_BLOCK\|DEGRADED_BLOCK\|COOLDOWN_BLOCK\|MAX_ORDER_USD_BLOCK' data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv | tail -n 30

Watch proof logs:
cd ~/Projects/trade && docker compose logs -f paper | egrep 'TEST: forcing entry signal once|Blocked entry at broker guard|Decision recorded|SKIP: already-processed|Latest features invalid'

================================================================
OPERATOR NOTES
================================================================

- Keep runtime .env boring and deduplicated
- Do not leave fault-injection knobs on after proofs
- Distinguish:
  - orchestration/runtime blockers
  - submit-boundary broker blockers
- repeated already-processed skips can be normal during the current in-progress candle window
- do not mark Mission 4 PASS until STOP/HALT/daily-limit/exits-under-halt are explicitly observed

================================================================
HONEST SUMMARY
================================================================

This session made real progress.

The architecture is better.
The submit-boundary model is cleaner.
The overnight loop looked healthy.
The proof plumbing works.
Real submit-boundary block reasons are landing in decisions.csv.

But Mission 4 is not fully closed yet.

Best current label:

Mission 4 — strong progress, healthy overnight runtime, partial proof complete, explicit STOP/HALT/DAILY_LIMIT and exit-under-halt proofs still pendin:> [!WARNING]

=================================================================

HANDOFF — 2026-03-08 — Mission 4 PASS + Mission 5A PASS + Next Mission

================================================================
MISSION STATUS
================================================================

Mission 4
PASS

Mission 5A
PASS

Current overall state:
- submit-boundary entry matrix proven
- STOP semantics proven during a live position
- realistic paper runtime proven with natural entries, holds, trailing, exits, and trade recording
- next work should move from semantics proofing into runtime quality / safety re-balancing / performance truth

================================================================
EXECUTIVE SUMMARY
================================================================

This cycle closed Mission 4 for real.

We proved from old-box runtime evidence that:
- STOP blocks new entries
- STOP freezes trailing during a live open position
- the live open position can still exit and record a trade while STOP is present

We also proved Mission 5A:
- the system can run in a realistic paper configuration
- natural positions can open without proof hooks
- positions can hold across bars
- trailing ratchets in normal runtime
- exits are recorded cleanly
- old-box runtime truth matches intended configuration

This is a major step up in system honesty.

We are no longer mainly asking:
- “are the guardrails wired?”
We are now mainly asking:
- “how well does the system behave in realistic paper runtime?”
- “what should be tuned next without breaking the proven semantics?”

================================================================
CURRENT TRUTH
================================================================

Repo / runtime discipline

Re-confirmed:
- local repo truth is not enough
- old-box runtime truth is what counts

For any serious claim, verify all four:
1) file truth
2) deploy truth
3) container env truth
4) runtime-state truth

Current architecture / ownership

- files/main.py owns orchestration/runtime behavior
- files/broker/guarded.py owns submit-boundary entry blocking
- PaperBroker handles paper position lifecycle
- operator flag files affect runtime immediately through mounted flags dir

Current proven submit-boundary blockers:
- ARM_BLOCK(...)
- STOP_BLOCK(...)
- HALT_BLOCK(...)
- DAILY_LIMIT_BLOCK(...)
- MAX_ORDER_USD_BLOCK(...)
- MAX_POSITION_USD_BLOCK(...)

Current runtime behavior:
- STOP/HALT block entries at submit boundary
- exits still go through realize_and_close(...)
- trailing freezes under STOP/HALT in main.py
- proof hooks exist but are now OFF in Mission 5A runtime

================================================================
WHAT WE PROVED THIS CYCLE
================================================================

A) Mission 5A realistic paper runtime proof

Runtime config was moved out of proof-junk mode and into realistic paper mode:
- proof hooks OFF
- MAX_ORDER_USD raised
- MAX_POSITION_USD raised
- daily loss guard kept on
- ARM active
- STOP/HALT absent during normal observation
- current runtime env confirmed inside running paper container

Observed from real runtime:
- natural entries occurred
- positions held across multiple 5m bars
- trailing stop updated with trail_reason=ratchet
- exits were recorded as trades
- repeated real paper activity occurred without proof hooks
- no degraded/cadence/features noise interfered

Mission 5A result:
PASS

B) Mission 4 final remainder proof

Goal:
prove that under STOP during a live position:
- trailing freezes
- new entries are blocked
- open position can still close and record a trade

A dedicated proof runner was created:
- ops/mission4_stop_exit_proof.sh

What it did:
1) wait for a live open position
2) create STOP automatically at the correct time
3) hold STOP in place during the live position
4) capture decision rows, logs, and trades
5) remove STOP after proof capture

Observed runtime evidence:

1. Entry blocked under STOP
Observed in decisions.csv:
- entry_should_enter=True
- entry_reason=trend_down_and_confident
- entry_blocked_reason=STOP_BLOCK(kill_switch=/home/kk7wus/trade_flags/STOP)

Examples captured:
- 2026-03-08T16:40:00+00:00
- 2026-03-08T16:45:00+00:00
- 2026-03-08T16:50:00+00:00
- 2026-03-08T16:55:00+00:00
- 2026-03-08T17:00:00+00:00
- 2026-03-08T18:45:00+00:00

2. Trailing froze under STOP during a live open position
Observed in decisions.csv for live SHORT position:
- trail_reason=halted_freeze_trailing(STOP_BLOCK(kill_switch=/home/kk7wus/trade_flags/STOP))

Also observed:
- position_stop_price remained fixed at 67041.87056700776 across multiple bars
- position remained open while STOP was present
- loop continued writing decision rows

Captured examples:
- 2026-03-08T18:55:00+00:00
- 2026-03-08T19:00:00+00:00
- 2026-03-08T19:05:00+00:00
- 2026-03-08T19:10:00+00:00
- 2026-03-08T19:15:00+00:00

3. Exit still completed under STOP
Observed:
- live SHORT position remained open under STOP
- exit_should_exit=True with exit_reason=stop_hit while STOP still present
- trade was recorded
- trades.csv captured:
  entry_ts_ms=1772996100000
  exit_ts_ms=1772997300000
  side=SHORT
  qty=0.01
  entry_price=66830.24
  exit_price=67041.87056700776
  reason=stop_hit

Log evidence also showed:
- Trade recorded

Mission 4 final remainder result:
PASS

================================================================
STRONGEST EVIDENCE TO REMEMBER
================================================================

From decisions.csv:
- STOP_BLOCK(...) rows exist for attempted fresh entries
- halted_freeze_trailing(STOP_BLOCK(...)) rows exist during live position
- exit_should_exit=True and exit_reason=stop_hit occurred while STOP remained present

From trades.csv:
- the STOP-window live SHORT did close and record correctly

From proof runner lifecycle:
- STOP was created automatically only after live position appeared
- STOP was removed automatically after proof capture
- proof packet saved at:
  /home/kk7wus/Projects/trade/ops/proofs/mission4_stop_exit_20260308T185914Z.log

================================================================
IMPORTANT FILES NOW IN PLAY
================================================================

Core runtime files
- files/main.py
- files/broker/guarded.py
- files/config.py
- ops/daily_limits_check.py

Proof tooling
- ops/mission4_stop_exit_proof.sh

Compose/runtime
- docker-compose.yml
- .env

Evidence locations
- data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv
- data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv
- ops/proofs/mission4_stop_exit_20260308T185914Z.log

================================================================
CURRENT MISSION 5A CONFIG TRUTH
================================================================

Mission 5A runtime mode was confirmed inside the running paper container:

- DATA_TAG=paper_oldbox_live
- SYMBOL=BTC/USD
- TIMEFRAME=5m
- BROKER=paper
- DRY_RUN=1
- COOLDOWN_BARS=1
- MAX_ORDER_SIZE=0.01
- MAX_ORDER_USD=1000
- MAX_POSITION_USD=1000
- MAX_TRADES_PER_DAY=0
- MAX_DAILY_LOSS_USD=25
- TEST_HOOKS_ENABLED=0
- FORCE_ENTRY_SIGNAL_ONCE=0
- FORCE_EXIT_SIGNAL_ONCE=0
- FORCE_COOLDOWN_BLOCK_ONCE=0
- FORCE_COOLDOWN_BARS=0
- FORCE_FEATURES_INVALID_N=0
- FORCE_CADENCE_FAIL_N=0
- BYPASS_FEATURE_VALIDATION=0
- ARM_FILE=/home/kk7wus/trade_flags/ARM
- KILL_SWITCH_FILE=/home/kk7wus/trade_flags/STOP
- HALT_ORDERS_FILE=/home/kk7wus/trade_flags/HALT
- TZ_LOCAL=America/Los_Angeles

Flags truth during normal runtime:
- ARM exists
- STOP absent except when intentionally used for proof
- HALT absent except when intentionally used for proof

================================================================
MAIN PITFALLS WE HIT
================================================================

1) Local truth != old-box truth
Still the biggest source of false confidence.

2) Proof timing matters
For STOP live-position proof, order matters:
- live position exists
- apply STOP
- observe freeze + exit
Not:
- apply STOP while flat
- hope later evidence still means the same thing

3) Manual proof timing is noisy
A dedicated proof runner was much better than human polling.

4) Historical decision rows can confuse current truth
Old proof rows stayed in decisions.csv, so always anchor to timestamps and current runtime state.

5) Safety semantics proof and strategy quality proof are different
The system can be semantically correct and still perform poorly.
Do not confuse those categories.

================================================================
WORKING CONTRACT — HOW WE WORK
================================================================

Purpose

We work in a way that is:
- safe
- grounded
- reproducible
- proof-driven
- low-noise

Core rules

1) One mission at a time
Stay on one mission until:
- proven
- cleanly blocked
- or intentionally parked

2) File-first discipline
Before proposing changes, identify the exact file(s).

3) Full-file replacements preferred
Avoid speculative patch fragments when possible.

4) Old-box runtime truth wins
Never trust local assumptions over running truth.

5) Proof over theory
A change is not done because it sounds right.
It is done when runtime evidence proves it.

6) Honest labels only
Use:
- PASS
- partial proof
- blocked
- failed
- deferred remainder

7) Clean proof state
When a proof is done, clean:
- STOP / HALT / ARM test state
- .env proof knobs
- seeded test data if used

8) Prefer proof tools over manual babysitting
If timing sensitivity is high, create a dedicated proof runner instead of relying on human polling.

================================================================
USEFUL COMMANDS
================================================================

Runtime env truth
cd ~/Projects/trade && docker compose exec -T paper sh -lc 'env | egrep "^(DATA_TAG|SYMBOL|TIMEFRAME|DRY_RUN|BROKER|COOLDOWN_BARS|MAX_ORDER_SIZE|MAX_ORDER_USD|MAX_POSITION_USD|MAX_TRADES_PER_DAY|MAX_DAILY_LOSS_USD|TEST_HOOKS_ENABLED|FORCE_ENTRY_SIGNAL_ONCE|FORCE_EXIT_SIGNAL_ONCE|FORCE_COOLDOWN_BLOCK_ONCE|FORCE_COOLDOWN_BARS|FORCE_FEATURES_INVALID_N|FORCE_CADENCE_FAIL_N|BYPASS_FEATURE_VALIDATION|ARM_FILE|KILL_SWITCH_FILE|HALT_ORDERS_FILE|TZ_LOCAL)="'

Latest decisions
cd ~/Projects/trade && tail -n 40 data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv

Latest trades
cd ~/Projects/trade && tail -n 20 data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv

Recent paper events
cd ~/Projects/trade && docker compose logs --since=12h paper | egrep 'Opened paper position|Updated stop|Trade recorded|Closed paper position|Blocked entry at broker guard|DEGRADED|Cadence check failed|Latest features invalid'

Proof log tail
cd ~/Projects/trade && tail -n 120 ops/proofs/mission4_stop_exit_20260308T185914Z.log

Run Mission 4 STOP/exit proof tool again
cd ~/Projects/trade && ./ops/mission4_stop_exit_proof.sh

Deploy to old-box safely
cd ~/Projects/trade && OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh

Important deploy note
Do not use:
- OLD_BOX_DIR=~/Projects/trade
Use:
- OLD_BOX_DIR=/home/kk7wus/Projects/trade

================================================================
RECOMMENDED STATUS LABEL NOW
================================================================

Mission 4
PASS

Expanded label:
- submit-boundary entry matrix proven
- STOP during live position freezes trailing
- STOP blocks fresh entries
- open position can still exit and record under STOP
- proven from old-box runtime evidence

Mission 5A
PASS

Expanded label:
- realistic paper runtime observed
- natural open / hold / trail / exit cycle(s) observed
- proof hooks off
- rails still active

================================================================
NEXT MISSION
================================================================

Mission 5B — Runtime Quality, Safety Re-Balancing, and Honest Paper Performance

Goal

Move from “semantics are proven” into:
- how well the system behaves in realistic paper runtime
- whether current sizing / stops / trailing / filters are sensible
- how to rebalance safety caps now that proof mode is over
- what the real next bottleneck is: strategy quality, runtime safety, or observability

Why this is the right next mission

- Mission 4 is now closed
- Mission 5A proved realistic runtime operation
- the next unanswered questions are quality questions, not wiring questions
- current paper trades show repeated stop_hit exits and cumulative drawdown
- now is the right time to analyze behavior honestly before changing architecture again

Mission 5B suggested targets

1) Quantify paper runtime performance
Look at:
- win/loss count
- average pnl
- cumulative pnl
- average hold duration
- stop_hit frequency
- time_stop frequency
- LONG vs SHORT behavior
- behavior by market_reason / trend / volatility

2) Assess whether current safety caps are still appropriate
Now that 0.01 positions are real:
- is MAX_DAILY_LOSS_USD=25 right?
- should MAX_TRADES_PER_DAY remain 0 or be restored to a real cap?
- should MAX_POSITION_USD stay at 1000 or be reduced to a more boring paper cap?

3) Inspect strategy/runtime quality
Questions:
- are entries too frequent or too weak?
- is trailing too tight?
- are many exits just noise-stop losses?
- is cooldown too permissive?
- are filter conditions admitting poor setups?

4) Improve observability if needed
Possible next improvements:
- better dashboard visibility for current position lifecycle
- clearer logging around open/close/trail/blocked events
- small summary scripts for paper performance truth

5) Only after the above, decide whether repo changes are needed
Do not jump into code surgery until paper-runtime truth says what actually hurts.

Suggested first moves for Mission 5B

1. Build a simple runtime-performance summary from trades.csv
2. Quantify what the current paper configuration actually did overnight
3. Decide whether next step is:
   - performance analysis script
   - dashboard/operator summary improvement
   - cap rebalance
   - strategy tuning

================================================================
HONEST SUMMARY
================================================================

This was a high-value cycle.

We did not just “test things.”
We turned ambiguous behavior into proven runtime truth.

What we now know for real:
- submit-boundary guard semantics are real
- STOP behavior is proven during a live open position
- realistic paper runtime works without proof hooks
- the system can naturally open, hold, trail, and exit
- the next dragon is no longer semantics; it is runtime quality and performance truth

Best current summary:

Mission 4 is closed.
Mission 5A is passed.
Next mission should be Mission 5B:
runtime quality, safety re-balancing, and honest paper-performance analysis.


===
SIDE HANDOFF — STRATEGY LAB EXPERIMENT — 2026-03-09

PURPOSE

This sub-handoff tracks the notebook-based strategy experiment work.
It is not the canonical runtime/system handoff.
It is the research handoff for understanding strategy behavior before repo changes.

CURRENT NOTEBOOK

Notebook file:
data/notebooks/strategy_lab_experiment_01.ipynb

Notebook state verified:
- notebook exists
- notebook runs
- imports work
- features compute correctly
- current workflow is usable

Important workflow note:
- notebook output copy/paste had been a problem
- user later found a way to copy/paste
- export-to-text helper also exists in notebook and still remains useful

CURRENT NOTEBOOK STRUCTURE

Verified sections:
- strategy notes markdown
- first notebook goals markdown
- 0 imports
- 1 exports
- 2 existence check
- 3 list raw partitions
- 4 raw coverage summary
- 5 load raw bars
- 6 raw bars summary
- 7 schema and nulls
- 8 load decisions
- 9 decisions summary
- 10 load trades
- 11 trades summary
- 12 last trades
- 13 compute features from raw bars
- 14 features summary
- 15 feature distributions
- 16 classify market state
- 17 market state counts
- 18 merge trades with nearest feature/state at entry time
- 19 inspect losing trades in context
- 20 regime table
- 21 MFE/MAE table
- 22 MFE/MAE summary by side and outcome
- 23 SHORT loss filter audit
- 24 SHORT filter variant audit
- 25 ALL vs LONG_ONLY vs LONG+filtered_SHORT comparison

DATA STATUS

Raw bar data:
- tag: paper_oldbox_live
- symbol: BTC_USD
- timeframe: 5m
- raw partitions present for 17 days
- date span includes:
  2026-02-09 through 2026-03-09
- raw feature rows observed:
  about 3608

Processed runtime data:
- decisions.csv present
- trades.csv present

This is enough for:
- exploratory analysis
- side/regime analysis
- first controlled notebook experiments

This is not yet enough for:
- high-confidence broad optimization
- trusting large parameter sweeps
- claiming robustness

KEY VERIFIED FINDINGS

1) Overall strategy is losing
From notebook trades summary:
- trades: 41
- wins: 9
- losses: 32
- total_pnl_usd: -63.26
- avg_pnl_usd: -1.54

2) SHORT is much worse than LONG
Side summary:
- SHORT
  trades: 19
  wins: 2
  losses: 17
  pnl_usd: -41.57
  avg_pnl_usd: -2.19
  win_rate: 10.53%

- LONG
  trades: 22
  wins: 7
  losses: 15
  pnl_usd: -21.70
  avg_pnl_usd: -0.99
  win_rate: 31.82%

Conclusion:
- both sides lose
- SHORT is the bigger problem by far

3) Worst regime is SHORT in down regimes, especially high volatility
Side by regime findings:
- SHORT + down + normal is the biggest total damage bucket
- SHORT + down + high is the worst average-loss bucket

Conclusion:
- SHORT is not just weak in general
- it is especially damaging in the exact conditions where it was expected to help

4) MFE / MAE analysis says SHORT is mainly an entry problem
MFE/MAE summary:
- SHORT losses:
  avg_mfe_atr about 0.75
  med_mfe_atr about 0.51
  avg_mae_atr about 1.63
  med_mae_atr about 1.54

Interpretation:
- losing SHORT trades do not move enough in the favorable direction
- they move against the position too quickly and too strongly
- this argues against widening SHORT stops first
- this supports the idea that SHORT entries are poor or late

5) SHORT loss audit found two failure modes
SHORT loss clusters:
A) oversold late-entry shorts
- RSI < 30
- negative ema_slow_slope
- likely shorting into exhausted downside

B) suspicious counter-trend shorts
- RSI >= 50
- positive ema_slow_slope
- likely shorting while slow trend context is still rising

Conclusion:
- SHORT failure is not a single issue
- there are at least two bad entry patterns

6) Simple SHORT filters helped but did not save SHORT
Filter tests:
- ema_slow_slope < 0 helped
- RSI > 35 helped a bit
- combined filter helped the most among tested variants
- but all filtered SHORT variants remained negative

Conclusion:
- filtering removes garbage
- but the remaining SHORT trades still do not show enough edge

7) Final comparison confirmed LONG_ONLY is cleaner than LONG + filtered SHORT
Portfolio comparison:
- ALL: -63.26
- LONG_ONLY: -21.70
- LONG + filtered SHORT: -34.35

Conclusion:
- filtered SHORT is less bad than raw SHORT
- filtered SHORT still makes portfolio worse than LONG_ONLY
- LONG_ONLY is the current clean baseline

MAIN RESEARCH CONCLUSION

SHORT should be quarantined.

Not because we dislike SHORT in theory,
but because current notebook evidence says:

- raw SHORT is bad
- filtered SHORT is still bad
- SHORT does not currently earn its place
- LONG_ONLY is the better baseline for the next phase

RECOMMENDED REPO DIRECTION

Do not widen SHORT stops first.

Preferred next repo change:
- disable SHORT explicitly
- keep LONG enabled
- do it in a configurable and observable way
- avoid silent hidden behavior if possible
- preserve honest blocked/disabled reasoning in decisions or logs if feasible

BEST NEXT RESEARCH DIRECTION AFTER QUARANTINE

Move into LONG calibration.

Priority questions:
1) Why do LONG winners reach large MFE but total LONG performance is still negative?
2) Is trailing giving back too much?
3) Is confidence threshold too low even for LONG?
4) Do LONG losses cluster in specific volatility or volume contexts?

WORKING PRINCIPLES RECONFIRMED

- do not change repo logic before notebook evidence is strong enough
- isolate one failure mode at a time
- prefer explicit conclusions over vague optimism
- quarantine failing subsystems rather than endlessly tweaking them
- keep the strategy lab notebook as the current research notebook
- do not split into a new notebook yet unless this one becomes crowded

NEXT INTENDED STEP

After repo change to quarantine SHORT:
- run paper as LONG_ONLY baseline
- measure honestly
- then begin LONG-side calibration work
===
GENERAL HANDOFF — 2026-03-09 — MISSION 5B STRATEGY LAB UPDATE

CURRENT BIG PICTURE

System work has shifted from semantics proofing into strategy quality.

Already proven from earlier mission work:
- Mission 4 PASS
- Mission 5A PASS
- submit-boundary entry matrix proven
- STOP semantics proven during live position
- realistic paper runtime proven
- runtime observability and proof discipline improved

What changed in this cycle:
- we started serious notebook-based strategy analysis
- we stopped guessing from tails
- we moved into data-backed regime / side / MFE-MAE analysis

CURRENT STATUS

Runtime / system side:
- infrastructure and semantics remain in a good place
- paper runtime is still operating
- notebook storage under data/notebooks is working
- strategy lab notebook is now in active use

Research side:
- current notebook:
  data/notebooks/strategy_lab_experiment_01.ipynb
- notebook state verified and usable
- enough raw and processed data exists for exploratory work

MOST IMPORTANT NEW FINDING

SHORT is currently a liability.

This is not just a feeling.
Notebook evidence now supports it from multiple angles:

- side summary
- regime summary
- MFE/MAE
- SHORT loss filter audit
- filtered SHORT vs LONG_ONLY comparison

KEY STRATEGY FINDINGS

1) Strategy is losing overall
Current observed notebook summary:
- trades: 41
- wins: 9
- losses: 32
- total pnl: -63.26 USD
- avg pnl per trade: -1.54 USD

2) SHORT is much worse than LONG
- SHORT:
  19 trades
  2 wins
  17 losses
  -41.57 USD
  avg -2.19 USD/trade
- LONG:
  22 trades
  7 wins
  15 losses
  -21.70 USD
  avg -0.99 USD/trade

3) Worst strategy zone is SHORT in down regimes
Especially:
- SHORT + down + normal
- SHORT + down + high

4) MFE/MAE says SHORT is mainly an entry problem
SHORT losers:
- do not go far enough in favorable direction
- move against the trade too quickly
- widening stops would likely subsidize bad entries

5) Two distinct SHORT failure modes exist
A) late oversold shorts
B) suspicious counter-trend shorts

6) Filtering helped but did not rescue SHORT
Trend-confirmed / RSI-filtered SHORT is still negative

7) LONG_ONLY beats LONG + filtered SHORT
This is the final operationally important comparison.
Filtered SHORT still drags the portfolio below LONG_ONLY.

CURRENT BEST CONCLUSION

The cleanest next baseline is LONG_ONLY.

SHORT should be quarantined.

This is not a final philosophical claim about all SHORT logic forever.
It is the correct operational claim for the current system and current evidence.

RECOMMENDED NEXT REPO CHANGE

Make a minimal repo change to disable SHORT.

Preferred style:
- configurable
- explicit
- observable
- not a hidden silent hack if avoidable

Rationale:
- notebook evidence is now strong enough
- LONG_ONLY is the better baseline
- this reduces strategy complexity and focuses the next phase

WHAT NOT TO DO NEXT

- do not broaden optimization yet
- do not widen SHORT stops first
- do not try to rescue SHORT in production logic immediately
- do not start a new notebook unless needed
- do not bury this conclusion under future side quests

NEXT PHASE AFTER SHORT QUARANTINE

Mission direction:
LONG calibration

Key questions:
- why does LONG still lose overall despite good MFE on winners?
- is trailing giving back too much?
- should LONG confidence threshold be increased?
- do LONG losses cluster in specific volatility or volume conditions?
- can LONG_ONLY be moved from slightly negative toward break-even or positive?

CURRENT RESEARCH NOTEBOOK

Notebook:
data/notebooks/strategy_lab_experiment_01.ipynb

Verified contents include:
- raw data coverage
- trade summary
- feature distributions
- regime table
- side summary
- portfolio comparison
- MFE/MAE table
- MFE/MAE by side/outcome
- SHORT loss filter audit
- SHORT filter variant audit
- LONG_ONLY vs LONG+filtered_SHORT comparison

WORKING CONTRACT RECONFIRMED

- one mission at a time
- no guessing on notebook state
- no pretending we know what was not verified
- no repo changes before enough evidence exists
- prefer explicit, boring, observable changes
- step by step

HONEST CURRENT LABEL

Mission 5B strategy lab:
IN PROGRESS

Sub-status:
- analysis phase produced a decisive finding
- SHORT quarantine now has evidence support
- next meaningful move is repo change to establish LONG_ONLY baseline

===
MISSION LIST — NEXT ORDER

MISSION 5B.1
Quarantine SHORT in repo logic

Goal:
- establish LONG_ONLY as the new clean runtime baseline

Definition of done:
- SHORT entries are explicitly disabled
- LONG still functions normally
- behavior is configurable and observable
- runtime truth on old-box confirms new behavior

Notes:
- keep this change small
- do not mix with unrelated tuning

MISSION 5B.2
Run LONG_ONLY paper baseline

Goal:
- collect honest runtime behavior with SHORT removed

Definition of done:
- paper runtime observed under LONG_ONLY
- decisions/trades confirm only LONG entries
- new runtime snapshot captured
- new trade summary produced

MISSION 5B.3
Analyze LONG_ONLY quality

Goal:
- understand why LONG still loses overall
- isolate whether the main issue is entry selectivity, trailing, or regime mismatch

Key questions:
- what do LONG winners vs LONG losers look like?
- how much MFE is being given back?
- do LONG losses cluster by volatility, rsi, vol_z, or dollar_vol_z?
- is confidence threshold too permissive?

Definition of done:
- notebook analysis produces clear LONG-side findings
- one dominant LONG calibration hypothesis is selected

MISSION 5B.4
Choose first LONG calibration experiment

Preferred small candidates:
- raise LONG confidence threshold
- improve LONG trailing behavior
- test a simple LONG regime filter if evidence supports it

Definition of done:
- one change only
- notebook evidence justifies it
- exact file(s) identified before change

MISSION 5B.5
Apply one repo change for LONG calibration

Goal:
- implement only the chosen LONG-side change

Definition of done:
- local file truth verified
- deploy safely to old-box
- runtime truth verified
- new baseline observation starts

PARKED / DEFERRED

SHORT redesign
Status:
- deferred / quarantined

Reason:
- current evidence says SHORT does not earn its place yet
- revisit only after LONG baseline is understood

Broad parameter sweeps
Status:
- deferred

Reason:
- current data is enough for exploratory work, not broad-trust optimization

Notebook split into second notebook
Status:
- deferred

Reason:
- current notebook is still usable
- no need to fragment context yet

NON-NEGOTIABLE RULES FOR NEXT MISSIONS

- step by step
- know the exact file before proposing change
- no broad multi-change surgery
- verify old-box runtime truth
- do not hide logic silently if observability can be preserved
- keep conclusions honest
===

GENERAL HANDOFF — 2026-03-10 — MISSION 5B.2 LONG_ONLY BASELINE

CURRENT BIG PICTURE

System work is in a solid state, and strategy work has now crossed an important boundary:

SHORT has been quarantined in live runtime.

We are no longer debating whether SHORT is harmful in the current system.
That was decided by notebook evidence and then promoted into repo + runtime truth.

We are now entering the next clean phase:
observe and measure LONG_ONLY honestly before making further strategy changes.

WHAT IS ALREADY PROVEN

System / runtime proofs already established from earlier missions:
- Mission 4 PASS
- Mission 5A PASS
- submit-boundary entry matrix proven
- STOP semantics proven during live position
- realistic paper runtime proven
- restart-safe idempotency proven
- runtime observability improved
- notebook workflow established under data/notebooks

Strategy / research conclusions already established:
- overall strategy is losing
- LONG loses less than SHORT
- SHORT is the larger liability
- filtered SHORT still underperforms LONG_ONLY
- LONG_ONLY is the current cleaner baseline

MISSION 5B.1 — STATUS

PASS

What was done:
- exact side-control file identified: files/strategy/rules.py
- minimal repo change applied
- SHORT explicitly disabled via side enable flags
- LONG behavior left untouched
- no hidden threshold hack used
- no SHORT code deleted

Runtime proof:
- old-box file truth verified
- container/runtime truth verified
- mission proof script created:
  ops/mission5b1_short_quarantine_check.sh

Observed runtime evidence:
- repeated post-cutoff rows in decisions.csv show:
  should_enter=False
  side=SHORT
  reason=trend_down_but_short_disabled

Meaning:
- runtime still detects short-type opportunities
- policy explicitly blocks them
- observability is preserved
- SHORT has lost runtime privileges

CURRENT RUNTIME STATE

old-box services:
- paper up
- trade up
- dashboard up

Current runtime behavior:
- paper loop healthy
- decisions continue recording
- restart-safe idempotency still normal
- repeated SHORT-disabled evidence observed overnight

Canonical proof command for Mission 5B.1:
./ops/mission5b1_short_quarantine_check.sh 2026-03-09T20:51:00+00:00

CURRENT STRATEGY STATE

Active baseline:
- LONG_ONLY in runtime practice
- SHORT quarantined

Important note:
- this does NOT prove LONG is good
- this only proves SHORT is currently not allowed to degrade the portfolio further

We now need honest observation of LONG-only runtime behavior before any more repo strategy changes.

MISSION 5B.2 — CURRENT MISSION

Run LONG_ONLY paper baseline

Goal:
- observe runtime behavior with SHORT removed
- confirm new entries/trades are effectively LONG-only
- collect a cleaner baseline for the next round of notebook analysis

Definition of done:
- enough fresh runtime collected under SHORT quarantine
- no evidence of live SHORT entries after cutoff
- updated trades/decisions snapshot captured
- fresh trade summary available for LONG_ONLY baseline window

WHAT NOT TO DO YET

- do not re-enable SHORT
- do not tune LONG threshold yet
- do not change trailing yet
- do not widen stops
- do not mix in new strategy surgery before baseline observation is captured
- do not start broad optimization
- do not split notebooks unless needed

NEXT ANALYSIS DIRECTION AFTER BASELINE WINDOW

Mission 5B.3:
Analyze LONG_ONLY quality

Key questions:
- why does LONG still lose overall?
- are LONG entries too permissive?
- is trailing giving back too much MFE?
- do LONG losses cluster in certain volatility / volume / RSI conditions?
- is one simple LONG-side calibration hypothesis stronger than the others?

Best candidate categories later:
- raise LONG confidence threshold
- improve LONG trailing behavior
- add a simple LONG regime filter only if notebook evidence supports it

MISSION SCRIPT NOTE

Mission-scoped scripts are now considered valid when they are:
- repeatable
- read-only or narrowly scoped
- operationally important
- explicit about PASS / PENDING / FAIL
- tied clearly to one mission

Current example:
- ops/mission5b1_short_quarantine_check.sh

This is part of the project’s proof discipline and should be expanded selectively, not carelessly.

WORKING CONTRACT RECONFIRMED

- one mission at a time
- no guessing
- know exact file truth before changes
- prefer explicit and observable behavior
- verify runtime truth on old-box
- do not mix multiple strategy changes into one patch
- baseline first, calibration second

HONEST CURRENT LABEL

Mission 5B.2:
IN PROGRESS

Sub-status:
- SHORT quarantine complete and proven
- LONG_ONLY baseline now active
- current job is observation, not surgery
