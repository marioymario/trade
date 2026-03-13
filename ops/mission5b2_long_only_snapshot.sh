#!/usr/bin/env bash
set -euo pipefail

# ops/mission5b2_long_only_snapshot.sh
#
# Part of:
#   Mission 5B.2 — Run LONG_ONLY paper baseline
#
# Big goal:
#   Produce a compact, read-only runtime snapshot of the current LONG_ONLY
#   baseline window without changing live behavior.
#
# What this script is for:
#   - summarize the post-cutoff observation window
#   - confirm services are up
#   - confirm SHORT quarantine is still visible in runtime truth
#   - summarize post-cutoff trades
#   - summarize post-cutoff decision flow
#   - provide a simple recommendation:
#       KEEP_COLLECTING_BASELINE
#       or
#       REVIEW_READY_FOR_5B3
#
# What this script does NOT do:
#   - does not deploy
#   - does not restart services
#   - does not modify files
#   - does not create fake data
#   - does not change strategy/runtime behavior
#
# Usage:
#   ./ops/mission5b2_long_only_snapshot.sh 2026-03-09T20:51:00+00:00
#
# Optional env overrides:
#   DECISIONS_CSV=...
#   TRADES_CSV=...
#   MIN_TRADES_FOR_REVIEW=8 ./ops/mission5b2_long_only_snapshot.sh <cutoff>
#
# Exit codes:
#   0 = snapshot completed
#   64 = usage error

CUTOFF="${1:-}"
if [[ -z "${CUTOFF}" ]]; then
  echo "USAGE: $0 <cutoff-timestamp-utc>"
  echo "Example: $0 2026-03-09T20:51:00+00:00"
  exit 64
fi

DECISIONS_CSV="${DECISIONS_CSV:-data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv}"
TRADES_CSV="${TRADES_CSV:-data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv}"
MIN_TRADES_FOR_REVIEW="${MIN_TRADES_FOR_REVIEW:-8}"

echo "=== Mission 5B.2 LONG_ONLY Baseline Snapshot ==="
echo "cutoff_utc=${CUTOFF}"
echo "decisions_csv=${DECISIONS_CSV}"
echo "trades_csv=${TRADES_CSV}"
echo "min_trades_for_review=${MIN_TRADES_FOR_REVIEW}"
echo

echo "--- Service Health ---"
docker compose ps
echo

python3 - "${CUTOFF}" "${DECISIONS_CSV}" "${TRADES_CSV}" "${MIN_TRADES_FOR_REVIEW}" <<'PY'
import csv
import sys
from collections import Counter
from pathlib import Path

cutoff = sys.argv[1]
decisions_csv = Path(sys.argv[2])
trades_csv = Path(sys.argv[3])
min_trades_for_review = int(sys.argv[4])

if not decisions_csv.exists():
    print(f"FAIL: missing decisions CSV: {decisions_csv}")
    sys.exit(0)

if not trades_csv.exists():
    print(f"FAIL: missing trades CSV: {trades_csv}")
    sys.exit(0)

with decisions_csv.open("r", newline="", encoding="utf-8") as f:
    decisions = list(csv.DictReader(f))

with trades_csv.open("r", newline="", encoding="utf-8") as f:
    trades = list(csv.DictReader(f))

post_decisions = [r for r in decisions if (r.get("timestamp", "") >= cutoff)]
post_trades = [r for r in trades if (r.get("entry_time", "") >= cutoff)]

print("--- Observation Window ---")
if post_decisions:
    print(f"decision_window_start={post_decisions[0].get('timestamp','')}")
    print(f"decision_window_end={post_decisions[-1].get('timestamp','')}")
    print(f"post_cutoff_decision_rows={len(post_decisions)}")
else:
    print("decision_window_start=")
    print("decision_window_end=")
    print("post_cutoff_decision_rows=0")
print(f"post_cutoff_trade_rows={len(post_trades)}")
print()

print("--- SHORT Quarantine Check ---")
short_disabled_rows = []
bad_live_short_rows = []
for r in post_decisions:
    side = r.get("entry_side", "")
    should_enter = r.get("entry_should_enter", "")
    reason = r.get("entry_reason", "")
    if side == "SHORT" and should_enter == "False" and "short_disabled" in reason:
        short_disabled_rows.append(r)
    if side == "SHORT" and should_enter == "True" and reason == "trend_down_and_confident":
        bad_live_short_rows.append(r)

print(f"short_disabled_rows={len(short_disabled_rows)}")
print(f"bad_live_short_rows={len(bad_live_short_rows)}")
if bad_live_short_rows:
    print("short_quarantine_status=BAD")
else:
    print("short_quarantine_status=PASS")
print()

print("--- Trades Summary (post-cutoff) ---")
sides = Counter((r.get("side","") or "").strip() for r in post_trades)
wins = 0
losses = 0
total_pnl = 0.0
gross_win = 0.0
gross_loss_abs = 0.0
win_pnls = []
loss_pnls = []

for r in post_trades:
    try:
        pnl = float(r.get("pnl_usd", "0") or 0.0)
    except Exception:
        pnl = 0.0
    total_pnl += pnl
    if pnl > 0:
        wins += 1
        gross_win += pnl
        win_pnls.append(pnl)
    elif pnl < 0:
        losses += 1
        gross_loss_abs += abs(pnl)
        loss_pnls.append(pnl)

trade_count = len(post_trades)
win_rate = (wins / trade_count * 100.0) if trade_count > 0 else 0.0
avg_win = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0.0
avg_loss = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
profit_factor = (gross_win / gross_loss_abs) if gross_loss_abs > 0 else 0.0

print(f"trade_count={trade_count}")
print(f"sides={dict(sides)}")
print(f"wins={wins}")
print(f"losses={losses}")
print(f"win_rate_pct={win_rate:.2f}")
print(f"total_pnl_usd={total_pnl:.2f}")
print(f"avg_win_usd={avg_win:.2f}")
print(f"avg_loss_usd={avg_loss:.2f}")
print(f"profit_factor={profit_factor:.3f}")
print()

print("--- Decision Flow Summary (post-cutoff) ---")
long_candidates = 0
long_enter_true = 0
long_blocked = 0
entry_reasons = Counter()
blocked_reasons = Counter()

for r in post_decisions:
    side = (r.get("entry_side","") or "").strip()
    should_enter = (r.get("entry_should_enter","") or "").strip()
    entry_reason = (r.get("entry_reason","") or "").strip()
    blocked = (r.get("entry_blocked_reason","") or "").strip()

    if entry_reason:
        entry_reasons[entry_reason] += 1
    if blocked:
        blocked_reasons[blocked] += 1

    if side == "LONG":
        long_candidates += 1
        if should_enter == "True":
            long_enter_true += 1
        if blocked:
            long_blocked += 1

print(f"long_candidate_rows={long_candidates}")
print(f"long_enter_true_rows={long_enter_true}")
print(f"long_blocked_rows={long_blocked}")
print(f"top_entry_reasons={entry_reasons.most_common(5)}")
print(f"top_blocked_reasons={blocked_reasons.most_common(5)}")
print()

print("--- First Take ---")
if bad_live_short_rows:
    print("first_take=SHORT quarantine regression detected")
elif trade_count == 0:
    print("first_take=No post-cutoff trades yet")
elif sides.get("SHORT", 0) > 0:
    print("first_take=Unexpected SHORT trades present post-cutoff")
elif avg_loss < 0 and abs(avg_loss) > max(avg_win, 0.0):
    print("first_take=LONG losses still larger than wins so far")
else:
    print("first_take=Baseline window is accumulating without obvious SHORT contamination")
print()

print("--- Recommendation ---")
if bad_live_short_rows:
    print("recommendation=NOT_READY__INVESTIGATE_SHORT_REGRESSION")
elif trade_count < min_trades_for_review:
    print("recommendation=KEEP_COLLECTING_BASELINE")
else:
    print("recommendation=REVIEW_READY_FOR_5B3")
PY
