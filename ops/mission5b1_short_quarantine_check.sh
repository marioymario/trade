#!/usr/bin/env bash
#set -euo pipefail

# mission5b1_short_quarantine_check.sh
#
# Part of:
#   GENERAL HANDOFF — Mission 5B.1
#   Goal: quarantine SHORT and establish LONG_ONLY as the new clean baseline.
#
# What this script does:
#   Read the runtime decisions CSV after a supplied cutoff timestamp and inspect
#   post-cutoff SHORT-related entry rows.
#
# Why it exists:
#   After changing repo logic, we do not want to "assume" the runtime is using
#   the new behavior. We want a repeatable proof command that answers:
#
#     - PASS: SHORT is explicitly disabled in live decisions truth
#     - PENDING: no post-cutoff SHORT candidate has appeared yet
#     - FAIL: SHORT is still being allowed post-cutoff
#
# How it fits into the system:
#   This trading stack has two important truths:
#
#   1) Repo truth
#      The code we changed locally / on old-box.
#
#   2) Runtime truth
#      What paper is actually doing, verified from outputs like:
#        data/processed/decisions/.../decisions.csv
#        data/processed/trades/.../trades.csv
#
#   This script is a runtime-truth proof helper.
#   It does not deploy, restart, edit files, or simulate data.
#   It only reads decisions.csv and reports whether the SHORT quarantine is:
#     PASS / PENDING / FAIL
#
# Expected good evidence:
#   should_enter=False
#   side=SHORT
#   reason=trend_down_but_short_disabled
#
# Expected bad evidence:
#   should_enter=True
#   side=SHORT
#   reason=trend_down_and_confident
#
# Usage:
#   ./ops/mission5b1_short_quarantine_check.sh 2026-03-09T20:51:00+00:00
#
# Optional env overrides:
#   DECISIONS_CSV=custom/path.csv ./ops/mission5b1_short_quarantine_check.sh <cutoff>
#
# Exit codes:
#   0 = PASS
#   1 = FAIL
#   2 = PENDING
#   64 = usage / input error
#
# Notes:
#   - This script is intentionally mission-scoped.
#   - This script is intentionally read-only.
#   - This script proves only Mission 5B.1 SHORT quarantine behavior.
#   - It does NOT prove overall profitability or LONG quality.

CUT_OFF="${1:-}"
if [[ -z "${CUT_OFF}" ]]; then
  echo "USAGE: $0 <cutoff-timestamp-utc>"
  echo "Example: $0 2026-03-09T20:51:00+00:00"
  exit 64
fi

DECISIONS_CSV="${DECISIONS_CSV:-data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv}"

if [[ ! -f "${DECISIONS_CSV}" ]]; then
  echo "FAIL: decisions CSV not found: ${DECISIONS_CSV}"
  exit 1
fi

echo "=== Mission 5B.1 SHORT Quarantine Check ==="
echo "cutoff_utc=${CUT_OFF}"
echo "decisions_csv=${DECISIONS_CSV}"
echo

python3 - "${CUT_OFF}" "${DECISIONS_CSV}" <<'PY'
import csv
import sys
from pathlib import Path

cutoff = sys.argv[1]
csv_path = Path(sys.argv[2])

rows = []
with csv_path.open("r", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

post_cutoff_rows = []
for row in rows:
    ts = row.get("timestamp", "")
    if ts >= cutoff:
        post_cutoff_rows.append(row)

interesting = []
for row in post_cutoff_rows:
    side = row.get("entry_side", "")
    reason = row.get("entry_reason", "")
    blocked = row.get("entry_blocked_reason", "")
    if side == "SHORT" or "short_disabled" in reason or "short_disabled" in blocked:
        interesting.append(row)

if not interesting:
    print("STATUS: PENDING")
    print("DETAIL: no post-cutoff SHORT-related decision rows yet")
    sys.exit(2)

saw_pass = False
saw_fail = False

print("POST-CUTOFF SHORT-RELATED ROWS:")
for row in interesting:
    ts = row.get("timestamp", "")
    should_enter = row.get("entry_should_enter", "")
    side = row.get("entry_side", "")
    reason = row.get("entry_reason", "")
    blocked = row.get("entry_blocked_reason", "")

    print(
        f"{ts}"
        f" | should_enter={should_enter}"
        f" | side={side}"
        f" | reason={reason}"
        f" | blocked={blocked}"
    )

    if side == "SHORT" and should_enter == "False" and "short_disabled" in reason:
        saw_pass = True

    if side == "SHORT" and should_enter == "True" and reason == "trend_down_and_confident":
        saw_fail = True

print()

if saw_fail:
    print("STATUS: FAIL")
    print("DETAIL: found live SHORT entry permission after cutoff")
    sys.exit(1)

if saw_pass:
    print("STATUS: PASS")
    print("DETAIL: found explicit SHORT-disabled runtime evidence after cutoff")
    sys.exit(0)

print("STATUS: PENDING")
print("DETAIL: found SHORT-related rows, but not yet a decisive PASS/FAIL pattern")
sys.exit(2)
PY
