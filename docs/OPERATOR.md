# OPERATOR GUIDE — v0.2.2

This is a **command-only, failure-oriented guide** for operating the system.
If something is wrong, start at the top and work downward.

---

## 0) Preconditions (do not skip)

From repo root:

```bash
pwd
ls -la docker-compose.yml files ops
```

Docker must be running:

```bash
docker info >/dev/null && echo "docker ok"
```

---

## 1) Fastest truth: status beacon (FIRST THING TO RUN)

### 1.1 Read beacon

```bash
tail -n 20 "${FLAGS_DIR:-$HOME/trade_flags}/status.txt"
```

Expected:
- `format_version=1`
- `ts_utc=...Z` advances every ~2 minutes
- `paper_status=up`, `trade_status=up`, `dashboard_status=up`
- `decisions_mtime_utc=...Z` advances on bar cadence (e.g. ~5m)

If beacon is stale or missing → go to section **2**.

### 1.2 Confirm beacon file is updating

```bash
stat -c 'status_mtime=%y size=%s' "${FLAGS_DIR:-$HOME/trade_flags}/status.txt"
```

---

## 2) systemd (ops hardening) — required for “boring reboots”

We run via **user systemd**:
- `trade-stack.service` starts `docker compose up -d` at boot
- `trade-heartbeat.timer` runs heartbeat every 2 minutes

### 2.1 Ensure linger is enabled (so timers run after reboot unattended)

Run once (on the target machine):

```bash
sudo loginctl enable-linger "$USER"
```

Verify:

```bash
loginctl show-user "$USER" -p Linger
```

Expected: `Linger=yes`

### 2.2 Check systemd units

```bash
systemctl --user status trade-stack.service --no-pager
systemctl --user status trade-heartbeat.timer --no-pager
```

Expected:
- `trade-stack.service`: `Active: active (exited)` and last start `SUCCESS`
- `trade-heartbeat.timer`: `Active: active (waiting)` with a real `Trigger:` time (not `n/a`)

### 2.3 If heartbeat timer is broken (Trigger: n/a)

Fix by switching to a calendar schedule:

```bash
cat > ~/.config/systemd/user/trade-heartbeat.timer <<'EOF'
[Unit]
Description=Run trade heartbeat every 2 minutes

[Timer]
OnCalendar=*:0/2
AccuracySec=10s
Persistent=true
Unit=trade-heartbeat.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user restart trade-heartbeat.timer
systemctl --user status trade-heartbeat.timer --no-pager
```

---

## 3) Health check: containers + loop

### 3.1 Containers up

```bash
docker compose ps
```

Expected: `paper`, `trade`, `dashboard` are Up.

### 3.2 Paper loop alive (recent logs)

```bash
docker compose logs --tail=80 paper
```

You must see recent timestamps and messages consistent with:
- startup
- market fetch
- persistence
- decisions being written

If logs stop advancing → LIVE is stalled.

### 3.3 Permission errors (CRITICAL)

```bash
docker compose logs --tail=400 paper | grep -i "permission" || echo "no permission errors"
```

If you see `PermissionError`:
- STOP
- do not trust outputs written after that point

---

## 4) Decision stream sanity (LIVE)

Decisions path is derived from env. Common vars:
- `DATA_TAG` (e.g. `paper_oldbox_live`)
- `SYMBOL` (e.g. `BTC_USD` or `BTC/USD`)
- `TIMEFRAME` (e.g. `5m`)

Heartbeat normalizes symbol path `BTC/USD -> BTC_USD` for filesystem layout.

### 4.1 Locate decisions.csv on the machine

```bash
PROJ="$HOME/Projects/trade"
cd "$PROJ" || exit 1
python - <<'PY'
import os
data_tag=os.getenv("DATA_TAG","paper_oldbox_live")
symbol=os.getenv("SYMBOL","BTC_USD").replace("/","_")
tf=os.getenv("TIMEFRAME","5m")
p=f"data/processed/decisions/{data_tag}/{symbol}/{tf}/decisions.csv"
print(p)
PY
```

### 4.2 Check last row and mtime

```bash
D="$(python - <<'PY'
import os
data_tag=os.getenv("DATA_TAG","paper_oldbox_live")
symbol=os.getenv("SYMBOL","BTC_USD").replace("/","_")
tf=os.getenv("TIMEFRAME","5m")
print(f"data/processed/decisions/{data_tag}/{symbol}/{tf}/decisions.csv")
PY
)"
stat -c 'csv_mtime=%y size=%s path=%n' "$D"
tail -n 1 "$D"
```

---

## 5) Control commands

### 5.1 Start LIVE

```bash
docker compose up -d
docker compose logs -f paper
```

### 5.2 Stop LIVE cleanly

```bash
docker compose down
```

### 5.3 Restart LIVE only

```bash
docker compose restart paper
```

LIVE must resume without duplicating decisions.

---

## 6) Backtest execution (windowed)

```bash
RUNID="bt_$(date +%Y%m%d_%H%M%S)"
START_TS_MS="PASTE_START_TS_MS"
END_TS_MS="PASTE_END_TS_MS"

START_TS_MS="$START_TS_MS" \
END_TS_MS="$END_TS_MS" \
RUNID="$RUNID" \
make backtest
```

Outputs:
- `data/processed/decisions/*bt_${RUNID}*/`
- `data/processed/trades/*bt_${RUNID}*/`

---

## 7) Equivalence validation

```bash
docker compose run --rm trade python -m files.main_live_vs_backtest_equivalence \
  --symbol BTC_USD \
  --timeframe 5m \
  --live-tag "${DATA_TAG:-paper_oldbox_live}" \
  --bt-tag "coinbase_bt_${RUNID}"
```

Expected:
- `[decisions] PASS`
- `[trades] PASS`
- `OVERALL PASS`

---

## 8) Failure modes & meaning (operator table)

Symptom | Meaning
---|---
Beacon stale | heartbeat not running; check systemd timer + linger
Containers down | stack not started; check trade-stack.service and docker
PermissionError | filesystem ownership bug; stop and investigate
Non-monotonic ts_ms | invariant violation
PnL mismatch only | expected (Phase 2A)
Equivalence fail | stop — investigate

---

## 9) What NOT to do (operator rules)

- Do not edit CSVs manually
- Do not delete rows to “fix” gaps
- Do not mix LIVE and BT outputs
- Do not judge correctness by PnL

---

## 10) Golden rule

If unsure:
- Trust the invariants, not the outcomes.

Correctness first. Speed second.
