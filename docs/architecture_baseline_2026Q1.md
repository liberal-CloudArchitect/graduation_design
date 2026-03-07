# LiterAI 代码现状校准清单 — 2026 Q1 基线

> **生成日期**: 2026-03-03
> **基线代码库**: `backend/app/` (当前 MVP)
> **目的**: 逐模块确认已实现 vs 未实现能力，为后续阶段改造提供准确的起点参照

---

## 1. PDF 解析模块

**关键文件**: `backend/app/services/pdf_parser.py`, `backend/app/services/layout_analyzer.py`

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| PDFPlumber 文本提取 | `TextExtractor.extract()` | 逐页提取，使用 `extract_words` 重建文本减少空格丢失，失败回退 `extract_text` |
| PyPDF2 备用提取 | `TextExtractor._fallback_extract()` | PDFPlumber 失败时自动回退 |
| Tesseract OCR | `OCREngine.recognize()` | 扫描件场景，文本量 < 100 字符时触发 |
| LayoutLMv3 布局分析 | `LayoutAnalyzer.analyze_pdf()` | 基模型特征提取 + 启发式规则分类，识别 14 种区域类型（TITLE/AUTHOR/ABSTRACT/TABLE/FORMULA 等） |
| 正则元数据提取 | `MetadataExtractor.extract()` | 标题/作者/摘要/关键词提取，含噪声过滤和打分排序 |
| LLM 元数据提取 | `LLMMetadataExtractor.extract()` | 可选启用，当前 `default_parser` 设置 `use_llm=False` |
| 布局增强元数据 | `PDFParser._extract_metadata_from_layout()` | 布局分析结果增强标题/作者/摘要提取，低质量时优先采用布局结果 |
| 标题质量判定 | `MetadataExtractor._is_likely_title()` | 多维度噪声过滤：长度/词数/数字率/噪声关键词/句号结尾检测 |

### 未实现能力

| 能力 | 差距等级 | 说明 |
|------|---------|------|
| 端到端 Markdown/LaTeX 恢复 | **严重** | 无法将 PDF 还原为结构化 Markdown，公式无法转 LaTeX |
| 复杂表格还原 | **严重** | 无跨行跨列表格识别与还原能力 |
| 数学公式识别 | **严重** | 仅能在布局分析中检测公式区域（含数学符号 > 3 个），不能还原公式内容 |
| 双栏排版重排 | **高** | PDFPlumber 按页面坐标提取，双栏论文可能交错混合 |
| 解析路由（简单/复杂分流） | 缺失 | 所有 PDF 走同一流程，无复杂度预检测 |
| MinerU/VLM 端到端解析 | 缺失 | 模型权重已在 `MinerU2.5-2509-1.2B/` 目录，未集成 |
| 解析质量评分 | 缺失 | 无自动判断解析质量好坏的机制 |
| Markdown 后处理 | 缺失 | 无输出清洗流程 |

### 质量评级: **中低**

LayoutLMv3 布局分析框架完整，但核心瓶颈在于无法还原学术论文中的公式、复杂表格、双栏排版。布局分析实际使用基模型 + 启发式规则，非微调后的分类模型。

### 后续改造点 (阶段 1)

- 集成 MinerU VLM 端到端解析
- 增加解析路由（简单/复杂分流）
- 增加降级链和质量评分
- Markdown 后处理清洗

---

## 2. 文本切分模块

**关键文件**: `backend/app/rag/chunker.py`

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| 语义递归分块 | `SemanticChunker._split_recursive()` | 按分隔符优先级递归：`\n\n` → `\n` → `。` → `.` → `；` → `;` → `，` → `,` → ` ` → 字符 |
| 小块合并 | `SemanticChunker._merge_small_chunks()` | 过小块自动与相邻块合并 |
| 重叠分块 | `OverlapChunker` | 固定大小 + 重叠的简单分块器 |
| 句子分块 | `SentenceChunker` | 按句子边界分块，支持中英文句号 |
| 文本清理 | `SemanticChunker._clean_text()` | 控制字符移除、多余空白压缩 |

### 当前参数

```
CHUNK_SIZE  = 1024  (config.py)
CHUNK_OVERLAP = 128  (config.py)
```

### 未实现能力

| 能力 | 差距等级 | 说明 |
|------|---------|------|
| 父子文档结构 | **高** | 无层级索引，所有块为平级 |
| 章节感知切分 | 中 | 不识别 Markdown 标题层级，纯按字符长度 + 分隔符 |
| `section_path` 元数据 | 缺失 | 子块无法追溯所属章节 |
| `parent_id` 关联 | 缺失 | 无父块概念 |

### 质量评级: **中**

基础切分功能完备，参数已调优至学术场景（1024/128），但缺乏层级结构导致 LLM 接收碎片化上下文。

### 后续改造点 (阶段 2)

- 新增 `HierarchicalChunker`，生成父子文档结构
- 子块携带 `parent_id` 和 `section_path`
- 父块存 MongoDB，子块向量化存 Milvus + ES

---

## 3. 向量化模块

**关键文件**: `backend/app/rag/engine.py` (`embed()` 方法)

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| BGE-M3 dense 向量化 | `RAGEngine.embed()` | `BGEM3FlagModel` 加载，`return_dense=True`，输出 1024 维 float 向量 |
| FP16 加速 | `_init_embedder()` | `use_fp16=True` |
| Mock embedder | `MockEmbedder` | 开发测试用，输出随机 1024 维向量 |

### 当前参数

```
BGE_MODEL_PATH = "BAAI/bge-m3"
向量维度 = 1024
```

### 未实现能力

| 能力 | 差距等级 | 说明 |
|------|---------|------|
| BGE-M3 sparse 向量输出 | 中 | `encode()` 仅请求 `return_dense=True`，未启用 `return_sparse` |
| 批量向量化优化 | 低 | 无显式批量控制，依赖 FlagEmbedding 内部 batch |

### 质量评级: **良好**

BGE-M3 是当前 SOTA 多语言嵌入模型，dense 路径已跑通。sparse 能力模型天然具备，仅需 API 层面启用。

### 后续改造点 (阶段 3)

- 可选启用 `return_sparse=True` 输出稀疏向量
- Milvus Schema 新增 `SPARSE_FLOAT_VECTOR` 字段

---

## 4. 检索模块

**关键文件**: `backend/app/rag/retriever.py`

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| Milvus 向量检索 | `VectorRetriever.search()` | IVF_FLAT 索引，COSINE 距离，支持 `filter_expr` |
| Elasticsearch BM25 | `BM25Retriever.search()` | 双分析器：`ik_max_word`(中文) + `english`(英文)，`multi_match` 查询 |
| RRF 混合融合 | `HybridRetriever._rrf_fusion()` | `score = sum(weight / (k + rank + 1))`，vector_weight=0.6, bm25_weight=0.4, rrf_k=60 |
| 并行双路检索 | `HybridRetriever.search()` | `asyncio.gather` 并行 Milvus + ES |
| project_id 隔离 | 多处 | Milvus filter + ES term query，含 `_supports_project_filter` 兼容旧索引 |
| paper_ids 筛选 | 多处 | Milvus `paper_id in [...]` + ES `terms` 查询 |
| 降级策略 | `RAGEngine.search()` | 混合检索失败时回退纯向量检索 |

### 当前参数

```
vector_weight = 0.6
bm25_weight   = 0.4
rrf_k         = 60
RETRIEVAL_TOP_K = 5 (config 默认)
实际检索: top_k * 3 候选 → rerank → top_k 最终
```

### 未实现能力

| 能力 | 差距等级 | 说明 |
|------|---------|------|
| BGE-M3 sparse 向量检索 | 中 | 无第三路 sparse 检索 |
| 检索审计日志 | 中 | `fusion_score` 已写入 metadata，但无完整审计（各路排名、来源、过滤原因） |
| 自适应检索预算 | 低 | `top_k` 固定，未按查询复杂度动态调整 |
| 三路 RRF 融合 | 缺失 | `_rrf_fusion` 仅支持双路 |

### 质量评级: **良好**

BM25 + Dense + RRF 混合检索骨架已完整实现并上线。是当前系统已有的最核心资产之一。

### 后续改造点 (阶段 3)

- 增加检索审计日志
- 可选接入 BGE-M3 sparse 三路融合
- 自适应检索预算

---

## 5. 重排序模块

**关键文件**: `backend/app/rag/engine.py` (`_rerank()` 方法)

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| LLM-based 重排序 | `RAGEngine._rerank()` | 将候选文档发给 LLM，要求返回相关性排序的 JSON 数组 |
| 解析容错 | `_rerank()` | 提取 JSON 数组失败时回退原序截断 |

### 未实现能力

| 能力 | 差距等级 | 说明 |
|------|---------|------|
| 专用 reranker 模型 | 中高 | 使用通用 LLM 而非 BGE-Reranker，精度和速度均不如专用模型 |
| 批量计算 cross-encoder 分数 | 缺失 | LLM rerank 需完整请求-响应周期，无法并行打分 |

### 质量评级: **中**

LLM rerank 有效但不够高效和精准。每次 rerank 消耗一次完整 LLM 调用，延迟较高。

### 后续改造点 (阶段 3)

- 接入 BGE-Reranker-v2-m3 专用重排模型
- 本地推理，毫秒级 cross-encoder 打分

---

## 6. 证据治理模块

**关键文件**: `backend/app/rag/engine.py` (`_prepare_evidence()` 及相关方法)

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| 参考文献过滤 | `_filter_reference_like_docs()` | 正则检测参考文献条目（`[n]` 格式、`et al.`、DOI 等），过滤占比 >= 20% 的文档 |
| 行政噪声过滤 | `_is_administrative_noise()` | 检测签字/公章/声明/联系方式等无价值内容 |
| 低信号文档过滤 | `_filter_low_signal_docs()` | 动态阈值 `max_score * 0.65`，剪掉明显尾部噪声 |
| 多文献多样性 | `_diversify_docs_by_paper()` | 两轮选择：先每篇文献选 1 条，再按排序补齐 |
| 检索元信息 | `retrieval_meta` | 记录 search_hit_count / filtered_count / covered_paper_ids 等 |
| 记忆融合 | `_build_context_with_memory()` | 历史记忆 + 文献证据合并构建上下文 |

### 质量评级: **良好**

证据治理链完整，从检索到生成之间有多层过滤和增强。这是应保留的核心资产。

### 后续改造点

- 引用一致性校验器（阶段 4 贯穿）
- 统一中间件治理框架

---

## 7. LLM 生成模块

**关键文件**: `backend/app/rag/engine.py`, `backend/app/rag/prompts.py`

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| DeepSeek API 接入 | `_init_llm()` | `ChatOpenAI` 兼容接口，model=`deepseek-reasoner`，temperature=0.3 |
| OpenRouter 备用 | `config.py` EFFECTIVE_* 属性 | LLM_API_KEY 优先 → OPENROUTER 回退 |
| 统一 Prompt 模板 | `prompts.py` | RAG QA / Retriever / Writer / Analyzer 等模板集中管理 |
| 结构化输出格式 | `SYSTEM_PERSONA` | 要求 Markdown 输出：结论 / 依据与分析 / 局限 / 参考来源 |
| 引用标注要求 | `SYSTEM_PERSONA` | 要求 `[1][2]` 格式标注，未检索到不编造 |
| 流式生成 | `answer_stream()` | SSE 事件流：references → chunk → done |
| 对话历史 | `build_conversation_history_text()` | 最近 5 轮对话注入 prompt |

### 当前参数

```
LLM_MODEL     = "deepseek-reasoner"
LLM_BASE_URL  = "https://api.deepseek.com"
temperature   = 0.3
```

### 质量评级: **良好**

DeepSeek API 已接入且提示词模板管理规范。

---

## 8. Agent 编排模块

**关键文件**: `backend/app/agents/coordinator.py`, `backend/app/agents/base_agent.py`

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| 4 类 Agent | coordinator.py | RetrieverAgent / AnalyzerAgent / WriterAgent / SearchAgent |
| 自动路由 | `_route_query()` | 每个 Agent 的 `can_handle()` 打分，选最高分 Agent |
| 多 Agent 并行 | `process_multi()` | `asyncio.gather` 并发执行多个 Agent |
| Skills 注册表 | `_skill_registry` | 代码型技能注册与注入 |
| 跨 Agent 记忆 | `CrossMemoryNetwork` | Agent 间共享记忆 |

### 未实现能力

| 能力 | 差距等级 | 说明 |
|------|---------|------|
| 动态子任务分解 | **中高** | 复杂问题无法自动拆分为多个子任务 |
| 任务状态流 | 中 | 无 SSE 推送子任务进度 |
| 中间件链 | 中 | 澄清/摘要/限流等逻辑未制度化 |
| 文档型技能协议 | 缺失 | 仅支持代码型技能 |
| MCP 工具网关 | 缺失 | 无外部工具扩展能力 |

### 质量评级: **中**

固定角色路由 + 并发执行能力已具备，但缺乏动态编排和可观测性。

### 后续改造点 (阶段 4/5)

- Runtime 中间件框架
- 动态子任务执行器
- SSE 事件流
- Markdown 技能协议 + MCP 网关

---

## 9. 记忆系统

**关键文件**: `backend/app/rag/memory_engine/`

### 已实现能力

| 能力 | 实现位置 | 说明 |
|------|---------|------|
| 动态记忆 | `DynamicMemoryEngine` | 记忆存储/检索/遗忘 |
| 重构记忆 | `reconstructive.py` | 基于线索重构历史记忆 |
| 跨 Agent 记忆 | `cross_memory.py` | Agent 间共享知识 |
| 线索提取 | `cue_extractor.py` | 查询线索提取 |
| 查询分类 | `query_classifier.py` | 分类查询意图 |
| 反思机制 | `reflector.py` | 记忆反思与整合 |
| 遗忘机制 | `forgetting.py` | 低价值记忆淘汰 |

### 质量评级: **良好**

记忆体系高于常见方案，DynamicMemory + Reconstructive + Cross 组合完整。

---

## 10. 配置管理

**关键文件**: `backend/app/core/config.py`

### 已实现能力

| 能力 | 说明 |
|------|------|
| Pydantic Settings | 环境变量 + `.env` 文件配置 |
| 多数据库配置 | PostgreSQL / MongoDB / Redis / Milvus / ES |
| LLM 双路配置 | DeepSeek 优先 → OpenRouter 回退 |
| RAG 参数 | `CHUNK_SIZE=1024`, `CHUNK_OVERLAP=128`, `RETRIEVAL_TOP_K=5` |

### 未实现能力

| 能力 | 说明 |
|------|------|
| Feature Flag 机制 | 无任何功能开关配置 |
| MinerU 相关配置 | 无 `MINERU_ENABLED` 等 |
| 检索增强配置 | 无 `SPARSE_RETRIEVAL_ENABLED` / `RERANKER_V2_ENABLED` 等 |
| 编排配置 | 无 `RUNTIME_MIDDLEWARE_ENABLED` / `SUBTASK_MODE_ENABLED` 等 |

### 后续改造点 (贯穿全程)

- 每个阶段新增对应的 Feature Flag 配置项
- 所有新功能默认 `False`，灰度开启

---

## 11. 存储架构

### 已实现

| 存储 | 用途 | Docker 配置 |
|------|------|------------|
| PostgreSQL 16 | 用户/项目/文献元数据 | 端口 5433 |
| MongoDB 7 | 文档分块文本存储 | 端口 27017 |
| Redis 7 | 缓存/会话 | 端口 6379 |
| Milvus 2.3.4 | 向量索引（BGE-M3 1024 维） | 端口 19530 |
| Elasticsearch 8.12 | BM25 全文索引（ik 分词） | 端口 9201 |

### 质量评级: **良好**

多存储互补架构职责边界清晰，Docker Compose 编排完整。

---

## 12. API 接口

**关键文件**: `backend/app/api/v1/`

### 已实现端点

| 路由 | 功能 | 关键端点 |
|------|------|---------|
| `/api/v1/auth` | 认证 | register / login |
| `/api/v1/projects` | 项目管理 | CRUD |
| `/api/v1/papers` | 文献管理 | upload / list / detail |
| `/api/v1/rag` | RAG 问答 | ask / stream / conversations |
| `/api/v1/agent` | Agent 系统 | ask / multi / write / analyze / stream / knowledge-graph |
| `/api/v1/writing` | 写作辅助 | outline / review / polish / suggest-citations |
| `/api/v1/memory` | 记忆系统 | stats / list / reconstruct |
| `/api/v1/external` | 外部学术 API | arXiv / CrossRef / OpenAlex / SemanticScholar |
| `/api/v1/trends` | 趋势分析 | trend API |

### 质量评级: **良好**

前端已对接的完整 API 契约，后续改造需保持兼容。

---

## 13. 测试与评测现状

### 已有

| 资产 | 位置 | 说明 |
|------|------|------|
| 4 篇测试 PDF | `backend/tests/test_doc/` | 3 篇 RAG survey + 1 篇 Cybersecurity |
| Live eval 脚本 | `backend/tests/run_llm_live_eval.sh` | 注册→上传→调 RAG/Agent/Writing/Memory API，保存请求响应 |
| 历史 eval 运行 | `backend/tests/llm_eval_results/` | 14 次时间戳目录 |
| 质量回归测试 | `test_quality_regressions.py` | PDF 标题质量判定 + KG 噪声过滤 |
| 记忆系统测试 | `test_memory_engine.py` 等 | memory / reconstructive / cross_memory / cue / forgetting / query_classifier |

### 缺失

| 缺失项 | 影响 |
|--------|------|
| 正式 ground-truth QA 标注集 | 无法量化回答质量 |
| IR 标准指标自动计算 | 无 Recall@K / nDCG@K |
| PDF 解析正确率结构化评测 | 无法量化解析质量 |
| baseline vs candidate 对比框架 | 无法证明改造收益 |
| 代码能力校准清单（本文档） | 后续阶段可能对着错误假设做方案 |

---

## 14. 总结：模块成熟度矩阵

| 模块 | 成熟度 | 核心差距 | 改造优先级 |
|------|--------|---------|-----------|
| PDF 解析 | ★★☆☆☆ | 无端到端 Markdown 恢复，无公式/复杂表格 | **P0** (阶段 1) |
| 文本切分 | ★★★☆☆ | 无父子文档结构 | **P0** (阶段 2) |
| 向量化 (BGE-M3) | ★★★★☆ | sparse 未启用（模型已支持） | P1 (阶段 3) |
| 混合检索 (BM25+RRF) | ★★★★☆ | 缺审计日志、sparse 三路 | P1 (阶段 3) |
| 重排序 | ★★★☆☆ | 通用 LLM 而非专用 reranker | P1 (阶段 3) |
| 证据治理 | ★★★★☆ | 核心资产，保留 | — |
| LLM 生成 | ★★★★☆ | DeepSeek 已接入 | — |
| Agent 编排 | ★★★☆☆ | 缺动态子任务、中间件、状态流 | P1 (阶段 4) |
| 记忆系统 | ★★★★☆ | 高于常见方案 | — |
| 存储架构 | ★★★★☆ | 职责清晰，Docker 完整 | — |
| API 接口 | ★★★★☆ | 前端已对接 | — |
| 配置管理 | ★★★☆☆ | 无 Feature Flag | 贯穿全程 |
| 测试/评测 | ★★☆☆☆ | 无量化评测框架 | **前置** (阶段 0) |

---

## 15. 关键资产保留清单

以下已实现能力经评估质量较好，后续改造时**必须保留**：

1. **BGE-M3 向量化 + Milvus 存储**: 基础向量化流程已跑通
2. **BM25(ES) + Dense(Milvus) + RRF 混合检索**: `retriever.py` 中 `HybridRetriever` 已实现并行双路检索与 RRF 融合
3. **证据治理链**: `engine.py` 中的参考文献过滤、行政噪声过滤、低信号过滤、多文献多样性
4. **记忆体系**: DynamicMemory + ReconstructiveMemory + CrossMemory 组合
5. **API 契约**: `/api/v1/rag/*`, `/api/v1/agent/*` 等前端已对接的接口
6. **多存储互补架构**: Postgres / Mongo / Milvus / ES / Redis 职责边界清晰
7. **统一 Prompt 模板**: `prompts.py` 集中管理，结构化输出格式
