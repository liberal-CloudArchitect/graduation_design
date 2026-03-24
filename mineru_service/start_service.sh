#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="${PYTHONPATH:-$SCRIPT_DIR}"
export MINERU_MODEL_SOURCE="${MINERU_MODEL_SOURCE:-local}"

GPU_MEM_UTIL="${GPU_MEMORY_UTILIZATION:-0.40}"
VLLM_PORT="${VLLM_SERVER_PORT:-30000}"
APP_PORT="${BIND_PORT:-8010}"
APP_HOST="${BIND_HOST:-0.0.0.0}"
PIPELINE_DEVICE="${PIPELINE_DEVICE:-cpu}"
START_VLLM="${START_VLLM:-auto}"
MAX_WAIT="${VLLM_STARTUP_TIMEOUT_SEC:-180}"

VLLM_PID=""
UVICORN_PID=""

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
