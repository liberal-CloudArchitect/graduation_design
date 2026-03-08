"""
MinerU PDF 解析服务 -- FastAPI wrapper

独立于主后端，通过 HTTP 提供 PDF → Markdown 解析能力。
部署到 4090 服务器，主后端通过 MinerUClient 调用。

解析后端优先级:
  1. magic-pdf (MinerU 端到端 VLM 解析) — 需要 GPU
  2. PyMuPDF 结构化提取 — CPU 回退
"""
import asyncio
import json
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from typing import Optional

import fitz  # PyMuPDF
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

import config

_semaphore: Optional[asyncio.Semaphore] = None
_backend = "none"  # "magic_pdf" | "pymupdf"


def _load_model() -> str:
    """尝试加载 magic-pdf 模型。返回实际使用的后端名称。"""
    global _backend
    try:
        from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
        from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze

        _backend = "magic_pdf"
        print("[startup] magic-pdf loaded successfully")
        return _backend
    except ImportError:
        pass

    _backend = "pymupdf"
    print("[startup] magic-pdf not available, using PyMuPDF fallback")
    return _backend


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _semaphore
    _semaphore = asyncio.Semaphore(config.MAX_CONCURRENT)
    _load_model()
    yield


app = FastAPI(title="MinerU PDF Parse Service", lifespan=lifespan)


def _verify_api_key(request: Request):
    if not config.API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {config.API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid API key")


# ---------------------------------------------------------------------------
# magic-pdf 解析
# ---------------------------------------------------------------------------

def _parse_with_magic_pdf(pdf_bytes: bytes) -> dict:
    """使用 magic-pdf 端到端解析 PDF → Markdown"""
    from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
    from magic_pdf.pipe.UNIPipe import UNIPipe

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "input.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir, exist_ok=True)
        image_dir = os.path.join(output_dir, "images")
        os.makedirs(image_dir, exist_ok=True)

        image_writer = FileBasedDataWriter(image_dir)
        md_writer = FileBasedDataWriter(output_dir)

        reader = FileBasedDataReader("")
        pdf_data = reader.read(pdf_path)

        model_json = []
        try:
            from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
            model_json = doc_analyze(pdf_data)
        except Exception as e:
            print(f"[magic-pdf] model analyze warning: {e}")

        pipe = UNIPipe(pdf_data, model_json, image_writer)
        pipe.pipe_classify()
        pipe.pipe_analyze()
        pipe.pipe_parse()

        md_content = pipe.pipe_mk_markdown("images", md_writer)
        if isinstance(md_content, bytes):
            md_content = md_content.decode("utf-8", errors="replace")

        content_list = pipe.pdf_mid_data.get("pdf_info", [])
        pages_output = []
        for i, page_info in enumerate(content_list):
            page_md = ""
            if isinstance(page_info, dict):
                page_md = page_info.get("md_content", "")
            pages_output.append({"page_number": i + 1, "markdown": page_md})

    if not pages_output:
        pages_output = [{"page_number": 1, "markdown": md_content}]

    metadata = _extract_metadata_from_markdown(md_content)

    return {
        "markdown": md_content,
        "pages": pages_output,
        "metadata": metadata,
        "parser_version": "magic-pdf-0.9",
        "elapsed_ms": 0,
    }


# ---------------------------------------------------------------------------
# PyMuPDF 回退解析
# ---------------------------------------------------------------------------

def _parse_with_pymupdf(pdf_bytes: bytes) -> dict:
    """PyMuPDF 结构化文本提取 — 当 magic-pdf 不可用时的 CPU 回退。"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_output = []
    full_markdown_parts = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        blocks = page.get_text("dict", sort=True).get("blocks", [])

        page_md_parts = []
        for block in blocks:
            if block.get("type") == 0:  # text block
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    text = "".join(s.get("text", "") for s in spans).strip()
                    if not text:
                        continue

                    avg_size = sum(s.get("size", 12) for s in spans) / len(spans)
                    is_bold = any(
                        "bold" in s.get("font", "").lower() for s in spans
                    )

                    if avg_size > 16 and is_bold:
                        page_md_parts.append(f"# {text}")
                    elif avg_size > 13 and is_bold:
                        page_md_parts.append(f"## {text}")
                    elif avg_size > 11 and is_bold:
                        page_md_parts.append(f"### {text}")
                    else:
                        page_md_parts.append(text)

        page_markdown = "\n\n".join(page_md_parts)
        pages_output.append(
            {"page_number": page_idx + 1, "markdown": page_markdown}
        )
        full_markdown_parts.append(page_markdown)

    doc.close()

    full_markdown = "\n\n".join(full_markdown_parts)
    metadata = _extract_metadata_from_markdown(full_markdown)

    return {
        "markdown": full_markdown,
        "pages": pages_output,
        "metadata": metadata,
        "parser_version": "pymupdf-structured-fallback",
        "elapsed_ms": 0,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_metadata_from_markdown(markdown: str) -> dict:
    """从 Markdown 中提取结构化元数据"""
    sections = []
    for m in re.finditer(r"^(#{1,3})\s+(.+)$", markdown, re.MULTILINE):
        level = len(m.group(1))
        title = m.group(2).strip()
        if title:
            sections.append({"title": title, "level": level})

    has_tables = bool(re.search(r"\|.+\|.+\|", markdown))
    has_formulas = bool(
        re.search(r"\$\$.+?\$\$", markdown, re.DOTALL)
        or re.search(r"(?<!\$)\$(?!\$).+?(?<!\$)\$(?!\$)", markdown)
    )
    has_figures = bool(re.search(r"!\[.*?\]\(.*?\)", markdown))

    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else None

    return {
        "title": title,
        "has_tables": has_tables,
        "has_formulas": has_formulas,
        "has_figures": has_figures,
        "section_titles": [s["title"] for s in sections],
    }


def _dispatch_parse(pdf_bytes: bytes) -> dict:
    """根据加载的后端选择解析方法"""
    if _backend == "magic_pdf":
        return _parse_with_magic_pdf(pdf_bytes)
    return _parse_with_pymupdf(pdf_bytes)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    gpu_mem = 0
    try:
        import torch
        if torch.cuda.is_available():
            gpu_mem = int(torch.cuda.mem_get_info()[1] / 1024 / 1024)
    except ImportError:
        pass

    return {
        "status": "ok",
        "model_loaded": _backend == "magic_pdf",
        "parse_backend": _backend,
        "gpu_memory_mb": gpu_mem,
    }


@app.post("/parse")
async def parse_pdf(request: Request, file: UploadFile = File(...)):
    _verify_api_key(request)

    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > config.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size_mb:.1f}MB > {config.MAX_FILE_SIZE_MB}MB limit",
        )

    if not _semaphore._value and _semaphore.locked():
        raise HTTPException(status_code=503, detail="Service busy, all slots occupied")

    try:
        async with _semaphore:
            start = time.time()
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, _dispatch_parse, content
                ),
                timeout=config.TASK_TIMEOUT_SEC,
            )
            result["elapsed_ms"] = int((time.time() - start) * 1000)
            return JSONResponse(content=result)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Parse timeout")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=config.BIND_HOST,
        port=config.BIND_PORT,
        workers=1,
    )
