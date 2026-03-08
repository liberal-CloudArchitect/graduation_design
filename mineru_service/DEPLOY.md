# MinerU 解析服务部署指南

## 概述

MinerU 解析服务独立于主后端，通过 HTTP 提供 PDF → Markdown 解析能力。
主后端通过 `MinerUClient` (`httpx`) 调用此服务。

## 部署矩阵

| 环境 | MinerU 服务 | 主后端 |
|------|------------|--------|
| 4090 服务器 | Docker 容器, GPU 直通, 端口 8010 | `MINERU_API_URL=http://localhost:8010` |
| Mac Mini M4 | 不部署 | `MINERU_API_URL=http://<4090-ip>:8010` |
| CI / 测试 | 不启动 | `MINERU_ENABLED=False` (走 legacy) |

## 4090 服务器部署

### 1. 构建 Docker 镜像

```bash
cd mineru_service
docker build -t mineru-service:latest .
```

### 2. 启动容器

```bash
docker run -d \
  --name mineru-service \
  --gpus all \
  -p 8010:8010 \
  -v /path/to/MinerU2.5-2509-1.2B:/models/MinerU2.5-2509-1.2B:ro \
  -e MAX_FILE_SIZE_MB=100 \
  -e TASK_TIMEOUT_SEC=300 \
  -e MAX_CONCURRENT=2 \
  -e BIND_HOST=0.0.0.0 \
  mineru-service:latest
```

### 3. 验证服务

```bash
curl http://localhost:8010/health
# 预期: {"status":"ok","model_loaded":true,"parse_backend":"magic_pdf","gpu_memory_mb":...}
# 如果 magic-pdf 未安装，parse_backend 会是 "pymupdf"（CPU 回退模式）

curl -X POST http://localhost:8010/parse \
  -F "file=@test.pdf" \
  | python -m json.tool
```

## 主后端配置

在 `.env` 中添加:

```env
MINERU_ENABLED=true
MINERU_API_URL=http://localhost:8010
PDF_PARSE_TIMEOUT=120
```

设置 `MINERU_ENABLED=false` 可随时回退到纯 legacy 管线。

## 运维约束

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_FILE_SIZE_MB` | 100 | 单文件上传上限 |
| `TASK_TIMEOUT_SEC` | 300 | 单任务硬超时 |
| `MAX_CONCURRENT` | 2 | 并发解析上限 |
| `API_KEY` | "" (空=不校验) | Bearer token 认证 |

## 错误码

| HTTP 状态码 | 含义 | 主后端处理 |
|------------|------|-----------|
| 200 | 成功 | 正常消费 |
| 400 | PDF 损坏 | 降级到 legacy |
| 413 | 文件过大 | 降级, reason=file_too_large |
| 503 | 并发已满 | 降级, reason=service_busy |
| 504 | 解析超时 | 降级, reason=service_timeout |
