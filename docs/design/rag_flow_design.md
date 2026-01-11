# RAG流程设计

> **版本**: v1.0  
> **架构**: RAG-First + 微调增强  
> **负责人**: 后端Lead + AI Lead

---

## 架构概览

```
┌────────────────────────────────────────────────────────────────────────┐
│                              RAG系统架构                                │
├─────────────────────────────┬──────────────────────────────────────────┤
│        文档处理层            │               问答层                      │
│  ┌─────────────────────┐    │    ┌─────────────────────────────────┐   │
│  │   PDF解析器         │    │    │       RAG引擎                    │   │
│  │   (LayoutLMv3)      │    │    │  ┌──────────┐  ┌─────────────┐  │   │
│  └──────────┬──────────┘    │    │  │ Retriever│→│  Generator  │  │   │
│             │               │    │  └──────────┘  └─────────────┘  │   │
│             ▼               │    └─────────────────────────────────┘   │
│  ┌─────────────────────┐    │                    ▲                      │
│  │   分块器            │    │                    │                      │
│  │   (Semantic Chunk)  │    │                    │                      │
│  └──────────┬──────────┘    │                    │                      │
│             │               │                    │                      │
│             ▼               │                    │                      │
│  ┌─────────────────────┐    │    ┌───────────────┴──────────────┐      │
│  │   向量化器          │    │    │        向量数据库             │      │
│  │   (BGE-M3)          │────┼───►│        (Milvus)              │      │
│  └─────────────────────┘    │    └──────────────────────────────┘      │
└─────────────────────────────┴──────────────────────────────────────────┘
```

---

## 1. 文档处理流程

### 1.1 PDF解析

```python
# 处理流程
PDF文件 → 文本提取 → 布局分析 → 信息抽取 → 结构化输出

# 多层解析策略
Layer 1: PDFPlumber (基础文本提取)
Layer 2: Tesseract OCR (扫描件识别)
Layer 3: LayoutLMv3 (布局分析)
Layer 4: LLM API (信息整合)
```

**解析输出:**
```json
{
    "title": "Attention Is All You Need",
    "authors": [...],
    "abstract": "...",
    "sections": [
        {"title": "Introduction", "content": "..."},
        {"title": "Model Architecture", "content": "..."}
    ],
    "tables": [...],
    "figures": [...],
    "keywords": [...]
}
```

### 1.2 文本分块策略

```python
# 分块配置
CHUNK_SIZE = 512          # 每块最大token数
CHUNK_OVERLAP = 50        # 重叠token数
SEPARATORS = ["\n\n", "\n", "。", ".", " "]

# 语义分块算法
def semantic_chunking(text: str) -> List[str]:
    """
    1. 按段落初步分割
    2. 计算段落间语义相似度
    3. 相似度低于阈值则分块
    4. 确保每块不超过最大长度
    """
```

### 1.3 向量化流程

```
分块文本 → BGE-M3编码 → 向量 (1024维) → 存入Milvus

# BGE-M3特性
- 支持中英文
- 密集向量 + 稀疏向量
- 最大长度 8192 tokens
```

---

## 2. 检索流程

### 2.1 混合检索架构

```
用户问题
    │
    ├─────────────────────────────────────┐
    │                                     │
    ▼                                     ▼
┌──────────────┐                   ┌──────────────┐
│  BM25检索    │                   │  向量检索    │
│ (Elasticsearch)                  │  (Milvus)    │
└──────┬───────┘                   └──────┬───────┘
       │                                   │
       └────────────┬──────────────────────┘
                    │
                    ▼
            ┌──────────────┐
            │  RRF融合     │
            │  (权重 0.4:0.6)
            └──────┬───────┘
                   │
                   ▼
            ┌──────────────┐
            │  BGE Rerank  │
            └──────┬───────┘
                   │
                   ▼
              Top-K 结果
```

### 2.2 检索参数

| 参数 | 值 | 说明 |
|-----|-----|------|
| initial_top_k | 20 | 初始检索数量 |
| final_top_k | 5 | 最终返回数量 |
| bm25_weight | 0.4 | BM25权重 |
| vector_weight | 0.6 | 向量检索权重 |
| rerank_threshold | 0.5 | 重排序阈值 |

### 2.3 RRF融合算法

```python
def rrf_fusion(result_lists: List[List], k: int = 60) -> List:
    """
    Reciprocal Rank Fusion
    score = Σ (weight_i / (k + rank_i))
    """
    scores = {}
    for results, weight in result_lists:
        for rank, doc in enumerate(results):
            doc_id = doc['id']
            scores[doc_id] = scores.get(doc_id, 0) + weight / (k + rank + 1)
    
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

---

## 3. 生成流程

### 3.1 上下文构建

```python
def build_context(question: str, docs: List[dict]) -> str:
    """
    构建Prompt上下文
    """
    context_parts = []
    for i, doc in enumerate(docs, 1):
        context_parts.append(f"[{i}] {doc['title']}\n{doc['text']}")
    
    return f"""根据以下参考文献回答用户问题。
    
参考文献:
{chr(10).join(context_parts)}

用户问题: {question}

要求:
1. 仅基于提供的参考文献回答
2. 如有引用，使用[1][2]格式标注
3. 如果文献中没有相关信息，请明确说明
"""
```

### 3.2 LLM调用

```python
# MVP阶段使用云端API
llm_config = {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.3,
    "max_tokens": 2048
}

# 后续可切换本地模型
# llm_config = {
#     "provider": "local",
#     "model": "ChatGLM3-6B",
#     "device": "cuda:0"
# }
```

### 3.3 流式输出

```python
async def stream_generate(question: str, docs: List) -> AsyncGenerator:
    """
    流式生成回答 (SSE)
    """
    context = build_context(question, docs)
    
    async for chunk in llm.astream(context):
        yield {
            "type": "token",
            "content": chunk.content
        }
    
    yield {
        "type": "references",
        "data": [{"paper_id": d["paper_id"], "text": d["text"][:200]} for d in docs]
    }
    
    yield {"type": "done"}
```

---

## 4. 评估指标

### 4.1 检索评估

| 指标 | 目标 | 说明 |
|-----|------|------|
| Recall@5 | ≥80% | Top5命中率 |
| Recall@10 | ≥85% | Top10命中率 |
| MRR | ≥0.70 | 平均倒数排名 |

### 4.2 生成评估

| 指标 | 目标 | 说明 |
|-----|------|------|
| 答案准确率 | ≥85% | 人工评估 |
| 引用准确率 | ≥90% | 引用是否正确 |
| 延迟 | ≤5s | 端到端响应时间 |

---

## 5. 数据流示意

```
┌─────────────────────────────────────────────────────────────────────┐
│                           完整数据流                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   用户上传PDF                                                        │
│        │                                                             │
│        ▼                                                             │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐      │
│   │ 解析PDF │ →  │ 分块    │ →  │ 向量化   │ →  │ 存入Milvus  │      │
│   └─────────┘    └─────────┘    └─────────┘    └─────────────┘      │
│                                       │                              │
│                                       ▼                              │
│                               ┌───────────────┐                      │
│                               │ 存入MongoDB   │                      │
│                               │ (chunks详情)  │                      │
│                               └───────────────┘                      │
│                                                                      │
│   ─────────────────────────────────────────────────────────────      │
│                                                                      │
│   用户提问                                                           │
│        │                                                             │
│        ▼                                                             │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────────┐      │
│   │ 向量化  │ →  │ 检索    │ →  │ 重排序   │ →  │  LLM生成    │      │
│   └─────────┘    └─────────┘    └─────────┘    └─────────────┘      │
│                                                        │             │
│                                                        ▼             │
│                                                  返回答案+引用        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

*RAG流程设计 v1.0*
