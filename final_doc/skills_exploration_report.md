# Agents Skills 融入多智能体架构的可行性与探索报告
> **生成时间**: 2026年2月9日
> **报告类型**: 架构升级可行性分析 & Skills 资源探索
> **当前架构状态**: 后端功能完备 (Feature-Complete)，Agent 系统已包含 Coordinator 和基础 Agent 类。
---
## Part 1: 可行性与兼容性深度分析

### 1. 可行性分析 (Feasibility)
#### 技术栈兼容性评估
*   **当前栈**: FastAPI (异步框架) + Python 3.10+ + LangChain (潜在/部分使用) + LLM (ChatGLM/OpenAI API)。
*   **评估**: **极高**。
    *   Python 是 Agent Skills 生态的首选语言。
    *   FastAPI 的异步特性 (`async def`) 完美契合网络密集型的 Skill 调用（如搜索、API 请求）。
    *   现有的 `BaseAgent` 类设计足够灵活，可以通过新增一个 `tools` 或 `skills` 属性来扩展，无需重写整个架构。
#### 现有 API 集成点识别
*   **集成点 A: `BaseAgent.execute`**: 目前是一个巨大的 `execute` 方法。改造后，LLM 可以输出 "Function Call" 指令，由 `execute` 方法动态分发到具体的 Skill 函数。
*   **集成点 B: `AnalyzerAgent`**: 目前依赖硬编码的 `TrendAnalyzer`。可以将其拆解为细粒度的 Skills（如 `fetch_timeline_data` ， `calculate_burst_terms`），供 Agent 按需组合。
*   **集成点 C: `WriterAgent`**: 写作任务通常需要多步操作（搜索 -> 大纲 -> 撰写）。Skills 可以作为步骤中的原子操作。
#### 性能瓶颈预测
*   **风险点**:
    *   **LLM 推理延迟**: 增加 Skill 选择步骤（Reasoning）会增加 Token 消耗和时间延迟。
    *   **上下文长度**: 注册过多的 Skills 会占用 System Prompt 的上下文窗口。
*   **对策**: 使用 "Tool Retrieval" 机制，仅动态加载当前任务相关的 Skills；或者使用支持 Function Calling 的轻量级模型。

### 2. 兼容性评估 (Compatibility)
#### 数据流与协议适配
*   **现状**: `Query -> Coordinator -> Agent -> Result (AgentResponse)`
*   **适配**: `Query -> Coordinator -> Agent -> [Skill Selection -> Skill Execution -> Result] -> AgentResponse`
*   **协议**: 需定义统一的 `SkillInterface` (输入 Schema, 输出 Schema, 执行函数)，与 OpenAI Function Calling 格式保持一致。
#### 并发控制机制
*   **现状**: `asyncio.gather` 用于多 Agent 并行。
*   **适配**: 单个 Agent 内部调用多个独立 Skills 时（如同时搜索3个不同的关键词），同样可以使用 `asyncio` 进行并行加速。FastAPI的事件循环天然支持。
#### 错误处理策略
*   **现状**: Agent 级别的 try-except。
*   **适配**: Skill 级别需要独立的沙箱化错误处理。如果一个 Skill（如 "Web Search"）失败，不应导致整个 Agent崩溃，而是返回错误信息给 LLM，让其决定重试或换一种方法。

### 3. 项目提升预测 (Enhancement Prediction)
*   **决策智能化**: Agent 不再是执行死板的 `if-else` 逻辑，而是能根据用户模糊指令（"帮我看看这篇论文的数据是不是造假了"）自主选择调用 "CheckCitation" 或 "AnalyzeDataConsistency"等Skills。
*   **可扩展性增强**: 新增功能（如"导出为 PDF"）只需编写一个 Python 函数并注册为 Skill，无需修改 Agent 核心代码。
*   **开发迭代周期**: 核心架构稳定后，开发人员可以并行开发 Skills，即插即用。
---
## Part 2: 优质 Skills 范例探索 (Skills Exploration)

1. 深度文档解析类 (Deep Document Analysis)
  这类 Skills 能够解决您目前“规则提取元数据”可能存在的局限，识别 PDF 中的复杂表格和图像。
   * Docling (IBM 开源)
       * 地址: https://github.com/DS4SD/docling (https://github.com/DS4SD/docling)
       * 功能: 极速、精准的 PDF 解析器，能够将 PDF 转换为 Markdown，并精准识别文档层次（标题、列表、表格）。
       * 适用场景: 替代现有的 Layer 1，为 RAG 提供更高质量、带语义结构的文本块。
   * Camelot
       * 地址: https://github.com/atlanhq/camelot (https://github.com/atlanhq/camelot)
       * 功能: 专门用于从 PDF 中提取表格数据。
       * 适用场景: 当用户询问“某篇论文实验部分的具体数值”时，AnalyzerAgent 调用此 Skill 精准提取表格。

2. 学术引用与文献管理类 (Citation & BibTeX)
  这类 Skills 确保您的 WriterAgent 生成的文献综述符合学术标准。
   * pdf2bib
       * 地址: https://github.com/pablocarbajo/pdf2bib (https://github.com/pablocarbajo/pdf2bib)
       * 功能: 自动从 PDF 文件中提取 DOI，并联网获取完整的 BibTeX 引用信息。
       * 适用场景: 用户上传本地论文后，自动补全缺失的元数据，并生成标准的参考文献格式。
   * BibtexParser (v2)
       * 地址: https://github.com/sciunto-org/python-bibtexparser (https://github.com/sciunto-org/python-bibtexparser)
       * 功能: 解析、操作 BibTeX 文件。
       * 适用场景: 辅助 WriterAgent 整理引用列表，确保生成的论文草稿参考文献条目正确。

3. 知识挖掘与图谱类 (Knowledge Discovery)
  这类 Skills 提升您项目的“大数据”分析深度，将零散论文串联成知识网。
   * LangChain LLMGraphTransformer
       * 地址: LangChain Documentation (https://python.langchain.com/docs/how_to/graph_transformering/)
       * 功能: 使用 LLM 将非结构化文本转换为“实体-关系-实体”的三元组。
       * 适用场景: 当用户需要“领域技术路线图”时，Agent 扫描多篇论文生成知识图谱并可视化。
   * PaperScraper
       * 地址: https://github.com/blackhc/paperscraper (https://github.com/blackhc/paperscraper)
       * 功能: 自动从 arXiv, PubMed 等平台抓取论文全文及元数据。
       * 适用场景: SearchAgent 的核心技能，实现从关键词到论文全文下载的自动化闭环。

4. 数据处理与可视化类 (Data & Viz)
  增强 AnalyzerAgent 的数据表达能力。
   * MatPlotAgent
       * 地址: https://github.com/msc-library/MatPlotAgent (https://github.com/msc-library/MatPlotAgent)
       * 功能: 让 Agent 能够自动生成、执行 Python 可视化代码并渲染出复杂的科学图表。
       * 适用场景: 根据论文中的趋势数据自动绘制折线图或热力图。
   * Geoplotlib
       * 地址: https://github.com/andrea-cuttone/geoplotlib (https://github.com/andrea-cuttone/geoplotlib)
       * 功能: 地理空间数据可视化。
       * 适用场景: 分析某一研究领域的全球研究机构分布（基于论文作者地址）。

5. LLM 工具增强类 (LLM Utilities)
  提升 Agent 内部处理效率的底层 Skills。
   * LiteLLM
       * 地址: https://github.com/BerriAI/litellm (https://github.com/BerriAI/litellm)
       * 功能: 统一所有 LLM API 的调用格式（OpenAI, Claude, Gemini, Ollama）。
       * 适用场景: 作为底层 Skills，让 Agent 能够根据任务成本或复杂度动态切换模型（如用低成本模型总结，用高推理模型写论文）。
   * Pydantic
       * 地址: https://github.com/pydantic/pydantic (https://github.com/pydantic/pydantic)
       * 功能: 数据验证与设置。
       * 适用场景: 强制所有 Skills 的输入输出必须符合预定义的 Schema，确保多智能体协作时数据传递的稳定性。

### 5. 推荐架构实现 (Implementation Strategy)
建议在 `backend/app/` 下新建 `skills/` 目录：
```                                                                
backend/app/
├── agents/
│  ├── base_agent.py  <-- 修改以支持 tool_calls
│  │   
│  └── ...
└── skills/            <-- 新增
    ├── __init__.py
    ├── registry.py    <-- Skill 注册与发现机制
    ├── academic/      <-- 学术相关 (Search, Citation)
    ├── visualization/ <-- 可视化相关 (ECharts)│
    └── utility/       <-- 通用工具 (PDF, FileIO)
```                                                                     
## 结论
将 **Agents Skills** 融入当前架构在技术上是**完全可行**的，且风险可控。它将把目前的“指令式 Agent”升级为真正的“自主Agent”，显著提升系统处理复杂、多步骤学术任务的能力。建议作为 Phase 5 的重点优化方向进行实施。 