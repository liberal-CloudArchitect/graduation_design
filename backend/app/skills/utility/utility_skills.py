"""
Utility Skills - 通用工具技能

包含 2 个 Skills:
9.  format_references    - 格式化参考文献列表
10. summarize_with_model - 使用指定模型进行文本摘要
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from loguru import logger

from app.skills.registry import skill_registry


# ===========================================================
# Skill 9: 参考文献格式化
# ===========================================================

class FormatReferencesInput(BaseModel):
    references: List[Dict[str, Any]] = Field(
        ...,
        description="参考文献列表，每个条目包含 title, author, year, journal, doi 等字段",
    )
    style: str = Field(
        default="apa",
        description="引用格式: apa, mla, chicago, gb_t_7714 (国标), bibtex",
    )


@skill_registry.register(
    name="format_references",
    description="将结构化的参考文献数据格式化为标准引用格式（APA、MLA、Chicago、GB/T 7714、BibTeX）。适用于论文写作时的参考文献整理。",
    input_schema=FormatReferencesInput,
    category="utility",
    timeout=15.0,
)
async def format_references(
    references: List[Dict[str, Any]], style: str = "apa"
):
    """格式化参考文献"""
    formatted = []

    for i, ref in enumerate(references, 1):
        title = ref.get("title", "Untitled")
        authors = ref.get("author", ref.get("authors", "Unknown"))
        year = ref.get("year", "n.d.")
        journal = ref.get("journal", ref.get("venue", ""))
        doi = ref.get("doi", "")
        volume = ref.get("volume", "")
        issue = ref.get("issue", "")
        pages = ref.get("pages", "")
        publisher = ref.get("publisher", "")
        url = ref.get("url", "")

        # 标准化作者格式
        if isinstance(authors, list):
            author_str = ", ".join(authors)
        else:
            author_str = str(authors)

        if style == "apa":
            # APA 7th Edition
            entry = f"{author_str} ({year}). {title}."
            if journal:
                entry += f" *{journal}*"
                if volume:
                    entry += f", *{volume}*"
                if issue:
                    entry += f"({issue})"
                if pages:
                    entry += f", {pages}"
                entry += "."
            if doi:
                entry += f" https://doi.org/{doi}"
            formatted.append(f"[{i}] {entry}")

        elif style == "mla":
            # MLA 9th Edition
            entry = f'{author_str}. "{title}."'
            if journal:
                entry += f" *{journal}*"
                if volume:
                    entry += f", vol. {volume}"
                if issue:
                    entry += f", no. {issue}"
                entry += f", {year}"
                if pages:
                    entry += f", pp. {pages}"
                entry += "."
            if doi:
                entry += f" doi:{doi}."
            formatted.append(f"[{i}] {entry}")

        elif style == "chicago":
            # Chicago Author-Date
            entry = f"{author_str}. {year}. \"{title}.\""
            if journal:
                entry += f" *{journal}*"
                if volume:
                    entry += f" {volume}"
                if issue:
                    entry += f", no. {issue}"
                if pages:
                    entry += f": {pages}"
                entry += "."
            if doi:
                entry += f" https://doi.org/{doi}."
            formatted.append(f"[{i}] {entry}")

        elif style == "gb_t_7714":
            # GB/T 7714-2015（中国国标）
            entry = f"{author_str}. {title}[J]."
            if journal:
                entry += f" {journal}"
                if year:
                    entry += f", {year}"
                if volume:
                    entry += f", {volume}"
                if issue:
                    entry += f"({issue})"
                if pages:
                    entry += f": {pages}"
                entry += "."
            if doi:
                entry += f" DOI: {doi}."
            formatted.append(f"[{i}] {entry}")

        elif style == "bibtex":
            # BibTeX 格式
            key = ref.get("key", f"ref{i}")
            entry_type = ref.get("type", "article")
            bib_entry = f"@{entry_type}{{{key},\n"
            bib_entry += f"  title = {{{title}}},\n"
            bib_entry += f"  author = {{{author_str}}},\n"
            bib_entry += f"  year = {{{year}}},\n"
            if journal:
                bib_entry += f"  journal = {{{journal}}},\n"
            if volume:
                bib_entry += f"  volume = {{{volume}}},\n"
            if issue:
                bib_entry += f"  number = {{{issue}}},\n"
            if pages:
                bib_entry += f"  pages = {{{pages}}},\n"
            if doi:
                bib_entry += f"  doi = {{{doi}}},\n"
            if url:
                bib_entry += f"  url = {{{url}}},\n"
            bib_entry += "}"
            formatted.append(bib_entry)

        else:
            # 默认简单格式
            entry = f"[{i}] {author_str}. {title}. {journal} ({year})."
            if doi:
                entry += f" DOI: {doi}"
            formatted.append(entry)

    separator = "\n\n" if style == "bibtex" else "\n"
    return {
        "formatted_text": separator.join(formatted),
        "count": len(formatted),
        "style": style,
    }


# ===========================================================
# Skill 10: 使用指定模型进行文本摘要
# ===========================================================

class SummarizeInput(BaseModel):
    text: str = Field(..., description="需要摘要的文本内容")
    max_length: int = Field(
        default=500, description="摘要的最大字数"
    )
    language: str = Field(
        default="auto",
        description="输出语言: 'zh'(中文), 'en'(英文), 'auto'(与原文一致)",
    )
    model: str = Field(
        default="",
        description="指定 LLM 模型名称（为空则使用默认模型）。"
        "支持通过 LiteLLM 调用各种模型，如 'gpt-4', 'claude-3-sonnet', 'deepseek-chat' 等。",
    )
    focus: str = Field(
        default="",
        description="摘要重点关注的方面，如 '方法论', '实验结果', '创新点'",
    )


@skill_registry.register(
    name="summarize_with_model",
    description="使用 LLM 对长文本进行智能摘要，支持指定模型、语言和关注重点。适用于论文摘要生成、文献快速浏览。",
    input_schema=SummarizeInput,
    category="utility",
    timeout=60.0,
)
async def summarize_with_model(
    text: str,
    max_length: int = 500,
    language: str = "auto",
    model: str = "",
    focus: str = "",
):
    """使用 LLM 生成文本摘要"""

    # 构建摘要 prompt
    lang_instruction = ""
    if language == "zh":
        lang_instruction = "请用中文输出摘要。"
    elif language == "en":
        lang_instruction = "Please output the summary in English."

    focus_instruction = ""
    if focus:
        focus_instruction = f"摘要应重点关注以下方面: {focus}"

    prompt = f"""请对以下文本生成一份简洁、准确的摘要。

要求：
1. 摘要长度不超过{max_length}字
2. 保留核心观点和关键信息
3. 使用学术风格的语言
{lang_instruction}
{focus_instruction}

原文：
{text[:8000]}

摘要："""

    try:
        # 优先尝试使用 LiteLLM（统一多模型接口）
        if model:
            try:
                import litellm

                response = await litellm.acompletion(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_length * 2,
                    temperature=0.3,
                )
                summary = response.choices[0].message.content
                return {
                    "summary": summary,
                    "model_used": model,
                    "char_count": len(summary),
                    "provider": "litellm",
                }
            except ImportError:
                logger.warning("LiteLLM not installed, falling back to default LLM")
            except Exception as e:
                logger.warning(f"LiteLLM call failed: {e}, falling back to default LLM")

        # 降级到默认 LLM（通过 LangChain）
        from langchain_openai import ChatOpenAI
        from app.core.config import settings

        llm = ChatOpenAI(
            model=getattr(settings, "LLM_MODEL", "gpt-3.5-turbo"),
            openai_api_key=getattr(settings, "OPENROUTER_API_KEY", ""),
            openai_api_base=getattr(settings, "OPENROUTER_BASE_URL", ""),
            temperature=0.3,
            max_tokens=max_length * 2,
        )

        response = await llm.ainvoke(prompt)
        summary = response.content

        return {
            "summary": summary,
            "model_used": getattr(settings, "LLM_MODEL", "default"),
            "char_count": len(summary),
            "provider": "langchain_openai",
        }

    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        # 最终降级：简单截断
        truncated = text[:max_length]
        last_period = max(
            truncated.rfind("。"),
            truncated.rfind("."),
            truncated.rfind("！"),
            truncated.rfind("？"),
        )
        if last_period > max_length // 2:
            truncated = truncated[:last_period + 1]

        return {
            "summary": truncated + "...",
            "model_used": "truncation_fallback",
            "char_count": len(truncated),
            "provider": "fallback",
            "warning": f"LLM 摘要失败，已使用截断降级: {str(e)}",
        }
