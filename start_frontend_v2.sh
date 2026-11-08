#!/usr/bin/env bash
# StockSignal Frontend v2 launcher (Git Bash / Linux).
# Starts the Flask backend (default 5050) and the Vite dev server (default 5173).
#
# Both services are started DETACHED by scripts/start_v2_detached.py:
# no console window is required, and closing this terminal does NOT stop them.
# On Windows the launcher uses CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
# on POSIX it uses start_new_session. Logs go to logs/*_v2.log (append mode).
#
# Usage:
#   ./start_frontend_v2.sh                              # start both
#   STOCKSIGNAL_PORT=5100 ./start_frontend_v2.sh         # custom backend port
#   STOCKSIGNAL_V2_PORT=5180 ./start_frontend_v2.sh      # custom vite port
#   STOCKSIGNAL_USE_MOCKS=1 ./start_frontend_v2.sh       # force MSW demo data
#   SS_NO_BROWSER=1 ./start_frontend_v2.sh               # do not open a browser
#
# Stop: _stop_services.bat (Windows, reads logs/active_ports_v2.json + kills by port).

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

# --- resolve python for the backend ---
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x "$HERE/venv/bin/python" ]; then
    PY="$HERE/venv/bin/python"
  elif [ -x "$HERE/venv/Scripts/python.exe" ]; then
    PY="$HERE/venv/Scripts/python.exe"
  elif command -v python3 >/dev/null 2>&1; then
    PY="$(command -v python3)"
  else
    PY="$(command -v python)"
  fi
fi

if ! command -v npm >/dev/null 2>&1 && ! command -v npm.cmd >/dev/null 2>&1; then
  echo "[ERROR] npm not found on PATH."
  exit 1
fi

# --- backend / frontend ports ---
BACKEND_PORT="${STOCKSIGNAL_PORT:-5050}"
V2_PORT="${STOCKSIGNAL_V2_PORT:-5173}"

# --- data source: this launcher also starts a real backend, so use it ---
# Default: real backend (MSW off). Set STOCKSIGNAL_USE_MOCKS=1 for demo data.
if [ "${STOCKSIGNAL_USE_MOCKS:-0}" = "1" ]; then
  export VITE_ENABLE_MOCKS=true
else
  export VITE_ENABLE_MOCKS=false
fi

# --- values consumed by the detached python launcher ---
export SS_PY="$PY"
export SS_NPM="$(command -v npm.cmd 2>/dev/null || command -v npm)"
export SS_BACKEND_PORT="$BACKEND_PORT"
export SS_V2_PORT="$V2_PORT"
# No visible window here, so let the worker open the browser exactly once.
if [ "${SS_NO_BROWSER:-0}" != "1" ]; then
  export SS_OPEN_BROWSER=1
fi

mkdir -p "$HERE/logs"

echo "======================================"
echo "  StockSignal Frontend v2 Launcher"
echo "======================================"
echo "  Backend  : http://127.0.0.1:${BACKEND_PORT}/api/health"
echo "  Frontend : http://127.0.0.1:${V2_PORT}/"
echo "  Data     : real backend (MSW=${VITE_ENABLE_MOCKS}); login demo / Demo@123"
echo "======================================"
echo ""

"$PY" "$HERE/scripts/start_v2_detached.py"
STATUS=$?

echo ""
echo "The services keep running after this terminal is closed."
echo "Stop them with _stop_services.bat (ports ${BACKEND_PORT} / ${V2_PORT})."
exit "$STATUS"
