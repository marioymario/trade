#!/usr/bin/env bash
# ops/deploy_target.sh
# Deploy from LOCAL to TARGET without editing repo on target:
# - push local commits
# - ssh into target: git pull --ff-only + restart compose
#
# Configure via env vars:
#   TARGET_HOST=10.0.0.82
#   TARGET_USER=kk7wus
#   TARGET_PORT=2332
#   TARGET_REPO=/home/kk7wus/Projects/trade
#
# Usage:
#   TARGET_HOST=... TARGET_USER=... TARGET_PORT=... ./ops/deploy_target.sh
#set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${TARGET_HOST:?Set TARGET_HOST}"
: "${TARGET_USER:?Set TARGET_USER}"
TARGET_PORT="${TARGET_PORT:-22}"
TARGET_REPO="${TARGET_REPO:-/home/${TARGET_USER}/Projects/trade}"

cd "$REPO_ROOT"

echo "=== Local: git status ==="
git status --porcelain || true

echo "=== Local: pushing current branch ==="
git push

echo "=== Target: pull + restart ==="
ssh -p "$TARGET_PORT" "${TARGET_USER}@${TARGET_HOST}" bash -lc "'
set -euo pipefail
cd \"$TARGET_REPO\"
echo \"[target] repo: \$PWD\"
git pull --ff-only
# restart using the same logic as cron (GPU->CPU fallback)
if [[ -x ops/cron_reboot.sh ]]; then
  ops/cron_reboot.sh
else
  docker compose up -d
fi
docker compose ps
'"
