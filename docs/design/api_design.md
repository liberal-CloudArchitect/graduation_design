# API设计文档

> **版本**: v1.0  
> **规范**: OpenAPI 3.0  
> **Base URL**: `/api/v1`

---

## 认证方式

- **JWT Bearer Token**
- Token有效期: 24小时
- Refresh Token有效期: 7天

```
Authorization: Bearer <access_token>
```

---

## 1. 用户认证 API

### POST /auth/register
注册新用户

**Request Body:**
```json
{
    "email": "user@example.com",
    "username": "researcher",
    "password": "securePassword123"
}
```

**Response 201:**
```json
{
    "id": 1,
    "email": "user@example.com",
    "username": "researcher",
    "created_at": "2026-01-11T02:00:00Z"
}
```

### POST /auth/login
用户登录

**Request Body:**
```json
{
    "email": "user@example.com",
    "password": "securePassword123"
}
```

**Response 200:**
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 86400
}
```

### POST /auth/refresh
刷新Token

### GET /auth/me
获取当前用户信息

---

## 2. 项目管理 API

### GET /projects
获取用户的项目列表

**Response 200:**
```json
{
    "items": [
        {
            "id": 1,
            "name": "深度学习研究",
            "description": "关于Transformer的文献调研",
            "paper_count": 15,
            "created_at": "2026-01-10T10:00:00Z"
        }
    ],
    "total": 1
}
```

### POST /projects
创建新项目

### GET /projects/{id}
获取项目详情

### PUT /projects/{id}
更新项目

### DELETE /projects/{id}
删除项目

---

## 3. 文献管理 API

### POST /papers/upload
上传文献PDF

**Request:** `multipart/form-data`
- `file`: PDF文件
- `project_id`: 项目ID（可选）

**Response 202:**
```json
{
    "id": 1,
    "status": "processing",
    "task_id": "task_abc123",
    "message": "PDF正在解析中"
}
```

### GET /papers
获取文献列表

**Query Parameters:**
- `project_id`: 项目ID筛选
- `status`: pending | processing | completed | failed
- `page`: 页码
- `page_size`: 每页数量

### GET /papers/{id}
获取文献详情

**Response 200:**
```json
{
    "id": 1,
    "title": "Attention Is All You Need",
    "authors": [
        {"name": "Ashish Vaswani", "affiliation": "Google Brain"}
    ],
    "abstract": "The dominant sequence...",
    "keywords": ["transformer", "attention", "NLP"],
    "status": "completed",
    "chunk_count": 45,
    "created_at": "2026-01-11T02:00:00Z"
}
```

### DELETE /papers/{id}
删除文献

### GET /papers/{id}/chunks
获取文献分块内容

---

## 4. RAG问答 API ⭐

### POST /rag/ask
同步问答接口

**Request Body:**
```json
{
    "question": "Transformer的自注意力机制是什么?",
    "project_id": 1,
    "top_k": 5
}
```

**Response 200:**
```json
{
    "answer": "自注意力机制(Self-Attention)是Transformer模型的核心组件...",
    "references": [
        {
            "paper_id": 1,
            "title": "Attention Is All You Need",
            "chunk_text": "The Transformer uses multi-head attention...",
            "page_number": 3,
            "relevance_score": 0.92
        }
    ],
    "method": "rag_mvp",
    "latency_ms": 850
}
```

### GET /rag/stream
流式问答接口 (SSE)

**Query Parameters:**
- `question`: 问题
- `project_id`: 项目ID

**Response:** `text/event-stream`
```
data: {"type": "token", "content": "自"}
data: {"type": "token", "content": "注意力"}
data: {"type": "references", "data": [...]}
data: {"type": "done"}
```

### GET /rag/history
获取问答历史

---

## 5. 分析 API

### GET /analysis/keywords
关键词统计

**Query Parameters:**
- `project_id`: 项目ID
- `top_n`: 返回Top N关键词

**Response 200:**
```json
{
    "keywords": [
        {"word": "transformer", "count": 45},
        {"word": "attention", "count": 38}
    ]
}
```

### GET /analysis/trends
研究趋势分析

### GET /analysis/graph
知识图谱数据

---

## 6. Agent API (Phase 5)

### POST /agents/review
文献综述生成

**Request Body:**
```json
{
    "topic": "大语言模型在科研领域的应用",
    "paper_ids": [1, 2, 3],
    "max_length": 5000
}
```

**Response 202:**
```json
{
    "task_id": "agent_task_xyz",
    "status": "processing",
    "estimated_time": 120
}
```

### GET /agents/tasks/{task_id}
获取Agent任务状态

### POST /agents/trend
趋势分析任务

---

## 错误响应格式

```json
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid request parameters",
        "details": [
            {"field": "email", "message": "Invalid email format"}
        ]
    }
}
```

**错误码:**
| Code | HTTP Status | Description |
|------|-------------|-------------|
| UNAUTHORIZED | 401 | 未认证 |
| FORBIDDEN | 403 | 无权限 |
| NOT_FOUND | 404 | 资源不存在 |
| VALIDATION_ERROR | 422 | 参数验证失败 |
| RATE_LIMITED | 429 | 请求过于频繁 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |

---

*API设计文档 v1.0*
