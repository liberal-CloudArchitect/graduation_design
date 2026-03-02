# 文献阅读多智能体框架融合 Deer-Flow 实施方案（分部分产出）

## 第1部分：当前项目架构的详细全面分析

### 1. 架构分层与职责边界（现状）

当前后端总体采用“业务 API 层 + Agent 编排层 + RAG 引擎层 + 多存储层”的分层结构，分层总体清晰，但在“执行编排标准化”上仍偏业务化耦合。

1. 接入层（FastAPI）
- 入口位于 `backend/main.py`，统一加载生命周期（DB/Mongo/Redis/RAG/AgentCoordinator）。
- API 路由在 `backend/app/api/v1/__init__.py` 注册，按业务域分为 `rag`、`agent`、`papers`、`memory`、`writing`、`trends` 等。
- 这意味着当前系统是“业务优先路由”，而不是“统一 Agent Runtime + 网关路由”模式。

2. Agent 编排层
- 核心是 `backend/app/agents/coordinator.py`，负责：
  - Query 路由到单个 agent（`_route_query`）
  - 多 agent 并发执行（`process_multi`，`asyncio.gather`）
  - skill registry 注入
- Agent 类型固定：`retriever/analyzer/writer/search`（`backend/app/agents/base_agent.py`）。
- 结论：当前是“固定角色多 Agent”架构，不是“动态任务分解型超级智能体”架构。

3. RAG 引擎层
- 统一 RAG 在 `backend/app/rag/engine.py`，负责索引、检索、重排、回答、流式回答、证据构建。
- 检索器 `backend/app/rag/retriever.py` 实现了 Milvus 向量检索 + Elasticsearch BM25 + RRF 融合。
- 这是当前系统最强的底座之一，体现了文献场景的工程定制能力。

4. 记忆层
- 不是简单会话缓存，而是独立的 `memory_engine` 子系统：
  - `dynamic_memory.py`（向量记忆）
  - `reconstructive.py`（Trace-Expand-Reconstruct）
  - `cross_memory.py`（跨 agent 共享）
  - `query_classifier.py`（System1/2 分流）
- 结论：记忆机制比通用 Agent 框架更“学术任务导向”，具备可保留价值。

5. Skills 层
- 当前 Skills 为 Python 函数注册体系（`backend/app/skills/registry.py`），支持：
  - 参数 Schema 校验
  - 超时控制
  - LLM 选择后执行（通过 prompt + JSON 解析）
- 结论：强约束、可控性高，但“发现机制/渐进加载/跨项目复用”能力不足。

6. 存储层
- PostgreSQL：项目、文献、会话等业务对象。
- MongoDB：文献分块文本缓存。
- Milvus：文献向量索引 + 动态记忆向量存储。
- Elasticsearch：BM25 检索索引。
- Redis：缓存与降级策略。
- 结论：数据基础设施完整，且非常适合继续承载融合方案，不建议重构替换。

---

### 2. 核心运行链路分析（从请求到响应）

#### 2.1 启动链路

`main.py` 在 lifespan 中顺序初始化：
1. 关系库
2. MongoDB
3. Redis
4. `rag_engine.initialize()`
5. `agent_coordinator.initialize(rag_engine)`

判断：
- 优点：系统启动顺序明确，Agent 与 RAG 依赖关系清楚。
- 隐患：Coordinator 紧耦合 rag_engine，未来如果引入“统一 Runtime + 子任务执行器”，需要显式解耦（例如依赖接口化）。

#### 2.2 文献入库链路（摄取）

在 `papers.py`：
1. 上传 PDF
2. 后台 `process_paper_async`
3. `PDFParser` 抽取结构化信息
4. `SemanticChunker` 分块
5. 过滤参考文献/低价值文本
6. `rag_engine.index_paper` 写入 Mongo + Milvus + ES

判断：
- 这是学术场景关键护城河：对噪声页、参考文献块、版式区域做了有针对性的过滤。
- 融合 deer-flow 时不能破坏该链路；这部分应作为“证据准备层”继续保留。

#### 2.3 RAG 问答链路

`rag.py -> rag_engine.answer/answer_stream`：
1. 检索记忆（可选）
2. 混合检索（向量 + BM25）
3. 取文档并过滤低信号文档
4. 重排序
5. 构建 prompt（含 history/extra_context）
6. LLM 生成
7. 保存会话 + 记忆

判断：
- 优点：已有“检索质量治理”闭环，不是简单向量召回。
- 隐患：检索链强，但执行链（复杂任务分解、并行搜索、阶段综合）尚未标准化。

#### 2.4 Agent 链路

`agents.py -> agent_coordinator.process/process_multi`：
1. 可指定 agent 或自动路由
2. 单 agent 执行或多 agent 并发
3. 结果聚合返回

判断：
- 当前并行是“按 agent 角色并行”，不是“按子任务并行”。
- 这会导致复杂查询下覆盖面依赖固定 agent 能力，而不是动态拆分任务获得更全面证据。

---

### 3. 当前多智能体能力画像（能力、边界、问题）

#### 3.1 已具备能力

1. 角色分工明确
- Retriever：RAG 检索问答
- Analyzer：趋势/图谱/图表导向分析
- Writer：综述/润色/引用建议
- Search：外部学术源聚合

2. 并发能力存在
- `process_multi` 支持多个 agent 并发执行。

3. 记忆协作机制存在
- CrossMemory 支持 agent 间共享记忆片段。

#### 3.2 能力边界

1. 编排粒度偏粗
- 仅支持“调用哪个 agent”，不支持“同一 agent 内按主题并发分解多子任务”。

2. 缺少任务级执行状态机
- 当前无统一 task 生命周期（pending/running/completed）对外流式可视化。
- 复杂任务执行可观测性不足。

3. 缺少硬并发护栏
- `process_multi` 有并发，但没有 deer-flow 风格“单轮工具调用硬上限 + 截断机制”。
- 在复杂任务下容易出现请求膨胀或链路不稳定。

4. 澄清机制弱
- 没有统一“澄清优先”中间件层；复杂任务中容易出现默认假设执行。

---

### 4. 当前 RAG 与证据治理能力画像

这是当前系统最值得保留并作为融合主干的部分。

1. 召回策略成熟
- 混合检索 + RRF 融合不是简单拼接，而是显式 score 融合。

2. 证据清洗有领域定制
- 参考文献噪声识别、行政噪声识别、低分尾部过滤、文献覆盖多样性。

3. 上下文构造合理
- 会话历史、extra_context（如 Skill 结果）分离注入，避免查询污染。

4. 外部检索有风险控制
- Aggregator 对 AI 语境做噪声过滤（例如生物学 RAG 误召回干扰）。

判断：
- deer-flow 的通用搜索/通用技能机制可以补执行层，但不能替换这套已做过学术调优的证据治理链路。

---

### 5. 当前 Skills 体系画像

#### 5.1 优势

1. 强类型输入校验（Pydantic）
2. 统一执行包装（超时、异常隔离）
3. 可导出 OpenAI function 格式
4. 分类管理（academic/analysis/utility/visualization）

#### 5.2 局限

1. 发现机制弱
- 技能主要靠代码注册；缺少 deer-flow 式 SKILL.md 元数据生态（说明、资源、脚本、引用模板）。

2. 渐进加载能力不足
- 当前 prompt 注入是“可用技能描述列表”，缺少“按需读取工作流文档并分层加载资源”的运行机制。

3. 技能治理粒度不足
- 缺少启停配置、版本化安装、跨会话可配置管理（deer-flow 在 gateway/extensions 上较完善）。

---

### 6. 当前系统的结构性优势（融合时应保留）

1. 学术场景工程化深度高
- PDF 解析、噪声过滤、混合检索、引用回放都已落地。

2. 多存储互补合理
- Postgres/Mongo/Milvus/ES/Redis 的职责边界清晰。

3. API 语义完整
- 已有 `/rag`、`/agent`、`/memory`、`/writing` 等产品接口，可作为融合后的业务兼容层。

4. 记忆体系有创新
- Reconstructive + CrossMemory 的组合明显高于常见“聊天摘要记忆”。

---

### 7. 当前系统的关键瓶颈与成因（需要 deer-flow 能力补位）

1. 复杂任务深度不足
- 成因：编排单位是“agent角色”而非“可并发子任务”。
- 结果：覆盖维度受限，跨来源深挖不足。

2. 执行可观测性不足
- 成因：没有统一 task 执行器及状态事件流。
- 结果：用户难理解“系统正在做什么”，复杂任务体验不稳定。

3. 上下文管理缺统一中间件
- 成因：上下文治理散落在 API、RAG、Agent 内部逻辑。
- 结果：策略难统一升级（如澄清优先、摘要阈值、工具异常修复）。

4. 技能体系难规模化
- 成因：技能主要是代码注册，缺少标准化文档技能协议与分发机制。
- 结果：新增技能成本上升，外部复用弱。

---

### 8. 融合前的硬约束（后续方案必须满足）

为避免“融合后能力倒退”，后续设计必须满足以下约束：

1. 不替换现有 RAG 证据治理链
- 保留 `engine.py` 内检索、过滤、重排、引用机制。

2. 不破坏现有 API 契约
- `/api/v1/rag/*` 与 `/api/v1/agent/*` 对前端保持兼容。

3. 不破坏项目级数据隔离
- 所有检索、记忆、技能执行继续受 `project_id/user_id` 约束。

4. 不引入不可控工具执行风险
- 若引入 deer-flow 式执行器，必须保留超时、并发上限、权限边界。

5. 逐步迁移而非全量替换
- 先增强编排层，再增强技能层，最后再处理运行时统一。

---

### 9. 当前架构成熟度评估（为融合决策提供依据）

1. 文献检索与证据质量：高成熟（可直接复用）
2. 多智能体执行编排：中成熟（需要结构升级）
3. 技能扩展与治理：中等偏低（需要标准化）
4. 会话中间件治理：中等（需要统一到 runtime 层）
5. 可观测性与任务状态：中等偏低（需要任务执行器事件化）

结论：
- 当前项目不是“能力不足”，而是“能力分散在业务层，缺统一超级智能体运行时”。
- 因此融合方向应是“补编排与运行时”，而不是推倒重来。

## 第2部分：deer-flow 架构的全面分析

### 1. deer-flow 的系统定位

deer-flow 2.x 的定位不是“单一研究型 RAG 框架”，而是“超级智能体运行时（super agent harness）”。  
其核心思想是把复杂任务拆成可执行的运行时能力组件，而不是只做 prompt 编排。

从架构角色看，可拆为三层：

1. Agent Runtime 层
- 基于 LangGraph + LangChain `create_agent`，由 `make_lead_agent` 统一构建。
- 提供模型、工具、中间件、系统提示词、状态管理。

2. 执行环境层
- 提供沙箱（本地/容器/provisioner）与统一文件系统映射。
- 支持线程级工作目录隔离（workspace/uploads/outputs）。

3. 扩展生态层
- Skills（Markdown 工作流技能）
- MCP（多协议外部工具）
- Gateway（模型、技能、MCP、上传与产物管理 API）

判断原因：
- 该架构将“能力编排”与“业务场景逻辑”分离，适合承载跨领域任务。
- 对文献场景而言，它提供的是可迁移的执行框架，而不是现成学术检索策略。

---

### 2. Lead Agent 运行时机制（核心）

#### 2.1 构建入口与状态

`backend/langgraph.json` 将图入口绑定到 `src.agents:make_lead_agent`。  
`make_lead_agent` 在运行时解析模型、是否开启 plan mode、是否开启 subagent mode，并生成最终 agent。

关键特征：
1. 动态模型选择与降级
- 若请求模型不存在自动回退默认模型。
- 若模型不支持 thinking，自动关闭 thinking。

2. 统一 ThreadState
- 包含 `messages/sandbox/thread_data/artifacts/todos/uploaded_files/viewed_images/title`。
- 相当于把“会话上下文 + 运行态元数据”统一建模。

判断原因：
- 这是 deer-flow 能稳定运行长任务的前提，因为状态字段不是散落在业务逻辑中。

#### 2.2 中间件链（运行时治理主轴）

deer-flow 通过中间件顺序实现能力治理，关键中间件包括：

1. ThreadDataMiddleware
- 建立线程级路径状态（workspace/uploads/outputs）。

2. UploadsMiddleware
- 将新上传文件列表注入到最后一条用户消息上下文。

3. SandboxMiddleware
- 管理沙箱获取（支持 lazy init，降低空耗）。

4. SummarizationMiddleware
- 按 token/消息阈值自动摘要，保留最近上下文。

5. TodoListMiddleware（plan mode）
- 复杂任务下提供 `write_todos`，显式追踪步骤状态。

6. TitleMiddleware
- 首轮对话后自动生成标题。

7. MemoryMiddleware
- 异步队列化记忆更新（过滤工具中间消息）。

8. ViewImageMiddleware
- 将 `view_image` 的图片内容块注入后续模型上下文。

9. SubagentLimitMiddleware
- 对 `task` 并发调用数量做硬截断（默认限制并可配置范围）。

10. ClarificationMiddleware
- 拦截 `ask_clarification` 工具调用并中断执行，强制先澄清。

判断原因：
- deer-flow 的“可靠性”来自中间件制度化治理，而不是仅靠提示词自律。
- 这类机制对复杂文献任务（多步检索、对比、综合）同样关键。

---

### 3. Subagent 动态分解执行机制

这是 deer-flow 区别于常见“固定多 Agent 角色路由”的关键。

1. 触发方式
- 主 agent 调用 `task` 工具，传入 `description/prompt/subagent_type`。
- 子 agent 类型内置 `general-purpose` 与 `bash`。

2. 执行方式
- `task_tool` 创建 `SubagentExecutor` 后，始终异步执行。
- 后端内部轮询任务状态，完成后一次性把结果回传给主 agent。
- 前端通过 `task_started/task_running/task_completed` 事件可见执行过程。

3. 并发与超时控制
- 双线程池（scheduler + execution）分离调度与执行。
- 子任务级 timeout + 轮询 safety timeout 双层保护。
- `SubagentLimitMiddleware` 进一步防止单轮过量并发。

4. 防递归机制
- 子 agent 工具集合禁用 `task`，避免无限嵌套。

判断原因：
- 这套机制使 deer-flow 能“稳定并发地做复杂任务”，而不仅是“支持并发 API 调用”。

---

### 4. Sandbox 与文件系统执行模型

1. 抽象统一
- `Sandbox` 抽象了 `execute/read/write/list/update`，上层工具不关心底层实现。

2. Provider 可替换
- `LocalSandboxProvider`：本地执行。
- `AioSandboxProvider`：容器执行（社区实现）。

3. 虚拟路径映射
- 统一使用 `/mnt/user-data/{workspace,uploads,outputs}` 与 `/mnt/skills`。
- 本地模式下做虚拟路径替换，容器模式下直接映射。

判断原因：
- 该机制的价值在于“让提示词与工具层看到稳定路径语义”，方便技能和任务跨环境复用。

---

### 5. Tool、Skills、MCP 扩展机制

#### 5.1 Tool 组合机制

工具来自三类：
1. config.yaml 配置工具（web_search/read_file/bash 等）
2. 内置工具（present_file/ask_clarification/task/view_image）
3. MCP 工具（通过 extensions_config 动态加载）

特点：
- 运行时按模型能力（如 vision）和开关（subagent_enabled）动态拼装工具集合。

#### 5.2 Skills 渐进加载机制

1. Skill 格式
- 每个技能目录一个 `SKILL.md`（带 frontmatter 的 name/description）。

2. 加载策略
- 先枚举“可用技能清单”注入系统提示词。
- 任务命中时再 `read_file` 加载对应技能主文档。
- 按技能文档引用路径增量读取资源（scripts/references/assets）。

3. 启停治理
- 通过 `extensions_config.json` 统一维护技能开关状态。

#### 5.3 MCP 动态配置机制

1. 支持 stdio/sse/http transport。
2. gateway 可更新 MCP 配置文件。
3. LangGraph 侧通过 mtime 检查自动失效重载缓存。

判断原因：
- deer-flow 在扩展治理上强调“配置驱动 + 热更新感知”，这是可运维化的重要基础。

---

### 6. deer-flow 架构优势与局限（针对文献场景）

#### 6.1 优势

1. 执行编排能力强
- 动态子任务、并发上限、超时、状态流事件完整。

2. 上下文治理成熟
- 摘要、澄清、上传注入、图像注入等中间件体系完善。

3. 扩展生态完整
- Skills + MCP + Gateway，适合持续扩展能力边界。

4. 运行时可移植
- 沙箱抽象与路径语义稳定，利于跨环境部署。

#### 6.2 局限

1. 领域检索策略不够深
- deer-flow 默认 web 工具与通用检索，不包含学术场景的证据治理细节。

2. 记忆偏“通用用户画像”导向
- 对“项目级证据链一致性”不如当前项目定制。

3. 子 agent 类型较泛化
- 若直接用于学术任务，需新增文献专用子 agent 模板与评分机制。

判断原因：
- deer-flow 强在“Runtime 通用能力”，弱在“学术垂直策略”；因此适合做上层编排，不适合替换你们现有 RAG 内核。

---

### 7. deer-flow 可迁移能力清单（后续融合输入）

建议作为可迁移资产的能力：

1. 中间件化执行治理框架  
2. `task` 子任务执行器模型（含并发与超时护栏）  
3. 技能渐进加载协议（SKILL.md）  
4. MCP 配置化与缓存失效重载机制  
5. 沙箱统一路径语义与运行态隔离模型  
6. 执行事件流（任务开始/运行/完成）可观测能力

不建议直接迁移的能力：

1. deer-flow 默认通用检索策略  
2. deer-flow 通用用户记忆注入策略（需改为项目级证据记忆优先）

---

## 第3部分：两个架构之间的对比分析

### 1. 对比维度总览

| 维度 | 当前项目 | deer-flow | 结论 |
|---|---|---|---|
| 核心定位 | 学术 RAG 产品后端 | 通用超级智能体运行时 | 互补，不冲突 |
| 编排方式 | 固定角色路由 + 并发 | 动态任务分解 + 子任务执行器 | deer-flow 更强 |
| 检索能力 | 学术混合检索 + 证据治理 | 通用工具检索 | 当前项目更强 |
| 记忆机制 | 动态/重构/跨 agent 记忆 | 通用记忆注入 + 事实提取 | 当前项目更适配学术 |
| 上下文治理 | 逻辑分散在 API/RAG/Agent | 中间件链制度化治理 | deer-flow 更强 |
| 技能生态 | 代码注册型 Skill | 文档协议型 Skill + 配置开关 | deer-flow 更强 |
| 扩展工具 | 代码内集成为主 | MCP 配置驱动、可热更新 | deer-flow 更强 |
| 可观测性 | API结果级 | 任务级事件流 | deer-flow 更强 |

---

### 2. 架构差异的本质

1. 当前项目偏“业务导向”
- 优先解决文献任务质量，架构演进围绕产品 API 展开。

2. deer-flow 偏“运行时导向”
- 优先解决智能体执行稳定性与扩展性，再由技能填充场景能力。

本质判断：
- 一个是“高质量学术能力内核”，一个是“高可扩展执行底座”。
- 最优策略不是二选一，而是“内核 + 底座”叠加。

---

### 3. 能力互补矩阵（吸收价值判断）

#### 3.1 deer-flow 对当前项目的补位价值

1. 动态子任务并发机制
- 价值：让复杂问题真正分解成多视角证据探索任务。

2. 中间件治理框架
- 价值：统一澄清、摘要、上传、工具异常修复策略。

3. 技能渐进加载协议
- 价值：降低新增复杂技能的开发与维护成本。

4. MCP 扩展机制
- 价值：快速接入外部学术工具（爬取、图数据库、数据源）。

#### 3.2 当前项目对 deer-flow 的补位价值

1. 学术证据治理链
- 价值：把 deer-flow 从“会做任务”提升为“会做高质量学术任务”。

2. 项目级记忆与重构机制
- 价值：降低跨会话遗忘与证据跳跃风险。

3. 学术搜索与噪声过滤策略
- 价值：显著降低外部召回污染对答案质量的冲击。

---

### 4. 冲突点与可兼容性分析

#### 4.1 主要冲突点

1. 路由模式冲突
- 当前：API 决定调用哪个 agent。
- deer-flow：runtime 决定如何拆解并调度。

2. 技能协议冲突
- 当前：函数注册。
- deer-flow：SKILL.md 文档协议。

3. 记忆注入语义冲突
- 当前：项目/任务证据记忆优先。
- deer-flow：通用用户事实注入优先。

#### 4.2 兼容方案判断

1. 保留 API 层，对内替换编排引擎
- 对前端无侵入，是最稳路径。

2. 双轨技能并存
- 代码技能继续承担关键能力；文档技能承载复杂工作流。

3. 记忆分层注入
- 第一层注入项目证据记忆；第二层可选注入通用偏好记忆。

---

### 5. 吸收优先级结论

一级优先（必须吸收）：
1. 子任务执行器与并发护栏
2. 中间件化上下文治理
3. 任务状态事件流可观测

二级优先（建议吸收）：
1. 技能渐进加载协议
2. MCP 配置驱动扩展

三级优先（谨慎吸收）：
1. deer-flow 通用记忆注入策略（需改造后再引入）

---

## 第4部分：完善全面的吸收融合实施方案

### 1. 融合目标与实施原则

#### 1.1 总体目标

构建“学术证据质量优先 + 超级智能体执行能力增强”的融合架构：

1. 保持现有文献检索与证据治理质量不下降
2. 提升复杂问题的分解深度与并发执行效率
3. 提升回答的可解释性、可追踪性、稳定性
4. 将能力扩展成本从“代码重开发”降低到“协议化技能扩展”

#### 1.2 实施原则

1. 内核不替换
- 保留 `backend/app/rag/engine.py` 为事实证据主引擎。

2. 编排先升级
- 先引入 runtime 编排层与中间件治理，再逐步迁移技能扩展机制。

3. 接口保持兼容
- `/api/v1/rag/*` 与 `/api/v1/agent/*` 响应结构保持稳定。

4. 分阶段可回滚
- 每阶段都有 feature flag 与验收指标，不做一次性切换。

---

### 2. 融合后目标架构（建议）

```
Frontend/API
  -> /api/v1/rag | /api/v1/agent (保持不变)
  -> Orchestration Runtime (新增)
     -> Middleware Chain (clarify/summarize/uploads/subtask_limit/observability)
     -> Task Executor (dynamic subagents)
     -> Skill Resolver (code-skills + markdown-skills)
     -> Tool Hub (local tools + MCP tools)
  -> Academic Evidence Core (保留现有 RAG 引擎)
     -> Hybrid Retrieval + Evidence Filtering + Rerank + Citation Grounding
     -> Project Memory (dynamic + reconstructive + cross-agent)
  -> Storage (Postgres/Mongo/Milvus/ES/Redis)
```

判断原因：
- 该结构把 deer-flow 的“可执行编排能力”置于你们现有证据内核之上，最大化互补价值。

---

### 3. 分阶段实施路线（可操作）

> 建议总周期 8~12 周，分 5 个阶段推进。  
> 每阶段结束均进行回归评估，满足门槛后再进入下一阶段。

### 阶段A：基线固化与评测框架统一（第1-2周）

目标：
- 建立融合前基线，防止“升级后主观变好、客观变差”。

关键任务：
1. 固化基线指标集
- 检索质量：Recall@K、nDCG@K、citation precision。
- 回答质量：事实一致性、引用可追溯率、覆盖广度。
- 执行质量：平均响应时延、95/99线、超时率、失败率。

2. 统一评测数据集
- 使用你们现有 `tests/llm_eval_results` 的问答集。
- 增加复杂多步查询集（对比、综述、争议、反例）。

3. 建立对照实验机制
- baseline=现网 coordinator。
- candidate=后续新 runtime。

交付物：
1. `docs/agent_fusion_eval_baseline.md`
2. `backend/tests/eval_fusion_baseline/`（结构化脚本与结果）

验收标准：
1. 基线报表可重复生成
2. 指标计算口径固定

---

### 阶段B：引入运行时中间件骨架（第2-4周）

目标：
- 把当前散落逻辑收敛到“中间件链”，先不改变业务功能。

关键任务：
1. 新增 Runtime 层模块
- 建议目录：`backend/app/runtime/`
- 组件：
  - `state.py`（统一状态）
  - `middleware/*.py`（clarification/uploads/summarization/subtask_limit）
  - `runner.py`（执行主入口）

2. 把现有逻辑搬迁为中间件
- 上传文件注入逻辑从 API 层抽离。
- 澄清流程统一为前置拦截。
- 长会话摘要规则集中管理。

3. 接入现有 API
- `agents.py` 改为调用 runtime runner，而不是直接调用 coordinator 内部流程。

交付物：
1. Runtime 中间件框架代码
2. API 兼容适配层

验收标准：
1. 功能回归通过（现有接口行为一致）
2. 平均时延增加不超过 10%

风险与回滚：
1. 风险：中间件顺序导致行为变化。
2. 回滚：feature flag `RUNTIME_MIDDLEWARE_ENABLED=false` 切回旧流程。

---

### 阶段C：动态子任务执行器融合（第4-7周）

目标：
- 把固定角色并发升级为“任务分解并发”，提升搜索深度与分析覆盖。

关键任务：
1. 新增 Task Executor
- 借鉴 deer-flow `task_tool + subagent executor` 模式。
- 状态：`pending/running/completed/failed/timed_out`。
- 双线程池 + 双超时保护。

2. 子任务模板化（学术场景专用）
- `retrieval_deep_dive`
- `method_comparison`
- `evidence_checker`
- `synthesis_writer`

3. 并发硬限制
- 引入 `max_concurrent_subtasks`，默认 3。
- 单轮超限截断并记录审计日志。

4. 事件流输出
- SSE 输出 `task_started/task_running/task_completed/task_failed`。
- 前端可视化任务进度。

交付物：
1. `backend/app/runtime/task_executor.py`
2. `backend/app/runtime/subagents/*`
3. `backend/app/api/v1/agents.py` 的流式事件扩展

验收标准：
1. 复杂查询覆盖维度提升（至少 +25%）
2. 超时率不高于基线 +3%
3. 并发失控问题可被护栏拦截

风险与回滚：
1. 风险：任务拆分不当引入冗余调用。
2. 回滚：`SUBTASK_MODE_ENABLED=false` 回退固定路由模式。

---

### 阶段D：Skills 双轨融合 + MCP 接入（第6-9周）

目标：
- 在保留代码型技能的前提下，加入 deer-flow 风格文档技能协议与外部工具扩展。

关键任务：
1. 双轨技能体系
- 轨道1：现有 `SkillRegistry` 代码技能（强约束核心能力）。
- 轨道2：新增 `MarkdownSkillLoader`（解析 SKILL.md 元数据、渐进加载资源）。

2. 技能选择器升级
- 先判定是否命中代码技能。
- 未命中或复杂任务时，加载文档技能工作流。

3. MCP 工具网关
- 新增配置文件（如 `extensions_config.json`）与启停 API。
- 支持 stdio/http/sse 三种 transport。

4. 安全与权限
- 技能白名单
- MCP server 白名单
- 参数 Schema 校验与审计日志

交付物：
1. `backend/app/runtime/skills/markdown_loader.py`
2. `backend/app/runtime/tools/mcp_client.py`
3. `backend/app/api/v1/extensions.py`（或复用现有 agents 路由扩展）

验收标准：
1. 新增一个文档技能无需改核心代码即可上线
2. MCP 工具接入流程可配置化
3. 安全策略通过内部审查

---

### 阶段E：记忆与证据协同优化（第8-12周）

目标：
- 避免“执行能力增强后证据一致性下降”，强化回答质量稳定性。

关键任务：
1. 记忆注入分层
- 层1：项目证据记忆（默认强制）
- 层2：用户偏好/历史风格记忆（可选）

2. 任务级证据缓存
- 子任务结果先落证据缓存层，再由主任务综合。
- 增加去重与冲突检测。

3. 引用一致性校验器
- 检查回答引用编号与证据映射是否一致。
- 检查“结论-证据”关系强度。

4. 失败恢复策略
- 子任务失败降级路径（替代检索或局部重试）。

交付物：
1. `backend/app/runtime/evidence_cache.py`
2. `backend/app/runtime/citation_validator.py`
3. `backend/app/rag/memory_engine/*` 的注入策略扩展

验收标准：
1. 引用一致性错误率下降至少 30%
2. 多子任务下回答稳定性不低于基线

---

### 4. 关键技术决策（明确取舍）

1. 不全量迁移到 LangGraph 服务形态
- 原因：当前 API 生态与业务模型已稳定，强制迁移成本高且风险大。
- 取舍：在现有 FastAPI 内引入 runtime 组件化，后续再评估独立 runtime 服务化。

2. 保留现有 RAG 引擎主导检索
- 原因：已有学术噪声治理和引用机制，替换将导致质量倒退风险。
- 取舍：deer-flow 式执行器调用现有 RAG 能力，不替换其内核。

3. 先双轨技能，后统一协议
- 原因：核心技能不可因协议迁移导致不可用。
- 取舍：短期并存，长期逐步把“流程型技能”迁移到 Markdown 协议。

---

### 5. 项目管理与质量保障机制

1. Feature Flags（必须）
- `RUNTIME_MIDDLEWARE_ENABLED`
- `SUBTASK_MODE_ENABLED`
- `MARKDOWN_SKILLS_ENABLED`
- `MCP_TOOLS_ENABLED`

2. 回归门槛
- 检索/回答质量不低于基线
- P95 延迟增幅 <= 20%
- 关键 API 兼容性 100%

3. 质量看板
- 每周输出融合看板：
  - 质量指标趋势
  - 稳定性指标趋势
  - 失败案例复盘

4. 人员建议
- 后端架构 1 人
- RAG/检索 1 人
- Agent/runtime 1-2 人
- 测试评估 1 人

---

## 第5部分：对融合后架构效果进行预测分析

### 1. 预测前提与方法

预测基于以下前提：

1. 前述五阶段方案按顺序完成且门槛达标。
2. 不替换现有学术检索与证据治理内核。
3. 动态子任务分解主要作用于复杂问题（而非所有请求）。

预测方法：
1. 参考你们现有 `llm_eval_results` 复杂查询模式
2. 结合 deer-flow 子任务机制在复杂任务上的理论收益
3. 按保守/中性/乐观三档估计

---

### 2. 效果预测（核心能力）

#### 2.1 搜索深度与分析完整性

预期变化：
1. 复杂问题的证据覆盖维度：+25% ~ +60%
2. 多来源交叉验证命中率：+20% ~ +45%
3. 单答案支持文献数（有效引用数）：+15% ~ +35%

原因：
1. 动态子任务分解可并发探索不同维度。
2. 执行器状态化降低“中途失败但无反馈”的隐性损耗。
3. 事件流让上层策略可做阶段性纠偏。

#### 2.2 回答质量与稳定性

预期变化：
1. 引用一致性错误率：-20% ~ -40%
2. 事实遗漏率（复杂问题）：-15% ~ -30%
3. 回答结构完整度（结论-依据-不确定性）：+20% ~ +50%

原因：
1. 证据缓存 + 引用一致性校验器降低编号漂移与误引。
2. 中间件化摘要/澄清减少上下文污染与需求误判。
3. 任务综合阶段可显式聚合子任务结果。

#### 2.3 执行效率与资源成本

预期变化：
1. 简单请求平均延迟：变化在 -5% ~ +10%
2. 复杂请求完成时间：-10% ~ +30%（取决于并发度与外部工具耗时）
3. token 成本：短期 +10% ~ +35%，中期通过策略优化回落到 +5% ~ +15%

原因：
1. 复杂任务更深入通常会增加中间推理和工具调用成本。
2. 但并发执行与失败快速回退可缩短端到端时间。
3. 成本可通过“分级调度 + 子任务预算 + 早停策略”收敛。

---

### 3. 风险预测与缓解

#### 3.1 主要风险

1. 任务过度分解导致成本上升
2. 外部工具接入导致不稳定性上升
3. 双轨技能并存导致策略冲突
4. 复杂链路调试难度增加

#### 3.2 缓解策略

1. 分解门槛控制
- 仅对复杂查询开启子任务模式。

2. 预算与早停
- 每请求最大子任务数、最大工具调用数、最大 token 预算。

3. 稳定性分级
- 核心链路仅用白名单工具，实验工具灰度发布。

4. 可观测性优先
- 子任务级 tracing + 失败原因结构化日志。

---

### 4. 融合后可达到的架构形态（目标成熟度）

预计完成后架构成熟度：

1. 学术证据质量：保持高成熟（并进一步稳定）
2. 任务编排能力：由中成熟提升至高成熟
3. 扩展治理能力：由中低提升至中高
4. 可观测性：由中低提升至高
5. 工程可维护性：由“业务耦合式演进”转为“运行时能力演进”

---

### 5. 结论性预测

在“保留现有学术 RAG 内核 + 吸收 deer-flow 执行编排能力”的策略下，  
融合后的系统将从“能回答文献问题”升级为“能稳定分解复杂学术任务并输出高质量证据化答案”的平台。

简化判断：
1. 对简单问答，体验基本持平或小幅改善。  
2. 对复杂研究任务（比较、综述、争议分析、多来源整合），质量与可解释性会显著提升。  
3. 工程侧将从“功能堆叠”转向“运行时治理”，后续迭代成本下降。  

