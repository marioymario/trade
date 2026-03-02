#!/usr/bin/env bash
# ops/cron_reboot.sh
#
# Boot-start script (boring + safe):
# - If KILL_SWITCH_FILE exists => DO NOTHING (log "HALTED", exit 0)
# - If daily limits exceeded => DO NOTHING (log "HALTED", exit 0)
# - Otherwise ensure compose stack is UP (idempotent)
#
# IMPORTANT: never call "down/stop/kill" here. This script must not kill paper.
#
# Logs to: $HOME/trade_reboot.log (override with LOG=/path)

# set -euo pipefail
# set -x

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROJ="${PROJ:-$REPO_ROOT}"
LOG="${LOG:-$HOME/trade_reboot.log}"
LOCK="${LOCK:-/tmp/trade_reboot.lock}"

DOCKER="${DOCKER:-/usr/bin/docker}"
FLOCK="${FLOCK:-/usr/bin/flock}"

BASE_YML="${BASE_YML:-docker-compose.yml}"
GPU_YML="${GPU_YML:-docker-compose.gpu.yml}"

touch "$LOG"
exec >>"$LOG" 2>&1

echo
echo "===== trade cron @reboot ====="
date -Is
id
echo "PROJ=$PROJ"

# Source .env if present
if [[ -f "$PROJ/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$PROJ/.env"
  set +a
fi

KILL_SWITCH_FILE="${KILL_SWITCH_FILE:-/tmp/TRADING_STOP}"
MAX_TRADES_PER_DAY="${MAX_TRADES_PER_DAY:-0}"
MAX_DAILY_LOSS_USD="${MAX_DAILY_LOSS_USD:-0}"
TZ_LOCAL="${TZ_LOCAL:-America/Los_Angeles}"

echo "KILL_SWITCH_FILE=$KILL_SWITCH_FILE"
echo "MAX_TRADES_PER_DAY=$MAX_TRADES_PER_DAY"
echo "MAX_DAILY_LOSS_USD=$MAX_DAILY_LOSS_USD"
echo "TZ_LOCAL=$TZ_LOCAL"

if [[ -e "$KILL_SWITCH_FILE" ]]; then
  echo "HALTED: kill switch present: $KILL_SWITCH_FILE"
  exit 0
fi

# Wait for docker daemon
for i in {1..30}; do
  "$DOCKER" info >/dev/null 2>&1 && break
  sleep 2
done
"$DOCKER" info >/dev/null 2>&1 || {
  echo "ERROR: docker not ready"
  exit 1
}

# Lock to prevent double-start
[[ -x "$FLOCK" ]] || {
  echo "ERROR: flock missing at $FLOCK"
  exit 1
}
exec 9>"$LOCK"
"$FLOCK" -n 9 || {
  echo "LOCKED: another instance running"
  exit 0
}

compose() {
  cd "$PROJ" || return 1
  "$DOCKER" compose --project-directory "$PROJ" "$@"
}

have_gpu_file() { [[ -f "$PROJ/$GPU_YML" ]]; }

# Daily-limit precheck (if exceeded, do NOT start)
DATA_TAG="${DATA_TAG:-paper_oldbox_live}"
SYMBOL="${SYMBOL:-BTC_USD}"
TIMEFRAME="${TIMEFRAME:-5m}"

SYMBOL_PATH="${SYMBOL//\//_}"
SYMBOL_PATH="${SYMBOL_PATH//-/_}"

TRADES_CSV="$PROJ/data/processed/trades/${DATA_TAG}/${SYMBOL_PATH}/${TIMEFRAME}/trades.csv"

python3 "$PROJ/ops/daily_limits_check.py" \
  --trades-csv "$TRADES_CSV" \
  --max-trades-per-day "$MAX_TRADES_PER_DAY" \
  --max-daily-loss-usd "$MAX_DAILY_LOSS_USD" \
  --tz "$TZ_LOCAL" || {
  rc=$?
  if [[ "$rc" == "2" ]]; then
    echo "HALTED: daily limits exceeded (precheck). Not starting containers."
    exit 0
  fi
  echo "WARN: daily limits check error rc=$rc (not halting)"
}

cd "$PROJ" || {
  echo "ERROR: cd PROJ failed"
  exit 1
}

# Start stack (idempotent). Prefer GPU overlay if present.
if have_gpu_file; then
  echo "=== compose up (GPU overlay present) ==="
  compose -f "$BASE_YML" -f "$GPU_YML" up -d
  compose ps || true
  exit 0
fi

echo "=== compose up (CPU only) ==="
compose -f "$BASE_YML" up -d
compose ps || true
