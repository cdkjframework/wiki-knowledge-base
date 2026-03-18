#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="knowledge-base"
SERVICE_UNIT="${SERVICE_NAME}.service"
UNIT_PATH="/etc/systemd/system/${SERVICE_UNIT}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_KB="${SCRIPT_DIR}/.venv/bin/knowledge-base"

if [[ -n "${SUDO_USER:-}" ]]; then
  TARGET_USER="${SUDO_USER}"
else
  TARGET_USER="$(id -un)"
fi

if [[ -n "${SUDO_GID:-}" ]]; then
  TARGET_GROUP="$(id -gn "${SUDO_USER:-$TARGET_USER}")"
else
  TARGET_GROUP="$(id -gn)"
fi

info() {
  echo "[*] $*"
}

ok() {
  echo "[+] $*"
}

warn() {
  echo "[!] $*"
}

need_systemd() {
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "[x] systemctl not found. This script requires systemd." >&2
    exit 1
  fi
}

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

show_usage() {
  cat <<'EOF'
Knowledge-Base Linux Service Management
Usage: ./manage_service.sh [command]

Commands:
  install    - Install systemd service unit
  uninstall  - Remove systemd service unit
  start      - Start service
  stop       - Stop service
  restart    - Restart service
  status     - Show service status
  help       - Show this help
EOF
}

install_service() {
  need_systemd
  if [[ ! -x "${VENV_KB}" ]]; then
    echo "[x] ${VENV_KB} not found. Please run install.sh first." >&2
    exit 1
  fi

  info "Installing ${SERVICE_UNIT} ..."
  local unit_tmp
  unit_tmp="$(mktemp)"
  cat >"${unit_tmp}" <<EOF
[Unit]
Description=Knowledge-Base Service
After=network.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
Environment=KB_PROJECT_ROOT=${SCRIPT_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${VENV_KB}
Restart=always
RestartSec=3
User=${TARGET_USER}
Group=${TARGET_GROUP}

[Install]
WantedBy=multi-user.target
EOF

  run_root cp "${unit_tmp}" "${UNIT_PATH}"
  rm -f "${unit_tmp}"
  run_root systemctl daemon-reload
  run_root systemctl enable "${SERVICE_UNIT}"
  ok "Service installed and enabled: ${SERVICE_UNIT}"
}

uninstall_service() {
  need_systemd
  info "Uninstalling ${SERVICE_UNIT} ..."
  run_root systemctl disable --now "${SERVICE_UNIT}" >/dev/null 2>&1 || true
  run_root rm -f "${UNIT_PATH}"
  run_root systemctl daemon-reload
  ok "Service uninstalled: ${SERVICE_UNIT}"
}

start_service() {
  need_systemd
  info "Starting ${SERVICE_UNIT} ..."
  run_root systemctl start "${SERVICE_UNIT}"
  ok "Service started"
}

stop_service() {
  need_systemd
  info "Stopping ${SERVICE_UNIT} ..."
  run_root systemctl stop "${SERVICE_UNIT}"
  ok "Service stopped"
}

restart_service() {
  need_systemd
  info "Restarting ${SERVICE_UNIT} ..."
  run_root systemctl restart "${SERVICE_UNIT}"
  ok "Service restarted"
}

status_service() {
  need_systemd
  run_root systemctl status "${SERVICE_UNIT}" --no-pager || true
}

COMMAND="${1:-help}"
case "${COMMAND}" in
  install)
    install_service
    ;;
  uninstall)
    uninstall_service
    ;;
  start)
    start_service
    ;;
  stop)
    stop_service
    ;;
  restart)
    restart_service
    ;;
  status)
    status_service
    ;;
  help|-h|--help)
    show_usage
    ;;
  *)
    echo "[x] Unknown command: ${COMMAND}" >&2
    show_usage
    exit 1
    ;;
esac
