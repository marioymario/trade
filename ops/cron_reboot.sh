#!/usr/bin/env bash
# ops/cron_reboot.sh
# Boot-start script (GPU-first with verification; CPU fallback).
# Logs to: $HOME/trade_reboot.log (override LOG=...)

#set -euo pipefail
#set -x

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
  cd "$PROJ"
  "$DOCKER" compose --project-directory "$PROJ" "$@"
}

have_gpu_file() { [[ -f "$PROJ/$GPU_YML" ]]; }

verify_gpu_runtime() {
  # Prefer nvidia-smi if present; else TF GPU list.
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
