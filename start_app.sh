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

source .venv/bin/activate

nohup python -m uvicorn main:app --host 0.0.0.0 --port 8080 > backend.log 2>&1 &
BACKEND_PID=$!

nohup streamlit run ui.py --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &
UI_PID=$!

echo "$BACKEND_PID" > backend.pid
echo "$UI_PID" > streamlit.pid

echo "Backend started on http://127.0.0.1:8080 (PID: $BACKEND_PID)"
echo "Streamlit started on http://127.0.0.1:8501 (PID: $UI_PID)"
echo "Logs: backend.log, streamlit.log"
