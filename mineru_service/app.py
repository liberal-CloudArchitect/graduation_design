"""
MinerU PDF 解析服务 -- FastAPI wrapper

独立于主后端，通过 HTTP 提供 PDF → Markdown 解析能力。
部署到 4090 服务器，主后端通过 MinerUClient 调用。

解析后端优先级:
  1. official mineru package — 需要 GPU
  2. legacy magic-pdf package — 兼容旧镜像
  3. PyMuPDF 结构化提取 — CPU 回退
"""
import asyncio
import os
import re
import tempfile
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

import config

_semaphore: Optional[asyncio.Semaphore] = None
_backend = "none"  # "mineru_official" | "magic_pdf_legacy" | "pymupdf"
_backend_error: Optional[str] = None


def _release_gpu_cache():
    """Release unused GPU memory after each parse to prevent OOM on low-VRAM cards."""
    try:
        import gc
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _load_model() -> str:
    """尝试加载 MinerU 运行时。返回实际使用的后端名称。"""
    global _backend, _backend_error
    _backend_error = None

    try:
        from mineru.cli.common import do_parse
        from mineru.version import __version__

        _backend = "mineru_official"
        print(f"[startup] official mineru loaded successfully (version={__version__})")
        return _backend
    except Exception as e:
        _backend_error = f"{type(e).__name__}: {e}"

    try:
        from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
        from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
        from magic_pdf.pipe.UNIPipe import UNIPipe

        _backend = "magic_pdf_legacy"
        print("[startup] legacy magic-pdf loaded successfully")
        return _backend
    except Exception as e:
        _backend_error = f"{type(e).__name__}: {e}"

    _backend = "pymupdf"
    print(
        "[startup] mineru runtime unavailable or broken, using PyMuPDF fallback: "
        f"{_backend_error}"
    )
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
# Official MinerU 解析
# ---------------------------------------------------------------------------

def _resolve_parse_dir(output_dir: str, pdf_name: str) -> str:
    backend = config.MINERU_BACKEND
    if backend == "pipeline":
        subdir = config.MINERU_PARSE_METHOD
    elif backend.startswith("vlm-"):
        subdir = "vlm"
    elif backend.startswith("hybrid-"):
        subdir = f"hybrid_{config.MINERU_PARSE_METHOD}"
    else:
        raise RuntimeError(f"Unsupported MINERU_BACKEND: {backend}")
    return os.path.join(output_dir, pdf_name, subdir)


def _content_item_to_markdown(item: Dict[str, Any]) -> str:
    item_type = str(item.get("type", "") or "").lower()

    if item_type == "table":
        return str(item.get("table_body") or item.get("content") or "").strip()
    if item_type == "list":
        list_items = item.get("list_items")
        if isinstance(list_items, list) and list_items:
            return "\n".join(f"- {str(entry).strip()}" for entry in list_items if str(entry).strip())
        return str(item.get("content") or "").strip()
    if item_type == "title":
        level = int(item.get("text_level") or 1)
        text = str(item.get("text") or item.get("content") or "").strip()
        return f"{'#' * max(1, min(level, 3))} {text}" if text else ""
    if item_type in {"header", "footer", "page_number"}:
        return ""

    text = str(item.get("text") or item.get("content") or "").strip()
    if not text:
        return ""

    if item_type in {"equation", "formula"}:
        return f"$$\n{text}\n$$"

    return text


def _pages_from_content_list(content_list: List[Dict[str, Any]], page_count: int) -> List[Dict[str, Any]]:
    if page_count <= 0:
        page_count = 1

    grouped: List[List[str]] = [[] for _ in range(page_count)]
    for item in content_list:
        try:
            page_idx = int(item.get("page_idx", 0))
        except Exception:
            page_idx = 0
        if page_idx < 0:
            page_idx = 0
        if page_idx >= page_count:
            grouped.extend([[] for _ in range(page_idx - page_count + 1)])
            page_count = len(grouped)
        md = _content_item_to_markdown(item)
        if md:
            grouped[page_idx].append(md)

    pages_output = []
    for idx, parts in enumerate(grouped):
        pages_output.append(
            {
                "page_number": idx + 1,
                "markdown": "\n\n".join(parts).strip(),
            }
        )
    return pages_output


def _parse_with_official_mineru(pdf_bytes: bytes) -> dict:
    """使用官方 mineru 包进行解析。"""
    from mineru.cli.common import do_parse
    from mineru.version import __version__

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_name = "input"
        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir, exist_ok=True)

        parse_kwargs: Dict[str, Any] = {}
        if config.MINERU_SERVER_URL:
            parse_kwargs["server_url"] = config.MINERU_SERVER_URL

        do_parse(
            output_dir=output_dir,
            pdf_file_names=[pdf_name],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=[config.MINERU_LANG],
            backend=config.MINERU_BACKEND,
            parse_method=config.MINERU_PARSE_METHOD,
            formula_enable=True,
            table_enable=True,
            f_draw_layout_bbox=False,
            f_draw_span_bbox=False,
            f_dump_md=True,
            f_dump_middle_json=True,
            f_dump_model_output=False,
            f_dump_orig_pdf=False,
            f_dump_content_list=True,
            **parse_kwargs,
        )

        parse_dir = _resolve_parse_dir(output_dir, pdf_name)
        markdown_path = os.path.join(parse_dir, f"{pdf_name}.md")
        content_list_path = os.path.join(parse_dir, f"{pdf_name}_content_list.json")

        if not os.path.exists(markdown_path):
            raise RuntimeError(f"MinerU output markdown not found: {markdown_path}")

        with open(markdown_path, "r", encoding="utf-8") as f:
            md_content = f.read()

        content_list: List[Dict[str, Any]] = []
        if os.path.exists(content_list_path):
            import json

            with open(content_list_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                content_list = loaded

    try:
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = pdf_doc.page_count
        pdf_doc.close()
    except Exception:
        page_count = max((int(item.get("page_idx", 0)) + 1 for item in content_list), default=1)

    pages_output = _pages_from_content_list(content_list, page_count)
    if not any(p.get("markdown") for p in pages_output):
        pages_output = [{"page_number": 1, "markdown": md_content}]

    metadata = _extract_metadata_from_markdown(md_content)

    return {
        "markdown": md_content,
        "pages": pages_output,
        "metadata": metadata,
        "parser_version": f"mineru-{__version__}",
        "elapsed_ms": 0,
    }


# ---------------------------------------------------------------------------
# legacy magic-pdf 解析
# ---------------------------------------------------------------------------

def _parse_with_legacy_magic_pdf(pdf_bytes: bytes) -> dict:
    """兼容旧版 magic-pdf 私有模块。"""
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
        "parser_version": "magic-pdf-legacy",
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
    global _backend, _backend_error
    if _backend == "mineru_official":
        try:
            return _parse_with_official_mineru(pdf_bytes)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if any(
                token in msg
                for token in (
                    "mineru",
                    "magic_pdf",
                    "magic-pdf",
                    "UNIPipe",
                    "doc_analyze",
                    "libs.commons",
                )
            ):
                _backend = "pymupdf"
                _backend_error = msg
                print(
                    "[runtime] official mineru parse path failed, "
                    f"switching to PyMuPDF fallback: {msg}"
                )
                return _parse_with_pymupdf(pdf_bytes)
            raise
    if _backend == "magic_pdf_legacy":
        try:
            return _parse_with_legacy_magic_pdf(pdf_bytes)
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if any(
                token in msg
                for token in (
                    "magic_pdf",
                    "magic-pdf",
                    "UNIPipe",
                    "doc_analyze",
                    "libs.commons",
                )
            ):
                _backend = "pymupdf"
                _backend_error = msg
                print(
                    "[runtime] legacy magic-pdf parse path failed, "
                    f"switching to PyMuPDF fallback: {msg}"
                )
                return _parse_with_pymupdf(pdf_bytes)
            raise
    return _parse_with_pymupdf(pdf_bytes)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    gpu_mem = 0
    gpu_used = 0
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            gpu_mem = int(total / 1024 / 1024)
            gpu_used = int((total - free) / 1024 / 1024)
    except ImportError:
        pass

    vllm_healthy = False
    if config.MINERU_SERVER_URL:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{config.MINERU_SERVER_URL}/health")
                vllm_healthy = resp.status_code == 200
        except Exception:
            pass

    return {
        "status": "ok",
        "model_loaded": _backend != "pymupdf",
        "parse_backend": _backend,
        "configured_backend": config.MINERU_BACKEND,
        "configured_lang": config.MINERU_LANG,
        "model_source": config.MINERU_MODEL_SOURCE,
        "gpu_memory_total_mb": gpu_mem,
        "gpu_memory_used_mb": gpu_used,
        "vllm_server_url": config.MINERU_SERVER_URL or None,
        "vllm_healthy": vllm_healthy,
        "backend_error": _backend_error,
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
            _release_gpu_cache()
            return JSONResponse(content=result)
    except asyncio.TimeoutError:
        _release_gpu_cache()
        raise HTTPException(status_code=504, detail="Parse timeout")
    except HTTPException:
        _release_gpu_cache()
        raise
    except Exception as e:
        _release_gpu_cache()
        raise HTTPException(status_code=400, detail=f"Parse failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=config.BIND_HOST,
        port=config.BIND_PORT,
        workers=1,
    )
