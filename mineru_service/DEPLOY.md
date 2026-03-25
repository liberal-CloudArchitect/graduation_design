# MinerU 解析服务部署指南 (Linux 5090/4090 裸机 + Docker)

## 概述

MinerU 解析服务独立于主后端，通过 HTTP 提供 PDF → Markdown 解析能力。
主后端通过 `MinerUClient` (`httpx`) 调用此服务。

**v2 更新**: 当前仓库同时保留两条可用路径，并优先适配 RTX 5090 / Blackwell:

- Linux 5090/4090 裸机启动: `requirements.native.txt` + `start_native.sh`
- Docker 启动: 保留原有 `Dockerfile` + `entrypoint.sh`

两条路径共享同一套 HTTP 契约: `POST /parse` 和 `GET /health`。

## 架构

裸机和容器路径都运行两个进程：

1. **mineru-openai-server** — vLLM 驱动的 VLM 推理服务 (端口 30000, 仅容器内访问)
2. **app.py (uvicorn)** — FastAPI 封装，使用 `hybrid-http-client` 后端
   - Pipeline 模型 (布局/OCR/公式/表格) — 本地 GPU 推理
   - VLM 模型 — 通过 HTTP 调用 mineru-openai-server

```
主后端                           MinerU 服务
┌──────────────┐               ┌──────────────────────────────────┐
│ MinerUClient │ ─ HTTP:8010 ─▶│ app.py (FastAPI)                 │
│ /parse       │               │   ├─ pipeline 模型               │
│ /health      │               │   └─ HTTP ─▶ mineru-openai-server│
└──────────────┘               │                 (:30000)         │
                               │                   └─ VLM (vLLM)   │
                               └──────────────────────────────────┘
```

## 部署矩阵

| 环境 | MinerU 服务 | 主后端 |
|------|------------|--------|
| Linux 5090/4090 服务器 | 裸机启动, 端口 8010 | `MINERU_API_URL=http://<gpu-server-ip>:8010` |
| 4060 笔记本 (Windows) | Docker 容器, GPU 直通, 端口 8010 | — |
| MacBook Pro (开发机) | 不部署 | `MINERU_API_URL=http://<server-ip>:8010` |
| CI / 测试 | 不启动 | `MINERU_ENABLED=False` (走 legacy) |

---

## Linux 5090 / 4090 裸机部署

这一条路径面向你要租用的 5090 或 4090 Linux 服务器。核心原则是: 不依赖 Docker，直接在宿主机上安装 Python 运行时、MinerU 核心依赖和模型缓存，然后使用 `start_native.sh` 启动同样的 FastAPI 服务。`start_linux.sh` 只是一个同义入口，最终会转到 `start_native.sh`。

### 1. 宿主机前置条件

- Linux 发行版建议 Ubuntu 22.04 / 24.04
- NVIDIA 驱动已安装，`nvidia-smi` 可用
- Python 3.10+，推荐 3.11
- 具备写权限的服务目录，例如 `/opt/mineru_service`
- 5090 / 4090 服务器可访问 HuggingFace 或对应镜像源
- 若是 RTX 5090 / Blackwell，建议驱动与 CUDA 运行时保持在 12.8 或更高

### 2. 安装系统依赖

```bash
sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-pip \
  build-essential curl git \
  libgl1 fontconfig fonts-noto-core fonts-noto-cjk
```

### 3. 创建虚拟环境并安装 Python 依赖

```bash
cd /opt/mineru_service
python3 -m venv .venv
source .venv/bin/activate
bash ./install_native.sh
```

如果你的服务器需要手动安装 CUDA 版 PyTorch，请先按宿主机 CUDA 驱动版本选择官方 wheel，再执行上面的依赖安装。`mineru-openai-server` 命令来自 `requirements.native.txt` 里的 `mineru[core]`。

如果你坚持手动执行 `pip install -r requirements.native.txt`，建议至少先跑一次：

```bash
python3 -m pip install -U pip setuptools wheel
python3 -m pip install --prefer-binary "colorlog>=6.8,<7"
```

这样可以避开部分镜像源把 `colorlog` 回退到极老源码包后触发的构建错误。

### 4. 下载模型与配置缓存

首次启动前执行一次模型下载，确保 `mineru-openai-server` 和 pipeline 模型可直接使用本地缓存。

```bash
source .venv/bin/activate
export MINERU_MODEL_SOURCE=local
mineru-models-download -s huggingface -m all
```

如果 HuggingFace 不可达，可切换为对应镜像源，但要保持 `MINERU_MODEL_SOURCE=local`。

### 5. 配置运行参数

建议先使用这一组最小配置:

```bash
export BIND_PORT=8010
export VLLM_SERVER_PORT=30000
export MINERU_BACKEND=hybrid-http-client
export MINERU_LANG=ch
```

`start_service.sh` 会自动识别 GPU 型号并套用默认参数：

- RTX 5090 / Blackwell / 32GB 档: `GPU_MEMORY_UTILIZATION=0.65`, `PIPELINE_DEVICE=cuda`, `MAX_CONCURRENT=2`
- RTX 4090 / 24GB 档: `GPU_MEMORY_UTILIZATION=0.60`, `PIPELINE_DEVICE=cuda`, `MAX_CONCURRENT=2`
- 低显存卡: 自动回落到 `PIPELINE_DEVICE=cpu`

如果你要手动覆盖，直接显式导出对应环境变量即可。若公式密集型文档仍然容易触发显存抖动，再把 `PIPELINE_DEVICE` 临时调回 `cpu`。

### 6. 启动服务

`start_native.sh` 会沿用当前 shell 中的环境变量，再调用共享的 `start_service.sh`。

```bash
cd /opt/mineru_service
source .venv/bin/activate
bash ./start_native.sh
```

服务启动后会先拉起 `mineru-openai-server`，再启动 FastAPI API。健康检查:

```bash
curl http://127.0.0.1:8010/health
```

解析测试:

```bash
curl -X POST http://127.0.0.1:8010/parse -F "file=@test.pdf"
```

### 7. 后台运行与 systemd 托管

临时后台运行可直接用 `nohup`:

```bash
cd /opt/mineru_service
source .venv/bin/activate
nohup ./start_native.sh > /var/log/mineru_service.log 2>&1 &
```

长期运行建议交给 `systemd`。最小可用单元:

```ini
[Unit]
Description=MinerU Parse Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/mineru_service
Environment=GPU_MEMORY_UTILIZATION=0.65
Environment=PIPELINE_DEVICE=cuda
Environment=MAX_CONCURRENT=2
Environment=MAX_QUEUE_SIZE=12
Environment=BIND_PORT=8010
Environment=VLLM_SERVER_PORT=30000
ExecStart=/bin/bash /opt/mineru_service/start_native.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

安装方式:

```bash
sudo cp mineru-service.service /etc/systemd/system/mineru-service.service
sudo systemctl daemon-reload
sudo systemctl enable --now mineru-service
sudo systemctl status mineru-service
```

---

## 前置要求

| 条件 | 要求 | 当前状态 |
|------|------|----------|
| GPU | RTX 4060 Laptop (8GB VRAM, Ada Lovelace CC 8.9) | ✓ |
| 宿主机 NVIDIA 驱动 | CUDA Version >= 12.8 | ✓ 12.8 (Driver 572.16) |
| Docker Desktop | 已安装, WSL2 后端, GPU 支持可用 | ✓ Docker 29.2.1 |
| 系统内存 | >= 16GB | ✓ 16GB |
| 磁盘空间 | 构建镜像需要 ~30GB (vLLM 基础镜像 ~20GB + 模型 ~5-8GB) | 需确认 |

## Docker 部署 (5090/4090/4060 兼容)

如需在 Docker 中跑 5090，优先使用 Blackwell 兼容的基础镜像；当前 `Dockerfile` 默认就是为 5090/Blackwell 预置的。若你之后还要回退到 4060，可在构建时显式指定旧镜像：

```bash
docker build \
  --build-arg VLLM_BASE_IMAGE=vllm/vllm-openai:v0.10.1.1 \
  -t mineru-service:latest .
```

下面保留 4060 的历史示例，方便兼容旧环境。

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
docker run -d --name mineru-service --gpus all --shm-size 8g --ipc=host -p 8010:8010 -e GPU_MEMORY_UTILIZATION=0.40 -e PIPELINE_DEVICE=cpu -e MAX_FILE_SIZE_MB=100 -e TASK_TIMEOUT_SEC=600 -e MAX_CONCURRENT=1 -e MAX_QUEUE_SIZE=16 -e ENABLE_CPU_OVERFLOW_FALLBACK=true -e GPU_PRESSURE_CPU_FALLBACK=true -e GPU_MIN_FREE_MB=1024 -e CUDA_OOM_CPU_FALLBACK=true -e PIPELINE_FALLBACK_ENABLED=true -e MINERU_LANG=ch mineru-service:latest
```

说明：

- `--shm-size 8g`：vLLM + PyTorch 推理需要大量共享内存。
- `--ipc=host`：vLLM 推荐设置，允许进程间共享内存。
- `GPU_MEMORY_UTILIZATION`：vLLM **允许占用的整卡显存比例**（权重 + KV cache 都在这个上限内），**不是**「给 vLLM 越少、越省给 pipeline」——设得过低会导致引擎初始化失败。
  - 日志中 `GPU_MEMORY_UTILIZATION=0.25` 时：8GB×0.25≈2.0GB 总预算，而 MinerU2.5 VLM 权重约 **2.16GiB**，KV 可用量为负，vLLM 报错 `No available memory for the cache blocks` 并退出。
  - 8GB 卡建议 **0.40~0.55** 先保证 vLLM 能拉起；并发用 `MAX_CONCURRENT=1` 控制，勿用过低比例「省显存」。
- **`PIPELINE_DEVICE=cpu`（关键）**：将 pipeline 模型（布局/OCR/公式/表格检测）卸载到系统内存运行，GPU VRAM 仅留给 vLLM。8GB 显卡**必须**设为 `cpu`，否则 pipeline 模型和 vLLM 争抢显存会导致处理公式密集型 PDF 时崩溃。
- `PIPELINE_FALLBACK_ENABLED=true`：当 hybrid (VLM) 解析失败时，自动降级到 pipeline-only 再尝试一次（不调用 VLM），再失败才走 PyMuPDF。
- `MAX_CONCURRENT=1`：8GB VRAM 建议并发数为 1。
- `MAX_QUEUE_SIZE=16`：额外请求先在系统内存中排队，不立即冲击显存。
- `ENABLE_CPU_OVERFLOW_FALLBACK=true`：排队已满时自动走 PyMuPDF CPU 回退，保证任务完成而不是直接 503。
- `GPU_PRESSURE_CPU_FALLBACK=true` + `GPU_MIN_FREE_MB=1024`：当空闲显存低于 1GB 时，本次任务直接走 CPU 回退。
- `CUDA_OOM_CPU_FALLBACK=true`：若 MinerU 在运行中触发 CUDA OOM，则自动释放缓存并退回 CPU 解析。
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
MINERU_API_URL=http://192.168.50.173:8010
PDF_PARSE_TIMEOUT=600
```

确保 `192.168.50.173` 是 4060 笔记本在局域网中的 IP。
设置 `MINERU_ENABLED=false` 可随时回退到纯 legacy 管线。

## 运维参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `GPU_MEMORY_UTILIZATION` | 0.40 | vLLM 使用 GPU 显存的比例 (8GB → 3.2GB) |
| `PIPELINE_DEVICE` | `cpu` | Pipeline 模型运行设备。`cpu`=系统内存, `cuda`=GPU (仅 >=12GB 显卡) |
| `PIPELINE_FALLBACK_ENABLED` | `true` | hybrid 失败时先尝试 pipeline-only 再降到 PyMuPDF |
| `VLLM_SERVER_PORT` | 30000 | 容器内 vLLM 服务端口 |
| `MAX_FILE_SIZE_MB` | 100 | 单文件上传上限 |
| `TASK_TIMEOUT_SEC` | 600 | 单任务硬超时 (VLM 比 pipeline 慢, 建议 600) |
| `MAX_CONCURRENT` | 1 | 并发解析上限 (8GB VRAM 建议 1) |
| `MAX_QUEUE_SIZE` | 16 | 等待 GPU 槽位的队列长度 |
| `ENABLE_CPU_OVERFLOW_FALLBACK` | `true` | 队列已满时直接走 CPU 回退 |
| `GPU_PRESSURE_CPU_FALLBACK` | `true` | 空闲显存过低时直接走 CPU 回退 |
| `GPU_MIN_FREE_MB` | 1024 | 触发显存压力回退的空闲显存阈值 |
| `CUDA_OOM_CPU_FALLBACK` | `true` | 捕获 CUDA OOM 后自动回退到 CPU |
| `API_KEY` | "" (空=不校验) | Bearer token 认证 |
| `MINERU_BACKEND` | `hybrid-http-client` | 解析后端 (由 entrypoint 自动设置) |
| `MINERU_PARSE_METHOD` | `auto` | 解析模式 |
| `MINERU_LANG` | `ch` | 文档主语言 (中文=ch, 英文=en) |

## VRAM 预算 (RTX 4060 Laptop, 8GB)

### PIPELINE_DEVICE=cpu（推荐，默认）

Pipeline 模型运行在系统内存 (RAM)，GPU 仅留给 vLLM：

| 组件 | GPU VRAM | 系统 RAM |
|------|---------|---------|
| vLLM VLM 模型 + KV cache (0.40) | ~3.2 GB | — |
| CUDA 运行时 | ~0.5 GB | — |
| Pipeline 布局/OCR/公式/表格模型 | — | ~2-3 GB |
| vLLM CPU 开销 | — | ~1-2 GB |
| **合计** | **~3.7 GB / 8.0 GB** | **~4-5 GB / 16 GB** |

GPU VRAM 余量充足，不再有 OOM 风险。Pipeline 推理速度比 GPU 慢 2-3 倍，但稳定性大幅提升。

### PIPELINE_DEVICE=cuda（仅 >=12 GB 显卡）

| 组件 | 显存占用 |
|------|---------|
| vLLM VLM 模型 + KV cache (0.40) | ~3.2 GB |
| Pipeline 布局/OCR 模型 | ~2.0 GB |
| Pipeline 公式/表格模型 | ~1.0 GB |
| CUDA 运行时 + 碎片 | ~0.5 GB |
| **合计** | **~6.7 GB / 8.0 GB** |

> 8GB 显卡使用 `cuda` 时，处理公式密集型 PDF 几乎必定触发 OOM。**8GB 卡务必使用 `PIPELINE_DEVICE=cpu`**。

## 三级降级策略

解析请求的处理顺序：

```
Tier 1: hybrid-http-client (VLM + pipeline)
  ↓ 失败 (VLM 连接错误 / CUDA OOM / ...)
Tier 2: pipeline-only (仅 pipeline 模型, 不调用 VLM)
  ↓ 失败
Tier 3: PyMuPDF (纯 CPU 文本提取)
```

- **Tier 1** 质量最高，使用 VLM 做视觉理解
- **Tier 2** 质量良好，使用传统 pipeline 模型（布局/OCR/公式/表格）
- **Tier 3** 质量最低，仅提取文本和粗略标题
- 降级是**按请求**的，不是永久性的；vLLM 恢复后下一个请求自动回到 Tier 1
- 返回结果的 `metadata.fallback_reason` 字段标明了使用的降级路径

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

如果是在 Linux 裸机上运行，可直接:

```bash
export MINERU_BACKEND=pipeline
export START_VLLM=0
./start_service.sh
```

Docker 路径下如需完全禁用 vLLM，可直接运行：

```powershell
docker run -d `
  --name mineru-service `
  --gpus all `
  --shm-size 4g `
  -p 8010:8010 `
  mineru-service:latest `
  python3 -m uvicorn app:app --host 0.0.0.0 --port 8010
```

这会跳过 `entrypoint.sh`，直接启动 `app.py`。如果你仍希望保留统一的启动逻辑，推荐继续走 `entrypoint.sh` 或 `start_service.sh`，仅通过 `START_VLLM=0` + `MINERU_BACKEND=pipeline` 关闭 VLM。
