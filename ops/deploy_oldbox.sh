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

GIT_COMMIT="$(git rev-parse HEAD)"
GIT_BRANCH="$(git branch --show-current)"
GIT_STATUS="$(git status --porcelain)"

if [[ -z "${GIT_COMMIT}" || -z "${GIT_BRANCH}" ]]; then
  echo "ERROR: unable to resolve Git identity"
  exit 2
fi

if [[ -z "${GIT_STATUS}" ]]; then
  GIT_WORKING_TREE_CLEAN=true
else
  GIT_WORKING_TREE_CLEAN=false
fi

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

DEPLOYED_AT_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

DEPLOY_IDENTITY_PATH="${OLD_BOX_DIR%/}/files/research/contracts/.deployed_git_identity.json"

"${SSH_CMD}" "${OLD_BOX_HOST}" \
  "mkdir -p '${OLD_BOX_DIR%/}/files/research/contracts' && cat > '${DEPLOY_IDENTITY_PATH}'" <<EOF
{
  "git_commit": "${GIT_COMMIT}",
  "git_branch": "${GIT_BRANCH}",
  "working_tree_clean": ${GIT_WORKING_TREE_CLEAN},
  "deployed_at_utc": "${DEPLOYED_AT_UTC}"
}
EOF

echo
echo "deployed_git_commit=${GIT_COMMIT}"
echo "deployed_git_branch=${GIT_BRANCH}"
echo "deployed_working_tree_clean=${GIT_WORKING_TREE_CLEAN}"
echo "Done."
