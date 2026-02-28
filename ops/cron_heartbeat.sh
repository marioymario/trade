#!/usr/bin/env bash
set -euo pipefail

LOG="${HOME}/trade_heartbeat.log"
LOCK="/tmp/trade_heartbeat.lock"

# Allowlist .env loader (safe: only exports explicitly allowed keys)
load_env_allowlist() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  local allow="^(DATA_TAG|SYMBOL|TIMEFRAME|DRY_RUN|FLAGS_DIR|KILL_SWITCH_FILE|HALT_ORDERS_FILE|ARM_FILE)=$"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    # trim leading/trailing spaces
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue

    local key="${line%%=*}"
    local val="${line#*=}"

    # strip surrounding quotes if present
    if [[ "$val" =~ ^\".*\"$ ]]; then val="${val:1:${#val}-2}"; fi
    if [[ "$val" =~ ^\'.*\'$ ]]; then val="${val:1:${#val}-2}"; fi

    if [[ "${key}=" =~ $allow ]]; then
      export "${key}=${val}"
    fi
  done < "$env_file"
}

as_utc() {
  local epoch="$1"
  date -u -d "@${epoch}" -Is 2>/dev/null | sed 's/+00:00/Z/' || echo "na"
}

svc_is_up() {
  local svc="$1"
  if docker inspect -f '{{.State.Running}}' "$svc" 2>/dev/null | grep -qx true; then
    echo "up"
  else
    echo "down"
  fi
}

(
  flock -n 9 || exit 0

  exec >>"$LOG" 2>&1
  echo "===== trade heartbeat ====="
  date -Is
  echo "pwd=$(pwd)"
  echo

  # Move to repo root if invoked from elsewhere
  PROJ="${HOME}/Projects/trade"
  cd "$PROJ" || exit 1

  # Load safe env vars
  load_env_allowlist "$PROJ/.env"

  # Defaults (portable)
  : "${FLAGS_DIR:=${HOME}/trade_flags}"
  : "${DATA_TAG:=paper_oldbox_live}"
  : "${SYMBOL:=BTC_USD}"
  : "${TIMEFRAME:=5m}"

  SYMBOL_PATH="${SYMBOL////_}"

  # Respect existing per-file overrides if provided; otherwise derive from FLAGS_DIR
  : "${KILL_SWITCH_FILE:=${FLAGS_DIR}/STOP}"
  : "${HALT_ORDERS_FILE:=${FLAGS_DIR}/HALT}"
  : "${ARM_FILE:=${FLAGS_DIR}/ARM}"

  STATUS_FILE="${FLAGS_DIR}/status.txt"
  mkdir -p "$FLAGS_DIR"

  # Compose status snapshot
  echo "=== docker compose ps ==="
  docker compose ps || true
  echo

  # Decisions path (convention)
  DECISIONS_CSV="$PROJ/data/processed/decisions/${DATA_TAG}/${SYMBOL_PATH}/${TIMEFRAME}/decisions.csv"

  echo "=== decisions.csv ==="
  echo "decisions_csv=${DECISIONS_CSV}"
  if [[ -f "$DECISIONS_CSV" ]]; then
    csv_epoch="$(stat -c %Y "$DECISIONS_CSV" 2>/dev/null || echo 0)"
    csv_mtime_utc="$(as_utc "$csv_epoch")"
    echo "decisions_mtime_utc=${csv_mtime_utc}"
    tail -n 1 "$DECISIONS_CSV" || true
  else
    csv_mtime_utc="na"
    echo "decisions_mtime_utc=na"
    echo "decisions_csv_missing=1"
  fi
  echo

  echo "=== paper logs (since 15m) ==="
  docker compose logs --since 15m --tail 200 paper 2>/dev/null || true
  echo

  # Flags
  STOP="off"; [[ -f "$KILL_SWITCH_FILE" ]] && STOP="ON"
  HALT="off"; [[ -f "$HALT_ORDERS_FILE" ]] && HALT="ON"
  ARM="off";  [[ -f "$ARM_FILE" ]] && ARM="ON"

  # Service statuses
  paper_status="$(svc_is_up paper)"
  trade_status="$(svc_is_up trade)"
  dashboard_status="$(svc_is_up dashboard)"

  # Write beacon atomically
  now_epoch="$(date -u +%s)"
  now_utc="$(date -u -Is | sed 's/+00:00/Z/')"
  tmp="${STATUS_FILE}.tmp.$$"

  {
    echo "format_version=1"
    echo "ts_utc=${now_utc}"
    echo "paper_status=${paper_status}"
    echo "trade_status=${trade_status}"
    echo "dashboard_status=${dashboard_status}"
    echo "STOP=${STOP}"
    echo "HALT=${HALT}"
    echo "ARM=${ARM}"
    echo "decisions_mtime_utc=${csv_mtime_utc}"
  } > "$tmp"
  mv -f "$tmp" "$STATUS_FILE"

  echo "=== status beacon ==="
  stat -c 'status_mtime=%y size=%s path=%n' "$STATUS_FILE" 2>/dev/null || true
  tail -n 20 "$STATUS_FILE" || true
  echo
) 9>"$LOCK"
