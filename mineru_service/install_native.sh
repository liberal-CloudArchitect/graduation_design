#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[install] python3 not found in PATH" >&2
  exit 1
fi

echo "[install] upgrading pip/setuptools/wheel ..."
python3 -m pip install -U pip setuptools wheel

echo "[install] preinstalling a modern colorlog wheel ..."
python3 -m pip install --prefer-binary "colorlog>=6.8,<7"

echo "[install] installing native MinerU runtime requirements ..."
python3 -m pip install --prefer-binary -r requirements.native.txt

echo "[install] done"
