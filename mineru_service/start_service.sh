#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="${PYTHONPATH:-$SCRIPT_DIR}"
export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-local}"

START_VLLM="${START_VLLM:-auto}"
MAX_WAIT="${VLLM_STARTUP_TIMEOUT_SEC:-180}"

VLLM_PID=""
UVICORN_PID=""
GPU_NAME=""
GPU_MEMORY_MB=0
GPU_PROFILE="generic"

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM

    if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
        kill "$UVICORN_PID" 2>/dev/null || true
        wait "$UVICORN_PID" 2>/dev/null || true
    fi

    if [[ -n "$VLLM_PID" ]] && kill -0 "$VLLM_PID" 2>/dev/null; then
        kill "$VLLM_PID" 2>/dev/null || true
        wait "$VLLM_PID" 2>/dev/null || true
    fi

    exit "$exit_code"
}

trap cleanup EXIT INT TERM

detect_gpu_profile() {
    if ! command -v nvidia-smi >/dev/null 2>&1; then
        return 0
    fi

    local raw
    raw="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
    if [[ -z "$raw" ]]; then
        return 0
    fi

    GPU_NAME="$(echo "$raw" | cut -d',' -f1 | xargs)"
    GPU_MEMORY_MB="$(echo "$raw" | cut -d',' -f2 | xargs)"

    if [[ "$GPU_NAME" == *"5090"* ]] || [[ "$GPU_NAME" == *"Blackwell"* ]] || [[ "${GPU_MEMORY_MB:-0}" -ge 30000 ]]; then
        GPU_PROFILE="rtx5090"
        export GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.65}"
        export PIPELINE_DEVICE="${PIPELINE_DEVICE:-cuda}"
        export MAX_CONCURRENT="${MAX_CONCURRENT:-2}"
        export MAX_QUEUE_SIZE="${MAX_QUEUE_SIZE:-12}"
        export GPU_MIN_FREE_MB="${GPU_MIN_FREE_MB:-4096}"
    elif [[ "$GPU_NAME" == *"4090"* ]] || [[ "${GPU_MEMORY_MB:-0}" -ge 22000 ]]; then
        GPU_PROFILE="rtx4090"
        export GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.60}"
        export PIPELINE_DEVICE="${PIPELINE_DEVICE:-cuda}"
        export MAX_CONCURRENT="${MAX_CONCURRENT:-2}"
        export MAX_QUEUE_SIZE="${MAX_QUEUE_SIZE:-8}"
        export GPU_MIN_FREE_MB="${GPU_MIN_FREE_MB:-3072}"
    else
        GPU_PROFILE="default"
        export GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.40}"
        export PIPELINE_DEVICE="${PIPELINE_DEVICE:-cpu}"
        export MAX_CONCURRENT="${MAX_CONCURRENT:-1}"
        export MAX_QUEUE_SIZE="${MAX_QUEUE_SIZE:-16}"
        export GPU_MIN_FREE_MB="${GPU_MIN_FREE_MB:-1024}"
    fi
}


detect_gpu_profile

GPU_MEM_UTIL="${GPU_MEMORY_UTILIZATION}"
VLLM_PORT="${VLLM_SERVER_PORT:-30000}"
APP_PORT="${BIND_PORT:-8010}"
APP_HOST="${BIND_HOST:-0.0.0.0}"
PIPELINE_DEVICE="${PIPELINE_DEVICE}"

echo "[startup] GPU profile=${GPU_PROFILE} name=${GPU_NAME:-unknown} memory_mb=${GPU_MEMORY_MB:-0}"
echo "[startup] Effective defaults: GPU_MEMORY_UTILIZATION=$GPU_MEM_UTIL PIPELINE_DEVICE=$PIPELINE_DEVICE MAX_CONCURRENT=${MAX_CONCURRENT} MAX_QUEUE_SIZE=${MAX_QUEUE_SIZE}"

configure_pipeline_device() {
    echo "[startup] Configuring pipeline models: device-mode=$PIPELINE_DEVICE"
    python3 <<'PYEOF'
import json
import os
import pathlib

config_path = pathlib.Path.home() / "magic-pdf.json"
if config_path.exists():
    cfg = json.loads(config_path.read_text())
    device = os.environ.get("PIPELINE_DEVICE", "cpu")
    old = cfg.get("device-mode", "unknown")
    cfg["device-mode"] = device
    config_path.write_text(json.dumps(cfg, indent=2))
    print(f"  magic-pdf.json: device-mode {old} -> {device}")
else:
    print(f"  WARNING: {config_path} not found, skipping")
PYEOF
}

want_local_vllm() {
    local backend="${MINERU_BACKEND:-hybrid-http-client}"

    case "${START_VLLM,,}" in
        0|false|no|off)
            return 1
            ;;
        1|true|yes|on)
            return 0
            ;;
    esac

    if [[ "$backend" == "pipeline" ]]; then
        return 1
    fi

    return 0
}

start_local_vllm() {
    if ! command -v mineru-openai-server >/dev/null 2>&1; then
        echo "[startup] mineru-openai-server not found; forcing pipeline-only mode"
        export MINERU_BACKEND="pipeline"
        export MINERU_SERVER_URL=""
        return 1
    fi

    echo "[startup] Starting MinerU OpenAI server (gpu-memory-utilization=$GPU_MEM_UTIL, port=$VLLM_PORT)..."
    mineru-openai-server \
        --host 127.0.0.1 \
        --port "$VLLM_PORT" \
        --gpu-memory-utilization "$GPU_MEM_UTIL" \
        --enforce-eager &
    VLLM_PID=$!

    local waited=0
    echo "[startup] Waiting for vLLM server to become healthy (timeout=${MAX_WAIT}s)..."
    while [[ "$waited" -lt "$MAX_WAIT" ]]; do
        if curl -sf "http://127.0.0.1:${VLLM_PORT}/health" >/dev/null 2>&1; then
            export MINERU_BACKEND="${MINERU_BACKEND:-hybrid-http-client}"
            export MINERU_SERVER_URL="${MINERU_SERVER_URL:-http://127.0.0.1:${VLLM_PORT}}"
            echo "[startup] vLLM server is ready (took ${waited}s)"
            echo "[startup] Using backend=${MINERU_BACKEND}, server_url=$MINERU_SERVER_URL"
            return 0
        fi

        if ! kill -0 "$VLLM_PID" 2>/dev/null; then
            echo "[startup] WARNING: vLLM server exited unexpectedly; falling back to pipeline-only mode"
            VLLM_PID=""
            export MINERU_BACKEND="pipeline"
            export MINERU_SERVER_URL=""
            return 1
        fi

        sleep 3
        waited=$((waited + 3))
    done

    echo "[startup] WARNING: vLLM server did not become healthy within ${MAX_WAIT}s; falling back to pipeline-only mode"
    if [[ -n "$VLLM_PID" ]] && kill -0 "$VLLM_PID" 2>/dev/null; then
        kill "$VLLM_PID" 2>/dev/null || true
        wait "$VLLM_PID" 2>/dev/null || true
    fi
    VLLM_PID=""
    export MINERU_BACKEND="pipeline"
    export MINERU_SERVER_URL=""
    return 1
}

start_api() {
    echo "[startup] Starting MinerU Parse API on ${APP_HOST}:${APP_PORT} ..."
    python3 -m uvicorn app:app --host "$APP_HOST" --port "$APP_PORT" &
    UVICORN_PID=$!
    wait "$UVICORN_PID"
}

configure_pipeline_device

if want_local_vllm; then
    start_local_vllm || true
else
    if [[ "${MINERU_BACKEND:-}" == "pipeline" ]]; then
        export MINERU_SERVER_URL=""
    fi
    echo "[startup] Skipping local vLLM startup (START_VLLM=$START_VLLM, backend=${MINERU_BACKEND:-unset})"
fi

start_api
