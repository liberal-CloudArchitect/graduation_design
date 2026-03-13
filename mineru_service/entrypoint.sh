#!/bin/bash
set -e

export MINERU_MODEL_SOURCE=local

GPU_MEM_UTIL=${GPU_MEMORY_UTILIZATION:-0.25}
VLLM_PORT=${VLLM_SERVER_PORT:-30000}
APP_PORT=${BIND_PORT:-8010}

# ---------------------------------------------------------------------------
# 1. Start vLLM-based MinerU OpenAI server in background
#    --enforce-eager: disables CUDA graph capture, saves ~500MB VRAM
#    --gpu-memory-utilization: lowered to 0.25 for 8GB cards (was 0.40)
# ---------------------------------------------------------------------------
echo "[entrypoint] Starting MinerU OpenAI server (gpu-memory-utilization=$GPU_MEM_UTIL, port=$VLLM_PORT)..."
mineru-openai-server \
    --host 127.0.0.1 \
    --port "$VLLM_PORT" \
    --gpu-memory-utilization "$GPU_MEM_UTIL" \
    --enforce-eager &
VLLM_PID=$!

# ---------------------------------------------------------------------------
# 2. Wait for vLLM server to be healthy
# ---------------------------------------------------------------------------
MAX_WAIT=180
WAITED=0
echo "[entrypoint] Waiting for vLLM server to become healthy (timeout=${MAX_WAIT}s)..."

while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -sf http://127.0.0.1:${VLLM_PORT}/health > /dev/null 2>&1; then
        echo "[entrypoint] vLLM server is ready (took ${WAITED}s)"
        break
    fi

    if ! kill -0 $VLLM_PID 2>/dev/null; then
        echo "[entrypoint] ERROR: vLLM server process exited unexpectedly"
        echo "[entrypoint] Falling back to pipeline-only mode"
        export MINERU_BACKEND=pipeline
        export MINERU_SERVER_URL=""
        exec python3 -m uvicorn app:app --host 0.0.0.0 --port "$APP_PORT"
    fi

    sleep 3
    WAITED=$((WAITED + 3))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "[entrypoint] WARNING: vLLM server did not become healthy within ${MAX_WAIT}s"
    echo "[entrypoint] Falling back to pipeline-only mode"
    kill $VLLM_PID 2>/dev/null || true
    export MINERU_BACKEND=pipeline
    export MINERU_SERVER_URL=""
fi

# ---------------------------------------------------------------------------
# 3. Configure MinerU to use vLLM via HTTP and start the API
# ---------------------------------------------------------------------------
if [ -z "$MINERU_BACKEND" ] || [ "$MINERU_BACKEND" = "hybrid-http-client" ]; then
    export MINERU_BACKEND=hybrid-http-client
    export MINERU_SERVER_URL="http://127.0.0.1:${VLLM_PORT}"
    echo "[entrypoint] Using backend=hybrid-http-client, server_url=$MINERU_SERVER_URL"
fi

echo "[entrypoint] Starting MinerU Parse API on port ${APP_PORT}..."
exec python3 -m uvicorn app:app --host 0.0.0.0 --port "$APP_PORT"
