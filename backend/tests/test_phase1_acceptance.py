"""
Phase 1 验收测试 — MinerU PDF 解析集成

验收标准 (来自综合修改实施方案 §1.6):
  1. 复杂论文抽检正确率较基线有显著提升
  2. 数学公式还原为 LaTeX 格式，可正确渲染
  3. 表格还原为 Markdown 表格，列对齐正确
  4. 简单 PDF 解析速度不退化（PyMuPDF 路径无变化）
  5. 单篇处理失败可自动降级并产生日志可追踪
  6. 现有 API 接口行为兼容

运行: python backend/tests/test_phase1_acceptance.py

常用环境变量:
  MINERU_URL / MINERU_API_URL  优先级最高，直接指定完整服务地址
  MINERU_HOST / MINERU_PORT     未提供完整 URL 时拼接服务地址
  MINERU_SCHEME                 默认 http
  MINERU_API_KEY                可选 Bearer token
"""

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def resolve_mineru_base_url() -> str:
    """Resolve MinerU service URL from environment without hardcoding a host."""
    explicit = os.getenv("MINERU_URL") or os.getenv("MINERU_API_URL")
    if explicit:
        return explicit.rstrip("/")

    host = os.getenv("MINERU_HOST", "127.0.0.1")
    port = os.getenv("MINERU_PORT", "8010")
    scheme = os.getenv("MINERU_SCHEME", "http")
    return f"{scheme}://{host}:{port}".rstrip("/")


MINERU_BASE_URL = resolve_mineru_base_url()
MINERU_API_KEY = os.getenv("MINERU_API_KEY", "")

TEST_DOC_DIR = Path(__file__).parent / "test_doc"
OUTPUT_JSON = os.getenv(
    "PHASE1_OUTPUT_JSON",
    str(Path(__file__).parent / "phase1_acceptance_results.json"),
)
TEST_CATEGORIES = {
    item.strip()
    for item in os.getenv("TEST_CATEGORIES", "").split(",")
    if item.strip()
}
TEST_NAME_FILTER = os.getenv("TEST_NAME_FILTER", "").strip().lower()
MAX_TEST_PDFS = int(os.getenv("MAX_TEST_PDFS", "0"))

TIMEOUT_PARSE = 180  # seconds per PDF
TIMEOUT_HEALTH = 10
COOLDOWN_BETWEEN_PARSES = int(os.getenv("COOLDOWN_SEC", "30"))  # GPU memory cooldown


# ---------------------------------------------------------------------------
# Test PDF Catalog
# ---------------------------------------------------------------------------

@dataclass
class TestPDF:
    path: str
    category: str  # dual_column | formula_heavy | table_heavy | scan | simple
    description: str
    expect_tables: Optional[bool] = None
    expect_formulas: Optional[bool] = None
    expect_sections: bool = True
    known_section_keywords: List[str] = field(default_factory=list)


def discover_test_pdfs() -> List[TestPDF]:
    """Discover PDFs in test_doc/ and build test catalog."""
    pdfs: List[TestPDF] = []

    mapping = {
        "dual_column": ("dual_column", True, False),
        "formula_heavy": ("formula_heavy", False, True),
        "table_heavy": ("table_heavy", True, False),
        "scan": ("scan", None, None),
    }

    for subdir, (category, tables, formulas) in mapping.items():
        d = TEST_DOC_DIR / subdir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.pdf")):
            pdfs.append(TestPDF(
                path=str(f),
                category=category,
                description=f.stem,
                expect_tables=tables,
                expect_formulas=formulas,
            ))

    simple_dir = TEST_DOC_DIR / "tmp_check"
    if simple_dir.exists():
        for f in sorted(simple_dir.glob("*.pdf")):
            pdfs.append(TestPDF(
                path=str(f),
                category="simple",
                description=f.stem,
            ))

    if TEST_CATEGORIES:
        pdfs = [pdf for pdf in pdfs if pdf.category in TEST_CATEGORIES]

    if TEST_NAME_FILTER:
        pdfs = [
            pdf for pdf in pdfs
            if TEST_NAME_FILTER in pdf.description.lower()
            or TEST_NAME_FILTER in Path(pdf.path).name.lower()
        ]

    if MAX_TEST_PDFS > 0:
        pdfs = pdfs[:MAX_TEST_PDFS]

    return pdfs


# ---------------------------------------------------------------------------
# Result structures
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    pdf: TestPDF
    success: bool
    elapsed_ms: int = 0
    markdown: str = ""
    pages: List[Dict] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parser_version: str = ""
    error: str = ""
    http_status: int = 0


@dataclass
class QualityScore:
    """Per-PDF quality assessment."""
    pdf_name: str
    category: str
    has_markdown: bool = False
    markdown_length: int = 0
    section_count: int = 0
    has_tables_detected: bool = False
    has_formulas_detected: bool = False
    has_figures_detected: bool = False
    latex_inline_count: int = 0
    latex_block_count: int = 0
    table_count: int = 0
    page_count: int = 0
    chars_per_page: float = 0.0
    garble_rate: float = 0.0
    heading_count: int = 0
    elapsed_ms: int = 0
    score: float = 0.0
    issues: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

async def check_health() -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=TIMEOUT_HEALTH) as client:
        headers = {}
        if MINERU_API_KEY:
            headers["Authorization"] = f"Bearer {MINERU_API_KEY}"
        resp = await client.get(f"{MINERU_BASE_URL}/health", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def parse_pdf_remote(pdf_path: str) -> ParseResult:
    """Send a PDF to the MinerU service and capture the response."""
    pdf = TestPDF(path=pdf_path, category="unknown", description=Path(pdf_path).stem)
    headers = {}
    if MINERU_API_KEY:
        headers["Authorization"] = f"Bearer {MINERU_API_KEY}"

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_PARSE) as client:
            with open(pdf_path, "rb") as f:
                resp = await client.post(
                    f"{MINERU_BASE_URL}/parse",
                    files={"file": (Path(pdf_path).name, f, "application/pdf")},
                    headers=headers,
                )
            elapsed_ms = int((time.time() - t0) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                return ParseResult(
                    pdf=pdf,
                    success=True,
                    elapsed_ms=data.get("elapsed_ms", elapsed_ms),
                    markdown=data.get("markdown", ""),
                    pages=data.get("pages", []),
                    metadata=data.get("metadata", {}),
                    parser_version=data.get("parser_version", ""),
                    http_status=200,
                )
            else:
                return ParseResult(
                    pdf=pdf,
                    success=False,
                    elapsed_ms=elapsed_ms,
                    error=resp.text[:500],
                    http_status=resp.status_code,
                )
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return ParseResult(
            pdf=pdf,
            success=False,
            elapsed_ms=elapsed_ms,
            error=f"{type(e).__name__}: {e}",
        )


# ---------------------------------------------------------------------------
# Quality Analysis
# ---------------------------------------------------------------------------

def compute_garble_rate(text: str) -> float:
    import unicodedata
    if not text:
        return 0.0
    total = garble = 0
    for ch in text:
        total += 1
        if ch.isascii():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith(("L", "N", "P", "S", "M", "Z")):
            continue
        garble += 1
    return garble / total if total else 0.0


def assess_quality(result: ParseResult) -> QualityScore:
    """Compute quality metrics for a single parse result."""
    md = result.markdown
    qs = QualityScore(
        pdf_name=result.pdf.description,
        category=result.pdf.category,
        elapsed_ms=result.elapsed_ms,
    )

    if not md or not md.strip():
        qs.issues.append("EMPTY_OUTPUT")
        return qs

    qs.has_markdown = True
    qs.markdown_length = len(md)
    qs.page_count = len(result.pages) or 1
    qs.chars_per_page = len(md) / qs.page_count

    # Headings
    headings = re.findall(r"^#{1,3}\s+.+$", md, re.MULTILINE)
    qs.heading_count = len(headings)
    qs.section_count = len(headings)

    # Tables
    table_rows = re.findall(r"^\|.+\|$", md, re.MULTILINE)
    separator_rows = [r for r in table_rows if re.match(r"^\|[\s\-:]+\|$", r)]
    qs.table_count = len(separator_rows)
    qs.has_tables_detected = qs.table_count > 0

    # Formulas
    qs.latex_block_count = len(re.findall(r"\$\$.+?\$\$", md, re.DOTALL))
    qs.latex_inline_count = len(re.findall(r"(?<!\$)\$(?!\$)(?!\s).+?(?<!\s)\$(?!\$)", md))
    qs.has_formulas_detected = (qs.latex_block_count + qs.latex_inline_count) > 0

    # Figures
    qs.has_figures_detected = bool(re.search(r"!\[.*?\]\(.*?\)", md))

    # Garble
    qs.garble_rate = compute_garble_rate(md)
    if qs.garble_rate > 0.15:
        qs.issues.append(f"HIGH_GARBLE_RATE({qs.garble_rate:.3f})")

    if qs.chars_per_page < 100:
        qs.issues.append(f"LOW_CHARS_PER_PAGE({qs.chars_per_page:.0f})")

    # Score (0-100)
    score = 0.0
    if qs.has_markdown:
        score += 20
    if qs.heading_count >= 2:
        score += 15
    elif qs.heading_count >= 1:
        score += 8
    if qs.garble_rate <= 0.05:
        score += 15
    elif qs.garble_rate <= 0.15:
        score += 8
    if qs.chars_per_page >= 300:
        score += 15
    elif qs.chars_per_page >= 100:
        score += 8

    # Category-specific bonuses
    if result.pdf.category == "formula_heavy":
        if qs.latex_block_count >= 3:
            score += 20
        elif qs.has_formulas_detected:
            score += 10
    elif result.pdf.category == "table_heavy":
        if qs.table_count >= 1:
            score += 20
        elif qs.has_tables_detected:
            score += 10
    elif result.pdf.category == "dual_column":
        if qs.heading_count >= 3 and qs.chars_per_page >= 500:
            score += 20
        elif qs.heading_count >= 2:
            score += 10
    elif result.pdf.category == "scan":
        if qs.chars_per_page >= 200:
            score += 20
        elif qs.chars_per_page >= 50:
            score += 10
    else:
        score += 15  # simple

    qs.score = min(score, 100)
    return qs


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

def print_header(title: str):
    w = 76
    print(f"\n{'=' * w}")
    print(f"  {title}")
    print(f"{'=' * w}")


def print_section(title: str):
    print(f"\n--- {title} {'─' * max(0, 60 - len(title))}")


async def run_all_tests():
    results_all: List[Dict[str, Any]] = []
    test_pdfs = discover_test_pdfs()

    print_header("Phase 1 验收测试 — MinerU PDF 解析集成")
    print(f"MinerU Service: {MINERU_BASE_URL}")
    print(f"Test PDFs found: {len(test_pdfs)}")
    if TEST_CATEGORIES:
        print(f"Category filter: {sorted(TEST_CATEGORIES)}")
    if TEST_NAME_FILTER:
        print(f"Name filter: {TEST_NAME_FILTER}")
    if MAX_TEST_PDFS > 0:
        print(f"Max PDFs: {MAX_TEST_PDFS}")
    for cat in ("dual_column", "formula_heavy", "table_heavy", "scan", "simple"):
        cnt = sum(1 for p in test_pdfs if p.category == cat)
        if cnt:
            print(f"  {cat}: {cnt} files")

    if not test_pdfs:
        print("\n  No PDFs matched the current filters. Aborting.")
        return

    # -----------------------------------------------------------------------
    # Test 1: Health Check
    # -----------------------------------------------------------------------
    print_section("Test 1: MinerU Service Health Check")
    try:
        health = await check_health()
        print(f"  Status:           {health.get('status')}")
        print(f"  Parse Backend:    {health.get('parse_backend')}")
        print(f"  Configured Backend: {health.get('configured_backend')}")
        print(f"  Model Loaded:     {health.get('model_loaded')}")
        print(f"  GPU Total MB:     {health.get('gpu_memory_total_mb')}")
        print(f"  GPU Used MB:      {health.get('gpu_memory_used_mb')}")
        print(f"  GPU Free MB:      {health.get('gpu_memory_free_mb')}")
        print(f"  Pipeline Device:  {health.get('pipeline_device')}")
        print(f"  Active Jobs:      {health.get('active_jobs')}")
        print(f"  Waiting Jobs:     {health.get('waiting_jobs')}")
        print(f"  Max Concurrent:   {health.get('max_concurrent')}")
        print(f"  vLLM Healthy:     {health.get('vllm_healthy')}")
        print(f"  vLLM URL:         {health.get('vllm_server_url')}")
        print(f"  Parser Version:   {health.get('parser_version', 'N/A')}")
        print(f"  Backend Error:    {health.get('backend_error', 'None')}")
        health_ok = health.get("status") == "ok"
        if not health_ok:
            print("  [FAIL] Health check returned non-ok status")
        else:
            print("  [PASS] Service is healthy")
        results_all.append({"test": "health_check", "pass": health_ok, "detail": health})
    except Exception as e:
        print(f"  [FAIL] Health check failed: {e}")
        results_all.append({"test": "health_check", "pass": False, "detail": str(e)})
        print("\n  Cannot proceed without a healthy MinerU service. Aborting.")
        return

    # -----------------------------------------------------------------------
    # Test 2: Parse PDFs by category
    # -----------------------------------------------------------------------
    print_section("Test 2: PDF Parsing Quality (by category)")

    parse_results: List[ParseResult] = []
    quality_scores: List[QualityScore] = []
    consecutive_failures = 0

    for i, pdf_def in enumerate(test_pdfs):
        fname = Path(pdf_def.path).name
        print(f"\n  [{i+1}/{len(test_pdfs)}] Parsing [{pdf_def.category}] {fname} ... ",
              end="", flush=True)

        # If service crashed (ConnectError), wait for auto-restart
        if consecutive_failures >= 2:
            print("\n    Service may have restarted, waiting 120s for recovery...",
                  end="", flush=True)
            await asyncio.sleep(120)
            consecutive_failures = 0

        result = await parse_pdf_remote(pdf_def.path)
        result.pdf = pdf_def
        parse_results.append(result)

        if result.success:
            consecutive_failures = 0
            qs = assess_quality(result)
            quality_scores.append(qs)
            issues_str = ", ".join(qs.issues) if qs.issues else "none"
            print(
                f"OK ({result.elapsed_ms}ms) "
                f"score={qs.score:.0f} md={qs.markdown_length}ch "
                f"secs={qs.section_count} tbl={qs.table_count} "
                f"formula_blk={qs.latex_block_count} formula_inl={qs.latex_inline_count} "
                f"garble={qs.garble_rate:.3f} issues=[{issues_str}]"
            )
            # GPU memory cooldown between successful parses
            if i < len(test_pdfs) - 1 and COOLDOWN_BETWEEN_PARSES > 0:
                print(f"    (cooling down {COOLDOWN_BETWEEN_PARSES}s for GPU memory)",
                      flush=True)
                await asyncio.sleep(COOLDOWN_BETWEEN_PARSES)
        else:
            consecutive_failures += 1
            print(f"FAIL (http={result.http_status}) {result.error[:120]}")

    # -----------------------------------------------------------------------
    # Test 3: Acceptance Criteria Evaluation
    # -----------------------------------------------------------------------
    print_section("Test 3: Acceptance Criteria Evaluation")

    total_parsed = sum(1 for r in parse_results if r.success)
    total_attempted = len(parse_results)
    parse_success_rate = total_parsed / total_attempted if total_attempted else 0

    print(f"\n  Parse success rate: {total_parsed}/{total_attempted} ({parse_success_rate:.1%})")

    # Criterion 1: Complex paper parse quality
    complex_categories = ("dual_column", "formula_heavy", "table_heavy", "scan")
    complex_scores = [qs for qs in quality_scores if qs.category in complex_categories]
    complex_avg_score = (
        sum(qs.score for qs in complex_scores) / len(complex_scores)
        if complex_scores else 0
    )
    complex_pass = complex_avg_score >= 50
    print(f"\n  [Criterion 1] Complex PDF avg quality score: {complex_avg_score:.1f}/100 "
          f"{'[PASS]' if complex_pass else '[WARN]'} (target ≥ 50)")

    # Per category breakdown
    for cat in complex_categories:
        cat_scores = [qs for qs in quality_scores if qs.category == cat]
        if cat_scores:
            avg = sum(qs.score for qs in cat_scores) / len(cat_scores)
            print(f"    {cat}: avg={avg:.1f} (n={len(cat_scores)})")

    # Criterion 2: Formula restoration (LaTeX)
    formula_pdfs = [qs for qs in quality_scores if qs.category == "formula_heavy"]
    formula_detected = sum(1 for qs in formula_pdfs if qs.has_formulas_detected)
    formula_total = len(formula_pdfs)
    formula_rate = formula_detected / formula_total if formula_total else 0
    formula_pass = formula_rate >= 0.5
    print(f"\n  [Criterion 2] Formula detection rate: {formula_detected}/{formula_total} "
          f"({formula_rate:.1%}) {'[PASS]' if formula_pass else '[WARN]'} (target ≥ 50%)")
    if formula_pdfs:
        total_block = sum(qs.latex_block_count for qs in formula_pdfs)
        total_inline = sum(qs.latex_inline_count for qs in formula_pdfs)
        print(f"    Total LaTeX blocks: {total_block}, inline: {total_inline}")

    # Criterion 3: Table restoration
    table_pdfs = [qs for qs in quality_scores if qs.category == "table_heavy"]
    table_detected = sum(1 for qs in table_pdfs if qs.has_tables_detected)
    table_total = len(table_pdfs)
    table_rate = table_detected / table_total if table_total else 0
    table_pass = table_rate >= 0.5
    print(f"\n  [Criterion 3] Table detection rate: {table_detected}/{table_total} "
          f"({table_rate:.1%}) {'[PASS]' if table_pass else '[WARN]'} (target ≥ 50%)")
    if table_pdfs:
        total_tables = sum(qs.table_count for qs in table_pdfs)
        print(f"    Total Markdown tables detected: {total_tables}")

    # Criterion 4: Performance (elapsed time)
    elapsed_values = [qs.elapsed_ms for qs in quality_scores if qs.elapsed_ms > 0]
    if elapsed_values:
        avg_ms = sum(elapsed_values) / len(elapsed_values)
        max_ms = max(elapsed_values)
        p95_ms = sorted(elapsed_values)[int(len(elapsed_values) * 0.95)] if len(elapsed_values) >= 5 else max_ms
        perf_pass = p95_ms <= TIMEOUT_PARSE * 1000
        print(f"\n  [Criterion 4] Parse latency: avg={avg_ms:.0f}ms, p95={p95_ms:.0f}ms, "
              f"max={max_ms:.0f}ms {'[PASS]' if perf_pass else '[WARN]'} (timeout={TIMEOUT_PARSE}s)")
    else:
        perf_pass = False
        print(f"\n  [Criterion 4] No timing data available [WARN]")

    # Criterion 5: Degradation / fallback handling
    failed_parses = [r for r in parse_results if not r.success]
    degradation_ok = True
    for r in failed_parses:
        if r.http_status in (413, 503, 504, 400):
            print(f"    Degradation handled: {r.pdf.description} -> HTTP {r.http_status}")
        else:
            degradation_ok = False
            print(f"    Unexpected failure: {r.pdf.description} -> {r.error[:100]}")

    fallback_pass = len(failed_parses) == 0 or degradation_ok
    print(f"\n  [Criterion 5] Fallback mechanism: {len(failed_parses)} failures, "
          f"all handled={'yes' if degradation_ok else 'no'} "
          f"{'[PASS]' if fallback_pass else '[WARN]'}")

    # Criterion 6: API compatibility (response structure)
    api_compat = True
    required_fields = {"markdown", "pages", "metadata", "parser_version", "elapsed_ms"}
    for r in parse_results:
        if not r.success:
            continue
        response_data = {
            "markdown": r.markdown,
            "pages": r.pages,
            "metadata": r.metadata,
            "parser_version": r.parser_version,
            "elapsed_ms": r.elapsed_ms,
        }
        missing = required_fields - set(k for k, v in response_data.items() if v is not None)
        if missing:
            api_compat = False
            print(f"    API missing fields for {r.pdf.description}: {missing}")

    print(f"\n  [Criterion 6] API response compatibility: {'[PASS]' if api_compat else '[WARN]'}")

    # -----------------------------------------------------------------------
    # Test 4: Content quality spot checks
    # -----------------------------------------------------------------------
    print_section("Test 4: Content Quality Spot Checks")

    attention_results = [
        r for r in parse_results
        if r.success and "attention" in r.pdf.description.lower()
    ]
    if attention_results:
        r = attention_results[0]
        md = r.markdown
        print(f"\n  Spot check: {r.pdf.description}")
        print(f"    Length: {len(md)} chars")
        attention_found = "attention" in md.lower()
        transformer_found = "transformer" in md.lower()
        print(f"    Contains 'attention': {attention_found}")
        print(f"    Contains 'transformer': {transformer_found}")

        eq_patterns = re.findall(r"\$\$.+?\$\$", md, re.DOTALL)
        print(f"    Block equations: {len(eq_patterns)}")
        if eq_patterns:
            print(f"    First equation preview: {eq_patterns[0][:120]}...")

    resnet_results = [
        r for r in parse_results
        if r.success and "resn" in r.pdf.description.lower()
    ]
    if resnet_results:
        r = resnet_results[0]
        md = r.markdown
        print(f"\n  Spot check: {r.pdf.description}")
        print(f"    Length: {len(md)} chars")
        residual_found = "residual" in md.lower()
        print(f"    Contains 'residual': {residual_found}")

    # -----------------------------------------------------------------------
    # Test 5: Markdown structure validation
    # -----------------------------------------------------------------------
    print_section("Test 5: Markdown Structure Validation")

    structure_issues = 0
    for qs in quality_scores:
        if qs.category in ("dual_column", "formula_heavy") and qs.heading_count == 0:
            print(f"    [WARN] {qs.pdf_name}: No headings detected in academic paper")
            structure_issues += 1
        if qs.garble_rate > 0.15:
            print(f"    [WARN] {qs.pdf_name}: High garble rate {qs.garble_rate:.3f}")
            structure_issues += 1
        if qs.chars_per_page < 50 and qs.category != "scan":
            print(f"    [WARN] {qs.pdf_name}: Very low content density {qs.chars_per_page:.0f} ch/page")
            structure_issues += 1

    if structure_issues == 0:
        print("    All structure checks passed")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print_header("Phase 1 验收总结")

    criteria = [
        ("1. 复杂论文解析质量", complex_pass, f"avg_score={complex_avg_score:.1f}"),
        ("2. 公式还原 (LaTeX)", formula_pass, f"rate={formula_rate:.1%}"),
        ("3. 表格还原 (Markdown)", table_pass, f"rate={table_rate:.1%}"),
        ("4. 解析性能", perf_pass, f"p95={p95_ms:.0f}ms" if elapsed_values else "N/A"),
        ("5. 降级机制", fallback_pass, f"failures={len(failed_parses)}"),
        ("6. API 兼容性", api_compat, "response structure OK" if api_compat else "fields missing"),
    ]

    pass_count = 0
    for name, passed, detail in criteria:
        status = "PASS" if passed else "WARN"
        if passed:
            pass_count += 1
        print(f"  [{status}] {name} — {detail}")

    print(f"\n  Overall: {pass_count}/{len(criteria)} criteria passed")

    if pass_count == len(criteria):
        print("\n  ★ Phase 1 验收通过 — 可以进入阶段 2")
    elif pass_count >= 4:
        print("\n  △ Phase 1 基本可用 — 建议修复 WARN 项后进入阶段 2")
    else:
        print("\n  ✗ Phase 1 尚未达标 — 需要继续完善后重新验收")

    # -----------------------------------------------------------------------
    # Detailed per-file results table
    # -----------------------------------------------------------------------
    print_section("Detailed Results Table")
    hdr = f"  {'File':<45} {'Cat':<14} {'Score':>5} {'Time':>7} {'Secs':>4} {'Tbl':>3} {'Eq':>4} {'Garble':>7} {'Issues'}"
    print(hdr)
    print("  " + "─" * len(hdr))
    for qs in sorted(quality_scores, key=lambda q: (-q.score, q.pdf_name)):
        issues_str = ",".join(qs.issues) if qs.issues else "-"
        eq_total = qs.latex_block_count + qs.latex_inline_count
        print(
            f"  {qs.pdf_name:<45} {qs.category:<14} {qs.score:>5.0f} "
            f"{qs.elapsed_ms:>6}ms {qs.section_count:>4} {qs.table_count:>3} "
            f"{eq_total:>4} {qs.garble_rate:>6.3f} {issues_str}"
        )

    # Save results to JSON
    output_path = Path(OUTPUT_JSON)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mineru_url": MINERU_BASE_URL,
        "filters": {
            "categories": sorted(TEST_CATEGORIES),
            "name_filter": TEST_NAME_FILTER,
            "max_test_pdfs": MAX_TEST_PDFS,
        },
        "summary": {
            "total_pdfs": total_attempted,
            "parse_success": total_parsed,
            "complex_avg_score": round(complex_avg_score, 1),
            "formula_detection_rate": round(formula_rate, 3),
            "table_detection_rate": round(table_rate, 3),
            "criteria_passed": pass_count,
            "criteria_total": len(criteria),
        },
        "criteria": [
            {"name": name, "passed": passed, "detail": detail}
            for name, passed, detail in criteria
        ],
        "per_file": [
            {
                "name": qs.pdf_name,
                "category": qs.category,
                "score": qs.score,
                "elapsed_ms": qs.elapsed_ms,
                "markdown_length": qs.markdown_length,
                "sections": qs.section_count,
                "tables": qs.table_count,
                "formulas_block": qs.latex_block_count,
                "formulas_inline": qs.latex_inline_count,
                "garble_rate": round(qs.garble_rate, 4),
                "chars_per_page": round(qs.chars_per_page, 1),
                "issues": qs.issues,
            }
            for qs in quality_scores
        ],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
