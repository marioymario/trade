#!/usr/bin/env bash

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FLAGS_DIR="${FLAGS_DIR:-${HOME}/trade_flags}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ -f "${REPO_ROOT}/.env" ]] || fail "missing ${REPO_ROOT}/.env"

mkdir -p "${REPO_ROOT}/data" || fail "cannot create ${REPO_ROOT}/data"
mkdir -p "${FLAGS_DIR}" || fail "cannot create ${FLAGS_DIR}"

[[ -w "${REPO_ROOT}/data" ]] || fail "${REPO_ROOT}/data is not writable"
[[ -w "${FLAGS_DIR}" ]] || fail "${FLAGS_DIR} is not writable"

echo "MJÖLNIR runtime directories ready."
echo "repo=${REPO_ROOT}"
echo "data=${REPO_ROOT}/data"
echo "flags=${FLAGS_DIR}"
