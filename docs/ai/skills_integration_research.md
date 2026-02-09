# 多智能体技能融合研究报告

## 1. 项目实现分析

### 1.1 当前架构
目前的系统是一个设计精良的**单智能体 RAG 系统**，具备模块化的“认知架构”。
- **核心智能体**：`RAGEngine` (位于 `backend/app/rag/engine.py`) 作为主要的协调者。
- **记忆系统**：一个复杂的 `DynamicMemoryEngine`（动态记忆引擎），模拟人类记忆机制（包含反思、遗忘、线索提取等功能）。
- **LLM 集成**：使用连接到 OpenRouter 的 `langchain_openai.ChatOpenAI`。
- **智能体交互性**：目前系统是反应式的（用户提问 -> RAG -> 回答）。它尚未具备自主使用外部工具（Function Calling/函数调用）来解决多步问题的能力。

### 1.2 "多智能体"语境
虽然目前的实现技术上是单智能体的，但 `RAGEngine` 在保存记忆时使用了 `agent_source="qa_agent"` 标签。这意味着架构设计上已经预留了支持多个智能体角色（例如“研究员”、“作家”、“审稿人”）共享同一记忆基质的空间。

## 2. 技能融合可行性评估

**可行性：高**

当前技术栈原生支持集成“Skills”（即 **工具使用 / 函数调用**），且非常建议进行此项升级，以便将系统从单纯的“RAG 聊天机器人”进化为“研究智能体”。

### 关键支持因素：
1.  **LangChain 基础**：项目已经使用了 `ChatOpenAI`，该组件支持 `.bind_tools()` 方法。这是将工具绑定到 LLM 的标准方式。
2.  **OpenRouter/OpenAI API**：底层的模型提供商支持 OpenAI 兼容的函数调用格式。
3.  **模块化设计**：`RAGEngine` 类结构清晰。添加 `tools` 注册表或引入 `AgentExecutor` 循环是自然的扩展方向。

### 集成策略：
工作流将不再仅仅是 `llm.invoke(prompt)`，而是演进为：
1.  **绑定工具**：将技能定义（搜索、计算器等）绑定到 LLM。
2.  **推理循环**：LLM 决定是直接回答还是调用工具。
3.  **工具执行**：系统执行请求的工具，并将结果反馈给 LLM。
4.  **最终回答**：LLM 综合工具输出和 RAG 上下文生成最终回复。

## 3. 推荐的高质量技能 (Skills)

针对 **文献综述与研究智能体**，以下技能至关重要。这些可以通过标准的 LangChain 社区工具或自定义 Python 函数实现。

### A. 学术文献搜索 (核心)
-   **ArXiv Search**: (`langchain_community.utilities.arxiv`)
    -   *功能*：搜索物理学、计算机科学、数学等领域的预印本论文。
    -   *价值*：在正式出版前获取最新的研究成果。
-   **Google Scholar**: (通过 `SerpAPI` 或 `Scholarly`)
    -   *功能*：查找同行评审论文、引用信息和作者主页。
    -   *价值*：学术溯源的黄金标准。
-   **PubMed**: (`langchain_community.tools.pubmed`)
    -   *功能*：生物医学文献搜索。
    -   *价值*：如果研究领域涉及生物/医学，此为必选。

### B. 通用信息与验证 (辅助)
-   **Tavily Search / Google Search**:
    -   *功能*：针对 LLM 优化的高质量网络搜索。
    -   *价值*：验证事实、查找技术文档或查询向量数据库中尚未包含的概念。
-   **Wikipedia**:
    -   *功能*：广泛主题的快速摘要。
    -   *价值*：为智能体提供通用概念的背景知识（Grounding）。

### C. 分析与实用工具 (进阶)
-   **Python REPL**: (`langchain_experimental.utilities.python`)
    -   *功能*：执行 Python 代码。
    -   *价值*：可用于绘制论文数据的图表、执行复杂计算或分析统计数据。
-   **Citation Manager (引用管理)**: (自定义工具)
    -   *功能*：格式化参考文献 (APA, IEEE, BibTeX) 或检查撤稿信息。

## 4. 实施计划

### 步骤 1: 定义技能接口
在 `backend/app/rag/skills/` 中创建一个标准的方式来注册工具。

```python
# backend/app/rag/skills/base.py
from langchain_core.tools import tool

@tool
def search_arxiv(query: str):
    """Search for research papers on ArXiv."""
    # ... implementation
```

### 步骤 2: 更新 RAGEngine
修改 `backend/app/rag/engine.py` 以接受并绑定这些工具。

```python
# In RAGEngine._init_llm
self.tools = [search_arxiv, search_google_scholar]
self.llm_with_tools = self.llm.bind_tools(self.tools)
```

### 步骤 3: 升级为智能体工作流
从简单的链式调用过渡到智能体循环（使用 `LangGraph` 或简单的 `while` 循环处理 `tool_calls`）。

## 5. 结论
本项目完全具备采用多智能体技能架构的条件。通过集成推荐的学术搜索技能，系统将从**被动检索**（仅知晓数据库已有的内容）转变为**主动研究**（主动查找新信息以回答用户问题）。