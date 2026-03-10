# COMMANDS — MJÖLNIR

Date: 2026-03-10

Purpose:
This file is the practical operator command reference for common recurring tasks.

It is intentionally:
- short
- copy/paste-friendly
- task-oriented

It is NOT:
- the canonical system-state document
- the active handoff
- a historical archive

For current truth:
- see docs/CANONICAL_CURRENT_STATE.md

For current mission:
- see HANDOFF.md


--------------------------------------------------
1) LOCAL → OLD-BOX DEPLOY
--------------------------------------------------

Run from local repo root:

cd ~/Projects/trade
OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh

Notes:
- deploy is rsync-based
- no delete
- runtime-only state must not ship:
  - .env
  - data/
  - trade_flags/


--------------------------------------------------
2) PAPER RESTART / RECREATE
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade

Restart paper after bind-mounted code changes:
docker compose restart paper

Recreate paper after env / compose runtime changes:
docker compose up -d --build --force-recreate paper

Rule:
- code change in ./files -> restart paper
- env / compose change -> recreate paper
- flag-file change -> no restart needed


--------------------------------------------------
3) LOGS / STATUS
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade

Paper logs:
docker compose logs --tail=60 paper

Follow paper logs:
docker compose logs -f paper

All service status:
docker compose ps

Dashboard / paper / trade status:
docker compose ps


--------------------------------------------------
4) MISSION 5B.1 — SHORT QUARANTINE PROOF
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade
./ops/mission5b1_short_quarantine_check.sh 2026-03-09T20:51:00+00:00

Expected good result:
STATUS: PASS

Meaning:
- post-cutoff SHORT candidates are explicitly disabled
- runtime truth confirms SHORT quarantine is live


--------------------------------------------------
5) DECISIONS / TRADES QUICK CHECKS
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade

Decisions CSV path:
data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv

Trades CSV path:
data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv


Last 20 decisions (selected fields):
python3 - <<'PY'
import csv
from pathlib import Path

p = Path("data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv")

with p.open("r", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

for row in rows[-20:]:
    print(
        row.get("timestamp", ""),
        "| should_enter=", row.get("entry_should_enter", ""),
        "| side=", row.get("entry_side", ""),
        "| reason=", row.get("entry_reason", ""),
        "| blocked=", row.get("entry_blocked_reason", ""),
        sep=""
    )
PY


Last 20 trades:
python3 - <<'PY'
import csv
from pathlib import Path

p = Path("data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv")

with p.open("r", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

for row in rows[-20:]:
    print(
        row.get("entry_time", ""),
        "| side=", row.get("side", ""),
        "| pnl_usd=", row.get("pnl_usd", ""),
        sep=""
    )
PY


--------------------------------------------------
6) POST-RESTART SHORT CHECK (MANUAL FORM)
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade

python3 - <<'PY'
import csv
from pathlib import Path

cutoff = "2026-03-09T20:51:00+00:00"
p = Path("data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv")

with p.open("r", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

found = False
for row in rows:
    ts = row.get("timestamp", "")
    if ts < cutoff:
        continue
    side = row.get("entry_side", "")
    reason = row.get("entry_reason", "")
    blocked = row.get("entry_blocked_reason", "")
    should_enter = row.get("entry_should_enter", "")
    if side == "SHORT" or "short_disabled" in reason or "short_disabled" in blocked:
        found = True
        print(
            ts,
            "| should_enter=", should_enter,
            "| side=", side,
            "| reason=", reason,
            "| blocked=", blocked,
            sep=""
        )

if not found:
    print("NO_POST_RESTART_SHORT_ROWS")
PY


--------------------------------------------------
7) VERIFY LIVE FILE TRUTH ON OLD-BOX
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade

Check current SHORT quarantine code in rules.py:
grep -n "ENABLE_SHORT\|trend_down_but_short_disabled\|trend_down_and_confident" files/strategy/rules.py

Check compose truth for paper:
docker compose config | sed -n '/paper:/,/^[^[:space:]]/p'


--------------------------------------------------
8) RAG COMMANDS
--------------------------------------------------

Run from repo root:

Start assistant:
./rag/rag.sh

Ask one question:
./rag/rag.sh "Where is GuardedBroker used?"

Re-index repo:
./rag/rag.sh index

Show help:
./rag/rag.sh --help


--------------------------------------------------
9) NOTEBOOK / JUPYTER
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade
docker compose ps
docker compose logs --tail=30 trade

Notebook / lab is exposed through the trade service on localhost binding configured in compose.


--------------------------------------------------
10) OPERATOR FLAGS
--------------------------------------------------

Run on old-box unless otherwise noted.

Flags directory:
~/trade_flags

Check flags:
ls -l ~/trade_flags

Meaning:
- STOP = strongest stop condition
- HALT = block entries
- ARM = allow entries when present

These act on next loop tick and do not require restart.


--------------------------------------------------
11) END-OF-DAY LIGHT CHECK
--------------------------------------------------

Run on old-box:

cd ~/Projects/trade
./ops/mission5b1_short_quarantine_check.sh 2026-03-09T20:51:00+00:00
docker compose logs --tail=20 paper
docker compose ps

Use this for a light sanity check before stepping away.


--------------------------------------------------
12) RULES OF USE
--------------------------------------------------

- prefer reading runtime truth before guessing
- use restart only when restart is enough
- use recreate only when runtime container/env truth changed
- do not mix proof work with new repo surgery
- update this file when a recurring workflow becomes stable
