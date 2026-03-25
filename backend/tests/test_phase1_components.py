"""
Phase 1 组件单元测试

测试 MinerU 集成链路上的核心组件，不需要外部服务即可运行。
覆盖: MarkdownPostProcessor, ParseSanityGate, ComplexityResult, 路由决策逻辑。
"""
import importlib.util
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.markdown_processor import MarkdownPostProcessor, SectionInfo
from app.services.parse_sanity import ParseSanityGate, SanityResult


# ---------------------------------------------------------------------------
# MarkdownPostProcessor
# ---------------------------------------------------------------------------

class TestMarkdownPostProcessor:

    def setup_method(self):
        self.proc = MarkdownPostProcessor()

    def test_process_merges_broken_paragraphs(self):
        md = "This is a bro-\nken line"
        result = self.proc.process(md)
        assert "broken" in result

    def test_process_normalizes_latex(self):
        md = r"inline \(x^2\) and block \[E=mc^2\]"
        result = self.proc.process(md)
        assert "$x^2$" in result
        assert "$$E=mc^2$$" in result

    def test_process_removes_page_numbers(self):
        md = "Some text\n42\nMore text"
        result = self.proc.process(md)
        assert "\n42\n" not in result

    def test_extract_metadata_title(self):
        md = "# Deep Residual Learning\n\nSome content"
        meta = self.proc.extract_metadata(md)
        assert meta["title"] == "Deep Residual Learning"

    def test_extract_metadata_abstract(self):
        md = "# Title\n\n## Abstract\n\nThis paper presents a novel approach to deep learning that achieves state of the art results on multiple benchmarks.\n\n## Introduction\n\nContent"
        meta = self.proc.extract_metadata(md)
        assert meta["abstract"] is not None
        assert "novel approach" in meta["abstract"]

    def test_extract_metadata_tables(self):
        md = "| Col1 | Col2 |\n| --- | --- |\n| a | b |"
        meta = self.proc.extract_metadata(md)
        assert meta["has_tables"] is True

    def test_extract_metadata_formulas(self):
        md = "The equation $$E = mc^2$$ is famous"
        meta = self.proc.extract_metadata(md)
        assert meta["has_formulas"] is True

    def test_extract_metadata_figures(self):
        md = "![Architecture](fig1.png)"
        meta = self.proc.extract_metadata(md)
        assert meta["has_figures"] is True

    def test_extract_metadata_no_features(self):
        md = "Just plain text without anything special"
        meta = self.proc.extract_metadata(md)
        assert meta["has_tables"] is False
        assert meta["has_formulas"] is False
        assert meta["has_figures"] is False

    def test_extract_sections(self):
        md = "# Title\n\n## Introduction\n\n## Methods\n\n### Dataset\n\n## Results"
        sections = self.proc.extract_sections(md)
        assert len(sections) == 5
        assert sections[0].title == "Title"
        assert sections[0].level == 1
        assert sections[1].title == "Introduction"
        assert sections[1].level == 2
        assert sections[4].title == "Results"

    def test_extract_sections_returns_section_info(self):
        md = "## Section One\n\nContent"
        sections = self.proc.extract_sections(md)
        assert isinstance(sections[0], SectionInfo)
        assert sections[0].page_start >= 1

    def test_markdown_to_plain_text_removes_headers(self):
        md = "# Title\n\n## Section\n\nContent"
        plain = self.proc.markdown_to_plain_text(md)
        assert "#" not in plain
        assert "Title" in plain
        assert "Content" in plain

    def test_markdown_to_plain_text_removes_bold(self):
        md = "**bold text** and *italic*"
        plain = self.proc.markdown_to_plain_text(md)
        assert "**" not in plain
        assert "*" not in plain
        assert "bold text" in plain
        assert "italic" in plain

    def test_markdown_to_plain_text_removes_links(self):
        md = "[click here](http://example.com)"
        plain = self.proc.markdown_to_plain_text(md)
        assert "click here" in plain
        assert "http://" not in plain

    def test_markdown_to_plain_text_removes_images(self):
        md = "![alt text](image.png)"
        plain = self.proc.markdown_to_plain_text(md)
        assert "![" not in plain
        assert "alt text" in plain

    def test_section_info_schema(self):
        sec = SectionInfo(title="Intro", level=2, page_start=1)
        assert sec.title == "Intro"
        assert sec.level == 2
        assert sec.page_start == 1
        assert sec.page_end is None
        assert sec.anchor is None


class TestPhase1AcceptanceHeuristics:

    @staticmethod
    def _load_phase1_acceptance_module():
        path = os.path.join(os.path.dirname(__file__), "test_phase1_acceptance.py")
        spec = importlib.util.spec_from_file_location("phase1_acceptance_module", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_assess_quality_detects_markdown_tables(self):
        module = self._load_phase1_acceptance_module()
        result = module.ParseResult(
            pdf=module.TestPDF(
                path="/tmp/table.pdf",
                category="table_heavy",
                description="table-sample",
            ),
            success=True,
            markdown=(
                "# Results\n\n"
                "| Col1 | Col2 |\n"
                "| --- | --- |\n"
                "| A | B |\n"
            ),
            pages=[{"page_number": 1}],
            elapsed_ms=123,
        )

        score = module.assess_quality(result)

        assert score.table_count == 1
        assert score.has_tables_detected is True


# ---------------------------------------------------------------------------
# ParseSanityGate
# ---------------------------------------------------------------------------

class TestParseSanityGate:

    def setup_method(self):
        self.gate = ParseSanityGate()

    def test_empty_text_fails(self):
        result = self.gate.check("", 5)
        assert result.passed is False
        assert result.reason == "sanity_empty_output"

    def test_whitespace_only_fails(self):
        result = self.gate.check("   \n\n  ", 5)
        assert result.passed is False

    def test_normal_text_passes(self):
        text = "This is a normal paragraph with enough content. " * 20
        result = self.gate.check(text, 1)
        assert result.passed is True
        assert result.reason is None

    def test_short_text_per_page_fails(self):
        text = "Short"
        result = self.gate.check(text, 10)
        assert result.passed is False
        assert result.reason == "sanity_text_short"

    def test_garbled_text_fails(self):
        # Use non-ASCII non-letter characters that unicodedata won't classify as L/N/P/S/M/Z
        garble = "\ufffd\udcff" * 50  # replacement character + surrogate (private use)
        # Actually: use chars from Private Use Area which have category "Co"
        garble = "\ue000\ue001\ue002\ue003" * 200
        normal = "Normal text " * 5
        text = garble + normal
        result = self.gate.check(text, 1)
        assert result.passed is False
        assert result.reason == "sanity_garble"

    def test_chinese_text_passes(self):
        text = "这是一段正常的中文文本，包含足够的内容来通过健全性检查。" * 10
        result = self.gate.check(text, 1)
        assert result.passed is True

    def test_mixed_cjk_ascii_passes(self):
        text = "Deep Learning 深度学习 is a powerful technique. " * 20
        result = self.gate.check(text, 1)
        assert result.passed is True

    def test_sanity_result_dataclass(self):
        r = SanityResult(passed=True)
        assert r.passed is True
        assert r.reason is None

        r2 = SanityResult(passed=False, reason="sanity_garble")
        assert r2.passed is False
        assert r2.reason == "sanity_garble"


# ---------------------------------------------------------------------------
# MinerUClient (structure + error mapping)
# ---------------------------------------------------------------------------

class TestMinerUClient:

    def test_import_and_instantiate(self):
        from app.services.mineru_client import MinerUClient
        client = MinerUClient(base_url="http://localhost:8010", timeout=30)
        assert client.base_url == "http://localhost:8010"
        assert client.timeout == 30

    def test_mineru_response_dataclass(self):
        from app.services.mineru_client import MinerUResponse
        resp = MinerUResponse(
            markdown="# Test",
            pages=[{"page_number": 1, "markdown": "# Test"}],
            metadata={"title": "Test"},
            parser_version="v1",
            elapsed_ms=100,
        )
        assert resp.markdown == "# Test"
        assert resp.elapsed_ms == 100

    def test_service_error_fallback_reasons(self):
        from app.services.mineru_client import MinerUServiceError
        assert MinerUServiceError(413, "too big").fallback_reason == "file_too_large"
        assert MinerUServiceError(503, "busy").fallback_reason == "service_busy"
        assert MinerUServiceError(504, "timeout").fallback_reason == "service_timeout"
        assert "500" in MinerUServiceError(500, "crash").fallback_reason


# ---------------------------------------------------------------------------
# ComplexityResult + routing (structure only, no I/O)
# ---------------------------------------------------------------------------

class TestComplexityResult:

    def test_import_and_create(self):
        from app.services.pdf_parser import ComplexityResult
        cr = ComplexityResult(complexity="complex", route_reason="scanned_pdf")
        assert cr.complexity == "complex"
        assert cr.route_reason == "scanned_pdf"

    def test_simple_result(self):
        from app.services.pdf_parser import ComplexityResult
        cr = ComplexityResult(complexity="simple", route_reason="plain_text")
        assert cr.complexity == "simple"


class TestPDFDocumentPhase1Fields:

    def test_default_values(self):
        from app.services.pdf_parser import PDFDocument
        doc = PDFDocument(file_path="/tmp/test.pdf")
        assert doc.parser_route == "legacy"
        assert doc.parser_version is None
        assert doc.raw_markdown is None
        assert doc.sections == []
        assert doc.has_tables is None
        assert doc.has_formulas is None
        assert doc.has_figures is None

    def test_mineru_values(self):
        from app.services.pdf_parser import PDFDocument
        doc = PDFDocument(
            file_path="/tmp/test.pdf",
            parser_route="mineru",
            parser_version="magic-pdf-0.9",
            raw_markdown="# Title\n\nContent",
            has_tables=True,
            has_formulas=False,
        )
        assert doc.parser_route == "mineru"
        assert doc.parser_version == "magic-pdf-0.9"
        assert doc.raw_markdown is not None
        assert doc.has_tables is True
