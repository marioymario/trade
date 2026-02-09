#!/usr/bin/env bash
# ops/cron_heartbeat.sh
#
# Proof-of-life + risk guard:
# - If KILL_SWITCH_FILE exists => stop paper + log HALTED
# - If daily limits exceeded => stop paper + log HALTED
# - Otherwise: compose ps + last decisions row + recent paper logs
#
# Logs to: $HOME/trade_heartbeat.log (override with LOG=/path)

# set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="${PROJ:-$REPO_ROOT}"
LOG="${LOG:-$HOME/trade_heartbeat.log}"

DOCKER="${DOCKER:-/usr/bin/docker}"
SERVICE_PAPER="${SERVICE_PAPER:-paper}"

touch "$LOG"
exec >>"$LOG" 2>&1

compose() {
  cd "$PROJ"
  "$DOCKER" compose --project-directory "$PROJ" "$@"
}

echo
echo "===== trade heartbeat ====="
date -Is
echo "PROJ=$PROJ"

# Source .env for tags + risk vars
if [[ -f "$PROJ/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$PROJ/.env"
  set +a
fi

KILL_SWITCH_FILE="${KILL_SWITCH_FILE:-/tmp/TRADING_STOP}"
MAX_TRADES_PER_DAY="${MAX_TRADES_PER_DAY:-0}"   # 0 disables
MAX_DAILY_LOSS_USD="${MAX_DAILY_LOSS_USD:-0}"   # 0 disables
TZ_LOCAL="${TZ_LOCAL:-America/Los_Angeles}"

DATA_TAG="${DATA_TAG:-paper_oldbox_live}"
SYMBOL="${SYMBOL:-BTC_USD}"
TIMEFRAME="${TIMEFRAME:-5m}"

SYMBOL_PATH="${SYMBOL//\//_}"
SYMBOL_PATH="${SYMBOL_PATH//-/_}"

DECISIONS="$PROJ/data/processed/decisions/${DATA_TAG}/${SYMBOL_PATH}/${TIMEFRAME}/decisions.csv"
TRADES_CSV="$PROJ/data/processed/trades/${DATA_TAG}/${SYMBOL_PATH}/${TIMEFRAME}/trades.csv"

halt_and_stop_paper() {
  local reason="$1"
  echo "HALTED: $reason"
  echo "Stopping service: $SERVICE_PAPER"
  compose stop "$SERVICE_PAPER" || true
  compose ps || true
}

# Kill switch check
if [[ -e "$KILL_SWITCH_FILE" ]]; then
  halt_and_stop_paper "kill switch present: $KILL_SWITCH_FILE"
  exit 0
fi

# Daily limits check (disabled if both limits are 0; OK if trades csv missing)
python3 "$PROJ/ops/daily_limits_check.py" \
  --trades-csv "$TRADES_CSV" \
  --max-trades-per-day "$MAX_TRADES_PER_DAY" \
  --max-daily-loss-usd "$MAX_DAILY_LOSS_USD" \
  --tz "$TZ_LOCAL" || {
    rc=$?
    if [[ "$rc" == "2" ]]; then
      halt_and_stop_paper "daily limits exceeded"
      exit 0
    fi
    echo "WARN: daily limits check error rc=$rc (not halting)"
  }

# Normal proof-of-life output
compose ps || true

if [[ -f "$DECISIONS" ]]; then
  echo "--- decisions last row ($DECISIONS) ---"
  tail -n 1 "$DECISIONS" || true
else
  echo "WARN: decisions file missing: $DECISIONS"
fi

echo "--- paper logs (last 15m, tail 30) ---"
compose logs --since=15m --tail=30 "$SERVICE_PAPER" || true

echo "===== done ====="
