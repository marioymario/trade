# CANONICAL CURRENT STATE — MJÖLNIR

Date: 2026-03-06

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
- repo-aware local RAG assistant

This is not yet a real-money-ready system.

--------------------------------------------------
2) TOPOLOGY
--------------------------------------------------

Local machine:
- edit code
- manage repo
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

Important:
Do not assume local runtime state matches old-box runtime state.

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

OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ops/deploy_oldbox.sh

Deploy contract:
- rsync
- no delete
- runtime-only state must not ship:
  - .env
  - data/
  - trade_flags/

After deploy:
- restart paper for code determinism when code changed
- force-recreate paper when .env changed

Known current dragon:
- deploy_oldbox.sh still needs more boring/deterministic hardening

--------------------------------------------------
7) RUNTIME RESTART RULES
--------------------------------------------------

Code changes in bind-mounted files:
- deploy
- restart paper

.env changes:
- force-recreate paper

Flag file changes:
- no restart needed

Canonical commands:

Restart paper:
docker compose restart paper

Recreate paper:
docker compose up -d --force-recreate paper

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
11) CURRENT RAG STATE
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
12) WORK RHYTHM / CONTRACT
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

--------------------------------------------------
13) CURRENT SCORECARD
--------------------------------------------------

Overall paper-system maturity:
74%

Real-money readiness:
28%

Important interpretation:
- not a toy project
- not ready for real money
- strong engineering foundation
- still has operational dragons left

Current area estimates:

- repo / architecture clarity: 85%
- development workflow discipline: 90%
- deploy / sync reliability: 62%
- runtime reproducibility: 70%
- safety rails / risk controls: 84%
- observability: 86%
- degraded mode / failure handling: 80%
- cadence protection: 78%
- paper execution path: 82%
- dashboard / operator UX: 73%
- documentation / handoff quality: 76%
- repo RAG assistant: 68%
- team/process maturity: 88%

--------------------------------------------------
14) CURRENT TOP PRIORITIES
--------------------------------------------------

In order:

1. Harden deploy_oldbox.sh and deploy verification
2. Normalize canonical docs
3. Increase unattended paper confidence
4. Improve dashboard/operator UX
5. Continue improving RAG until it is genuinely teammate-grade

--------------------------------------------------
15) CANONICAL RULE
--------------------------------------------------

If another document conflicts with this one:

- archive snapshot loses
- generic/generated handoff loses
- current canonical state wins

--------------------------------------------------
16) BOTTOM LINE
--------------------------------------------------

The system now has:
- real safety thinking
- real observability
- disciplined workflow
- real runtime contracts
- a usable repo assistant

The biggest remaining leverage is operational boringness:
- deploy clarity
- runtime reproducibility
- cleaner docs
- trustworthy long-run behavior
