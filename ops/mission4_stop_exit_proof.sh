#!/usr/bin/env bash
#set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

DECISIONS_CSV="data/processed/decisions/paper_oldbox_live/BTC_USD/5m/decisions.csv"
TRADES_CSV="data/processed/trades/paper_oldbox_live/BTC_USD/5m/trades.csv"
FLAGS_DIR="/home/kk7wus/trade_flags"
STOP_FILE="${FLAGS_DIR}/STOP"
OUT_DIR="${REPO_ROOT}/ops/proofs"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="${OUT_DIR}/mission4_stop_exit_${STAMP}.log"

POLL_SECONDS="${POLL_SECONDS:-10}"
MAX_WAIT_OPEN_SECONDS="${MAX_WAIT_OPEN_SECONDS:-21600}"   # 6h
MAX_WAIT_CLOSE_SECONDS="${MAX_WAIT_CLOSE_SECONDS:-14400}" # 4h
REMOVE_STOP_ON_EXIT="${REMOVE_STOP_ON_EXIT:-1}"

mkdir -p "${OUT_DIR}"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "${OUT_FILE}"
}

require_file() {
  local path="$1"
  if [[ ! -f "${path}" ]]; then
    log "ERROR: required file missing: ${path}"
    exit 1
  fi
}

latest_position_state() {
  python3 - "${DECISIONS_CSV}" <<'PY'
import csv, sys
from pathlib import Path

p = Path(sys.argv[1])
if not p.exists():
    print("missing")
    raise SystemExit(0)

rows = list(csv.DictReader(p.open()))
if not rows:
    print("empty")
    raise SystemExit(0)

last = rows[-1]
timestamp = last.get("timestamp", "")
side = (last.get("position_side") or "").strip()
qty = (last.get("position_qty") or "").strip()
stop = (last.get("position_stop_price") or "").strip()
trail_reason = (last.get("trail_reason") or "").strip()
entry_blocked_reason = (last.get("entry_blocked_reason") or "").strip()
exit_should_exit = (last.get("exit_should_exit") or "").strip()
exit_reason = (last.get("exit_reason") or "").strip()

print(f"timestamp={timestamp}")
print(f"position_side={side}")
print(f"position_qty={qty}")
print(f"position_stop_price={stop}")
print(f"trail_reason={trail_reason}")
print(f"entry_blocked_reason={entry_blocked_reason}")
print(f"exit_should_exit={exit_should_exit}")
print(f"exit_reason={exit_reason}")
PY
}

position_is_open() {
  python3 - "${DECISIONS_CSV}" <<'PY'
import csv, sys
from pathlib import Path

p = Path(sys.argv[1])
if not p.exists():
    print("0")
    raise SystemExit(0)

rows = list(csv.DictReader(p.open()))
if not rows:
    print("0")
    raise SystemExit(0)

last = rows[-1]
side = (last.get("position_side") or "").strip()
qty = (last.get("position_qty") or "").strip()
print("1" if side and qty else "0")
PY
}

capture_packet() {
  {
    echo
    echo "===== FLAGS ====="
    ls -l "${FLAGS_DIR}" || true

    echo
    echo "===== DOCKER COMPOSE PS ====="
    docker compose ps || true

    echo
    echo "===== RECENT PAPER LOGS ====="
    docker compose logs --since=2h paper || true

    echo
    echo "===== DECISION TAIL (last 40) ====="
    tail -n 40 "${DECISIONS_CSV}" || true

    echo
    echo "===== PROOF ROWS ====="
    grep -n 'STOP_BLOCK\|halted_freeze_trailing\|entry_blocked_reason\|exit_should_exit\|stop_hit' "${DECISIONS_CSV}" | tail -n 80 || true

    echo
    echo "===== TRADES TAIL (last 20) ====="
    tail -n 20 "${TRADES_CSV}" || true
  } >>"${OUT_FILE}"
}

log "START mission4 STOP/exit proof runner"
log "REPO_ROOT=${REPO_ROOT}"
log "DECISIONS_CSV=${DECISIONS_CSV}"
log "TRADES_CSV=${TRADES_CSV}"
log "STOP_FILE=${STOP_FILE}"
log "OUT_FILE=${OUT_FILE}"

require_file "${DECISIONS_CSV}"
require_file "${TRADES_CSV}"

if [[ -e "${STOP_FILE}" ]]; then
  log "ERROR: STOP already exists. Remove it before starting."
  exit 1
fi

if ! docker compose ps --status running | grep -q 'paper'; then
  log "ERROR: paper service is not running."
  exit 1
fi

log "Initial latest position state:"
latest_position_state | tee -a "${OUT_FILE}"

log "Waiting for a live position to appear..."
open_deadline=$(($(date +%s) + MAX_WAIT_OPEN_SECONDS))

while true; do
  now_epoch="$(date +%s)"
  if ((now_epoch > open_deadline)); then
    log "TIMEOUT: no live position appeared within MAX_WAIT_OPEN_SECONDS=${MAX_WAIT_OPEN_SECONDS}"
    capture_packet
    exit 2
  fi

  if [[ "$(position_is_open)" == "1" ]]; then
    log "Live position detected."
    latest_position_state | tee -a "${OUT_FILE}"
    break
  fi

  sleep "${POLL_SECONDS}"
done

log "Creating STOP file."
touch "${STOP_FILE}"
ls -l "${FLAGS_DIR}" | tee -a "${OUT_FILE}"

log "Waiting for position to close while STOP remains present..."
close_deadline=$(($(date +%s) + MAX_WAIT_CLOSE_SECONDS))

while true; do
  now_epoch="$(date +%s)"
  latest_position_state | tee -a "${OUT_FILE}"

  if [[ "$(position_is_open)" == "0" ]]; then
    log "Position is now closed."
    break
  fi

  if ((now_epoch > close_deadline)); then
    log "TIMEOUT: position did not close within MAX_WAIT_CLOSE_SECONDS=${MAX_WAIT_CLOSE_SECONDS}"
    capture_packet
    if [[ "${REMOVE_STOP_ON_EXIT}" == "1" ]]; then
      rm -f "${STOP_FILE}" || true
      log "STOP removed after timeout cleanup."
    fi
    exit 3
  fi

  sleep "${POLL_SECONDS}"
done

log "Capturing proof packet."
capture_packet

if [[ "${REMOVE_STOP_ON_EXIT}" == "1" ]]; then
  rm -f "${STOP_FILE}" || true
  log "STOP removed after proof capture."
else
  log "STOP left in place because REMOVE_STOP_ON_EXIT=${REMOVE_STOP_ON_EXIT}"
fi

log "DONE mission4 STOP/exit proof runner"
log "Proof file: ${OUT_FILE}"
