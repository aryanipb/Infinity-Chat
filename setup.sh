#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v pixi >/dev/null 2>&1; then
  echo "pixi is required but not found in PATH."
  echo "Install pixi first: https://pixi.sh/latest/"
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Optional: install pixi environment and tasks for convenience.
pixi install

echo "Setup complete."
echo "Activate with: source .venv/bin/activate"
