"""
MinerU PDF 解析服务 -- FastAPI wrapper

独立于主后端，通过 HTTP 提供 PDF → Markdown 解析能力。
部署到 GPU 服务器 (Docker)，主后端通过 MinerUClient 调用。

三级降级策略:
  Tier 1: hybrid-http-client — VLM (vLLM GPU) + pipeline 模型 (CPU/GPU)
  Tier 2: pipeline-only      — 仅 pipeline 模型，不调用 VLM
  Tier 3: PyMuPDF             — 纯 CPU 文本提取
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
_state_lock: Optional[asyncio.Lock] = None
_backend = "none"  # "mineru_official" | "magic_pdf_legacy" | "pymupdf"
_backend_error: Optional[str] = None
_active_jobs = 0
_waiting_jobs = 0


def _release_gpu_cache():
    """Release unused GPU memory after each parse to prevent OOM on low-VRAM cards."""
    try:
        import gc
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
    except Exception:
        pass


def _configure_pipeline_device():
    """Update magic-pdf.json so pipeline models run on the configured device.

    When PIPELINE_DEVICE=cpu, layout/OCR/formula/table models use system RAM
    instead of GPU VRAM, leaving the GPU exclusively for vLLM.
    """
    import json as _json

    config_path = os.path.expanduser("~/magic-pdf.json")
    if not os.path.exists(config_path):
        print(f"[startup] magic-pdf.json not found at {config_path}, skipping device config")
        return

    try:
        with open(config_path) as f:
            cfg = _json.load(f)
        current = cfg.get("device-mode", "unknown")
        target = config.PIPELINE_DEVICE
        if current != target:
            cfg["device-mode"] = target
            with open(config_path, "w") as f:
                _json.dump(cfg, f, indent=2)
            print(f"[startup] pipeline device-mode: {current} -> {target}")
        else:
            print(f"[startup] pipeline device-mode: {current} (unchanged)")
    except Exception as e:
        print(f"[startup] WARNING: failed to update magic-pdf.json: {e}")


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
    global _semaphore, _state_lock
    _semaphore = asyncio.Semaphore(config.MAX_CONCURRENT)
    _state_lock = asyncio.Lock()
    _configure_pipeline_device()
    _load_model()
    yield


app = FastAPI(title="MinerU PDF Parse Service", lifespan=lifespan)


def _verify_api_key(request: Request):
    if not config.API_KEY:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {config.API_KEY}":
        raise HTTPException(status_code=401, detail="Invalid API key")


def _is_cuda_oom_error(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    return any(
        token in message
        for token in (
            "cuda out of memory",
            "outofmemoryerror",
            "cublas_status_alloc_failed",
            "cuda error: out of memory",
            "hip out of memory",
        )
    )


_RECOVERABLE_ERROR_TOKENS = (
    # VLM / vLLM connection failures
    "connection attempts failed",
    "connection refused",
    "connection reset",
    "server disconnected",
    "remoteprotocolerror",
    "connecterror",
    "readtimeout",
    "writetimeout",
    "connectionerror",
    "httpcore",
    # MinerU / magic-pdf internal errors
    "mineru",
    "magic_pdf",
    "magic-pdf",
    "unipipe",
    "doc_analyze",
    "libs.commons",
    # Generic CUDA/GPU errors (non-OOM ones are also recoverable)
    "cuda error",
    "cudnn error",
    "nccl error",
    "device-side assert",
)


def _is_recoverable_parse_error(exc: Exception) -> bool:
    """Return True if *exc* should trigger fallback to a simpler backend."""
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(token in msg for token in _RECOVERABLE_ERROR_TOKENS)


def _check_vllm_health_sync() -> bool:
    """Quick sync probe — is the vLLM server still responding?"""
    if not config.MINERU_SERVER_URL:
        return False
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{config.MINERU_SERVER_URL}/health", method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _current_gpu_memory() -> Dict[str, int]:
    info = {
        "total_mb": 0,
        "used_mb": 0,
        "free_mb": 0,
    }
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            info["total_mb"] = int(total / 1024 / 1024)
            info["free_mb"] = int(free / 1024 / 1024)
            info["used_mb"] = int((total - free) / 1024 / 1024)
    except Exception:
        pass
    return info


def _should_fallback_to_cpu_due_to_gpu_pressure() -> Optional[str]:
    if not config.GPU_PRESSURE_CPU_FALLBACK:
        return None
    if _backend == "pymupdf":
        return None

    gpu = _current_gpu_memory()
    if gpu["total_mb"] <= 0:
        return None
    if gpu["free_mb"] < config.GPU_MIN_FREE_MB:
        return (
            f"gpu_pressure_free_{gpu['free_mb']}mb_below_{config.GPU_MIN_FREE_MB}mb"
        )
    return None


# ---------------------------------------------------------------------------
# Official MinerU 解析
# ---------------------------------------------------------------------------

def _resolve_parse_dir(output_dir: str, pdf_name: str, backend: str | None = None) -> str:
    if backend is None:
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


def _parse_with_official_mineru(pdf_bytes: bytes, backend: str | None = None) -> dict:
    """使用官方 mineru 包进行解析。*backend* 可覆盖 config 默认值。"""
    from mineru.cli.common import do_parse
    from mineru.version import __version__

    if backend is None:
        backend = config.MINERU_BACKEND

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_name = "input"
        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir, exist_ok=True)

        parse_kwargs: Dict[str, Any] = {}
        if config.MINERU_SERVER_URL and "hybrid" in backend:
            parse_kwargs["server_url"] = config.MINERU_SERVER_URL

        do_parse(
            output_dir=output_dir,
            pdf_file_names=[pdf_name],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=[config.MINERU_LANG],
            backend=backend,
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

        parse_dir = _resolve_parse_dir(output_dir, pdf_name, backend)
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
    """Three-tier fallback: hybrid → pipeline-only → PyMuPDF.

    Unlike the old implementation this does NOT permanently downgrade
    ``_backend`` for transient VLM failures.  Each request starts from
    the best available tier so that a recovered vLLM server is used
    immediately.
    """
    global _backend, _backend_error

    if _backend == "mineru_official":
        configured = config.MINERU_BACKEND  # e.g. "hybrid-http-client"
        is_hybrid = "hybrid" in configured

        # -- Tier 1: configured backend (hybrid-http-client) ---------------
        # Quick-check: if vLLM is known dead, skip straight to tier 2.
        if is_hybrid and not _check_vllm_health_sync():
            print("[fallback] vLLM server unreachable, skipping tier-1")
        else:
            try:
                return _parse_with_official_mineru(pdf_bytes)
            except Exception as e:
                tier1_err = f"{type(e).__name__}: {e}"
                recoverable = (
                    _is_recoverable_parse_error(e) or _is_cuda_oom_error(e)
                )
                if not recoverable:
                    raise
                print(f"[fallback] tier-1 ({configured}) failed: {tier1_err}")
                _release_gpu_cache()

        # -- Tier 2: pipeline-only (MinerU without VLM) --------------------
        if config.PIPELINE_FALLBACK_ENABLED and is_hybrid:
            try:
                print("[fallback] trying tier-2: pipeline-only backend")
                result = _parse_with_official_mineru(
                    pdf_bytes, backend="pipeline",
                )
                result["metadata"]["fallback_reason"] = "vlm_unavailable_pipeline"
                return result
            except Exception as e2:
                print(f"[fallback] tier-2 (pipeline) failed: {e2}")
                _release_gpu_cache()

        # -- Tier 3: PyMuPDF CPU extraction --------------------------------
        print("[fallback] tier-3: PyMuPDF CPU extraction")
        _backend_error = "all_gpu_backends_failed"
        result = _parse_with_pymupdf(pdf_bytes)
        result["metadata"]["fallback_reason"] = "all_backends_failed_pymupdf"
        return result

    if _backend == "magic_pdf_legacy":
        try:
            return _parse_with_legacy_magic_pdf(pdf_bytes)
        except Exception as e:
            if _is_recoverable_parse_error(e) or _is_cuda_oom_error(e):
                _backend = "pymupdf"
                _backend_error = f"{type(e).__name__}: {e}"
                print(
                    "[fallback] magic-pdf failed, using PyMuPDF: "
                    f"{_backend_error}"
                )
                _release_gpu_cache()
                return _parse_with_pymupdf(pdf_bytes)
            raise

    return _parse_with_pymupdf(pdf_bytes)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    gpu = _current_gpu_memory()

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
        "pipeline_device": config.PIPELINE_DEVICE,
        "pipeline_fallback_enabled": config.PIPELINE_FALLBACK_ENABLED,
        "gpu_memory_total_mb": gpu["total_mb"],
        "gpu_memory_used_mb": gpu["used_mb"],
        "gpu_memory_free_mb": gpu["free_mb"],
        "active_jobs": _active_jobs,
        "waiting_jobs": _waiting_jobs,
        "max_concurrent": config.MAX_CONCURRENT,
        "max_queue_size": config.MAX_QUEUE_SIZE,
        "cpu_overflow_fallback": config.ENABLE_CPU_OVERFLOW_FALLBACK,
        "gpu_min_free_mb": config.GPU_MIN_FREE_MB,
        "vllm_server_url": config.MINERU_SERVER_URL or None,
        "vllm_healthy": vllm_healthy,
        "backend_error": _backend_error,
    }


@app.post("/parse")
async def parse_pdf(request: Request, file: UploadFile = File(...)):
    global _active_jobs, _waiting_jobs
    _verify_api_key(request)

    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > config.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size_mb:.1f}MB > {config.MAX_FILE_SIZE_MB}MB limit",
        )

    if _semaphore is None or _state_lock is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    queued = False
    acquired_slot = False
    overflow_to_cpu = False

    async with _state_lock:
        if _active_jobs >= config.MAX_CONCURRENT or _semaphore.locked():
            if config.MAX_QUEUE_SIZE >= 0 and _waiting_jobs >= config.MAX_QUEUE_SIZE:
                overflow_to_cpu = config.ENABLE_CPU_OVERFLOW_FALLBACK
                if not overflow_to_cpu:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Service busy, queue is full; "
                            "increase MAX_QUEUE_SIZE or enable CPU overflow fallback"
                        ),
                    )
            else:
                _waiting_jobs += 1
                queued = True

    try:
        start = time.time()

        if overflow_to_cpu:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, _parse_with_pymupdf, content
                ),
                timeout=config.TASK_TIMEOUT_SEC,
            )
            result["metadata"]["fallback_reason"] = "queue_full_cpu_fallback"
            result["metadata"]["queue_overflow"] = True
            result["elapsed_ms"] = int((time.time() - start) * 1000)
            return JSONResponse(content=result)

        await _semaphore.acquire()
        acquired_slot = True

        async with _state_lock:
            if queued and _waiting_jobs > 0:
                _waiting_jobs -= 1
            _active_jobs += 1

        fallback_reason = _should_fallback_to_cpu_due_to_gpu_pressure()
        parse_target = _parse_with_pymupdf if fallback_reason else _dispatch_parse

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, parse_target, content
                ),
                timeout=config.TASK_TIMEOUT_SEC,
            )
            if fallback_reason:
                result["metadata"]["fallback_reason"] = fallback_reason
        except Exception as e:
            if config.CUDA_OOM_CPU_FALLBACK and _is_cuda_oom_error(e):
                _release_gpu_cache()
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, _parse_with_pymupdf, content
                    ),
                    timeout=config.TASK_TIMEOUT_SEC,
                )
                result["metadata"]["fallback_reason"] = "cuda_oom_cpu_fallback"
            else:
                raise

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
    finally:
        if acquired_slot:
            async with _state_lock:
                if _active_jobs > 0:
                    _active_jobs -= 1
            _semaphore.release()
        elif queued:
            async with _state_lock:
                if _waiting_jobs > 0:
                    _waiting_jobs -= 1


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=config.BIND_HOST,
        port=config.BIND_PORT,
        workers=1,
    )
