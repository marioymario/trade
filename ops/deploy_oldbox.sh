#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ops/deploy_oldbox.sh kk7wus@10.0.0.222 2222
#
# Deploys the current git HEAD to old-box via rsync, excluding .env and data/.
# Refuses to run if working tree is dirty.

TARGET_HOST="${1:-}"
SSH_PORT="${2:-2222}"

if [[ -z "$TARGET_HOST" ]]; then
  echo "usage: $0 <user@host> [ssh_port]" >&2
  exit 2
fi

cd "$(git rev-parse --show-toplevel)" || exit 1

# Must be a git repo
git rev-parse --is-inside-work-tree >/dev/null

# Refuse dirty tree
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: working tree is dirty. Commit or stash before deploy." >&2
  git status --porcelain >&2
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COMMIT="$(git rev-parse HEAD)"
SHORT="$(git rev-parse --short HEAD)"

echo "Deploying branch=${BRANCH} commit=${COMMIT} to ${TARGET_HOST}:${SSH_PORT}"

# Write deploy marker into ops/ (excluded from gitignore) and sync it too
DEPLOY_MARKER="ops/DEPLOYED_${SHORT}.txt"
{
  echo "ts_utc=$(date -u -Is | sed 's/+00:00/Z/')"
  echo "branch=${BRANCH}"
  echo "commit=${COMMIT}"
  echo "short=${SHORT}"
} > "${DEPLOY_MARKER}"

# Rsync repo contents excluding local-only/runtime data
rsync -av --progress -e "ssh -p ${SSH_PORT}" \
  --delete \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude 'data/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  ./ "${TARGET_HOST}:~/Projects/trade/"

echo "Done."
echo "Marker synced: ${DEPLOY_MARKER}"

