#!/usr/bin/env bash
# StockSignal Frontend v2 launcher (Git Bash / Linux).
# Starts the Flask backend (default 5050) and the Vite dev server (default 5173).
# Vite proxies /api and /webapps to the backend, so the backend must run too.
#
# Usage:
#   ./start_frontend_v2.sh                              # start both
#   STOCKSIGNAL_PORT=5100 ./start_frontend_v2.sh         # custom backend port
#   STOCKSIGNAL_V2_PORT=5180 ./start_frontend_v2.sh      # custom vite port
#
# Stop: kill the printed PIDs, or run _stop_services.bat (Windows) for the backend.
#   pkill -f "flask --app backend.app"   # stop backend
#   pkill -f vite                       # stop frontend

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

# --- backend / frontend ports ---
BACKEND_PORT="${STOCKSIGNAL_PORT:-5050}"
V2_PORT="${STOCKSIGNAL_V2_PORT:-5173}"

# --- require npm ---
if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm not found on PATH."
  exit 1
fi

mkdir -p "$HERE/logs"

# --- if backend port is not the default 5050, point vite proxy at it ---
if [ "$BACKEND_PORT" != "5050" ]; then
  export VITE_PROXY_TARGET="http://127.0.0.1:${BACKEND_PORT}"
fi

echo "======================================"
echo "  StockSignal Frontend v2 Launcher"
echo "======================================"
echo "  Backend  : http://127.0.0.1:${BACKEND_PORT}/api/health"
echo "  Frontend : http://127.0.0.1:${V2_PORT}/"
echo "======================================"

# --- start backend (background, logs to file) ---
nohup "$PY" -m flask --app backend.app:app run --host 127.0.0.1 --port "$BACKEND_PORT" \
  > "$HERE/logs/backend_v2.log" 2>&1 &
BE_PID=$!

# --- start vite dev server (background, logs to file) ---
cd "$HERE/frontend-v2"
nohup npm run dev -- --port "$V2_PORT" > "$HERE/logs/frontend_v2.log" 2>&1 &
FE_PID=$!
cd "$HERE"

sleep 3

echo ""
echo "Backend  PID=$BE_PID  ->  logs/backend_v2.log"
echo "Frontend PID=$FE_PID  ->  logs/frontend_v2.log"
echo "Open: http://127.0.0.1:${V2_PORT}/"

# --- try to open the browser ---
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://127.0.0.1:${V2_PORT}/" >/dev/null 2>&1 &
elif command -v start >/dev/null 2>&1; then
  start "" "http://127.0.0.1:${V2_PORT}/" >/dev/null 2>&1 &
fi

echo ""
echo "Stop: kill $BE_PID $FE_PID   (or: pkill -f vite / pkill -f \"flask --app backend.app\")"
