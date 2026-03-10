# CANONICAL CURRENT STATE — MJÖLNIR

Date: 2026-03-10

This is the current canonical system-state document.

If another note, older handoff, or historical snapshot conflicts with this file, this file wins.

--------------------------------------------------
1) MISSION
--------------------------------------------------

Build an operationally boring, reproducible, observable paper-trading system with:

- local development
- old-box runtime
- file-based operator controls
- guarded execution
- decision logging
- degraded-mode safety
- disciplined deploy workflow
- notebook-based strategy evaluation
- mission-scoped proof scripts
- repo-aware local RAG assistant

This is not yet a real-money-ready system.

The project now has two active layers:

1. system / runtime layer
2. strategy / research layer

The system layer is in a solid enough state to support strategy work.
The current strategy layer focus is LONG_ONLY baseline observation.

--------------------------------------------------
2) TOPOLOGY
--------------------------------------------------

Local machine:
- edit code
- manage repo
- maintain docs/handoffs
- deploy to old-box

old-box:
- runtime execution
- paper loop
- dashboard
- operator control plane
- runtime-owned .env / data / trade_flags

Repo root:

~/Projects/trade

--------------------------------------------------
3) CONTAINERS / SERVICES
--------------------------------------------------

docker-compose.yml defines:

- trade
- paper
- dashboard

Main runtime loop:

paper -> python -m files.main

Current compose/runtime truth:
- paper bind-mounts ./files into /work/files
- paper bind-mounts ./data into /work/data
- paper uses working_dir=/work

This means:
- code changes in bind-mounted files do not require image rebuild
- restart paper is sufficient for code determinism after code change
- .env / compose env changes still require recreate

RAG stack is separate and uses:

- docker-compose.rag.yml
- rag/
- Ollama on host
- qwen2.5-coder:14b

--------------------------------------------------
4) SOURCE OF TRUTH
--------------------------------------------------

Code truth:
- local repo
- deployed to old-box via rsync

Runtime truth on old-box:
- .env
- /home/kk7wus/trade_flags/
- data/

Research truth:
- notebook analysis
- decisions.csv
- trades.csv
- runtime snapshots
- mission proof scripts

Important:
Do not assume local runtime state matches old-box runtime state.
Do not assume notebook conclusions are live until repo + runtime proof confirm them.

--------------------------------------------------
5) OPERATOR CONTROL PLANE
--------------------------------------------------

Runtime flag directory:

/home/kk7wus/trade_flags

Important files:
- STOP
- HALT
- ARM
- status.txt

Meaning:
- STOP = strongest stop condition
- HALT = block entries
- ARM = allow entries when present

These files affect runtime behavior immediately on next loop tick.
They do not require restart.

--------------------------------------------------
6) DEPLOY MODEL
--------------------------------------------------

Canonical deploy command from local:

OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh

Deploy contract:
- rsync
- no delete
- runtime-only state must not ship:
  - .env
  - data/
  - trade_flags/

After deploy:
- restart paper for code determinism when bind-mounted code changed
- force-recreate paper when env/compose/runtime container configuration changed

Known current dragon:
- deploy_oldbox.sh still needs more boring/deterministic hardening
- deploy verification should continue improving

--------------------------------------------------
7) RUNTIME RESTART RULES
--------------------------------------------------

Bind-mounted code changes:
- deploy
- restart paper

.env or compose env changes:
- force-recreate paper

Flag file changes:
- no restart needed

Canonical commands:

Restart paper:
docker compose restart paper

Recreate paper:
docker compose up -d --build --force-recreate paper

Operational lesson now confirmed:
- inspect compose truth before assuming rebuild is required
- prefer the smallest correct restart action

--------------------------------------------------
8) OBSERVABILITY
--------------------------------------------------

Primary truth artifact:
data/processed/decisions/{data_tag}/{symbol}/{timeframe}/decisions.csv

Also important:
data/processed/trades/{data_tag}/{symbol}/{timeframe}/trades.csv

Main observability contract:
- entry_reason = signal / strategy truth
- entry_blocked_reason = execution / guardrail truth

This separation is important and has been preserved.

Status beacon:
${FLAGS_DIR:-$HOME/trade_flags}/status.txt

Decisions truth is the primary runtime proof source for strategy-policy validation.

--------------------------------------------------
9) SAFETY RAILS
--------------------------------------------------

Confirmed current safety themes:
- GuardedBroker path exists
- ARM_BLOCK works
- STOP/HALT semantics exist in guarded flow
- daily/risk gates exist in the design
- machine-readable blocked reasons exist
- degraded mode is real
- submit-boundary enforcement is real

Current safety posture:
- safety semantics are much stronger than early project state
- strategy quality is now the larger concern, not basic execution discipline

--------------------------------------------------
10) DEGRADED MODE
--------------------------------------------------

Degraded mode has been proven through features_invalid behavior.

Observed examples:
DEGRADED(features_invalid_xN_in_last6)::...

This proves:
- degraded state tracking
- reason propagation
- decisions logging under degraded conditions
- continued observability during degraded operation

Cadence detector notes:
- cadence guard exists
- cadence design is robust / median-based
- deterministic cadence proof was not pushed further to avoid unnecessary complexity
- engineering stance: cadence design verified, degraded pipeline proven through features_invalid path

--------------------------------------------------
11) STRATEGY RESEARCH STATE
--------------------------------------------------

Strategy work is now active and notebook-driven.

Current primary notebook:
data/notebooks/strategy_lab_experiment_01.ipynb

Verified notebook capabilities include:
- raw data coverage checks
- decisions/trades loading
- feature computation
- regime analysis
- side analysis
- MFE/MAE analysis
- SHORT loss audit
- filtered SHORT audit
- LONG_ONLY vs LONG+filtered_SHORT comparison

Current research conclusion:
- strategy loses overall
- LONG loses less than SHORT
- SHORT is the larger liability
- filtered SHORT still underperforms LONG_ONLY
- LONG_ONLY is the current cleaner baseline

Operational conclusion:
SHORT has been quarantined.

Important:
This does not prove LONG is good.
It only proves SHORT does not currently deserve runtime privileges.

--------------------------------------------------
12) CURRENT STRATEGY POLICY
--------------------------------------------------

Current live runtime policy:
- LONG enabled
- SHORT quarantined

Exact control file:
files/strategy/rules.py

Current implementation style:
- explicit side enable flags
- minimal patch
- no deleted SHORT code
- no fake threshold hack
- no mixed LONG tuning included in the same change

Observed runtime proof:
post-cutoff decisions rows repeatedly show:

- should_enter=False
- side=SHORT
- reason=trend_down_but_short_disabled

Meaning:
- runtime still detects short-type setups
- policy blocks them explicitly
- observability is preserved
- SHORT has lost runtime privileges

--------------------------------------------------
13) MISSION-SCOPED PROOF SCRIPTS
--------------------------------------------------

Mission-scoped proof scripts are now a real part of project workflow.

Purpose:
- repeatable runtime proof
- reduced operator error
- clearer PASS / PENDING / FAIL outcomes
- easier handoff and reproducibility

Current example:
ops/mission5b1_short_quarantine_check.sh

This script proves Mission 5B.1 runtime truth by checking post-cutoff
SHORT-related rows in decisions.csv.

Mission scripts should be:
- mission-scoped
- small
- readable
- mostly read-only
- explicit about what they prove
- explicit about PASS / PENDING / FAIL

They should not become junk-drawer automation.

--------------------------------------------------
14) CURRENT RAG STATE
--------------------------------------------------

RAG is now a real part of the system environment.

Current RAG stack:
- local
- Dockerized
- terminal-first
- Ollama on host
- model: qwen2.5-coder:14b

Canonical commands:

Start assistant:
./rag/rag.sh

Re-index repo:
./rag/rag.sh index

Current RAG strengths:
- docs/operator questions work reasonably well
- grounded failure mode exists:
  Insufficient repository context.
- one-command launcher exists

Current RAG weaknesses:
- multi-hop code tracing still weak
- startup noise still exists
- retrieval ranking still imperfect for implementation traces

RAG is useful, but not yet teammate-grade for long code-path reconstruction.

--------------------------------------------------
15) DOCUMENTATION / HANDOFF MODEL
--------------------------------------------------

Current doc model:

Root current files:
- HANDOFF.md
- docs/CANONICAL_CURRENT_STATE.md

Archive files:
- docs/ARCHIVE_handoffs.md
- docs/ARCHIVE_project_snapshots.md

Rules:
- current files hold current truth only
- superseded versions move to archive files
- do not endlessly append old handoffs into root HANDOFF.md

This keeps current truth sharp and archive truth historical.

--------------------------------------------------
16) WORK RHYTHM / CONTRACT
--------------------------------------------------

The current engineering contract is:

- one mission at a time
- Step 0 always: identify exact file(s) first
- inspect full current file before edits
- use full-file replacements when practical
- deploy from local to old-box
- restart only what is needed
- prove with commands/outputs
- commit/push only after proof

Do not guess files.
Do not skip verification.
Do not contaminate a clean baseline with unrelated changes.

--------------------------------------------------
17) CURRENT SCORECARD
--------------------------------------------------

Overall paper-system maturity:
78%

Real-money readiness:
30%

Important interpretation:
- not a toy project
- not ready for real money
- system layer is materially stronger than before
- strategy edge is still not proven
- strategy quality is now the main constraint

Current area estimates:

- repo / architecture clarity: 86%
- development workflow discipline: 92%
- deploy / sync reliability: 66%
- runtime reproducibility: 78%
- safety rails / risk controls: 86%
- observability: 89%
- degraded mode / failure handling: 82%
- cadence protection: 79%
- paper execution path: 85%
- dashboard / operator UX: 73%
- documentation / handoff quality: 84%
- strategy research workflow: 81%
- repo RAG assistant: 69%
- team/process maturity: 90%

--------------------------------------------------
18) CURRENT TOP PRIORITIES
--------------------------------------------------

In order:

1. Observe LONG_ONLY paper baseline honestly
2. Capture fresh runtime snapshot under SHORT quarantine
3. Analyze LONG_ONLY behavior in notebook
4. Improve mission-script / commands documentation
5. Harden deploy_oldbox.sh and deploy verification
6. Improve dashboard/operator UX
7. Continue improving RAG until it is genuinely teammate-grade

--------------------------------------------------
19) CURRENT NON-NEGOTIABLES
--------------------------------------------------

- do not re-enable SHORT without evidence
- do not tune LONG yet before baseline observation
- do not mix multiple strategy changes into one patch
- do not touch runtime logic casually while LONG_ONLY baseline is being collected
- parallel-safe work is allowed only if it does not contaminate current runtime truth

--------------------------------------------------
20) CANONICAL RULE
--------------------------------------------------

If another document conflicts with this one:

- archive snapshot loses
- old handoff loses
- generic/generated handoff loses
- current canonical state wins

--------------------------------------------------
21) BOTTOM LINE
--------------------------------------------------

The system now has:
- real safety thinking
- real observability
- disciplined workflow
- mission-scoped proof discipline
- notebook-backed strategy decisions
- a proven live SHORT quarantine
- a usable repo assistant

The biggest current leverage is no longer just semantics proofing.

The biggest current leverage is:
- honest LONG_ONLY baseline observation
- disciplined next-step strategy calibration
- continued operational boringness
