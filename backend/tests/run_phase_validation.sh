#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$BACKEND_DIR/.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PYTEST_BIN="${PYTEST_BIN:-pytest}"
RUN_PHASE1_REMOTE="${RUN_PHASE1_REMOTE:-0}"
PHASE1_OUTPUT_JSON="${PHASE1_OUTPUT_JSON:-$SCRIPT_DIR/phase1_acceptance_results.json}"

echo "[phase-validation] project root: $PROJECT_ROOT"
echo "[phase-validation] python: $PYTHON_BIN"
echo "[phase-validation] pytest: $PYTEST_BIN"

cd "$BACKEND_DIR"

echo
echo "[phase-validation] Step 1/2: local unit + acceptance tests"
"$PYTEST_BIN" \
  tests/test_phase1_components.py \
  tests/test_phase2_acceptance.py

if [[ "$RUN_PHASE1_REMOTE" == "1" || "$RUN_PHASE1_REMOTE" == "true" ]]; then
  echo
  echo "[phase-validation] Step 2/2: remote MinerU acceptance"
  PHASE1_OUTPUT_JSON="$PHASE1_OUTPUT_JSON" \
  "$PYTHON_BIN" tests/test_phase1_acceptance.py
  echo "[phase-validation] remote report: $PHASE1_OUTPUT_JSON"
else
  echo
  echo "[phase-validation] Step 2/2 skipped: set RUN_PHASE1_REMOTE=1 to run MinerU remote acceptance"
fi
