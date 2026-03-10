#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

pick_python() {
  if command -v python3.13 >/dev/null 2>&1; then
    echo python3.13
    return
  fi

  if command -v python3.12 >/dev/null 2>&1; then
    echo python3.12
    return
  fi

  if command -v python3.11 >/dev/null 2>&1; then
    echo python3.11
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    echo python3
    return
  fi

  echo "No suitable Python interpreter found. Install Python 3.11, 3.12, or 3.13." >&2
  exit 1
}

PYTHON_BIN="$(pick_python)"
PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

case "$PYTHON_VERSION" in
  3.11|3.12|3.13) ;;
  *)
    echo "Unsupported Python version: $PYTHON_VERSION" >&2
    echo "This project currently requires Python 3.11, 3.12, or 3.13 because some dependencies do not build on 3.14 yet." >&2
    exit 1
    ;;
esac

echo "Using $PYTHON_BIN (Python $PYTHON_VERSION)"

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if command -v pixi >/dev/null 2>&1; then
  if pixi install; then
    echo "pixi environment prepared"
  else
    echo "pixi install failed; continuing because the local .venv is already ready."
  fi
else
  echo "pixi not found; skipped pixi install (venv setup is complete)."
fi

echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
