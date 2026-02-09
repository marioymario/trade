#!/usr/bin/env bash
# ops/archive_logs.sh
#
# Archives ops logs + docker compose logs into a tar.gz on a storage drive,
# then truncates the live ops logs (NOT docker logs).
#
# REQUIRED env:
#   ARCHIVE_ROOT  e.g. /mnt/trade_storage/trade_archives
#
# Optional env:
#   KEEP_DAYS             delete archives older than N days (0 disables), default 0
#   PROJ                  repo path (default: script parent)
#   INCLUDE_DOCKER_LOGS   1/0 (default 1)
#   DOCKER_LOG_SINCE      override "since" timestamp (RFC3339). If unset, uses last successful archive time; else 24h ago.

# set -euo pipefail

ARCHIVE_ROOT="${ARCHIVE_ROOT:-}"
if [[ -z "$ARCHIVE_ROOT" ]]; then
  echo "ERROR: ARCHIVE_ROOT is required (example: /mnt/trade_storage/trade_archives)" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJ="${PROJ:-$REPO_ROOT}"

INCLUDE_DOCKER_LOGS="${INCLUDE_DOCKER_LOGS:-1}"

TS="$(date -Is | tr ':' '-' )"
DAY="$(date +%F)"
HOST="$(hostname -s 2>/dev/null || hostname)"

SRC1="${SRC1:-$HOME/trade_heartbeat.log}"
SRC2="${SRC2:-$HOME/trade_reboot.log}"
SRC3="${SRC3:-$HOME/trade_archive.log}"

DEST_DIR="$ARCHIVE_ROOT/logs/$DAY"
STATE_DIR="$ARCHIVE_ROOT/state"
mkdir -p "$DEST_DIR" "$STATE_DIR"

ARCHIVE_FILE="$DEST_DIR/trade_bundle_${HOST}_${TS}.tar.gz"
LAST_TS_FILE="$STATE_DIR/last_archive_rfc3339.txt"

echo "=== archive_logs ==="
echo "PROJ=$PROJ"
echo "DEST_DIR=$DEST_DIR"
echo "ARCHIVE_FILE=$ARCHIVE_FILE"
echo "SRC1=$SRC1"
echo "SRC2=$SRC2"
echo "SRC3=$SRC3"
echo "INCLUDE_DOCKER_LOGS=$INCLUDE_DOCKER_LOGS"

touch "$SRC1" "$SRC2" "$SRC3"

SINCE=""
if [[ -n "${DOCKER_LOG_SINCE:-}" ]]; then
  SINCE="$DOCKER_LOG_SINCE"
elif [[ -f "$LAST_TS_FILE" ]]; then
  SINCE="$(cat "$LAST_TS_FILE" || true)"
fi
if [[ -z "$SINCE" ]]; then
  SINCE="$(date -Is -d '24 hours ago')"
fi
echo "DOCKER_LOGS_SINCE=$SINCE"

STAGE="$(mktemp -d "$DEST_DIR/.stage_${TS}.XXXXXX")"
cleanup() { rm -rf "$STAGE" 2>/dev/null || true; }
trap cleanup EXIT

cp -f "$SRC1" "$STAGE/trade_heartbeat.log"
cp -f "$SRC2" "$STAGE/trade_reboot.log"
cp -f "$SRC3" "$STAGE/trade_archive.log"

{
  date -Is
  echo
  echo "=== docker compose ps ==="
  cd "$PROJ" && /usr/bin/docker compose --project-directory "$PROJ" ps 2>&1 || true
} > "$STAGE/compose_status.txt"

if [[ "$INCLUDE_DOCKER_LOGS" == "1" ]]; then
  {
    echo "=== docker compose logs paper (since=$SINCE) ==="
    cd "$PROJ" && /usr/bin/docker compose --project-directory "$PROJ" logs --since "$SINCE" --no-color paper 2>&1 || true
  } > "$STAGE/docker_paper.log"

  {
    echo "=== docker compose logs trade (since=$SINCE) ==="
    cd "$PROJ" && /usr/bin/docker compose --project-directory "$PROJ" logs --since "$SINCE" --no-color trade 2>&1 || true
  } > "$STAGE/docker_trade.log"
fi

TMP_TAR="$(mktemp -p "$DEST_DIR" ".tmp_trade_bundle_${TS}.XXXXXX.tar.gz")"
tar -czf "$TMP_TAR" -C "$STAGE" .
tar -tzf "$TMP_TAR" >/dev/null
mv -f "$TMP_TAR" "$ARCHIVE_FILE"

: > "$SRC1"
: > "$SRC2"
: > "$SRC3"

date -Is > "$LAST_TS_FILE"

echo "OK: archived bundle and truncated ops logs."
echo "Wrote: $ARCHIVE_FILE"

KEEP_DAYS="${KEEP_DAYS:-0}"
if [[ "$KEEP_DAYS" -gt 0 ]]; then
  echo "Cleanup: removing archives older than $KEEP_DAYS days under $ARCHIVE_ROOT/logs"
  find "$ARCHIVE_ROOT/logs" -mindepth 1 -maxdepth 2 -type d -mtime +"$KEEP_DAYS" -print -exec rm -rf {} \; || true
fi
