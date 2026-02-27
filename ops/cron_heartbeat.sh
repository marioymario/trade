#!/usr/bin/env bash
# ops/cron_heartbeat.sh
#
# Proof-of-life + risk guard:
# - If KILL_SWITCH_FILE exists => HALT only (do NOT stop paper)
# - If daily limits exceeded  => HALT only (do NOT stop paper)
# - Otherwise: compose ps + last decisions row + recent paper logs
#
# Logs to: $HOME/trade_heartbeat.log (override with LOG=/path)

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="${PROJ:-$REPO_ROOT}"
LOG="${LOG:-$HOME/trade_heartbeat.log}"

DOCKER="${DOCKER:-/usr/bin/docker}"
FLOCK="${FLOCK:-/usr/bin/flock}"
LOCK="${LOCK:-/tmp/trade_heartbeat.lock}"

SERVICE_PAPER="${SERVICE_PAPER:-paper}"

touch "$LOG"
exec >>"$LOG" 2>&1

compose() {
  cd "$PROJ" || return 1
  "$DOCKER" compose --project-directory "$PROJ" "$@"
}

echo
echo "===== trade heartbeat ====="
date -Is
echo "PROJ=$PROJ"

# Lock to prevent overlapping runs (cron + manual)
[[ -x "$FLOCK" ]] || { echo "ERROR: flock missing at $FLOCK"; exit 1; }
exec 9>"$LOCK"
"$FLOCK" -n 9 || { echo "LOCKED: another heartbeat running"; exit 0; }

# Load a small allowlist from .env (avoid UID= which is readonly in bash)
load_env_allowlist() {
  local f="$1"
  [[ -f "$f" ]] || return 0
  local line k v
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    k="${line%%=*}"
    v="${line#*=}"
    k="${k//[[:space:]]/}"
    # strip surrounding quotes
    v="${v%$'\r'}"
    if [[ "$v" == \"*\" && "$v" == *\" ]]; then v="${v:1:${#v}-2}"; fi
    if [[ "$v" == \'*\' && "$v" == *\' ]]; then v="${v:1:${#v}-2}"; fi
    case "$k" in
      DATA_TAG|SYMBOL|TIMEFRAME|CCXT_EXCHANGE|DRY_RUN|ARMED|TZ_LOCAL|KILL_SWITCH_FILE|HALT_ORDERS_FILE|MAX_TRADES_PER_DAY|MAX_DAILY_LOSS_USD)
        export "$k=$v"
        ;;
    esac
  done < "$f"
}
load_env_allowlist "$PROJ/.env"

KILL_SWITCH_FILE="${KILL_SWITCH_FILE:-/tmp/TRADING_STOP}"
HALT_ORDERS_FILE="${HALT_ORDERS_FILE:-/tmp/TRADING_HALT}"
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

halt_only() {
  local reason="$1"
  echo "HALTED: $reason"
  echo "HALT_ORDERS_FILE=$HALT_ORDERS_FILE"
  mkdir -p "$(dirname "$HALT_ORDERS_FILE")" 2>/dev/null || true
  : > "$HALT_ORDERS_FILE" 2>/dev/null || touch "$HALT_ORDERS_FILE" 2>/dev/null || true
  compose ps || true
}

# Kill switch check (do NOT stop paper)
if [[ -e "$KILL_SWITCH_FILE" ]]; then
  echo "KILL_SWITCH present: $KILL_SWITCH_FILE (not stopping paper)"
  compose ps || true
  exit 0
fi

# Daily limits check (rc=2 means limit exceeded)
python3 "$PROJ/ops/daily_limits_check.py" \
  --trades-csv "$TRADES_CSV" \
  --max-trades-per-day "$MAX_TRADES_PER_DAY" \
  --max-daily-loss-usd "$MAX_DAILY_LOSS_USD" \
  --tz "$TZ_LOCAL" || {
    rc=$?
    if [[ "$rc" == "2" ]]; then
      halt_only "daily limits exceeded"
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
