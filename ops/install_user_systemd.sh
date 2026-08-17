#!/usr/bin/env bash

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
FLAGS_DIR="${FLAGS_DIR:-${HOME}/trade_flags}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker not found"
docker compose version >/dev/null 2>&1 || fail "docker compose not available"

[[ -f "${REPO_ROOT}/.env" ]] || fail "missing ${REPO_ROOT}/.env"
[[ -f "${REPO_ROOT}/ops/systemd/trade-stack.service" ]] || fail "missing trade-stack.service"
[[ -f "${REPO_ROOT}/ops/systemd/trade-heartbeat.service" ]] || fail "missing trade-heartbeat.service"
[[ -f "${REPO_ROOT}/ops/systemd/trade-heartbeat.timer" ]] || fail "missing trade-heartbeat.timer"
[[ -x "${REPO_ROOT}/ops/prepare_runtime.sh" ]] || fail "missing executable ops/prepare_runtime.sh"

FLAGS_DIR="${FLAGS_DIR}" "${REPO_ROOT}/ops/prepare_runtime.sh" || fail "runtime preparation failed"
mkdir -p "${SYSTEMD_USER_DIR}" || fail "cannot create ${SYSTEMD_USER_DIR}"

render_unit() {
  local src="$1"
  local dst="$2"

  sed \
    -e "s|%h/Projects/trade|${REPO_ROOT}|g" \
    "${src}" > "${dst}" || fail "failed to install ${dst}"
}

render_unit \
  "${REPO_ROOT}/ops/systemd/trade-stack.service" \
  "${SYSTEMD_USER_DIR}/trade-stack.service"

render_unit \
  "${REPO_ROOT}/ops/systemd/trade-heartbeat.service" \
  "${SYSTEMD_USER_DIR}/trade-heartbeat.service"

cp \
  "${REPO_ROOT}/ops/systemd/trade-heartbeat.timer" \
  "${SYSTEMD_USER_DIR}/trade-heartbeat.timer" \
  || fail "failed to install trade-heartbeat.timer"

systemctl --user daemon-reload || fail "systemctl --user daemon-reload failed"
systemctl --user enable trade-stack.service || fail "failed to enable trade-stack.service"
systemctl --user enable trade-heartbeat.timer || fail "failed to enable trade-heartbeat.timer"

echo
echo "Installed MJÖLNIR user-systemd configuration."
echo "repo=${REPO_ROOT}"
echo "flags_dir=${FLAGS_DIR}"
echo

linger="$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || true)"
if [[ "${linger}" == "yes" ]]; then
  echo "linger=yes"
else
  echo "linger=${linger:-unknown}"
  echo "Run once if unattended reboot startup is required:"
  echo "  sudo loginctl enable-linger \"${USER}\""
fi

echo
echo "No services were started or restarted."
echo "No .env, STOP, HALT, ARM, data, or safety settings were modified."
