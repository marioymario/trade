#!/usr/bin/env bash
# ops/cron_heartbeat.sh
#
# Contract:
# - Heartbeat is NON-LETHAL: it never stops/restarts containers.
# - It only publishes truth + intent to status.txt.
# - Safety enforcement happens inside paper (files/main.py).

#set -u -o pipefail

LOG="${HOME}/trade_heartbeat.log"
LOCK="/tmp/trade_heartbeat.lock"

load_env_allowlist() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  # NOTE:
  # - ARMED is intentionally NOT treated as authority anymore (ARM_FILE existence is).
  # - DRY_RUN *is* authoritative from .env for reporting (compose create-time truth).
  local allow="^(DATA_TAG|SYMBOL|TIMEFRAME|DRY_RUN|FLAGS_DIR|KILL_SWITCH_FILE|HALT_ORDERS_FILE|ARM_FILE|MAX_TRADES_PER_DAY|MAX_DAILY_LOSS_USD|TZ_LOCAL)=$"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue

    local key="${line%%=*}"
    local val="${line#*=}"

    # Strip wrapping quotes
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

_exists() {
  local p="$1"
  [[ -n "$p" && -f "$p" ]]
}

# Read a single env var from inside the running paper container (best-effort debug only).
paper_env_get() {
  local name="$1"
  docker compose exec -T paper sh -lc "printf '%s' \"\${${name}:-}\"" 2>/dev/null || true
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
  : "${DRY_RUN:=1}"

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
  csv_mtime_utc="na"
  if [[ -f "$DECISIONS_CSV" ]]; then
    csv_epoch="$(stat -c %Y "$DECISIONS_CSV" 2>/dev/null || echo 0)"
    csv_mtime_utc="$(as_utc "$csv_epoch")"
    echo "decisions_mtime_utc=${csv_mtime_utc}"
    tail -n 1 "$DECISIONS_CSV" || true
  else
    echo "decisions_mtime_utc=na"
    echo "decisions_csv_missing=1"
  fi
  echo

  echo "=== paper logs (since 15m) ==="
  docker compose logs --since 15m --tail 200 paper 2>/dev/null || true
  echo

  STOP="off"
  _exists "$KILL_SWITCH_FILE" && STOP="ON"
  HALT="off"
  _exists "$HALT_ORDERS_FILE" && HALT="ON"
  ARM="off"
  _exists "$ARM_FILE" && ARM="ON"

  paper_status="$(svc_is_up paper)"
  trade_status="$(svc_is_up trade)"
  dashboard_status="$(svc_is_up dashboard)"

  # --- ARMED truth (single source): ARM_FILE existence ---
  ARMED_SRC="arm_file"
  if [[ "$ARM" == "ON" ]]; then
    ARMED="1"
  else
    ARMED="0"
  fi

  # Debug-only: capture container ARMED env if paper is up (never authoritative)
  ARMED_ENV="na"
  ARMED_ENV_MISMATCH="na"
  if [[ "$paper_status" == "up" ]]; then
    v="$(paper_env_get ARMED)"
    if [[ -n "$v" ]]; then
      ARMED_ENV="$v"
      if [[ "$ARMED_ENV" != "$ARMED" ]]; then
        ARMED_ENV_MISMATCH="1"
      else
        ARMED_ENV_MISMATCH="0"
      fi
    fi
  fi

  # --- DRY_RUN truth: from .env (authoritative for reporting) ---
  DRY_RUN_SRC="env_file"
  DRY_RUN_ENV="na"
  DRY_RUN_ENV_MISMATCH="na"
  if [[ "$paper_status" == "up" ]]; then
    v="$(paper_env_get DRY_RUN)"
    if [[ -n "$v" ]]; then
      DRY_RUN_ENV="$v"
      if [[ "$DRY_RUN_ENV" != "$DRY_RUN" ]]; then
        DRY_RUN_ENV_MISMATCH="1"
      else
        DRY_RUN_ENV_MISMATCH="0"
      fi
    fi
  fi

  # ---- Compute halt intent (NON-LETHAL) ----
  HALTED_REASON=""

  LIMITS_STATE="na"
  LIMITS_REASON="na"
  LIMITS_TRADES_TODAY="na"
  LIMITS_PNL_TODAY_USD="na"

  if _exists "$KILL_SWITCH_FILE"; then
    HALTED_REASON="kill_switch(${KILL_SWITCH_FILE})"
  elif _exists "$HALT_ORDERS_FILE"; then
    HALTED_REASON="halt_orders(${HALT_ORDERS_FILE})"
  else
    if [[ -x "$PROJ/ops/daily_limits_check.py" ]]; then
      rc=0
      out=""
      set +e
      out="$(
        python3 "$PROJ/ops/daily_limits_check.py" \
          --trades-csv "$TRADES_CSV" \
          --max-trades-per-day "$MAX_TRADES_PER_DAY" \
          --max-daily-loss-usd "$MAX_DAILY_LOSS_USD" \
          --tz "$TZ_LOCAL" \
          --quiet
      )"
      rc=$?
      set -e

      for tok in $out; do
        case "$tok" in
        limits_state=*) LIMITS_STATE="${tok#limits_state=}" ;;
        reason=*) LIMITS_REASON="${tok#reason=}" ;;
        trades_today=*) LIMITS_TRADES_TODAY="${tok#trades_today=}" ;;
        pnl_today_usd=*) LIMITS_PNL_TODAY_USD="${tok#pnl_today_usd=}" ;;
        esac
      done

      if [[ "$rc" == "2" ]]; then
        HALTED_REASON="daily_limits(${LIMITS_REASON})"
      elif [[ "$rc" != "0" ]]; then
        echo "WARN: daily_limits_check rc=$rc (non-fatal) out='$out'"
      fi
    else
      echo "WARN: daily_limits_check.py missing or not executable (non-fatal)"
    fi
  fi

  ENFORCEMENT_MODE="soft"
  ENFORCEMENT_WOULD_STOP="0"
  ENFORCEMENT_ACTION="none"
  if [[ -n "$HALTED_REASON" ]]; then
    ENFORCEMENT_WOULD_STOP="1"
  fi

  PAPER_ACTION="none"

  # ---- Position snapshot from latest decision row (header-aware) ----
  POS_SIDE="na"
  POS_QTY="na"
  POS_ENTRY_PX="na"
  POS_STOP_PX="na"
  POS_TRAIL_ANCHOR_PX="na"
  POS_UNREAL_PNL_USD="na"
  POS_UNREAL_PNL_PCT="na"

  TRAIL_REASON="na"
  TRAIL_NEW_STOP="na"
  TRAIL_NEW_ANCHOR="na"

  ENTRY_SHOULD_ENTER="na"
  ENTRY_SIDE="na"
  ENTRY_CONFIDENCE="na"
  ENTRY_REASON="na"

  EXIT_SHOULD_EXIT="na"
  EXIT_REASON="na"

  if [[ -f "$DECISIONS_CSV" ]]; then
    while IFS='=' read -r k v; do
      [[ -z "$k" ]] && continue
      case "$k" in
      POS_SIDE) POS_SIDE="$v" ;;
      POS_QTY) POS_QTY="$v" ;;
      POS_ENTRY_PX) POS_ENTRY_PX="$v" ;;
      POS_STOP_PX) POS_STOP_PX="$v" ;;
      POS_TRAIL_ANCHOR_PX) POS_TRAIL_ANCHOR_PX="$v" ;;
      POS_UNREAL_PNL_USD) POS_UNREAL_PNL_USD="$v" ;;
      POS_UNREAL_PNL_PCT) POS_UNREAL_PNL_PCT="$v" ;;
      TRAIL_REASON) TRAIL_REASON="$v" ;;
      TRAIL_NEW_STOP) TRAIL_NEW_STOP="$v" ;;
      TRAIL_NEW_ANCHOR) TRAIL_NEW_ANCHOR="$v" ;;
      ENTRY_SHOULD_ENTER) ENTRY_SHOULD_ENTER="$v" ;;
      ENTRY_SIDE) ENTRY_SIDE="$v" ;;
      ENTRY_CONFIDENCE) ENTRY_CONFIDENCE="$v" ;;
      ENTRY_REASON) ENTRY_REASON="$v" ;;
      EXIT_SHOULD_EXIT) EXIT_SHOULD_EXIT="$v" ;;
      EXIT_REASON) EXIT_REASON="$v" ;;
      esac
    done < <(
      python3 - "$DECISIONS_CSV" <<'PY'
import csv, sys
path = sys.argv[1]
out = {k:"na" for k in [
  "POS_SIDE","POS_QTY","POS_ENTRY_PX","POS_STOP_PX","POS_TRAIL_ANCHOR_PX",
  "POS_UNREAL_PNL_USD","POS_UNREAL_PNL_PCT",
  "TRAIL_REASON","TRAIL_NEW_STOP","TRAIL_NEW_ANCHOR",
  "ENTRY_SHOULD_ENTER","ENTRY_SIDE","ENTRY_CONFIDENCE","ENTRY_REASON",
  "EXIT_SHOULD_EXIT","EXIT_REASON",
]}
def get(row, k):
  v = (row or {}).get(k, "")
  if v is None or str(v).strip() == "":
    return "na"
  return str(v).strip()
try:
  with open(path, "r", newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    last = None
    for row in r:
      last = row
    if last:
      out["POS_SIDE"] = get(last, "position_side")
      out["POS_QTY"] = get(last, "position_qty")
      out["POS_ENTRY_PX"] = get(last, "position_entry_price")
      out["POS_STOP_PX"] = get(last, "position_stop_price")
      out["POS_TRAIL_ANCHOR_PX"] = get(last, "position_trailing_anchor_price")
      out["POS_UNREAL_PNL_USD"] = get(last, "unrealized_pnl_usd")
      out["POS_UNREAL_PNL_PCT"] = get(last, "unrealized_pnl_pct")
      out["TRAIL_REASON"] = get(last, "trail_reason")
      out["TRAIL_NEW_STOP"] = get(last, "trail_new_stop")
      out["TRAIL_NEW_ANCHOR"] = get(last, "trail_new_anchor")
      out["ENTRY_SHOULD_ENTER"] = get(last, "entry_should_enter")
      out["ENTRY_SIDE"] = get(last, "entry_side")
      out["ENTRY_CONFIDENCE"] = get(last, "entry_confidence")
      out["ENTRY_REASON"] = get(last, "entry_reason")
      out["EXIT_SHOULD_EXIT"] = get(last, "exit_should_exit")
      out["EXIT_REASON"] = get(last, "exit_reason")
except Exception:
  pass
for k, v in out.items():
  print(f"{k}={v}")
PY
    )
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

    # Debug-only arming env signal (never authoritative)
    echo "armed_env=${ARMED_ENV}"
    echo "armed_env_mismatch=${ARMED_ENV_MISMATCH}"

    # DRY_RUN reporting (authoritative from env_file + debug from container)
    echo "DRY_RUN=${DRY_RUN}"
    echo "dry_run_src=${DRY_RUN_SRC}"
    echo "dry_run_env=${DRY_RUN_ENV}"
    echo "dry_run_env_mismatch=${DRY_RUN_ENV_MISMATCH}"

    echo "decisions_mtime_utc=${csv_mtime_utc}"
    echo "halted_reason=${HALTED_REASON}"

    echo "enforcement_mode=${ENFORCEMENT_MODE}"
    echo "enforcement_would_stop=${ENFORCEMENT_WOULD_STOP}"
    echo "enforcement_action=${ENFORCEMENT_ACTION}"

    echo "paper_action=${PAPER_ACTION}"

    echo "limits_state=${LIMITS_STATE}"
    echo "limits_reason=${LIMITS_REASON}"
    echo "trades_today=${LIMITS_TRADES_TODAY}"
    echo "pnl_today_usd=${LIMITS_PNL_TODAY_USD}"

    echo "pos_side=${POS_SIDE}"
    echo "pos_qty=${POS_QTY}"
    echo "pos_entry_px=${POS_ENTRY_PX}"
    echo "pos_stop_px=${POS_STOP_PX}"
    echo "pos_trailing_anchor_px=${POS_TRAIL_ANCHOR_PX}"
    echo "pos_unreal_pnl_usd=${POS_UNREAL_PNL_USD}"
    echo "pos_unreal_pnl_pct=${POS_UNREAL_PNL_PCT}"

    echo "trail_reason=${TRAIL_REASON}"
    echo "trail_new_stop=${TRAIL_NEW_STOP}"
    echo "trail_new_anchor=${TRAIL_NEW_ANCHOR}"

    echo "entry_should_enter=${ENTRY_SHOULD_ENTER}"
    echo "entry_side=${ENTRY_SIDE}"
    echo "entry_confidence=${ENTRY_CONFIDENCE}"
    echo "entry_reason=${ENTRY_REASON}"

    echo "exit_should_exit=${EXIT_SHOULD_EXIT}"
    echo "exit_reason=${EXIT_REASON}"
  } >"$tmp"
  mv -f "$tmp" "$STATUS_FILE"

  echo "=== status beacon ==="
  stat -c 'status_mtime=%y size=%s path=%n' "$STATUS_FILE" 2>/dev/null || true
  tail -n 160 "$STATUS_FILE" || true
  echo
) 9>"$LOCK"
