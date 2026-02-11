---
name: RAG Dialogue Quality Fix
overview: 全面修复项目对话质量问题，涵盖 RAG 流程统一、混合检索启用、Prompt 精细化、分块策略优化、上下文管理改进和后处理增强六大方向。
todos:
  - id: unify-rag-stream
    content: "Phase 1.1: 在 engine.py 新增 answer_stream() 方法，统一流式RAG逻辑（含记忆），重构 agents.py 和 rag.py 的流式端点调用统一方法"
    status: completed
  - id: fix-query-pollution
    content: "Phase 1.2: 修复 retriever_agent.py 的查询污染，将 extra_context 与 query 分离，engine.py 增加 extra_context 参数"
    status: completed
  - id: add-conversation-history
    content: "Phase 1.3: 前端传递 conversation_id，后端加载历史对话注入 Prompt"
    status: completed
  - id: enable-hybrid-retrieval
    content: "Phase 2.1: 在 engine.py 中集成 HybridRetriever，修改 search() 和 index_paper() 方法"
    status: completed
  - id: add-reranker
    content: "Phase 2.2: 在检索后增加 LLM-based 或 BGE-Reranker 重排序步骤"
    status: completed
  - id: optimize-chunking
    content: "Phase 2.3: 调整 CHUNK_SIZE=1024, CHUNK_OVERLAP=128，修复 _clean_text() 保留段落结构"
    status: completed
  - id: centralize-prompts
    content: "Phase 3.1-3.3: 新建 prompts.py 统一管理，添加学术 Persona，放宽检索约束，为各 Agent 设计专用 Prompt"
    status: completed
  - id: enhance-postprocessing
    content: "Phase 4.1-4.3: 增大引用窗口、修复 Analyzer 回退、支持 paper_ids 筛选"
    status: completed
isProject: false
---

# RAG 对话质量全面优化方案

## 一、独立分析报告

经过对后端所有关键文件的逐行审查，我独立发现了以下问题。部分与你的分析一致，部分有差异或是新发现的问题。

---

### 1. 对话输入处理逻辑

**1.1 流式接口的真实调用路径（与你的分析有差异）**

前端 Chat 页面实际调用的是 `agentsApi.stream()` -> `/api/v1/agent/stream`（[agents.py](backend/app/api/v1/agents.py) L100-323），而**不是** `/api/v1/rag/stream`（[rag.py](backend/app/api/v1/rag.py) L144-223）。

在 `agent/stream` 中，当路由到 `retriever_agent` 时（L174-237），代码手动重建了 RAG 流程，**并且确实集成了记忆系统**（L192-198 检索记忆、L230-237 保存记忆）。所以用户在主聊天界面中并非"完全无记忆"。

**但问题在于：** `agent/stream` 的 retriever 路径**完全绕过了 `RetrieverAgent.execute()` 方法**，意味着：

- PDF 解析等 Skill 不会被触发
- Agent 的增强逻辑（自动 Skill 选择）被跳过
- 存在两套并行的 RAG 实现需要维护（agents.py L174-237 vs engine.py `answer()` 方法）

`/api/v1/rag/stream` 确实完全没有记忆系统（L169-214），但它不是主要调用路径。不过它仍然暴露为 API，可能被其他场景调用。

**1.2 查询污染（确认你的分析）**

[retriever_agent.py](backend/app/agents/retriever_agent.py) L132-135：

```132:135:backend/app/agents/retriever_agent.py
            enhanced_query = query
            if extra_context:
                enhanced_query = f"{query}\n\n参考上下文:{extra_context[:2000]}"
```

污染后的 `enhanced_query` 被传入 `rag_engine.answer()`，在 [engine.py](backend/app/rag/engine.py) L327 中被用于向量检索（`self.search(question, ...)`），同时在 L342 被作为 "用户问题" 写入 Prompt。这导致：

- 向量检索用一个 2000+ 字符的混合文本做相似度匹配，准确度严重下降
- LLM 的 Prompt 中 "用户问题" 部分变成了混合内容，模型难以区分指令和背景

**1.3 对话上下文连续性断裂（新发现）**

前端 [Chat/index.tsx](frontend/src/pages/Chat/index.tsx) L270-275 只发送 `{ query, project_id, agent_type, params }`，**不发送对话历史或 conversation_id**。后端每次创建全新的 Conversation 记录（agents.py L293-303），只包含当前一轮 Q&A。

记忆引擎是唯一的上下文桥梁，但它基于向量相似度检索历史，容易遗漏上下文相关但措辞不同的对话。

**1.4 paper_ids 参数被忽略（新发现）**

`QuestionRequest` 接受 `paper_ids` 字段，但 [rag.py](backend/app/api/v1/rag.py) L99 和 [agents.py](backend/app/api/v1/agents.py) L176 都未将其传递给引擎，用户无法聚焦特定论文进行问答。

---

### 2. Prompt 模板与生成模型配置

**2.1 Prompt 过于通用（确认）**

核心 RAG Prompt（[engine.py](backend/app/rag/engine.py) L337-349）：

```337:349:backend/app/rag/engine.py
            prompt = f"""根据以下参考资料回答用户问题。

参考资料:
{context}

用户问题: {question}

要求:
1. 仅基于提供的参考资料回答
2. 如有引用，使用[1][2]格式标注
3. 如果资料中没有相关信息，请明确说明
4. 如有历史对话记忆相关内容，可适当参考
"""
```

问题：

- 没有角色设定（System Persona），模型不知道自己应该扮演学术助手
- 没有思维链（Chain of Thought）引导
- 没有输出格式规范（如结构化回答、学术写作风格）
- 缺少 Few-shot 示例

**2.2 约束过于僵化（确认）**

"仅基于提供的参考资料回答" + "如果资料中没有相关信息，请明确说明" 在 top-k=5 且检索质量不高时，频繁导致 "资料中没有相关信息" 的回退响应，即便模型自身知识足以回答。

**2.3 Prompt 三处重复（新发现）**

同一套 RAG Prompt 分散在三个文件中：

- [engine.py](backend/app/rag/engine.py) L337-349
- [rag.py](backend/app/api/v1/rag.py) L188-199
- [agents.py](backend/app/api/v1/agents.py) L204-216

修改一处不会自动同步到其他位置，易造成行为不一致。

**2.4 模型能力瓶颈（确认）**

默认模型 `google/gemma-3-12b-it:free`（[config.py](backend/app/core/config.py) L62），对于学术分析、长文本推理和结构化输出能力有限。温度 0.3（engine.py L166）合理但可按任务类型微调。

---

### 3. 数据预处理与检索流程

**3.1 混合检索完全未启用（确认）**

[retriever.py](backend/app/rag/retriever.py) 实现了完整的 `HybridRetriever`（BM25 + Vector + RRF 融合，L309-442），包括：

- `VectorRetriever`：Milvus 向量搜索
- `BM25Retriever`：Elasticsearch BM25 搜索
- `HybridRetriever`：RRF 融合策略

但 [engine.py](backend/app/rag/engine.py) 的 `search()` 方法（L257-293）直接调用 Milvus，**从未导入或使用 `HybridRetriever**`。全局实例 `hybrid_retriever` 从未被初始化或调用。

**3.2 分块粒度过小（确认）**

[config.py](backend/app/core/config.py) L73-74：`CHUNK_SIZE=512`, `CHUNK_OVERLAP=50`。

[chunker.py](backend/app/rag/chunker.py) 的 `SemanticChunker` 采用递归分隔符策略（段落 -> 换行 -> 句号 -> ... -> 字符），虽然比纯固定窗口好，但 512 字符对于学术论文段落（通常 1000-2000 字符）仍然太小，会切断逻辑完整的段落。

此外，`_clean_text()` 方法（L95-101）将所有空白压缩为单个空格（`re.sub(r'\s+', ' ', text)`），这会破坏论文中有意义的段落结构。

**3.3 缺乏重排序（确认）**

即使在 `HybridRetriever` 中，也仅使用 RRF 数值融合，没有基于交叉编码器的语义重排序。主流程中更是完全没有重排序。

---

### 4. 后处理与校验机制

**4.1 引用内容严重截断（确认）**

[writer_agent.py](backend/app/agents/writer_agent.py)：

- 大纲生成：L242 `r.get('text', '')[:200]` -- 每篇引用仅 200 字符
- 综述生成：L283 `r.get('text', '')[:500]` -- 每篇引用仅 500 字符
- 通用写作：L390 `r.get('text', '')[:200]` -- 每篇引用仅 200 字符

学术综述任务需要深度理解原文，200-500 字符远远不够。

**4.2 分析回退数据丢失（确认）**

[analyzer_agent.py](backend/app/agents/analyzer_agent.py) L261-277：当 `trend_service` 不可用时，LLM 的 Prompt 仅包含：

```
问题：{query}
分析类型：{analysis_type}
```

完全丢失了之前通过 Skill 获取的数据（`skill_data`）和项目文本。

**4.3 无输出质量校验（新发现）**

整个流程没有任何后置校验：

- 无幻觉检测（答案是否与引用一致）
- 无引用验证（[1][2] 标记是否对应真实引用）
- 无答案完整性检查
- 无质量评分或自动重试机制

---

## 二、综合分析：你的分析 vs 我的分析


| 问题            | 你的分析            | 我的分析                                       | 综合结论                                 |
| ------------- | --------------- | ------------------------------------------ | ------------------------------------ |
| 流式接口缺失记忆      | rag/stream 无记忆  | 主路径是 agent/stream，有记忆；但绕过了 Agent.execute() | 部分正确，核心问题是 agent/stream 绕过了 Agent 逻辑 |
| 查询污染          | PDF 内容拼接到 query | 确认，影响向量检索和 Prompt                          | 完全一致                                 |
| Prompt 过于简化   | 缺乏学术 Persona    | 确认，且 Prompt 三处重复                           | 一致，补充了重复维护问题                         |
| 约束僵化          | "仅基于资料回答"       | 确认                                         | 完全一致                                 |
| 模型瓶颈          | gemma-3-12b 不够  | 确认                                         | 完全一致                                 |
| 混合检索未启用       | 确认              | 确认                                         | 完全一致                                 |
| 分块过小          | 512 chars       | 确认，且 clean_text 破坏段落结构                     | 一致，补充了文本清理问题                         |
| 缺乏重排序         | 确认              | 确认                                         | 完全一致                                 |
| 引用截断          | 200-500 chars   | 确认                                         | 完全一致                                 |
| 回退数据丢失        | 确认              | 确认                                         | 完全一致                                 |
| 对话连续性断裂       | 未提及             | 前端不发送历史                                    | 新增重要发现                               |
| paper_ids 被忽略 | 未提及             | 两个端点都不传递                                   | 新增发现                                 |
| 无输出校验         | 未提及             | 无幻觉检测/引用验证                                 | 新增发现                                 |
| Prompt 三处重复   | 未提及             | 分散在 3 个文件                                  | 新增维护问题                               |


---

## 三、修改方案

### Phase 1: 核心架构修复（高优先级）

#### 1.1 统一 RAG 流式输出到 engine.py

**目标**：将流式输出能力集成到 `RAGEngine`，消除 agents.py 和 rag.py 中的重复 RAG 逻辑。

**修改文件**：

- [engine.py](backend/app/rag/engine.py)：新增 `async def answer_stream()` 方法，集成记忆检索、上下文构建、流式 LLM 输出、记忆保存
- [agents.py](backend/app/api/v1/agents.py)：retriever_agent 的流式路径改为调用 `rag_engine.answer_stream()`
- [rag.py](backend/app/api/v1/rag.py)：`/stream` 端点改为调用 `rag_engine.answer_stream()`

```python
# engine.py 新增方法
async def answer_stream(
    self, question, project_id=None, top_k=5, 
    use_memory=True, conversation_history=None
):
    """流式 RAG 问答（记忆增强）- async generator"""
    memory_results = []
    if use_memory and self.memory_engine:
        memory_results = await self.memory_engine.retrieve(question, project_id, top_k=3)
    
    search_results = await self.search(question, project_id, top_k)
    docs = await self._fetch_documents(search_results)
    context = self._build_context_with_memory(docs, memory_results)
    prompt = self._build_prompt(question, context, conversation_history)
    
    yield {"type": "references", "data": docs}
    
    full_answer = ""
    async for chunk in self.llm.astream(prompt):
        if hasattr(chunk, 'content') and chunk.content:
            full_answer += chunk.content
            yield {"type": "chunk", "data": chunk.content}
    
    yield {"type": "done", "data": {"answer": full_answer}}
    
    if use_memory and self.memory_engine:
        await self.memory_engine.add_memory(
            content=f"Q: {question}\nA: {full_answer}",
            metadata={"project_id": project_id or 0}
        )
```

#### 1.2 修复查询污染

**修改文件**：[retriever_agent.py](backend/app/agents/retriever_agent.py)

将 extra_context 与 query 分离，通过独立参数传递：

```python
# 修改前 (L132-135)
enhanced_query = query
if extra_context:
    enhanced_query = f"{query}\n\n参考上下文:{extra_context[:2000]}"

# 修改后
result = await self.rag_engine.answer(
    question=query,  # 保持原始查询用于检索
    project_id=project_id,
    top_k=top_k,
    use_memory=use_memory,
    extra_context=extra_context,  # 新参数，在构建 Prompt 时注入
)
```

同步修改 `engine.py` 的 `answer()` 和 `answer_stream()` 方法，增加 `extra_context` 参数，在 `_build_prompt()` 中将其作为独立的 "[补充参考材料]" 段注入，不影响检索查询。

#### 1.3 增加对话历史传递

**修改文件**：

- [frontend/src/services/agents.ts](frontend/src/services/agents.ts)：stream 请求增加 `conversation_id` 字段
- [frontend/src/pages/Chat/index.tsx](frontend/src/pages/Chat/index.tsx)：发送时携带 `activeConversationId`
- [agents.py](backend/app/api/v1/agents.py)：从数据库加载最近 N 轮对话，传递给 `rag_engine.answer_stream()`
- [engine.py](backend/app/rag/engine.py)：`_build_prompt()` 中添加对话历史段

---

### Phase 2: 检索质量提升（高优先级）

#### 2.1 启用混合检索

**修改文件**：[engine.py](backend/app/rag/engine.py)

将 `search()` 方法改为使用 `HybridRetriever`：

```python
async def initialize(self):
    # ... 现有初始化 ...
    # 新增: 初始化混合检索器
    await self._init_hybrid_retriever()

async def _init_hybrid_retriever(self):
    from app.rag.retriever import HybridRetriever
    self.hybrid_retriever = HybridRetriever(
        vector_weight=0.6, bm25_weight=0.4
    )
    await self.hybrid_retriever.initialize(
        milvus_host=settings.MILVUS_HOST,
        milvus_port=settings.MILVUS_PORT,
        es_host=settings.ES_HOST,
        es_port=settings.ES_PORT
    )

async def search(self, query, project_id=None, top_k=5):
    query_embedding = self.embed([query])[0]
    if self.hybrid_retriever and self.hybrid_retriever._initialized:
        results = await self.hybrid_retriever.search(
            query=query, query_vector=query_embedding,
            top_k=top_k, paper_ids=None
        )
        return [{"paper_id": r.paper_id, "chunk_index": r.chunk_index, 
                 "distance": r.score, "text": r.text} for r in results]
    # 降级到纯向量搜索
    return await self._vector_search(query_embedding, project_id, top_k)
```

同步修改 `index_paper()` 方法，在索引时同时写入 Elasticsearch（调用 `hybrid_retriever.index_paper()`）。

#### 2.2 引入重排序（Reranker）

**新增逻辑**：在 `engine.py` 的 `answer()` / `answer_stream()` 中，检索后增加 rerank 步骤。

推荐使用 BGE-Reranker-v2（与项目已有的 BGE-M3 生态一致）或通过 LLM 做 Listwise Reranking：

```python
async def _rerank(self, query: str, docs: List[Dict], top_k: int = 5) -> List[Dict]:
    """使用 LLM 对检索结果重排序"""
    if not self.llm or len(docs) <= top_k:
        return docs[:top_k]
    
    doc_summaries = "\n".join(
        f"[{i}] {d.get('text', '')[:300]}" for i, d in enumerate(docs)
    )
    prompt = f"""对以下文档按与查询的相关性排序，返回最相关的文档编号（JSON数组）。
查询：{query}
文档：
{doc_summaries}
返回格式：[0, 3, 1, ...]（仅返回编号数组）"""
    
    response = await self.llm.ainvoke(prompt)
    # 解析排序结果，返回重排后的 top_k 文档
    ...
```

#### 2.3 优化分块策略

**修改文件**：[config.py](backend/app/core/config.py), [chunker.py](backend/app/rag/chunker.py)

- 将默认 `CHUNK_SIZE` 从 512 提高到 1024，`CHUNK_OVERLAP` 从 50 提高到 128
- 修改 `SemanticChunker._clean_text()` 保留段落分隔符（`\n\n`），只压缩行内多余空白
- 可选：为学术论文添加基于节标题（Abstract, Introduction, Methods...）的分块逻辑

```python
# config.py
CHUNK_SIZE: int = 1024  # 从 512 改为 1024
CHUNK_OVERLAP: int = 128  # 从 50 改为 128
```

---

### Phase 3: Prompt 精细化（中优先级）

#### 3.1 集中管理 Prompt 模板

**新增文件**：`backend/app/rag/prompts.py`

将所有 Prompt 统一到一个模块，消除三处重复：

```python
# prompts.py
SYSTEM_PERSONA = """你是一位专业的学术研究助手，具有深厚的跨学科知识背景。
你的职责是帮助研究者理解、分析和综合学术文献。
回答时请遵循以下原则：
- 优先基于提供的参考资料，辅以你的知识进行补充说明
- 采用严谨的学术语言，逻辑清晰
- 对不确定的内容明确标注"据我所知"或"参考资料未涉及"
- 使用[1][2]格式标注引用来源"""

RAG_QA_TEMPLATE = """<<系统>>
{system_persona}

<<对话历史>>
{conversation_history}

<<参考资料>>
{context}

{extra_context}

<<用户问题>>
{question}

请基于以上参考资料回答。如果参考资料不足以完整回答，可以结合你的知识进行补充，但需注明哪些是基于资料、哪些是补充说明。"""
```

#### 3.2 放宽检索约束

将 "仅基于提供的参考资料回答" 改为 "优先基于参考资料，可辅以自身知识补充"，避免检索结果不足时的无效回退。

#### 3.3 为不同 Agent 设计专用 Prompt

- RetrieverAgent：学术问答 Persona，强调准确引用和深度分析
- WriterAgent：学术写作 Persona，强调结构性、学术规范、批判性思维
- AnalyzerAgent：数据分析 Persona，强调定量分析和可视化建议

---

### Phase 4: 后处理增强（中优先级）

#### 4.1 增大引用内容窗口

**修改文件**：[writer_agent.py](backend/app/agents/writer_agent.py)

- 大纲生成：200 -> 500 字符
- 综述生成：500 -> 1500 字符
- 通用写作：200 -> 800 字符

#### 4.2 修复 Analyzer 回退逻辑

**修改文件**：[analyzer_agent.py](backend/app/agents/analyzer_agent.py) L260-277

在 LLM 回退分支中，注入已获取的 skill_data 和项目文本：

```python
# 修改后的 LLM 回退分支
if self._llm:
    project_text = ""
    if project_id and self.rag_engine:
        project_text = await self._fetch_project_text(project_id)
    
    skill_info = ""
    if skill_data:  # 需要将 skill_data 传入此方法
        skill_info = f"\n已获取的数据:\n{json.dumps(skill_data, ensure_ascii=False)[:3000]}"
    
    prompt = f"""请分析以下研究问题并给出数据洞察：
问题：{query}
分析类型：{analysis_type}
{f"项目文献摘要：{project_text[:3000]}" if project_text else ""}
{skill_info}
请给出：1. 主要发现 2. 数据趋势描述 3. 建议关注的方向"""
```

#### 4.3 支持 paper_ids 筛选

**修改文件**：[rag.py](backend/app/api/v1/rag.py), [agents.py](backend/app/api/v1/agents.py), [engine.py](backend/app/rag/engine.py)

将 `paper_ids` 传递到 `search()` 方法，在 Milvus 过滤条件中添加 `paper_id in [...]` 筛选。

---

### Phase 5: 模型与配置优化（低优先级，视资源）

#### 5.1 模型升级建议

在 [config.py](backend/app/core/config.py) 中支持多模型配置：

- 默认对话：可选用更强的免费/低成本模型（如 `deepseek-chat`、`qwen2.5-72b-instruct`）
- 重要任务（综述、分析）：可选用 GPT-4o / Claude 3.5

#### 5.2 动态温度控制

按任务类型自动调整温度：

- 事实性问答：temperature=0.1
- 综述/写作：temperature=0.5
- 创意性任务：temperature=0.7

