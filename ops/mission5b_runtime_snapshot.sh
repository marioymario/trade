#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${ROOT_DIR}/ops/proofs"
OUT_FILE="${OUT_DIR}/runtime_snapshot_${STAMP}.log"

mkdir -p "${OUT_DIR}"

DATA_TAG_DEFAULT="${DATA_TAG:-paper_oldbox_live}"
SYMBOL_DEFAULT="${SYMBOL:-BTC/USD}"
TIMEFRAME_DEFAULT="${TIMEFRAME:-5m}"
LOG_WINDOW_DEFAULT="${LOG_WINDOW:-24h}"
DECISIONS_TAIL_DEFAULT="${DECISIONS_TAIL:-80}"
TRADES_TAIL_DEFAULT="${TRADES_TAIL:-30}"

DATA_TAG_VALUE="${1:-$DATA_TAG_DEFAULT}"
SYMBOL_VALUE="${2:-$SYMBOL_DEFAULT}"
TIMEFRAME_VALUE="${3:-$TIMEFRAME_DEFAULT}"

STORAGE_SYMBOL="$(printf '%s' "${SYMBOL_VALUE}" | tr '[:lower:]' '[:upper:]' | sed 's|/|_|g; s|:|_|g; s| |_|g')"

TRADES_CSV="data/processed/trades/${DATA_TAG_VALUE}/${STORAGE_SYMBOL}/${TIMEFRAME_VALUE}/trades.csv"
DECISIONS_CSV="data/processed/decisions/${DATA_TAG_VALUE}/${STORAGE_SYMBOL}/${TIMEFRAME_VALUE}/decisions.csv"

{
  echo "=== Mission 5B Runtime Snapshot ==="
  echo "ts_utc=${STAMP}"
  echo "root_dir=${ROOT_DIR}"
  echo "data_tag=${DATA_TAG_VALUE}"
  echo "symbol=${SYMBOL_VALUE}"
  echo "timeframe=${TIMEFRAME_VALUE}"
  echo "trades_csv=${TRADES_CSV}"
  echo "decisions_csv=${DECISIONS_CSV}"
  echo

  echo "=== paper container env truth ==="
  docker compose exec -T paper sh -lc 'env | egrep "^(DATA_TAG|SYMBOL|TIMEFRAME|CCXT_EXCHANGE|BROKER|DRY_RUN|COOLDOWN_BARS|MAX_ORDER_SIZE|MAX_ORDER_USD|MAX_POSITION_USD|MAX_TRADES_PER_DAY|MAX_DAILY_LOSS_USD|TEST_HOOKS_ENABLED|FORCE_ENTRY_SIGNAL_ONCE|FORCE_EXIT_SIGNAL_ONCE|FORCE_COOLDOWN_BLOCK_ONCE|FORCE_COOLDOWN_BARS|FORCE_FEATURES_INVALID_N|FORCE_CADENCE_FAIL_N|BYPASS_FEATURE_VALIDATION|ARM_FILE|KILL_SWITCH_FILE|HALT_ORDERS_FILE|TZ_LOCAL)="'
  echo

  echo "=== trade report ==="
  docker compose exec -T trade sh -lc "REPORT_EXCHANGE='${DATA_TAG_VALUE}' REPORT_SYMBOL='${SYMBOL_VALUE}' REPORT_TIMEFRAME='${TIMEFRAME_VALUE}' python -m files.utils.trade_report"
  echo

  echo "=== latest trades tail (${TRADES_TAIL_DEFAULT}) ==="
  if [ -f "${TRADES_CSV}" ]; then
    tail -n "${TRADES_TAIL_DEFAULT}" "${TRADES_CSV}"
  else
    echo "missing: ${TRADES_CSV}"
  fi
  echo

  echo "=== latest decisions tail (${DECISIONS_TAIL_DEFAULT}) ==="
  if [ -f "${DECISIONS_CSV}" ]; then
    tail -n "${DECISIONS_TAIL_DEFAULT}" "${DECISIONS_CSV}"
  else
    echo "missing: ${DECISIONS_CSV}"
  fi
  echo

  echo "=== recent paper logs (${LOG_WINDOW_DEFAULT}) ==="
  docker compose logs --since="${LOG_WINDOW_DEFAULT}" paper | egrep 'Opened paper position|Updated stop|Closed paper position|Trade recorded|Blocked entry at broker guard|stop_hit|time_stop|DEGRADED|Cadence check failed|Latest features invalid' || true
  echo

  echo "=== snapshot done ==="
  echo "out_file=${OUT_FILE}"
} | tee "${OUT_FILE}"

echo
echo "Saved: ${OUT_FILE}"
