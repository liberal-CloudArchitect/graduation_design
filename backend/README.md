# 文献分析大数据平台 - 后端服务

> **技术栈**: FastAPI + SQLAlchemy + Celery + LangChain  
> **Python版本**: >= 3.10

---

## 项目结构

```
backend/
├── app/
│   ├── api/v1/           # API路由
│   │   ├── auth.py       # 认证API
│   │   ├── papers.py     # 文献API
│   │   ├── rag.py        # RAG问答API
│   │   └── analysis.py   # 分析API
│   ├── core/             # 核心配置
│   │   ├── config.py     # 配置管理
│   │   ├── security.py   # JWT认证
│   │   └── deps.py       # 依赖注入
│   ├── models/           # SQLAlchemy模型
│   ├── schemas/          # Pydantic模型
│   ├── services/         # 业务逻辑
│   └── rag/              # RAG引擎
│       ├── engine.py     # RAG核心
│       ├── retriever.py  # 检索器
│       └── generator.py  # 生成器
├── tests/                # 测试
├── alembic/              # 数据库迁移
├── requirements.txt
└── main.py
```

---

## 快速开始

### 1. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件
```

### 4. 启动服务

```bash
# 开发环境
uvicorn main:app --reload --port 8000

# 生产环境
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 环境变量

| 变量 | 说明 | 示例 |
|-----|------|------|
| DATABASE_URL | PostgreSQL连接 | postgresql://postgres:password@localhost:5432/graduation_project |
| MONGODB_URI | MongoDB连接 | mongodb://localhost:27017/ |
| REDIS_URL | Redis连接 | redis://localhost:6379/0 |
| MILVUS_HOST | Milvus地址 | localhost |
| SECRET_KEY | JWT密钥 | your-secret-key |
| LLM_API_KEY | LLM API密钥（DeepSeek/OpenRouter） | sk-xxx |
| LLM_BASE_URL | LLM接口基址 | https://api.deepseek.com |
| LLM_MODEL | LLM模型名 | deepseek-reasoner |

---

## API文档

启动服务后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

*后端服务 v1.0*
