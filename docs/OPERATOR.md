# OPERATOR GUIDE — v0.2.1

This document is a **command-only, failure-oriented guide** for operating the system.
If something is wrong, start at the top and work downward.

---

## 0) Preconditions (do not skip)

From repo root:
```bash
`pwd``

Must be the project root containing:

    docker-compose.yml

    files/

    data/

Docker must be running:

docker info >/dev/null && echo "docker ok"

1) Health check (FIRST THING TO RUN)
1.1 Containers up

docker compose ps

Expected:

    paper → Up

    trade → Up

If either is missing or restarting → stop here.
1.2 LIVE loop alive (paper)

docker compose logs --tail=50 paper

You must see recent timestamps and messages like:

    Trading system starting

    Fetched market data

    Persisted bars

    Decision recorded

If logs stop advancing → LIVE is stalled.
1.3 No permission errors (CRITICAL)

docker compose logs --tail=200 paper | grep -i "permission" || echo "no permission errors"

Expected:

no permission errors

If you see PermissionError:

    STOP

    Do not trust data written after that point

1.4 Decision stream growing

tail -n 5 data/processed/decisions/coinbase/BTC_USD/5m/decisions.csv

Verify:

    ts_ms increases in fixed 5m steps (300000 ms)

    New rows appear over time

2) Structural invariants (quick sanity)
2.1 Monotonic decision timestamps

docker compose run --rm trade python - <<'PY'
import csv
p="data/processed/decisions/coinbase/BTC_USD/5m/decisions.csv"
ts=[]
with open(p) as f:
    r=csv.DictReader(f)
    for row in r:
        ts.append(int(float(row["ts_ms"])))
bad=[(a,b) for a,b in zip(ts,ts[1:]) if b<=a]
print("rows:",len(ts))
print("violations:",bad[:5])
PY

Expected:

violations: []

2.2 Cadence gaps (5m bars)

docker compose run --rm trade python - <<'PY'
import csv
p="data/processed/decisions/coinbase/BTC_USD/5m/decisions.csv"
step=300000
ts=[]
with open(p) as f:
    r=csv.DictReader(f)
    for row in r:
        ts.append(int(float(row["ts_ms"])))
ts=sorted(set(ts))
gaps=[(a,b,b-a) for a,b in zip(ts,ts[1:]) if b-a!=step]
print("gap_count:",len(gaps))
print("first_gaps:",gaps[:5])
PY

Expected:

gap_count: 0

3) Control commands
3.1 Start LIVE

docker compose up -d
docker compose logs -f paper

3.2 Stop LIVE cleanly

docker compose down

3.3 Restart LIVE only

docker compose restart paper

LIVE must resume without duplicating decisions.
4) BACKTEST execution
4.1 Run windowed BACKTEST

RUNID="bt_$(date +%Y%m%d_%H%M%S)"
START_TS_MS="PASTE_START_TS_MS"
END_TS_MS="PASTE_END_TS_MS"

START_TS_MS="$START_TS_MS" \
END_TS_MS="$END_TS_MS" \
RUNID="$RUNID" \
make backtest

BACKTEST output goes to:

data/processed/decisions/coinbase_bt_${RUNID}/
data/processed/trades/coinbase_bt_${RUNID}/

5) Equivalence validation

docker compose run --rm trade python -m files.main_live_vs_backtest_equivalence \
  --symbol BTC_USD \
  --timeframe 5m \
  --live-tag coinbase \
  --bt-tag "coinbase_bt_${RUNID}"

Expected:

[decisions] PASS
[trades]    PASS
OVERALL PASS

6) Failure modes & meaning
Symptom	Meaning
Missing decisions	LIVE was down
PermissionError	Filesystem ownership bug
Non-monotonic ts_ms	Invariant violation
PnL mismatch only	Expected (Phase 2A)
Equivalence fail	Stop — investigate
7) What NOT to do (operator rules)

    Do not edit CSVs manually

    Do not delete rows to “fix” gaps

    Do not mix LIVE and BT outputs

    Do not judge correctness by PnL

8) Golden rule

If unsure:

    Trust the invariants, not the outcomes.

Correctness first. Speed second.
