#!/usr/bin/env bash
set -euo pipefail

LOG="${HOME}/trade_heartbeat.log"
LOCK="/tmp/trade_heartbeat.lock"

load_env_allowlist() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  local allow="^(DATA_TAG|SYMBOL|TIMEFRAME|DRY_RUN|FLAGS_DIR|KILL_SWITCH_FILE|HALT_ORDERS_FILE|ARM_FILE|MAX_TRADES_PER_DAY|MAX_DAILY_LOSS_USD|TZ_LOCAL)=$"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue

    local key="${line%%=*}"
    local val="${line#*=}"

    if [[ "$val" =~ ^\".*\"$ ]]; then val="${val:1:${#val}-2}"; fi
    if [[ "$val" =~ ^\'.*\'$ ]]; then val="${val:1:${#val}-2}"; fi

    if [[ "${key}=" =~ $allow ]]; then
      export "${key}=${val}"
    fi
  done <"$env_file"
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

  PROJ="${HOME}/Projects/trade"
  cd "$PROJ" || exit 1

  load_env_allowlist "$PROJ/.env"

  : "${FLAGS_DIR:=${HOME}/trade_flags}"
  : "${DATA_TAG:=paper_oldbox_live}"
  : "${SYMBOL:=BTC_USD}"
  : "${TIMEFRAME:=5m}"

  SYMBOL_PATH="${SYMBOL////_}"
  SYMBOL_PATH="${SYMBOL_PATH//-/_}"

  : "${KILL_SWITCH_FILE:=${FLAGS_DIR}/STOP}"
  : "${HALT_ORDERS_FILE:=${FLAGS_DIR}/HALT}"
  : "${ARM_FILE:=${FLAGS_DIR}/ARM}"

  : "${MAX_TRADES_PER_DAY:=0}"
  : "${MAX_DAILY_LOSS_USD:=0}"
  : "${TZ_LOCAL:=America/Los_Angeles}"

  STATUS_FILE="${FLAGS_DIR}/status.txt"
  mkdir -p "$FLAGS_DIR"

  echo "=== docker compose ps ==="
  docker compose ps || true
  echo

  DECISIONS_CSV="$PROJ/data/processed/decisions/${DATA_TAG}/${SYMBOL_PATH}/${TIMEFRAME}/decisions.csv"
  TRADES_CSV="$PROJ/data/processed/trades/${DATA_TAG}/${SYMBOL_PATH}/${TIMEFRAME}/trades.csv"

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

  STOP="off"
  [[ -f "$KILL_SWITCH_FILE" ]] && STOP="ON"
  HALT="off"
  [[ -f "$HALT_ORDERS_FILE" ]] && HALT="ON"
  ARM="off"
  [[ -f "$ARM_FILE" ]] && ARM="ON"

  paper_status="$(svc_is_up paper)"
  trade_status="$(svc_is_up trade)"
  dashboard_status="$(svc_is_up dashboard)"

  # ---- ENFORCEMENT (A+B): STOP/HALT/DAILY LIMITS => stop paper ----
  HALTED_REASON=""

  if [[ -f "$KILL_SWITCH_FILE" ]]; then
    HALTED_REASON="kill_switch(${KILL_SWITCH_FILE})"
  elif [[ -f "$HALT_ORDERS_FILE" ]]; then
    HALTED_REASON="halt_orders(${HALT_ORDERS_FILE})"
  else
    if [[ -x "$PROJ/ops/daily_limits_check.py" ]]; then
      # daily_limits_check returns rc=2 to mean "limits exceeded".
      # With `set -e`, we must capture rc manually or the script exits early.
      rc=0
      set +e
      python3 "$PROJ/ops/daily_limits_check.py" \
        --trades-csv "$TRADES_CSV" \
        --max-trades-per-day "$MAX_TRADES_PER_DAY" \
        --max-daily-loss-usd "$MAX_DAILY_LOSS_USD" \
        --tz "$TZ_LOCAL" \
        --quiet
      rc=$?
      set -e

      if [[ "$rc" == "2" ]]; then
        HALTED_REASON="daily_limits(max_trades=${MAX_TRADES_PER_DAY} max_loss=${MAX_DAILY_LOSS_USD} tz=${TZ_LOCAL})"
      elif [[ "$rc" != "0" ]]; then
        echo "WARN: daily_limits_check rc=$rc (not halting)"
      fi
    else
      echo "WARN: daily_limits_check.py missing or not executable (not halting)"
    fi
  fi

  PAPER_ACTION="none"
  if [[ -n "$HALTED_REASON" ]]; then
    if docker inspect -f '{{.State.Running}}' paper 2>/dev/null | grep -qx true; then
      echo "ENFORCE: stopping paper due to ${HALTED_REASON}"
      docker compose stop paper || true
      PAPER_ACTION="stopped"
    else
      PAPER_ACTION="already_down"
    fi
    paper_status="$(svc_is_up paper)"
  fi

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
    echo "halted_reason=${HALTED_REASON}"
    echo "paper_action=${PAPER_ACTION}"
  } >"$tmp"
  mv -f "$tmp" "$STATUS_FILE"

  echo "=== status beacon ==="
  stat -c 'status_mtime=%y size=%s path=%n' "$STATUS_FILE" 2>/dev/null || true
  tail -n 30 "$STATUS_FILE" || true
  echo
) 9>"$LOCK"
