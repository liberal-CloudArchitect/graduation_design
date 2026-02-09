"""
Utility Skills - 通用工具类技能实现

包含 2 个 Skills:
1. extract_tables_from_pdf  - Camelot 精准 PDF 表格提取
2. call_alternative_llm     - LiteLLM 多模型代理调用
"""
import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.skills.registry import skill_registry
from loguru import logger


# ============================================================
# 1. Camelot 表格提取
# ============================================================

class TableExtractInput(BaseModel):
    file_path: str = Field(..., description="PDF文件路径")
    pages: str = Field("1", description="页码，例如 '1,2' 或 'all'")


@skill_registry.register(
    name="extract_tables_from_pdf",
    description="使用 Camelot 引擎从 PDF 页面中精准提取结构化表格数据，返回所有表格的 JSON 数据。",
    input_schema=TableExtractInput,
    category="utility",
    timeout=60.0,
)
async def extract_tables_from_pdf(file_path: str, pages: str = "1"):
    """使用 Camelot 提取 PDF 中的所有表格"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF 文件不存在: {file_path}")

    try:
        import camelot

        tables = camelot.read_pdf(file_path, pages=pages)

        if len(tables) == 0:
            return {"tables": [], "count": 0, "message": "指定页面未发现表格"}

        # 返回所有表格而非仅第一个
        all_tables = []
        for i, table in enumerate(tables):
            all_tables.append({
                "index": i,
                "rows": table.df.shape[0],
                "cols": table.df.shape[1],
                "data": table.df.to_dict(orient="records"),
                "accuracy": getattr(table, "accuracy", None),
            })

        return {
            "tables": all_tables,
            "count": len(all_tables),
            "pages": pages,
        }

    except ImportError:
        # 降级：使用 pdfplumber 简单提取
        logger.warning("camelot 未安装，使用 pdfplumber 降级提取表格")
        import pdfplumber

        all_tables = []
        with pdfplumber.open(file_path) as pdf:
            target_pages = (
                range(len(pdf.pages))
                if pages == "all"
                else [int(p.strip()) - 1 for p in pages.split(",")]
            )
            for idx in target_pages:
                if 0 <= idx < len(pdf.pages):
                    page_tables = pdf.pages[idx].extract_tables()
                    for t_idx, table in enumerate(page_tables or []):
                        if table:
                            headers = table[0] if table else []
                            rows = [
                                dict(zip(headers, row))
                                for row in table[1:]
                                if len(row) == len(headers)
                            ]
                            all_tables.append({
                                "index": len(all_tables),
                                "rows": len(rows),
                                "cols": len(headers),
                                "data": rows,
                                "page": idx + 1,
                            })

        return {
            "tables": all_tables,
            "count": len(all_tables),
            "pages": pages,
            "fallback": True,
        }


# ============================================================
# 2. LiteLLM 代理调用
# ============================================================

class MultiModelQueryInput(BaseModel):
    prompt: str = Field(..., description="要发送给模型的提示词")
    model: str = Field("gpt-3.5-turbo", description="模型名称，如 claude-2, gemini-pro")


@skill_registry.register(
    name="call_alternative_llm",
    description="使用 LiteLLM 代理调用非默认的大模型（如 Claude 或 Gemini），用于交叉验证或特定任务优化。",
    input_schema=MultiModelQueryInput,
    category="utility",
)
async def call_alternative_llm(prompt: str, model: str = "gpt-3.5-turbo"):
    """通过 LiteLLM 调用第三方大模型"""
    try:
        import litellm

        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "content": response.choices[0].message.content,
            "model": model,
            "usage": {
                "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(response.usage, "completion_tokens", 0),
            },
        }
    except ImportError:
        raise ImportError("litellm 库未安装，请运行 pip install litellm")
