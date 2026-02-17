# AI 文献阅读系统重构实施方案（上传到回答全链路）

## 1. 目标与验收标准
- 目标：回答必须基于“已上传文献正文证据 + 外部补充文献证据”联合推理，而不是只引用参考文献片段。
- 验收标准：
1. 上传后可追踪每篇文献的分块质量（总块数、过滤块数、过滤页数）。
2. 检索阶段默认过滤参考文献噪声，且回答证据覆盖多篇文献。
3. 生成阶段可选协作模式：`retriever + search + analyzer` 联合提供上下文。
4. 前端可看到检索诊断元数据（命中文档数、过滤数、覆盖文献数）。

## 2. 当前系统实际流程（As-Is）
1. 上传 PDF：`/api/v1/papers/upload` 保存文件并异步处理。
2. 解析：`process_paper_async` 调 `PDFParser.parse` 提取 `pages/full_text/metadata`。
3. 分块与索引：`SemanticChunker` 分块后写入 Mongo（chunk 文本）+ Milvus（向量）+ ES（BM25）。
4. 提问（聊天）：前端调用 `/api/v1/agent/stream`。
5. 路由：Coordinator 将查询路由到 `retriever_agent`。
6. 回答：`rag_engine.answer_stream` 执行记忆检索 + 文献检索 + 重排 + LLM 生成 + 引用返回。

## 3. 已识别的关键问题（Before）
- 参考文献区噪声会进入检索候选，导致“回答只抓到引文列表片段”。
- 检索结果可能被单篇文献主导，跨文献综合不足。
- 协作链路弱：外部搜索与分析能力未稳定并入检索主链路。
- 可观测性弱：无法直接判断回答到底使用了多少有效证据。

## 4. 分阶段改造方案（To-Be）

### Stage A：检索与权限收敛（已完成）
- `paper_ids` 权限校验（用户/项目维度）接入 `/rag/*` 与 `/agent/*`。
- 修复混合检索 project 过滤与旧索引降级策略。

### Stage B：上传与分块质量提升（已完成）
- 按页分块并保留页码/布局元数据。
- 过滤参考文献重块，删除文献时同步清理 Milvus/ES/Mongo 索引。

### Stage C：证据质量增强（本轮完成）
- 回答前统一执行证据准备：
1. 检索结果取回后过滤参考文献噪声块。
2. 文献覆盖增强（优先每篇至少 1 条证据）。
3. 输出 `retrieval_meta`（命中数、过滤数、覆盖文献数）。

### Stage D：多 Agent 协作生成（本轮完成）
- 在 `retriever_agent` 流式路径新增协作模式：
1. `search_agent` 生成外部补充文献上下文。
2. `analyzer_agent` 生成分析视角补充上下文。
3. 合并本地证据与外部/分析上下文后再进入 `rag_engine.answer_stream`。

### Stage E：回归验证（进行中）
- 语法检查、接口回归、端到端问答回放。
- 增补集成测试（依赖修复后执行）。

## 5. 本次落地改动清单
- `backend/app/rag/engine.py`
  - 新增证据准备链路：参考文献噪声过滤、跨文献覆盖增强、检索元数据输出。
  - `answer/answer_stream` 统一复用证据准备结果，并透传 `retrieval_meta`。
- `backend/app/api/v1/papers.py`
  - 新增布局感知页面文本重建，跳过参考文献主导页面。
  - 解析结果新增 `skipped_reference_pages`。
  - 新增重处理接口 `POST /papers/{paper_id}/reprocess`，用于历史文献重建索引。
- `backend/app/api/v1/agents.py`
  - 新增协作模式判定（显式参数或查询意图触发）。
  - `retriever` 流式路径支持 `search + analyzer` 协同补充上下文。
  - 元数据新增：`collaborative_mode/collaboration_agents/retrieval_meta`。

## 6. 后续待办（下一步）
1. 增加“重建索引”任务，清理历史已入库的参考文献噪声块。
2. 前端增加协作模式开关与检索诊断展示。
3. 增加端到端自动化测试：上传 2-3 篇论文后验证“方法归纳类问题”必须覆盖多篇文献证据。
