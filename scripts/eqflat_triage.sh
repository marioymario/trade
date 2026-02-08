#!/usr/bin/env bash
# eqflat_triage.sh
# Intentionally NOT using `set -euo pipefail` for operator resilience.

DATA_TAG="${DATA_TAG:-${1:-}}"
RUNID="${RUNID:-${2:-}}"
BT_TAG_OVERRIDE="${BT_TAG:-}"

if [[ -z "$DATA_TAG" ]]; then
  echo "usage:"
  echo "  DATA_TAG=<tag> make eqflat_triage"
  echo "  DATA_TAG=<tag> RUNID=<runid> make eqflat_triage"
  echo "  DATA_TAG=<tag> BT_TAG=<bt_tag> make eqflat_triage"
  exit 2
fi

SYMBOL="${SYMBOL:-BTC_USD}"
TIMEFRAME="${TIMEFRAME:-5m}"

# Determine BT_TAG
if [[ -n "$BT_TAG_OVERRIDE" ]]; then
  BT_TAG="$BT_TAG_OVERRIDE"
elif [[ -n "$RUNID" ]]; then
  BT_TAG="${DATA_TAG}_bt_${RUNID}"
else
  # Infer the most recent eqflat bt tag based on trades folders
  inferred="$(
    ls -1d "data/processed/trades/${DATA_TAG}_bt_eqflat_"* 2>/dev/null |
      sort |
      tail -n 1 |
      xargs -n1 basename 2>/dev/null
  )"
  if [[ -z "$inferred" ]]; then
    echo "ERROR: could not infer bt tag under data/processed/trades/${DATA_TAG}_bt_eqflat_*" >&2
    exit 2
  fi
  BT_TAG="$inferred"
fi

LIVE_DEC="data/processed/decisions/${DATA_TAG}/${SYMBOL}/${TIMEFRAME}/decisions.csv"
BT_DEC="data/processed/decisions/${BT_TAG}/${SYMBOL}/${TIMEFRAME}/decisions.csv"
LIVE_TR="data/processed/trades/${DATA_TAG}/${SYMBOL}/${TIMEFRAME}/trades.csv"
BT_TR="data/processed/trades/${BT_TAG}/${SYMBOL}/${TIMEFRAME}/trades.csv"

echo "== eqflat_triage =="
echo "DATA_TAG=$DATA_TAG"
echo "RUNID=${RUNID:-<inferred>}"
echo "BT_TAG=$BT_TAG"
echo "SYMBOL=$SYMBOL"
echo "TIMEFRAME=$TIMEFRAME"
echo
echo "[paths]"
echo "LIVE_DEC=$LIVE_DEC"
echo "BT_DEC  =$BT_DEC"
echo "LIVE_TR =$LIVE_TR"
echo "BT_TR   =$BT_TR"
echo

# Validate files exist
for f in "$LIVE_DEC" "$BT_DEC" "$LIVE_TR" "$BT_TR"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing file: $f" >&2
    exit 2
  fi
done

echo "[counts] (lines include header)"
wc -l "$LIVE_DEC" "$BT_DEC" "$LIVE_TR" "$BT_TR" 2>/dev/null || true
echo

echo "[window] decisions (computed from ts_ms)"
LIVE_DEC="$LIVE_DEC" BT_DEC="$BT_DEC" python3 - <<'PY'
import os, csv

live_path = os.environ["LIVE_DEC"]
bt_path   = os.environ["BT_DEC"]

def read_ts(path: str):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            v = (row.get("ts_ms") or "").strip()
            if not v:
                continue
            try:
                out.append(int(float(v)))
            except Exception:
                pass
    return out

live_ts = read_ts(live_path)
bt_ts   = read_ts(bt_path)

def describe(name, ts):
    if not ts:
        print(f"{name}: empty")
        return None
    lo, hi = min(ts), max(ts)
    print(f"{name}: [{lo},{hi}] rows={len(ts)}")
    return lo, hi

live_rng = describe("LIVE", live_ts)
bt_rng   = describe("BT  ", bt_ts)

if not live_rng or not bt_rng:
    raise SystemExit(0)

overlap_lo = max(live_rng[0], bt_rng[0])
overlap_hi = min(live_rng[1], bt_rng[1])

if overlap_lo > overlap_hi:
    print("overlap: none")
    raise SystemExit(0)

live_in = sum(1 for t in live_ts if overlap_lo <= t <= overlap_hi)
bt_in   = sum(1 for t in bt_ts   if overlap_lo <= t <= overlap_hi)

print(f"overlap: [{overlap_lo},{overlap_hi}]")
print(f"rows_in_overlap: LIVE={live_in}  BT={bt_in}")
if len(bt_ts) != bt_in:
    print("note: BT decisions often include warmup-prefix rows outside overlap (expected).")
PY
echo

echo "[tails] trades (last 5)"
tail -n 5 "$LIVE_TR" 2>/dev/null || true
echo
tail -n 5 "$BT_TR" 2>/dev/null || true
echo

# entry_ts_ms is column 4 in trades.csv
cut -d, -f4 "$LIVE_TR" 2>/dev/null | tail -n +2 | sort -n >/tmp/live_entry_ts.txt
cut -d, -f4 "$BT_TR" 2>/dev/null | tail -n +2 | sort -n >/tmp/bt_entry_ts.txt

echo "=== entry_ts_ms present in BT but not LIVE ==="
comm -13 /tmp/live_entry_ts.txt /tmp/bt_entry_ts.txt | head -n 20 || true
echo

echo "=== entry_ts_ms present in LIVE but not BT ==="
comm -23 /tmp/live_entry_ts.txt /tmp/bt_entry_ts.txt | head -n 20 || true
echo

EXTRA_TS="$(comm -13 /tmp/live_entry_ts.txt /tmp/bt_entry_ts.txt | head -n 1 || true)"
if [[ -z "$EXTRA_TS" ]]; then
  echo "No BT-only trade entry_ts_ms detected. ✅"
  exit 0
fi

echo "EXTRA_TS=$EXTRA_TS"
echo
echo "=== BT row(s) for EXTRA_TS ==="
awk -F, -v ts="$EXTRA_TS" 'NR==1 || $4==ts {print}' "$BT_TR"
echo

echo "=== Search all processed trades for EXTRA_TS ==="
grep -R "$EXTRA_TS" -n data/processed/trades | head -n 60 || true
echo

echo "=== Decision context around EXTRA_TS (LIVE vs BT) ==="
LIVE_DEC="$LIVE_DEC" BT_DEC="$BT_DEC" EXTRA_TS="$EXTRA_TS" python3 - <<'PY'
import csv, os

live = os.environ["LIVE_DEC"]
bt   = os.environ["BT_DEC"]
target = int(os.environ["EXTRA_TS"])

def dump(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)

    idx = {}
    for i,row in enumerate(rows):
        v = (row.get("ts_ms") or "").strip()
        if not v:
            continue
        try:
            ts = int(float(v))
        except Exception:
            continue
        idx[ts] = i

    if target not in idx:
        print(f"{path}: missing ts_ms={target}")
        return

    i = idx[target]
    lo = max(0, i-3)
    hi = min(len(rows), i+4)

    print(path)
    for j in range(lo, hi):
        row = rows[j]
        print(
            " ts_ms=", row.get("ts_ms",""),
            " pos=", row.get("position_side",""),
            " entry=", row.get("entry_should_enter",""),
            " exit=", row.get("exit_should_exit",""),
            " exit_reason=", row.get("exit_reason",""),
            " stop=", row.get("position_stop_price",""),
            sep=""
        )
    print("-"*60)

dump(live)
dump(bt)
PY
