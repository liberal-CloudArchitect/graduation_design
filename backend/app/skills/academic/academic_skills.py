"""
Academic Skills - 核心学术处理能力实现

包含 4 个 Skills:
1. parse_pdf_with_docling    - IBM Docling 高精度 PDF 解析
2. get_paper_bibtex          - 从 PDF 自动提取 DOI 并获取 BibTeX
3. search_and_scrape_papers  - arXiv 等平台联网论文搜索
4. parse_bibtex_entries      - 解析 BibTeX 文件/字符串为结构化数据
"""
import os
import asyncio
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.skills.registry import skill_registry
from loguru import logger


# ============================================================
# 1. Docling 高级 PDF 解析
# ============================================================

class DoclingParseInput(BaseModel):
    file_path: str = Field(..., description="PDF文件的本地路径")


@skill_registry.register(
    name="parse_pdf_with_docling",
    description="使用 IBM Docling 引擎解析 PDF，能够识别复杂的层次结构、表格并转换为标准的 Markdown 格式。",
    input_schema=DoclingParseInput,
    category="academic",
    timeout=120.0,
)
async def parse_pdf_with_docling(file_path: str):
    """使用 Docling 将 PDF 转为结构化 Markdown"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF 文件不存在: {file_path}")

    try:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(file_path)
        markdown = result.document.export_to_markdown()
        return {
            "markdown": markdown,
            "char_count": len(markdown),
        }
    except ImportError:
        # 降级：使用 pdfplumber
        logger.warning("docling 未安装，使用 pdfplumber 降级解析")
        import pdfplumber

        texts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
        content = "\n\n".join(texts)
        return {
            "markdown": content,
            "char_count": len(content),
            "fallback": True,
        }


# ============================================================
# 2. pdf2bib 引用自动补全
# ============================================================

class ExtractBibInput(BaseModel):
    file_path: str = Field(..., description="PDF文件路径")


@skill_registry.register(
    name="get_paper_bibtex",
    description="自动识别 PDF 中的 DOI 或特征信息，并从网络数据库检索对应的标准 BibTeX 引用条目。",
    input_schema=ExtractBibInput,
    category="academic",
)
async def get_paper_bibtex(file_path: str):
    """从 PDF 提取 DOI 并获取 BibTeX 引用"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF 文件不存在: {file_path}")

    try:
        import pdf2bib

        result = pdf2bib.pdf2bib(file_path)

        # pdf2bib 返回列表或字典
        if isinstance(result, list) and len(result) > 0:
            entry = result[0]
        elif isinstance(result, dict):
            entry = result
        else:
            return {"bibtex": "", "doi": "", "message": "未能从PDF中提取到引用信息"}

        return {
            "bibtex": entry.get("bibtex", ""),
            "doi": entry.get("doi", ""),
            "title": entry.get("title", ""),
            "metadata": {
                k: v for k, v in entry.items() if k not in ("bibtex",)
            },
        }
    except ImportError:
        # 降级：用正则从文本中提取 DOI
        logger.warning("pdf2bib 未安装，使用正则降级提取 DOI")
        import re
        import pdfplumber

        doi_pattern = r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+"
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:3]:
                text = page.extract_text() or ""
                match = re.search(doi_pattern, text)
                if match:
                    return {
                        "bibtex": "",
                        "doi": match.group(0),
                        "title": "",
                        "message": f"找到DOI: {match.group(0)}，pdf2bib未安装无法获取完整BibTeX",
                        "fallback": True,
                    }
        return {"bibtex": "", "doi": "", "message": "未能提取DOI，pdf2bib也未安装"}


# ============================================================
# 3. arXiv 联网论文搜索
# ============================================================

class PaperSearchInput(BaseModel):
    query: str = Field(..., description="学术搜索关键词")
    limit: int = Field(default=5, description="最大返回数量")


@skill_registry.register(
    name="search_and_scrape_papers",
    description="在 arXiv 平台搜索学术论文，返回论文标题、摘要、作者和 PDF 链接等元数据。",
    input_schema=PaperSearchInput,
    category="academic",
    timeout=60.0,
)
async def search_and_scrape_papers(query: str, limit: int = 5):
    """使用 arxiv 库搜索论文并返回结构化元数据"""
    try:
        import arxiv

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=limit,
            sort_by=arxiv.SortCriterion.Relevance,
        )
        results = list(client.results(search))

        papers = []
        for r in results:
            papers.append({
                "title": r.title,
                "abstract": r.summary[:500] if r.summary else "",
                "authors": [a.name for a in r.authors],
                "url": r.entry_id,
                "pdf_url": r.pdf_url,
                "published": r.published.strftime("%Y-%m-%d") if r.published else "",
                "categories": list(r.categories) if r.categories else [],
                "source": "arxiv",
            })

        return {
            "papers": papers,
            "total": len(papers),
            "query": query,
        }

    except ImportError:
        # 降级：直接调用 arXiv REST API
        logger.warning("arxiv 库未安装，使用 httpx 降级调用 arXiv API")
        import httpx
        import re

        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
        }
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            resp = await http_client.get(
                "http://export.arxiv.org/api/query", params=params
            )
            resp.raise_for_status()

        entries = re.findall(r"<entry>(.*?)</entry>", resp.text, re.DOTALL)
        papers = []
        for entry in entries[:limit]:
            title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
            summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
            authors = re.findall(r"<name>(.*?)</name>", entry)
            link = re.search(r"<id>(.*?)</id>", entry)
            published = re.search(r"<published>(.*?)</published>", entry)
            papers.append({
                "title": title.group(1).strip() if title else "",
                "abstract": summary.group(1).strip()[:500] if summary else "",
                "authors": authors,
                "url": link.group(1).strip() if link else "",
                "pdf_url": "",
                "published": published.group(1)[:10] if published else "",
                "source": "arxiv",
                "fallback": True,
            })

        return {"papers": papers, "total": len(papers), "query": query}


# ============================================================
# 4. BibtexParser 解析 BibTeX 数据
# ============================================================

class ParseBibtexInput(BaseModel):
    bibtex_content: str = Field(
        default="",
        description="BibTeX 格式的字符串内容（与 file_path 二选一）",
    )
    file_path: str = Field(
        default="",
        description="BibTeX 文件路径（与 bibtex_content 二选一）",
    )


@skill_registry.register(
    name="parse_bibtex_entries",
    description="解析 BibTeX 文件或字符串，提取所有参考文献条目的结构化信息（标题、作者、年份、期刊等）。",
    input_schema=ParseBibtexInput,
    category="academic",
    timeout=15.0,
)
async def parse_bibtex_entries(bibtex_content: str = "", file_path: str = ""):
    """解析 BibTeX 并返回结构化条目列表"""
    if not bibtex_content and not file_path:
        raise ValueError("必须提供 bibtex_content 或 file_path 之一")

    if file_path and not bibtex_content:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"BibTeX 文件不存在: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            bibtex_content = f.read()

    try:
        import bibtexparser

        library = bibtexparser.parse(bibtex_content)

        entries = []
        for entry in library.entries:
            fields = entry.fields_dict
            entries.append({
                "key": entry.key,
                "type": entry.entry_type,
                "title": fields["title"].value if "title" in fields else "",
                "author": fields["author"].value if "author" in fields else "",
                "year": fields["year"].value if "year" in fields else "",
                "journal": fields["journal"].value if "journal" in fields else "",
                "doi": fields["doi"].value if "doi" in fields else "",
                "abstract": fields["abstract"].value if "abstract" in fields else "",
                "all_fields": {k: v.value for k, v in fields.items()},
            })

        return {"entries": entries, "count": len(entries)}

    except ImportError:
        # 降级：简单正则解析
        logger.warning("bibtexparser 未安装，使用正则降级解析")
        import re

        entries = []
        matches = re.findall(
            r"@(\w+)\{([^,]+),(.*?)\}(?=\s*@|\s*$)",
            bibtex_content,
            re.DOTALL,
        )
        for match in matches:
            entry_type, key, body = match
            fields = {}
            for field_match in re.finditer(r"(\w+)\s*=\s*\{([^}]*)\}", body):
                fields[field_match.group(1).lower()] = field_match.group(2)

            entries.append({
                "key": key.strip(),
                "type": entry_type,
                "title": fields.get("title", ""),
                "author": fields.get("author", ""),
                "year": fields.get("year", ""),
                "journal": fields.get("journal", ""),
                "doi": fields.get("doi", ""),
                "abstract": fields.get("abstract", ""),
                "all_fields": fields,
            })

        return {"entries": entries, "count": len(entries), "fallback": True}
