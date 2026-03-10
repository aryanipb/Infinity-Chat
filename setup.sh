#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if command -v pixi >/dev/null 2>&1; then
  pixi install
  echo "pixi environment prepared"
else
  echo "pixi not found; skipped pixi install (venv setup is complete)."
fi

echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
