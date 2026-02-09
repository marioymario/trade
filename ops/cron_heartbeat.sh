#!/usr/bin/env bash
# ops/cron_heartbeat.sh
# Proof-of-life: compose ps + last decision row + recent paper logs.
# Logs to: $HOME/trade_heartbeat.log (override LOG=...)

#set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="${PROJ:-$REPO_ROOT}"
LOG="${LOG:-$HOME/trade_heartbeat.log}"

DOCKER="${DOCKER:-/usr/bin/docker}"
BASE_YML="${BASE_YML:-docker-compose.yml}"
SERVICE_PAPER="${SERVICE_PAPER:-paper}"

touch "$LOG"
exec >>"$LOG" 2>&1

# Source .env if present for DATA_TAG/SYMBOL/TIMEFRAME
if [[ -f "$PROJ/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$PROJ/.env"
  set +a
fi

DATA_TAG="${DATA_TAG:-paper_oldbox_live}"
SYMBOL="${SYMBOL:-BTC_USD}"
TIMEFRAME="${TIMEFRAME:-5m}"

DECISIONS="data/processed/decisions/${DATA_TAG}/${SYMBOL}/${TIMEFRAME}/decisions.csv"

compose() {
  cd "$PROJ"
  "$DOCKER" compose --project-directory "$PROJ" "$@"
}

echo
echo "===== trade heartbeat ====="
date -Is
echo "PROJ=$PROJ"
compose ps || true

if [[ -f "$PROJ/$DECISIONS" ]]; then
  echo "--- decisions last row ($DECISIONS) ---"
  tail -n 1 "$PROJ/$DECISIONS" || true
else
  echo "WARN: decisions file missing: $DECISIONS"
fi

echo "--- paper logs (last 15m, tail 30) ---"
compose logs --since=15m --tail=30 "$SERVICE_PAPER" || true

echo "===== done ====="
