#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXCLUDE_FILE="${ROOT_DIR}/ops/rsync_exclude.txt"

OLD_BOX_HOST="${OLD_BOX_HOST:-}"
OLD_BOX_DIR="${OLD_BOX_DIR:-}"
RSYNC_SSH_OPTS="${RSYNC_SSH_OPTS:-}"
RSYNC_EXTRA_OPTS="${RSYNC_EXTRA_OPTS:-}"
MODE="${1:-}"

if [[ -z "${OLD_BOX_HOST}" || -z "${OLD_BOX_DIR}" ]]; then
  echo "ERROR: set OLD_BOX_HOST and OLD_BOX_DIR"
  echo "Example:"
  echo "  OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=~/Projects/trade $0 --dry-run"
  exit 2
fi

if [[ ! -f "${EXCLUDE_FILE}" ]]; then
  echo "ERROR: missing ${EXCLUDE_FILE}"
  exit 2
fi

cd "${ROOT_DIR}"

SSH_CMD="ssh"
if [[ -n "${RSYNC_SSH_OPTS}" ]]; then
  SSH_CMD="ssh ${RSYNC_SSH_OPTS}"
fi

# Make rsync boring:
# - no delete (ever)
# - don't fail on directory timestamp updates (common on some FS/permissions)
RSYNC_BASE=(
  rsync -az
  --no-perms --no-owner --no-group
  --omit-dir-times
  --itemize-changes
  --human-readable
  --exclude-from="${EXCLUDE_FILE}"
  -e "${SSH_CMD}"
)

if [[ -n "${RSYNC_EXTRA_OPTS}" ]]; then
  # shellcheck disable=SC2206
  RSYNC_BASE+=( ${RSYNC_EXTRA_OPTS} )
fi

SRC="${ROOT_DIR}/"
DST="${OLD_BOX_HOST}:${OLD_BOX_DIR%/}/"

echo "=== deploy_oldbox ==="
echo "root=${ROOT_DIR}"
echo "src=${SRC}"
echo "dst=${DST}"
echo "exclude=${EXCLUDE_FILE}"
echo "mode=${MODE:-deploy}"
echo

if [[ "${MODE}" == "--dry-run" ]]; then
  echo "=== RSYNC DRY RUN (no delete) ==="
  "${RSYNC_BASE[@]}" --dry-run --checksum "${SRC}" "${DST}"
  echo
  echo "PASS expectation: runtime-only paths must not appear in the itemized list."
  exit 0
fi

echo "=== RSYNC DEPLOY (no delete) ==="
"${RSYNC_BASE[@]}" "${SRC}" "${DST}"

echo
echo "Done."
