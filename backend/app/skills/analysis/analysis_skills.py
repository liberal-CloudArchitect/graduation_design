"""
Analysis Skills - 数据分析与可视化相关技能

包含 3 个 Skills:
6. build_knowledge_graph - 从文本提取实体关系三元组构建知识图谱
7. generate_chart        - 根据数据生成统计图表（matplotlib + seaborn）
8. generate_viz_code     - 让 LLM 生成可执行的 Python 可视化代码
"""
import os
import io
import base64
import json
import tempfile
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from loguru import logger

from app.skills.registry import skill_registry


# ===========================================================
# Skill 6: 知识图谱构建（实体关系提取）
# ===========================================================

class KnowledgeGraphInput(BaseModel):
    text: str = Field(..., description="待分析的文本内容")
    max_entities: int = Field(
        default=30, description="最大实体数量"
    )


@skill_registry.register(
    name="build_knowledge_graph",
    description="从非结构化文本中提取实体和关系，构建知识图谱三元组。适用于分析论文间的概念关联、技术路线图生成。",
    input_schema=KnowledgeGraphInput,
    category="analysis",
    timeout=300.0,
)
async def build_knowledge_graph(text: str, max_entities: int = 30):
    """从文本中提取知识图谱"""
    try:
        # 优先使用 LangChain LLMGraphTransformer
        from langchain_experimental.graph_transformers import LLMGraphTransformer
        from langchain_core.documents import Document
        from langchain_openai import ChatOpenAI
        from app.core.config import settings

        llm = ChatOpenAI(
            model=settings.OPENROUTER_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=0,
        )

        transformer = LLMGraphTransformer(llm=llm)

        # 如果文本过长，截断
        truncated_text = text[:4000] if len(text) > 4000 else text
        documents = [Document(page_content=truncated_text)]

        graph_documents = await transformer.aconvert_to_graph_documents(documents)

        # 提取节点和边
        nodes = []
        edges = []
        seen_nodes = set()

        for doc in graph_documents:
            for node in doc.nodes[:max_entities]:
                if node.id not in seen_nodes:
                    nodes.append({
                        "id": node.id,
                        "type": node.type,
                    })
                    seen_nodes.add(node.id)

            for rel in doc.relationships:
                edges.append({
                    "source": rel.source.id,
                    "target": rel.target.id,
                    "relation": rel.type,
                })

        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    except ImportError as e:
        logger.warning(f"LLMGraphTransformer not available: {e}, using networkx + regex fallback")
        # 降级方案：使用 networkx + 简单 NLP
        return await _build_kg_fallback(text, max_entities)


async def _build_kg_fallback(text: str, max_entities: int = 30) -> dict:
    """降级知识图谱构建：优先使用 LLM 提取实体关系，其次基于关键词共现"""
    
    # 优先尝试 LLM 提取
    try:
        result = await _build_kg_with_llm(text, max_entities)
        if result and result.get("node_count", 0) > 0:
            return result
    except Exception as e:
        logger.warning(f"LLM-based KG extraction failed: {e}, falling back to regex")
    
    # 最终回退：正则 + 共现
    return _build_kg_regex(text, max_entities)


async def _build_kg_with_llm(text: str, max_entities: int = 30) -> dict:
    """使用 LLM 从文本中提取实体和关系"""
    from langchain_openai import ChatOpenAI
    from app.core.config import settings
    
    llm = ChatOpenAI(
        model=settings.OPENROUTER_MODEL,
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        temperature=0,
    )
    
    truncated_text = text[:4000] if len(text) > 4000 else text
    
    prompt = f"""请从以下学术文本中提取关键实体和它们之间的关系。

要求：
1. 提取最多 {max_entities} 个重要实体（概念、技术、方法、模型等）
2. 识别实体之间的关系（如：使用、改进、基于、对比、包含等）
3. 严格按照 JSON 格式输出，不要输出其他内容

输出格式：
{{"nodes": [{{"id": "实体名称", "type": "实体类型"}}], "edges": [{{"source": "源实体", "target": "目标实体", "relation": "关系类型"}}]}}

实体类型包括：concept, method, model, dataset, metric, task, tool, person, organization
关系类型包括：uses, improves, based_on, compared_with, contains, part_of, evaluates, produces, applied_to

文本：
{truncated_text}

请仅输出 JSON，不要添加其他说明文字："""
    
    response = await llm.ainvoke(prompt)
    content = response.content.strip()
    
    # 提取 JSON（兼容 LLM 可能添加的 markdown 代码块）
    import re
    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        content = json_match.group(1)
    
    # 解析 JSON
    result = json.loads(content)
    
    nodes = result.get("nodes", [])[:max_entities]
    edges = result.get("edges", [])
    
    # 验证边的源和目标都在节点中
    node_ids = {n["id"] for n in nodes}
    valid_edges = [
        e for e in edges
        if e.get("source") in node_ids and e.get("target") in node_ids
    ]
    
    return {
        "nodes": nodes,
        "edges": valid_edges,
        "node_count": len(nodes),
        "edge_count": len(valid_edges),
        "method": "llm_extraction",
    }


def _build_kg_regex(text: str, max_entities: int = 30) -> dict:
    """最终回退：基于关键词共现的知识图谱构建"""
    import re
    from collections import Counter

    # 提取可能的实体
    # 英文实体: 包括缩写词（全大写）和标题格式词组
    en_entities = re.findall(r'\b[A-Z][A-Za-z]*(?:[-][A-Za-z]+)*(?:\s+[A-Z][A-Za-z]*)*\b', text)
    # 英文缩写（如 BERT, GPT, NLP）
    en_acronyms = re.findall(r'\b[A-Z]{2,}(?:-\d+)?(?:\b)', text)
    # 中文关键短语（2-8字的连续中文）
    zh_entities = re.findall(r'[\u4e00-\u9fff]{2,8}', text)

    # 过滤常见停用词
    stop_words = {
        "The", "This", "That", "These", "Those", "With", "From", "However",
        "Although", "Because", "Table", "Figure", "Section", "Chapter",
        "Abstract", "Introduction", "Conclusion", "References", "Page",
        "的", "了", "是", "在", "有", "和", "与", "及", "或", "等",
        "对", "为", "从", "到", "中", "上", "下", "也", "但", "并",
        "这个", "那个", "一个", "我们", "他们", "可以", "已经", "进行",
        "使用", "通过", "其中", "以及", "由于", "因此", "然而",
    }
    
    all_entities = [e for e in (en_entities + en_acronyms + zh_entities) if e not in stop_words and len(e) > 1]
    entity_counts = Counter(all_entities)
    top_entities = [e for e, _ in entity_counts.most_common(max_entities)]

    if not top_entities:
        return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}

    # 构建共现关系（同一句中出现的实体）
    sentences = re.split(r'[.!?。！？\n]', text)
    edges = []
    edge_set = set()

    for sentence in sentences:
        present = [e for e in top_entities if e in sentence]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                key = tuple(sorted([present[i], present[j]]))
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({
                        "source": present[i],
                        "target": present[j],
                        "relation": "co_occurrence",
                    })

    nodes = [{"id": e, "type": "entity"} for e in top_entities]

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "method": "co_occurrence_fallback",
    }


# ===========================================================
# Skill 7: 统计图表生成
# ===========================================================

class GenerateChartInput(BaseModel):
    chart_type: str = Field(
        ...,
        description="图表类型: bar, line, pie, scatter, heatmap, wordcloud",
    )
    data: Dict[str, Any] = Field(
        ...,
        description="图表数据，格式取决于图表类型。"
        "例如 bar/line: {'labels': [...], 'values': [...]}; "
        "pie: {'labels': [...], 'sizes': [...]}; "
        "heatmap: {'matrix': [[...]], 'x_labels': [...], 'y_labels': [...]}",
    )
    title: str = Field(default="", description="图表标题")
    output_format: str = Field(
        default="base64",
        description="输出格式: 'base64'(Base64 PNG), 'file'(保存文件并返回路径)",
    )
    save_path: str = Field(default="", description="当 output_format='file' 时的保存路径")


@skill_registry.register(
    name="generate_chart",
    description="根据提供的数据生成统计图表（柱状图、折线图、饼图、散点图、热力图、词云图），返回 Base64 图片或文件路径。",
    input_schema=GenerateChartInput,
    category="analysis",
    timeout=30.0,
)
async def generate_chart(
    chart_type: str,
    data: Dict[str, Any],
    title: str = "",
    output_format: str = "base64",
    save_path: str = "",
):
    """生成统计图表"""
    import matplotlib
    matplotlib.use("Agg")  # 非交互式后端
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    # 尝试设置中文字体
    try:
        plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans", "Arial"]
        plt.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    fig, ax = plt.subplots(figsize=(10, 6))

    if chart_type == "bar":
        labels = data.get("labels", [])
        values = data.get("values", [])
        ax.bar(labels, values)
        if title:
            ax.set_title(title)
        plt.xticks(rotation=45, ha="right")

    elif chart_type == "line":
        labels = data.get("labels", [])
        values = data.get("values", [])
        ax.plot(labels, values, marker="o")
        if title:
            ax.set_title(title)
        plt.xticks(rotation=45, ha="right")

    elif chart_type == "pie":
        labels = data.get("labels", [])
        sizes = data.get("sizes", data.get("values", []))
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90)
        if title:
            ax.set_title(title)

    elif chart_type == "scatter":
        x = data.get("x", [])
        y = data.get("y", [])
        ax.scatter(x, y, alpha=0.6)
        ax.set_xlabel(data.get("x_label", "X"))
        ax.set_ylabel(data.get("y_label", "Y"))
        if title:
            ax.set_title(title)

    elif chart_type == "heatmap":
        try:
            import seaborn as sns
            import numpy as np

            matrix = np.array(data.get("matrix", []))
            x_labels = data.get("x_labels", None)
            y_labels = data.get("y_labels", None)
            sns.heatmap(
                matrix, annot=True, fmt=".2f",
                xticklabels=x_labels, yticklabels=y_labels, ax=ax,
            )
            if title:
                ax.set_title(title)
        except ImportError:
            ax.text(0.5, 0.5, "seaborn required for heatmap",
                    ha="center", va="center", transform=ax.transAxes)

    elif chart_type == "wordcloud":
        try:
            from wordcloud import WordCloud

            # data 应为 {"words": {"word": frequency, ...}}
            word_freqs = data.get("words", {})
            if not word_freqs and "labels" in data and "values" in data:
                word_freqs = dict(zip(data["labels"], data["values"]))

            wc = WordCloud(
                width=800, height=400,
                background_color="white",
                max_words=100,
            ).generate_from_frequencies(word_freqs)
            ax.imshow(wc, interpolation="bilinear")
            ax.axis("off")
            if title:
                ax.set_title(title)
        except ImportError:
            # 降级为柱状图
            words = data.get("words", {})
            if words:
                sorted_words = sorted(words.items(), key=lambda x: x[1], reverse=True)[:20]
                labels = [w[0] for w in sorted_words]
                values = [w[1] for w in sorted_words]
                ax.barh(labels, values)
                if title:
                    ax.set_title(title + " (WordCloud unavailable, showing bar chart)")

    else:
        ax.text(
            0.5, 0.5, f"Unsupported chart type: {chart_type}",
            ha="center", va="center", transform=ax.transAxes,
        )

    plt.tight_layout()

    # 输出
    if output_format == "file":
        if not save_path:
            fd, save_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {"file_path": save_path, "chart_type": chart_type}

    else:
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        img_base64 = base64.b64encode(buf.read()).decode("utf-8")
        return {
            "image_base64": img_base64,
            "chart_type": chart_type,
            "format": "png",
        }


# ===========================================================
# Skill 8: LLM 生成可视化代码
# ===========================================================

class GenerateVizCodeInput(BaseModel):
    description: str = Field(
        ...,
        description="对所需可视化的自然语言描述，例如 '绘制2020-2024年深度学习论文发表量的折线图'",
    )
    data_context: str = Field(
        default="",
        description="数据上下文描述或实际数据片段，帮助 LLM 理解数据格式",
    )
    execute: bool = Field(
        default=False,
        description="是否直接执行生成的代码并返回图片（True）或仅返回代码（False）",
    )


@skill_registry.register(
    name="generate_viz_code",
    description="根据自然语言描述生成 Python 可视化代码（matplotlib/seaborn），可选择直接执行并返回图表图片。",
    input_schema=GenerateVizCodeInput,
    category="analysis",
    timeout=60.0,
)
async def generate_viz_code(
    description: str, data_context: str = "", execute: bool = False
):
    """让 LLM 生成可视化代码"""
    try:
        from langchain_openai import ChatOpenAI
        from app.core.config import settings

        llm = ChatOpenAI(
            model=getattr(settings, "LLM_MODEL", "gpt-3.5-turbo"),
            openai_api_key=getattr(settings, "OPENROUTER_API_KEY", ""),
            openai_api_base=getattr(settings, "OPENROUTER_BASE_URL", ""),
            temperature=0.2,
        )

        prompt = f"""你是一个 Python 数据可视化专家。请根据以下描述生成一段完整的、可直接运行的 Python 代码。

要求：
1. 使用 matplotlib 和/或 seaborn 库
2. 代码必须包含示例数据（如果用户未提供实际数据）
3. 图表要美观、专业，适合学术论文使用
4. 使用 plt.savefig() 保存到变量 output_path
5. 代码末尾设置 output_path = "/tmp/viz_output.png"
6. 不要使用 plt.show()
7. 设置中文字体支持

可视化描述：{description}
{"数据上下文：" + data_context if data_context else ""}

请只输出 Python 代码，不要添加解释文字。用 ```python 和 ``` 包裹代码。"""

        response = await llm.ainvoke(prompt)
        code_text = response.content

        # 提取代码块
        import re
        code_match = re.search(r'```python\s*(.*?)\s*```', code_text, re.DOTALL)
        if code_match:
            code = code_match.group(1)
        else:
            code = code_text

        result = {
            "code": code,
            "description": description,
        }

        # 如果需要执行代码
        if execute:
            try:
                import matplotlib
                matplotlib.use("Agg")

                output_path = "/tmp/viz_output.png"
                # 在安全的命名空间中执行
                exec_globals = {"__builtins__": __builtins__}
                exec(code, exec_globals)

                actual_path = exec_globals.get("output_path", output_path)
                if os.path.exists(actual_path):
                    with open(actual_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode("utf-8")
                    result["image_base64"] = img_data
                    result["executed"] = True
                    # 清理临时文件
                    os.remove(actual_path)
                else:
                    result["executed"] = False
                    result["error"] = "代码执行完成但未生成图片文件"
            except Exception as exec_error:
                result["executed"] = False
                result["error"] = f"代码执行失败: {str(exec_error)}"

        return result

    except ImportError:
        return {
            "code": "# LLM 服务不可用，无法生成可视化代码",
            "description": description,
            "error": "LangChain OpenAI not available",
        }
