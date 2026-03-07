#!/usr/bin/env bash
# ops/cron_heartbeat.sh
#
# Contract:
# - Heartbeat is NON-LETHAL: it never stops/restarts containers.
# - It only publishes truth + intent to status.txt.
# - Safety enforcement happens inside paper (files/main.py).

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

    if [[ "${key}=" =~ $allow ]]; then
      export "${key}=${val}"
    fi
  done <"$env_file"
}

svc_is_up() {
  local svc="$1"
  if docker inspect -f '{{.State.Running}}' "$svc" 2>/dev/null | grep -qx true; then
    echo "up"
  else
    echo "down"
  fi
}

_exists() {
  local p="$1"
  [[ -n "$p" && -f "$p" ]]
}

(
  flock -n 9 || exit 0

  exec >>"$LOG" 2>&1

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

  STATUS_FILE="${FLAGS_DIR}/status.txt"
  mkdir -p "$FLAGS_DIR"

  DECISIONS_CSV="$PROJ/data/processed/decisions/${DATA_TAG}/${SYMBOL_PATH}/${TIMEFRAME}/decisions.csv"

  STOP="off"
  _exists "$KILL_SWITCH_FILE" && STOP="ON"

  HALT="off"
  _exists "$HALT_ORDERS_FILE" && HALT="ON"

  ARM="off"
  _exists "$ARM_FILE" && ARM="ON"

  paper_status="$(svc_is_up paper)"
  trade_status="$(svc_is_up trade)"
  dashboard_status="$(svc_is_up dashboard)"

  ARMED_SRC="arm_file"
  if [[ "$ARM" == "ON" ]]; then
    ARMED="1"
  else
    ARMED="0"
  fi

  # --- Extract latest decision info ---
  MARKET_REASON="na"
  ENTRY_SHOULD_ENTER="na"
  EXIT_SHOULD_EXIT="na"
  POS_SIDE="na"

  if [[ -f "$DECISIONS_CSV" ]]; then
    while IFS='=' read -r k v; do
      case "$k" in
      MARKET_REASON) MARKET_REASON="$v" ;;
      ENTRY_SHOULD_ENTER) ENTRY_SHOULD_ENTER="$v" ;;
      EXIT_SHOULD_EXIT) EXIT_SHOULD_EXIT="$v" ;;
      POS_SIDE) POS_SIDE="$v" ;;
      esac
    done < <(
      python3 - "$DECISIONS_CSV" <<'PY'
import csv, sys
path = sys.argv[1]

keys = {
"MARKET_REASON": "market_reason",
"ENTRY_SHOULD_ENTER": "entry_should_enter",
"EXIT_SHOULD_EXIT": "exit_should_exit",
"POS_SIDE": "position_side",
}

vals = {k:"na" for k in keys}

try:
    with open(path,"r",newline="",encoding="utf-8") as f:
        r = csv.DictReader(f)
        last = None
        for row in r:
            last=row
        if last:
            for k, col in keys.items():
                v = last.get(col)
                if v and str(v).strip():
                    vals[k]=str(v).strip()
except:
    pass

for k,v in vals.items():
    print(f"{k}={v}")
PY
    )
  fi

  # --- Determine system mode ---
  SYSTEM_MODE="normal"

  if [[ "$MARKET_REASON" == DEGRADED* ]]; then
    SYSTEM_MODE="$MARKET_REASON"
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
    echo "ARMED=${ARMED}"
    echo "armed_src=${ARMED_SRC}"

    echo "system_mode=${SYSTEM_MODE}"

    echo "pos_side=${POS_SIDE}"
    echo "entry_should_enter=${ENTRY_SHOULD_ENTER}"
    echo "exit_should_exit=${EXIT_SHOULD_EXIT}"

  } >"$tmp"

  mv -f "$tmp" "$STATUS_FILE"

) 9>"$LOCK"
