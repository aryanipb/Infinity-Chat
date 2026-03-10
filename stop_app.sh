#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

stop_from_pid_file() {
  local file="$1"
  local name="$2"
  if [ -f "$file" ]; then
    pid="$(cat "$file")"
    if kill "$pid" >/dev/null 2>&1; then
      echo "Stopped $name (PID: $pid)"
    else
      echo "$name already stopped or PID invalid"
    fi
    rm -f "$file"
  else
    echo "No $name pid file"
  fi
}

stop_from_pid_file backend.pid backend
stop_from_pid_file streamlit.pid streamlit
