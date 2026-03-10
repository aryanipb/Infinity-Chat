#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if [ ! -d .venv ]; then
  echo "Missing .venv. Run ./setup.sh first."
  exit 1
fi

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8080}"
UI_HOST="${UI_HOST:-0.0.0.0}"
UI_PORT="${UI_PORT:-8501}"

source .venv/bin/activate

nohup python -m uvicorn main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" > backend.log 2>&1 &
BACKEND_PID=$!

nohup streamlit run ui.py --server.port "$UI_PORT" --server.address "$UI_HOST" > streamlit.log 2>&1 &
UI_PID=$!

echo "$BACKEND_PID" > backend.pid
echo "$UI_PID" > streamlit.pid

echo "Backend started on http://127.0.0.1:$BACKEND_PORT (PID: $BACKEND_PID)"
echo "Streamlit started on http://127.0.0.1:$UI_PORT (PID: $UI_PID)"
echo "LAN access: http://<your-lan-ip>:$UI_PORT"
echo "Logs: backend.log, streamlit.log"
