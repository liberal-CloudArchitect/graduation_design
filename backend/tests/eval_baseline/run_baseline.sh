#!/usr/bin/env bash
#
# 基线评测启动脚本
#
# 前置条件:
#   1. Docker 服务已启动: docker compose up -d (在项目根目录)
#   2. 后端服务已启动: cd backend && uvicorn app.main:app --port 8000
#   3. 已安装 httpx: pip install httpx
#
# 用法:
#   bash tests/eval_baseline/run_baseline.sh                    # 运行全部评测
#   bash tests/eval_baseline/run_baseline.sh retrieval          # 仅检索评测
#   bash tests/eval_baseline/run_baseline.sh answer             # 仅回答评测
#   bash tests/eval_baseline/run_baseline.sh parse              # 仅解析评测
#   bash tests/eval_baseline/run_baseline.sh latency            # 仅延迟评测
#   ROUNDS=5 bash tests/eval_baseline/run_baseline.sh latency   # 5 轮延迟评测
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
BENCH="${1:-all}"
ROUNDS="${ROUNDS:-3}"
HTTP_TIMEOUT="${HTTP_TIMEOUT:-360}"
MAX_RETRIES="${MAX_RETRIES:-4}"
RETRY_BACKOFF="${RETRY_BACKOFF:-2}"
RESUME="${RESUME:-1}"
CHECKPOINT_PATH="${CHECKPOINT_PATH:-$SCRIPT_DIR/reports/eval_checkpoint.json}"
REUSE_PROJECT_ID="${REUSE_PROJECT_ID:-}"

echo "[baseline] Script dir: $SCRIPT_DIR"
echo "[baseline] Backend dir: $BACKEND_DIR"
echo "[baseline] Base URL: $BASE_URL"
echo "[baseline] Bench: $BENCH"
echo "[baseline] Rounds: $ROUNDS"
echo "[baseline] HTTP timeout: $HTTP_TIMEOUT"
echo "[baseline] Max retries: $MAX_RETRIES"
echo "[baseline] Retry backoff: $RETRY_BACKOFF"
echo "[baseline] Resume: $RESUME"
echo "[baseline] Checkpoint: $CHECKPOINT_PATH"
echo "[baseline] Reuse project id: ${REUSE_PROJECT_ID:-<auto-from-checkpoint>}"

# Check backend is reachable
if ! curl -sf --max-time 5 "$BASE_URL/docs" > /dev/null 2>&1; then
    echo "[ERROR] Backend not reachable at $BASE_URL"
    echo "        Please start Docker services and the backend first:"
    echo "        1. cd $(dirname "$BACKEND_DIR") && docker compose up -d"
    echo "        2. cd $BACKEND_DIR && uvicorn app.main:app --port 8000"
    exit 1
fi

echo "[baseline] Backend is reachable"

cd "$BACKEND_DIR"

EXTRA_ARGS=(--checkpoint-path "$CHECKPOINT_PATH")
if [ "$RESUME" != "1" ]; then
  EXTRA_ARGS+=(--no-resume)
fi
if [ -n "${REUSE_PROJECT_ID}" ]; then
  EXTRA_ARGS+=(--reuse-project-id "$REUSE_PROJECT_ID")
fi

EVAL_HTTP_TIMEOUT="$HTTP_TIMEOUT" \
EVAL_MAX_RETRIES="$MAX_RETRIES" \
EVAL_RETRY_BACKOFF="$RETRY_BACKOFF" \
python3 -m tests.eval_baseline.eval_runner \
    --base-url "$BASE_URL" \
    --output "$SCRIPT_DIR/reports/" \
    --bench "$BENCH" \
    --rounds "$ROUNDS" \
    --http-timeout "$HTTP_TIMEOUT" \
    "${EXTRA_ARGS[@]}"

echo "[baseline] Done. Reports saved to $SCRIPT_DIR/reports/"
