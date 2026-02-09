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
