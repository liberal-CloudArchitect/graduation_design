# MinerU 解析服务部署指南 (vLLM 加速版)

## 概述

MinerU 解析服务独立于主后端，通过 HTTP 提供 PDF → Markdown 解析能力。
主后端通过 `MinerUClient` (`httpx`) 调用此服务。

**v2 更新**: 驱动升级至 572.16 (CUDA 12.8) 后，切换到 vLLM 基础镜像，
使用 `hybrid-http-client` 后端获得 VLM 加速，显著提升解析质量。

## 架构

容器内运行两个进程：

1. **mineru-openai-server** — vLLM 驱动的 VLM 推理服务 (端口 30000, 仅容器内访问)
2. **app.py (uvicorn)** — FastAPI 封装，使用 `hybrid-http-client` 后端
   - Pipeline 模型 (布局/OCR/公式/表格) — 本地 GPU 推理
   - VLM 模型 — 通过 HTTP 调用 mineru-openai-server

```
MacBook (主后端)                    4060 笔记本 (Docker 容器)
┌──────────────┐                   ┌────────────────────────────────┐
│  MinerUClient│ ─── HTTP:8010 ──▶ │  app.py (FastAPI)              │
│  /parse      │                   │    ├─ pipeline 模型 (GPU)       │
│  /health     │                   │    └─ HTTP ──▶ mineru-openai   │
└──────────────┘                   │                -server (:30000)│
                                   │                  └─ VLM (vLLM) │
                                   └────────────────────────────────┘
```

## 部署矩阵

| 环境 | MinerU 服务 | 主后端 |
|------|------------|--------|
| 4060 笔记本 (Windows) | Docker 容器, GPU 直通, 端口 8010 | — |
| MacBook Pro (开发机) | 不部署 | `MINERU_API_URL=http://<4060-ip>:8010` |
| CI / 测试 | 不启动 | `MINERU_ENABLED=False` (走 legacy) |

## 前置要求

| 条件 | 要求 | 当前状态 |
|------|------|----------|
| GPU | RTX 4060 Laptop (8GB VRAM, Ada Lovelace CC 8.9) | ✓ |
| 宿主机 NVIDIA 驱动 | CUDA Version >= 12.8 | ✓ 12.8 (Driver 572.16) |
| Docker Desktop | 已安装, WSL2 后端, GPU 支持可用 | ✓ Docker 29.2.1 |
| 系统内存 | >= 16GB | ✓ 16GB |
| 磁盘空间 | 构建镜像需要 ~30GB (vLLM 基础镜像 ~20GB + 模型 ~5-8GB) | 需确认 |

## 4060 笔记本部署

### 0. 前置验证

在构建前，先验证 vLLM 镜像能否正常访问 GPU。

> **注意**: `vllm/vllm-openai` 镜像的 ENTRYPOINT 是 vLLM 服务器，
> 必须用 `--entrypoint` 覆盖才能运行其他命令。
> 直接 `docker run ... vllm/vllm-openai nvidia-smi` 会把 `nvidia-smi`
> 当成 vLLM 参数，导致 vLLM 以默认 90% 显存启动并报 OOM。

```powershell
docker run --rm --gpus all --entrypoint nvidia-smi vllm/vllm-openai:v0.10.1.1
```

预期输出应显示 RTX 4060 和 CUDA 12.8。如果失败，检查：
- Docker Desktop 是否启用了 WSL2 后端
- 是否安装了 NVIDIA Container Toolkit

还可验证 PyTorch 是否能访问 GPU：

```powershell
docker run --rm --gpus all --entrypoint python3 vllm/vllm-openai:v0.10.1.1 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

### 1. 准备代码

确保 4060 笔记本上的 `mineru_service/` 目录包含最新代码。
可通过 Git pull 或 LocalSend 等方式从 MacBook 同步。

### 2. 构建 Docker 镜像

```powershell
cd E:\project\graduation_design-main\mineru_service
docker build -t mineru-service:latest .
```

说明：

- 基础镜像 `vllm/vllm-openai:v0.10.1.1`，包含 vLLM + PyTorch + CUDA。
- RTX 4060 (Ada Lovelace, CC 8.9) 与此版本兼容。
- 构建过程中下载 pipeline + VLM 全部模型。
- **首次构建耗时很长**（基础镜像 ~20GB + 模型 ~5-8GB），后续重建利用层缓存。
- 如 HuggingFace 下载失败，修改 Dockerfile 中的 `-s huggingface` 为 `-s modelscope`。

### 3. 启动容器

```powershell
docker run -d --name mineru-service --gpus all --shm-size 8g --ipc=host -p 8010:8010 -e GPU_MEMORY_UTILIZATION=0.40 -e MAX_FILE_SIZE_MB=100 -e TASK_TIMEOUT_SEC=600 -e MAX_CONCURRENT=1 -e MINERU_LANG=ch mineru-service:latest
```

说明：

- `--shm-size 8g`：vLLM + PyTorch 推理需要大量共享内存。
- `--ipc=host`：vLLM 推荐设置，允许进程间共享内存。
- `GPU_MEMORY_UTILIZATION=0.40`：vLLM 使用 GPU 显存的比例。
  - 0.40 × 8GB ≈ 3.2GB 给 vLLM (VLM 模型 + KV cache)
  - 剩余 ~4.8GB 给 pipeline 模型 (布局/OCR/公式/表格)
  - 如遇 OOM，降低到 0.35；如 pipeline 模型加载失败，提高到 0.45。
- `MAX_CONCURRENT=1`：8GB VRAM 建议并发数为 1。
- `MINERU_LANG=ch`：中文文档，改为 `en` 处理英文文档。
- 不需要 `-v` 挂载模型目录，模型已嵌入镜像。
- `entrypoint.sh` 自动启动 vLLM 服务器 + FastAPI 应用。

### 4. 验证服务

容器启动后，vLLM 服务器需要 1~3 分钟加载模型。可通过日志观察进度：

```powershell
docker logs -f mineru-service
```

预期日志序列：
```
[entrypoint] Starting MinerU OpenAI server (gpu-memory-utilization=0.4, port=30000)...
[entrypoint] Waiting for vLLM server to become healthy...
[entrypoint] vLLM server is ready (took 60s)
[entrypoint] Using backend=hybrid-http-client, server_url=http://127.0.0.1:30000
[entrypoint] Starting MinerU Parse API on port 8010...
[startup] official mineru loaded successfully (version=x.x.x)
```

健康检查：

```powershell
curl http://localhost:8010/health
```

预期响应:
```json
{
  "status": "ok",
  "model_loaded": true,
  "parse_backend": "mineru_official",
  "configured_backend": "hybrid-http-client",
  "configured_lang": "ch",
  "vllm_server_url": "http://127.0.0.1:30000",
  "vllm_healthy": true,
  "gpu_memory_total_mb": 8188,
  "gpu_memory_used_mb": 5500
}
```

关键字段：
- `vllm_healthy=true`：vLLM 推理服务正常
- `configured_backend="hybrid-http-client"`：使用 VLM 加速的混合后端

实际解析测试：

```powershell
curl -X POST http://localhost:8010/parse -F "file=@test.pdf"
```

### 5. 故障回退

`entrypoint.sh` 内置了自动回退逻辑：
- 如果 vLLM 服务器启动失败或超时 (180s)，自动降级为 `pipeline` 后端
- Pipeline 后端不依赖 vLLM，仅使用传统 layout/OCR 模型
- 解析质量略低但仍远优于 PyMuPDF 回退

## 主后端配置 (MacBook Pro)

在 `backend/.env` 中:

```env
MINERU_ENABLED=true
MINERU_API_URL=http://192.168.0.87:8010
PDF_PARSE_TIMEOUT=120
```

确保 `192.168.0.87` 是 4060 笔记本在局域网中的 IP。
设置 `MINERU_ENABLED=false` 可随时回退到纯 legacy 管线。

## 运维参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `GPU_MEMORY_UTILIZATION` | 0.40 | vLLM 使用 GPU 显存的比例 (8GB → 3.2GB) |
| `VLLM_SERVER_PORT` | 30000 | 容器内 vLLM 服务端口 |
| `MAX_FILE_SIZE_MB` | 100 | 单文件上传上限 |
| `TASK_TIMEOUT_SEC` | 600 | 单任务硬超时 (VLM 比 pipeline 慢, 建议 600) |
| `MAX_CONCURRENT` | 1 | 并发解析上限 (8GB VRAM 建议 1) |
| `API_KEY` | "" (空=不校验) | Bearer token 认证 |
| `MINERU_BACKEND` | `hybrid-http-client` | 解析后端 (由 entrypoint 自动设置) |
| `MINERU_PARSE_METHOD` | `auto` | 解析模式 |
| `MINERU_LANG` | `ch` | 文档主语言 (中文=ch, 英文=en) |

## VRAM 预算 (RTX 4060 Laptop, 8GB)

| 组件 | 显存占用 |
|------|---------|
| vLLM VLM 模型 + KV cache (0.40) | ~3.2 GB |
| Pipeline 布局/OCR 模型 | ~2.0 GB |
| Pipeline 公式/表格模型 | ~1.0 GB |
| CUDA 运行时 + 碎片 | ~0.5 GB |
| **合计** | **~6.7 GB / 8.0 GB** |

> 如果频繁 OOM，将 `GPU_MEMORY_UTILIZATION` 降低到 0.35，
> 或切换到 `pipeline` 后端 (环境变量 `MINERU_BACKEND=pipeline`)。

## 重建镜像

如遇运行时异常，清理重建：

```powershell
cd E:\project\graduation_design-main\mineru_service
docker rm -f mineru-service
docker build --no-cache -t mineru-service:latest .
# 然后重新执行上面的 docker run 命令
```

仅修改 `app.py` / `config.py` 等应用代码时，不需要 `--no-cache`，
Docker 层缓存会跳过模型下载直接重建应用层。

## 错误码

| HTTP 状态码 | 含义 | 主后端处理 |
|------------|------|-----------|
| 200 | 成功 | 正常消费 |
| 400 | PDF 损坏 | 降级到 legacy |
| 413 | 文件过大 | 降级, reason=file_too_large |
| 503 | 并发已满 | 降级, reason=service_busy |
| 504 | 解析超时 | 降级, reason=service_timeout |

## 后端模式切换

如需临时切换回 pipeline 模式 (不使用 VLM)：

```powershell
docker rm -f mineru-service
docker run -d `
  --name mineru-service `
  --gpus all `
  --shm-size 4g `
  -p 8010:8010 `
  -e MINERU_BACKEND=pipeline `
  -e MINERU_SERVER_URL="" `
  -e MAX_CONCURRENT=2 `
  mineru-service:latest
```

此时 entrypoint 仍会尝试启动 vLLM，但 app.py 会使用 `pipeline` 后端，
vLLM 服务器的 GPU 占用会在 pipeline 后端下被浪费。
如需完全禁用 vLLM，可直接运行：

```powershell
docker run -d `
  --name mineru-service `
  --gpus all `
  --shm-size 4g `
  -p 8010:8010 `
  mineru-service:latest `
  python3 -m uvicorn app:app --host 0.0.0.0 --port 8010
```

这会跳过 entrypoint.sh，直接启动 app.py (默认 pipeline 后端)。
