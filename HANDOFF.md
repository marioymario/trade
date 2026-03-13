# HANDOFF — 2026-03-10 — MISSION 5B.2 LONG_ONLY BASELINE

CURRENT BIG PICTURE

We have crossed an important strategy boundary.

SHORT is no longer an active runtime side.
It has been quarantined in repo logic and proven disabled in live runtime truth.

The project is no longer focused mainly on semantics proofing.
The system/runtime layer is now strong enough to support cleaner strategy work.

We are now in the next phase:
observe and measure LONG_ONLY honestly before making any new strategy changes.

--------------------------------------------------
1) CURRENT STATUS
--------------------------------------------------

Mission 5B.1:
PASS

Current live strategy policy:
- LONG enabled
- SHORT quarantined

Current active mission:
- Mission 5B.2 — Run LONG_ONLY paper baseline

Current sub-status:
- baseline is running
- paper runtime is healthy
- repeated runtime proof shows SHORT candidates are explicitly blocked
- no new strategy surgery should be done yet

--------------------------------------------------
2) WHAT WAS JUST PROVEN
--------------------------------------------------

Mission 5B.1 proved that SHORT quarantine is real in runtime truth.

Exact control file:
- files/strategy/rules.py

Implemented behavior:
- explicit side enable flags
- ENABLE_LONG = True
- ENABLE_SHORT = False

Important design choices:
- minimal patch
- no deleted SHORT code
- no fake threshold hack
- no mixed LONG tuning in same change
- observability preserved

Decisive runtime evidence from decisions.csv:
- should_enter=False
- side=SHORT
- reason=trend_down_but_short_disabled

This was observed repeatedly post-cutoff, not just once.

Meaning:
- runtime still detects short-type setups
- policy explicitly blocks them
- SHORT has lost runtime privileges
- Mission 5B.1 is closed

--------------------------------------------------
3) CURRENT RUNTIME HEALTH
--------------------------------------------------

old-box service state:
- paper up
- trade up
- dashboard up

Observed behavior:
- paper loop healthy
- restart-safe idempotency still normal
- decisions continue recording
- repeated SHORT-disabled evidence present overnight and after restart
- no obvious crash/restart weirdness

Current runtime is stable enough to continue baseline observation.

--------------------------------------------------
4) CANONICAL PROOF COMMAND
--------------------------------------------------

On old-box:

cd ~/Projects/trade
./ops/mission5b1_short_quarantine_check.sh 2026-03-09T20:51:00+00:00

Expected result:
STATUS: PASS

This script is now the canonical runtime proof for Mission 5B.1.

--------------------------------------------------
5) WHAT CHANGED IN REPO
--------------------------------------------------

Committed/pushed milestone:
- SHORT quarantine patch in files/strategy/rules.py
- COMMANDS.md added
- ops/README.md added/updated
- ops/README_missions.md added
- docs/CANONICAL_CURRENT_STATE.md updated

Milestone tag created:
- mission5b1-short-quarantine-pass

This tag represents:
- committed
- pushed
- deployed
- runtime-verified SHORT quarantine

--------------------------------------------------
6) CURRENT STRATEGY CONTEXT
--------------------------------------------------

Notebook research already established:

- overall strategy loses
- LONG loses less than SHORT
- SHORT is the larger liability
- filtered SHORT still underperforms LONG_ONLY
- LONG_ONLY is the cleaner current baseline

Important interpretation:
This does NOT prove LONG is good.
It only proves SHORT does not currently deserve to remain active.

That is why Mission 5B.2 exists.

--------------------------------------------------
7) CURRENT MISSION — 5B.2
--------------------------------------------------

Mission:
Run LONG_ONLY paper baseline

Goal:
- observe runtime behavior with SHORT removed
- confirm the active runtime baseline is effectively LONG-only
- gather honest evidence before any new LONG-side tuning

Definition of done:
- enough fresh runtime under SHORT quarantine
- no evidence of live SHORT entries after cutoff
- updated runtime snapshot captured
- updated trades/decisions summary available
- enough baseline evidence exists to support Mission 5B.3 analysis

--------------------------------------------------
8) WHAT NOT TO DO
--------------------------------------------------

Do not:

- re-enable SHORT
- tune LONG threshold yet
- change trailing yet
- widen stops
- add a regime filter yet
- perform broad optimization
- mix strategy changes into the baseline window
- casually touch runtime logic while baseline is being collected

This phase is observation first, calibration later.

--------------------------------------------------
9) SAFE PARALLEL WORK
--------------------------------------------------

Allowed parallel-safe work, as long as it does not contaminate runtime truth:

- docs cleanup
- handoff cleanup
- commands documentation
- mission-script documentation
- support tooling that is read-only
- local inventory/cleanup planning for non-runtime files

Not allowed right now:
- changing active trading logic
- changing paper semantics
- touching anything that muddies the LONG_ONLY baseline

--------------------------------------------------
10) CURRENT DOCUMENT MODEL
--------------------------------------------------

Current files:
- HANDOFF.md = current mission handoff only
- docs/CANONICAL_CURRENT_STATE.md = current canonical truth
- COMMANDS.md = recurring operator commands

Archive files:
- docs/ARCHIVE_handoffs.md
- docs/ARCHIVE_project_snapshots.md

Rule:
- current files stay current-only
- superseded versions move to archive

--------------------------------------------------
11) CURRENT MISSION-SCRIPT MODEL
--------------------------------------------------

Mission scripts are now accepted as part of workflow when they are:

- mission-scoped
- repeatable
- small
- mostly read-only
- explicit about PASS / PENDING / FAIL

Current example:
- ops/mission5b1_short_quarantine_check.sh

This script proved valuable and should be treated as part of the project’s proof discipline.

--------------------------------------------------
12) SUGGESTED NEXT MOVES
--------------------------------------------------

In order:

1. keep LONG_ONLY baseline running
2. capture a fresh runtime snapshot later
3. summarize fresh decisions/trades under SHORT quarantine
4. move into Mission 5B.3 LONG_ONLY analysis
5. only then choose one LONG calibration hypothesis

Preferred future calibration candidates:
- raise LONG confidence threshold
- improve LONG trailing behavior
- add a simple LONG regime filter only if notebook evidence supports it

But none of those should be changed yet.

--------------------------------------------------
13) WORKING CONTRACT
--------------------------------------------------

- one mission at a time
- know exact file before editing
- inspect current full file before change
- prefer minimal explicit patches
- deploy from local to old-box
- restart only what is needed
- prove with runtime truth
- commit/push after proof
- do not confuse repo truth with runtime truth

--------------------------------------------------
14) HONEST CURRENT LABEL
--------------------------------------------------

Mission 5B.2:
IN PROGRESS

Sub-status:
- SHORT quarantine complete and proven
- LONG_ONLY baseline active
- current job is observation, not surgery

--------------------------------------------------
15) BOTTOM LINE
--------------------------------------------------

The project is in a stronger place now.

System/runtime work is no longer the main blocker.
The main blocker is strategy quality.

SHORT has been judged, quarantined, and stripped of runtime privileges.
Now the job is to let LONG_ONLY speak for itself.

Do not rush the next change.
Collect the baseline honestly first.
