# 数据库Schema设计

> **版本**: v1.0  
> **日期**: 2026年1月  
> **负责人**: 后端Lead

---

## 数据库配置

### PostgreSQL (主数据库)
- **Host**: localhost
- **Port**: 5432
- **Database**: graduation_project
- **User**: postgres

### MongoDB (文档存储)
- **URI**: mongodb://localhost:27017/
- **Database**: graduation_project

---

## PostgreSQL Schema

### 1. 用户表 (users)

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    role VARCHAR(50) DEFAULT 'user',  -- user, admin, researcher
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
```

### 2. 项目表 (projects)

```sql
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_projects_user_id ON projects(user_id);
```

### 3. 文献表 (papers)

```sql
CREATE TABLE papers (
    id SERIAL PRIMARY KEY,
    project_id INT REFERENCES projects(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    
    -- 基础信息
    title VARCHAR(500) NOT NULL,
    authors JSONB,           -- [{name, affiliation, email}]
    abstract TEXT,
    keywords JSONB,          -- ["keyword1", "keyword2"]
    
    -- 来源信息
    source VARCHAR(50),      -- upload, semantic_scholar, arxiv
    doi VARCHAR(100),
    arxiv_id VARCHAR(50),
    publication_date DATE,
    venue VARCHAR(200),      -- 期刊/会议名称
    
    -- 文件信息
    file_path VARCHAR(500),
    file_size INT,
    page_count INT,
    
    -- 向量索引
    vector_ids JSONB,        -- Milvus中的向量ID列表
    chunk_count INT,         -- 分块数量
    
    -- 处理状态
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    parse_result JSONB,      -- 解析结果详情
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_papers_project_id ON papers(project_id);
CREATE INDEX idx_papers_user_id ON papers(user_id);
CREATE INDEX idx_papers_status ON papers(status);
CREATE INDEX idx_papers_doi ON papers(doi);
```

### 4. 对话历史表 (conversations)

```sql
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    project_id INT REFERENCES projects(id) ON DELETE SET NULL,
    
    title VARCHAR(200),
    messages JSONB,          -- [{role, content, references, timestamp}]
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_project_id ON conversations(project_id);
```

### 5. 文献笔记表 (notes)

```sql
CREATE TABLE notes (
    id SERIAL PRIMARY KEY,
    paper_id INT REFERENCES papers(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id) ON DELETE CASCADE,
    
    content TEXT NOT NULL,
    page_number INT,
    highlight_text TEXT,     -- 高亮的原文
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_notes_paper_id ON notes(paper_id);
```

### 6. 任务队列表 (tasks)

```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(50) NOT NULL,  -- pdf_parse, vectorize, review_generate
    status VARCHAR(50) DEFAULT 'pending',
    payload JSONB,
    result JSONB,
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_type ON tasks(task_type);
```

---

## MongoDB Collections

### 1. paper_chunks (文档分块)

```javascript
{
    _id: ObjectId,
    paper_id: Number,           // 关联PostgreSQL papers.id
    chunk_index: Number,        // 分块索引
    content: String,            // 分块内容
    metadata: {
        page_number: Number,
        section: String,        // 章节标题
        is_table: Boolean,
        is_figure: Boolean
    },
    vector_id: String,          // Milvus向量ID
    created_at: Date
}
```

**索引**:
```javascript
db.paper_chunks.createIndex({ paper_id: 1, chunk_index: 1 });
db.paper_chunks.createIndex({ vector_id: 1 });
```

### 2. pdf_layouts (PDF布局分析结果)

```javascript
{
    _id: ObjectId,
    paper_id: Number,
    pages: [{
        page_number: Number,
        elements: [{
            type: String,       // title, author, abstract, section, table, figure
            bbox: [x1, y1, x2, y2],
            text: String,
            confidence: Number
        }]
    }],
    created_at: Date
}
```

### 3. agent_sessions (Agent会话记录)

```javascript
{
    _id: ObjectId,
    user_id: Number,
    task_type: String,          // literature_review, trend_analysis
    topic: String,
    steps: [{
        agent: String,          // retriever, analyzer, writer
        action: String,
        result: Mixed,
        timestamp: Date
    }],
    final_result: String,
    status: String,
    created_at: Date,
    completed_at: Date
}
```

---

## 向量数据库 (Milvus)

### Collection: paper_vectors

```python
from pymilvus import CollectionSchema, FieldSchema, DataType

fields = [
    FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
    FieldSchema(name="paper_id", dtype=DataType.INT64),
    FieldSchema(name="chunk_index", dtype=DataType.INT64),
    FieldSchema(name="project_id", dtype=DataType.INT64),
    FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),  # BGE-M3 维度
]

schema = CollectionSchema(fields, description="Paper embeddings")

# 索引配置
index_params = {
    "metric_type": "IP",        # Inner Product (余弦相似度)
    "index_type": "HNSW",
    "params": {"M": 16, "efConstruction": 256}
}
```

---

## E-R 关系图

```
┌─────────┐      1:N      ┌──────────┐      1:N      ┌────────┐
│  users  │──────────────►│ projects │──────────────►│ papers │
└─────────┘               └──────────┘               └────────┘
     │                                                    │
     │ 1:N                                                │ 1:N
     ▼                                                    ▼
┌───────────────┐                                   ┌─────────┐
│ conversations │                                   │  notes  │
└───────────────┘                                   └─────────┘
```

---

*数据库Schema设计 v1.0*
