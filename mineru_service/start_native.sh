#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[native] python3 not found in PATH" >&2
  exit 1
fi

if ! command -v mineru-openai-server >/dev/null 2>&1; then
  echo "[native] mineru-openai-server not found in PATH" >&2
  echo "[native] install the native runtime with: pip install -r requirements.native.txt" >&2
  exit 1
fi

export VLLM_SERVER_PORT="${VLLM_SERVER_PORT:-30000}"
export BIND_PORT="${BIND_PORT:-8010}"
export TASK_TIMEOUT_SEC="${TASK_TIMEOUT_SEC:-600}"
export START_VLLM="${START_VLLM:-auto}"

echo "[native] Starting MinerU service from $SCRIPT_DIR"
echo "[native] GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-auto} VLLM_SERVER_PORT=$VLLM_SERVER_PORT BIND_PORT=$BIND_PORT"
echo "[native] PIPELINE_DEVICE=${PIPELINE_DEVICE:-auto} MAX_CONCURRENT=${MAX_CONCURRENT:-auto} MAX_QUEUE_SIZE=${MAX_QUEUE_SIZE:-auto}"

exec /bin/bash "$SCRIPT_DIR/start_service.sh"
