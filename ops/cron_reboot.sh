#!/usr/bin/env bash
# ops/cron_reboot.sh
#
# Boot-start script:
# - If KILL_SWITCH_FILE exists => DO NOTHING (log "HALTED", exit 0)
# - If daily limits exceeded => DO NOTHING (log "HALTED", exit 0)
# - Otherwise start compose (GPU-first if docker-compose.gpu.yml exists; CPU fallback)
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

SERVICE_TRADE="${SERVICE_TRADE:-trade}"

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
"$DOCKER" info >/dev/null 2>&1 || { echo "ERROR: docker not ready"; exit 1; }

# Lock to prevent double-start
[[ -x "$FLOCK" ]] || { echo "ERROR: flock missing at $FLOCK"; exit 1; }
exec 9>"$LOCK"
"$FLOCK" -n 9 || { echo "LOCKED: another instance running"; exit 0; }

compose() {
  cd "$PROJ"
  "$DOCKER" compose --project-directory "$PROJ" "$@"
}

have_gpu_file() { [[ -f "$PROJ/$GPU_YML" ]]; }

verify_gpu_runtime() {
  if compose -f "$BASE_YML" -f "$GPU_YML" exec -T "$SERVICE_TRADE" sh -lc 'command -v nvidia-smi >/dev/null 2>&1'; then
    compose -f "$BASE_YML" -f "$GPU_YML" exec -T "$SERVICE_TRADE" nvidia-smi >/dev/null 2>&1
    return $?
  fi
  compose -f "$BASE_YML" -f "$GPU_YML" exec -T "$SERVICE_TRADE" python - <<'PY'
import tensorflow as tf
gpus = tf.config.list_physical_devices("GPU")
print("TF GPUs:", gpus)
raise SystemExit(0 if gpus else 2)
PY
}

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

cd "$PROJ"

if have_gpu_file; then
  echo "=== TRY GPU compose ==="
  if compose -f "$BASE_YML" -f "$GPU_YML" up -d; then
    echo "GPU compose up: OK"
  else
    echo "GPU compose up: FAIL -> CPU"
    compose -f "$BASE_YML" up -d
    echo "CPU_OK"
    compose ps || true
    exit 0
  fi

  echo "=== VERIFY GPU usability ==="
  if verify_gpu_runtime; then
    echo "GPU_OK"
    compose ps || true
    exit 0
  fi

  echo "GPU_NOT_USABLE -> FALLBACK CPU"
  compose -f "$BASE_YML" -f "$GPU_YML" down || true
  compose -f "$BASE_YML" up -d
  echo "CPU_OK"
  compose ps || true
  exit 0
fi

echo "=== No GPU compose file; starting CPU only ==="
compose -f "$BASE_YML" up -d
echo "CPU_OK"
compose ps || true
