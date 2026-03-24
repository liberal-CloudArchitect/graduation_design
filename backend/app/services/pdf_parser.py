"""
PDF Parser - 多层PDF解析器
"""
import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import asyncio
from loguru import logger


@dataclass
class PDFPage:
    """PDF页面"""
    page_number: int
    text: str
    layout: Optional[Dict] = None
    images: List[str] = field(default_factory=list)


@dataclass 
class PDFDocument:
    """PDF文档解析结果"""
    file_path: str
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    abstract: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    pages: List[PDFPage] = field(default_factory=list)
    full_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Phase 1 新增字段 (全部有默认值, legacy 路径自动兼容)
    parser_route: str = "legacy"
    parser_version: Optional[str] = None
    raw_markdown: Optional[str] = None
    sections: List[Any] = field(default_factory=list)  # List[SectionInfo]
    has_tables: Optional[bool] = None
    has_formulas: Optional[bool] = None
    has_figures: Optional[bool] = None
    
    @property
    def page_count(self) -> int:
        return len(self.pages)


class TextExtractor:
    """Layer 1: 基础文本提取 (PDFPlumber)"""

    _LINE_MERGE_TOP_GAP = 2.5
    
    def extract(self, pdf_path: str) -> List[PDFPage]:
        """提取PDF文本"""
        try:
            import pdfplumber
        except ImportError:
            logger.warning("pdfplumber not installed, using fallback")
            return self._fallback_extract(pdf_path)
        
        pages = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    text = self._extract_page_text(page)
                    pages.append(PDFPage(
                        page_number=i + 1,
                        text=text
                    ))
        except Exception as e:
            logger.error(f"PDFPlumber extraction failed: {e}")
            return self._fallback_extract(pdf_path)
        
        return pages

    def _extract_page_text(self, page) -> str:
        """
        优先使用 extract_words 重建文本，减少词间空格丢失。
        回退到 extract_text。
        """
        try:
            words = page.extract_words(
                x_tolerance=2,
                y_tolerance=3,
                keep_blank_chars=False,
            ) or []
        except Exception:
            words = []

        if words:
            text = self._rebuild_text_from_words(words)
            if text and len(text) >= 20:
                return text

        return (page.extract_text() or "").strip()

    def _rebuild_text_from_words(self, words: List[Dict[str, Any]]) -> str:
        """按行重建 extract_words 结果。"""
        if not words:
            return ""

        ordered = sorted(
            words,
            key=lambda w: (float(w.get("top", 0.0)), float(w.get("x0", 0.0))),
        )

        lines: List[List[str]] = []
        current_line: List[str] = []
        current_top: Optional[float] = None

        for w in ordered:
            token = str(w.get("text", "") or "").strip()
            if not token:
                continue

            top = float(w.get("top", 0.0))
            if current_top is None or abs(top - current_top) <= self._LINE_MERGE_TOP_GAP:
                current_line.append(token)
                if current_top is None:
                    current_top = top
            else:
                lines.append(current_line)
                current_line = [token]
                current_top = top

        if current_line:
            lines.append(current_line)

        merged = "\n".join(" ".join(line) for line in lines)
        return re.sub(r"[ \t]+", " ", merged).strip()
    
    def _fallback_extract(self, pdf_path: str) -> List[PDFPage]:
        """备用提取方法 (PyPDF2)"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages.append(PDFPage(page_number=i + 1, text=text))
            return pages
        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
            return []


class OCREngine:
    """Layer 2: OCR识别 (Tesseract)"""
    
    def __init__(self, lang: str = "chi_sim+eng"):
        self.lang = lang
    
    def recognize(self, pdf_path: str) -> List[PDFPage]:
        """OCR识别PDF"""
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError:
            logger.warning("pytesseract or pdf2image not installed")
            return []
        
        pages = []
        try:
            # 转换PDF为图像
            images = convert_from_path(pdf_path, dpi=200)
            
            for i, image in enumerate(images):
                text = pytesseract.image_to_string(image, lang=self.lang)
                pages.append(PDFPage(
                    page_number=i + 1,
                    text=text
                ))
        except Exception as e:
            logger.error(f"OCR failed: {e}")
        
        return pages


class MetadataExtractor:
    """Layer 3: 元数据提取 (规则 + LLM)"""
    
    def __init__(self):
        # 常见的元数据模式
        self.title_patterns = [
            r'^\s*([^\n]{12,220})\n',
            r'(?im)^title[:\s]+([^\n]{10,220})$',
        ]
        self.author_patterns = [
            r'(?:Authors?|By)[:\s]+(.+?)(?:\n|$)',
        ]
        self.abstract_patterns = [
            r'Abstract[:\s]*\n?(.+?)(?:\n\n|Keywords|Introduction)',
            r'摘\s*要[：:\s]*(.+?)(?:\n\n|关键[词字]|引\s*言)',
        ]
        self.keyword_patterns = [
            r'Keywords?[:\s]+(.+?)(?:\n\n|\n[A-Z])',
            r'关键[词字][：:\s]+(.+?)(?:\n\n|\n\d)',
        ]
    
    def extract(self, text: str) -> Dict[str, Any]:
        """提取元数据"""
        text_clean = text[:5000]  # 只分析前5000字符
        
        result = {
            "title": self._extract_title(text_clean),
            "authors": self._extract_authors(text_clean),
            "abstract": self._extract_abstract(text_clean),
            "keywords": self._extract_keywords(text_clean),
        }
        
        return result
    
    # 非标题关键词（版权声明、许可、页眉等）
    _NON_TITLE_KEYWORDS = [
        'permission', 'license', 'copyright', 'granted', 'attribution',
        'provided', 'rights reserved', 'published by', 'preprint',
        'arxiv', 'proceedings', 'conference', 'journal of', 'vol.',
        'pages ', 'pp.', '©', 'doi:', 'issn', 'ieee', 'acm',
        'springer', 'elsevier', 'under review',
        'information 20', 'editorial', 'journal', 'mdpi',
    ]

    _AUTHOR_NOISE_KEYWORDS = [
        "open access",
        "citation",
        "article",
        "published",
        "license",
        "doi",
        "received",
        "accepted",
        "correspondence",
    ]

    _ABSTRACT_CUTOFF_MARKERS = (
        "keywords",
        "index terms",
        "introduction",
        "1.",
        "i.",
        "citation:",
    )
    _TITLE_NOISE_TOKENS = [
        "academiceditors",
        "academic editors",
        "received:",
        "accepted:",
        "published:",
        "citation:",
        "doi:",
        "keywords:",
        "keywords",
        "our daily lives",
        "despite their awareness",
        "in this article",
        "copyright",
    ]

    def _is_likely_title(self, text: str) -> bool:
        """判断文本是否可能是标题（而非版权声明等）"""
        text = self._clean_text(text)
        if not text:
            return False
        lower = text.lower()
        # 包含过多非标题关键词则排除
        hit_count = sum(1 for kw in self._NON_TITLE_KEYWORDS if kw in lower)
        if hit_count >= 2:
            return False
        # 过长一般不是标题
        if len(text) > 200:
            return False
        # 过短一般不是标题
        if len(text) < 12:
            return False
        # 含数字过多通常是期刊头/页码信息
        digit_ratio = sum(ch.isdigit() for ch in text) / max(1, len(text))
        if digit_ratio > 0.2:
            return False
        # 标题长度（词数）通常有限
        word_count = len(text.split())
        if word_count > 28:
            return False
        # 全是小写且很长，通常不是标题
        if text == text.lower() and len(text) > 80:
            return False
        # 标题通常不是单词或双词短语
        if len(text.split()) <= 2 and not re.search(r'[\u4e00-\u9fff]', text):
            return False
        lower_no_space = lower.replace(" ", "")
        if any(tok in lower_no_space for tok in [t.replace(" ", "") for t in self._TITLE_NOISE_TOKENS]):
            return False
        # 标题很少以完整句号结尾
        if text.endswith(".") and word_count > 6:
            return False
        # 标题很少包含大量作者分隔符
        if text.count(";") >= 2:
            return False
        return True

    def is_reliable_authors(self, authors: List[str]) -> bool:
        """判断作者列表质量是否可靠。"""
        if not authors:
            return False
        valid = [a for a in authors if self._is_valid_author(a)]
        return len(valid) >= max(1, len(authors) // 2)

    def is_reliable_abstract(self, abstract: Optional[str]) -> bool:
        """判断摘要质量是否可靠。"""
        if not abstract:
            return False
        text = self._clean_text(abstract)
        if len(text) < 60:
            return False
        # 英文摘要若几乎无空格，通常是提取质量差
        has_cjk = bool(re.search(r'[\u4e00-\u9fff]', text))
        alpha_count = sum(ch.isalpha() for ch in text)
        space_count = text.count(" ")
        if not has_cjk and alpha_count > 200 and space_count < max(10, int(alpha_count * 0.02)):
            return False
        return True

    def _extract_title(self, text: str) -> Optional[str]:
        """提取标题"""
        candidates: List[str] = []
        # 尝试用 PDF metadata 标记模式
        for pattern in self.title_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                title = self._clean_text(match.group(1))
                if self._is_likely_title(title):
                    candidates.append(title)
        
        # 备用：从前 40 行中找最可能的标题行
        lines = text.split('\n')
        for line in lines[:40]:
            line = self._clean_text(line)
            if self._is_likely_title(line):
                candidates.append(line)

        if not candidates:
            return None

        # 选分数最高的候选标题
        candidates = list(dict.fromkeys(candidates))
        candidates.sort(key=self._score_title, reverse=True)
        return candidates[0]

    def _score_title(self, title: str) -> float:
        """标题候选打分：更长、更像句子、更少噪声优先。"""
        score = 0.0
        words = title.split()
        score += min(len(title), 160) / 40.0
        if 4 <= len(words) <= 24:
            score += 2.0
        if ":" in title or "-" in title:
            score += 0.6
        if re.search(r'[A-Z][a-z]+', title):
            score += 0.4
        score -= sum(1 for kw in self._NON_TITLE_KEYWORDS if kw in title.lower()) * 1.5
        return score

    def _clean_text(self, text: Optional[str]) -> str:
        return re.sub(r'\s+', ' ', str(text or '')).strip()

    def _is_valid_author(self, name: str) -> bool:
        n = self._clean_text(name)
        if len(n) < 2 or len(n) > 60:
            return False
        lower = n.lower()
        if any(k in lower for k in self._AUTHOR_NOISE_KEYWORDS):
            return False
        if re.search(r'\d', n):
            return False
        if n.count(",") > 1:
            return False
        tokens = [t for t in n.split(" ") if t]
        if len(tokens) > 6:
            return False
        # 英文名至少应有首字母大写特征；中文名允许无空格
        if re.search(r'[A-Za-z]', n) and not any(t[0].isupper() for t in tokens if t):
            return False
        return True

    def _extract_authors(self, text: str) -> List[str]:
        """提取作者"""
        authors = []
        # 仅在论文头部文本中提取作者，避免被正文污染
        head_text = text[:1500]
        abstract_pos = re.search(r'(?i)\babstract\b|摘\s*要', head_text)
        if abstract_pos:
            head_text = head_text[:abstract_pos.start()]

        for pattern in self.author_patterns:
            matches = re.findall(pattern, head_text, re.IGNORECASE)
            for match in matches:
                # 分割多个作者
                parts = re.split(r'[,;，；]|\sand\s', match)
                for part in parts:
                    part = self._clean_text(part)
                    if self._is_valid_author(part):
                        authors.append(part)

        # 回退：尝试从前若干行中识别作者行
        if not authors:
            for line in head_text.split("\n")[:25]:
                line = self._clean_text(line)
                if not line:
                    continue
                lower = line.lower()
                if any(k in lower for k in ("abstract", "citation", "doi", "keywords", "introduction")):
                    continue
                parts = [self._clean_text(p) for p in re.split(r'[,;，；]|\sand\s', line)]
                valid_parts = [p for p in parts if self._is_valid_author(p)]
                if 2 <= len(valid_parts) <= 8:
                    authors.extend(valid_parts)
                    break

        # 保序去重
        deduped = list(dict.fromkeys(authors))
        return deduped[:10]
    
    def _extract_abstract(self, text: str) -> Optional[str]:
        """提取摘要"""
        for pattern in self.abstract_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                abstract = self._clean_text(match.group(1))
                # 裁剪到摘要正文
                lower = abstract.lower()
                cutoff_pos = len(abstract)
                for marker in self._ABSTRACT_CUTOFF_MARKERS:
                    pos = lower.find(marker)
                    if pos > 80:
                        cutoff_pos = min(cutoff_pos, pos)
                abstract = abstract[:cutoff_pos].strip()

                if self.is_reliable_abstract(abstract):
                    return abstract[:2000]  # 限制长度
        
        return None
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        keywords = []
        for pattern in self.keyword_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                kw_text = match.group(1).strip()
                # 分割关键词
                parts = re.split(r'[,;，；、]', kw_text)
                for part in parts:
                    part = part.strip()
                    if part and len(part) > 1 and len(part) < 50:
                        keywords.append(part)
        
        return list(set(keywords))[:20]


class LLMMetadataExtractor:
    """Layer 4: LLM元数据提取"""
    
    def __init__(self, llm=None):
        self.llm = llm
    
    async def extract(self, text: str) -> Dict[str, Any]:
        """使用LLM提取元数据"""
        if not self.llm:
            return {}
        
        prompt = f"""请从以下论文文本中提取元数据，返回JSON格式：

文本（前2000字）:
{text[:2000]}

请提取：
1. title: 论文标题
2. authors: 作者列表
3. abstract: 摘要
4. keywords: 关键词列表

返回格式示例:
{{"title": "...", "authors": ["..."], "abstract": "...", "keywords": ["..."]}}
"""
        
        try:
            response = await self.llm.ainvoke(prompt)
            import json
            result = json.loads(response.content)
            return result
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return {}


@dataclass
class ComplexityResult:
    """PDF 复杂度检测结果"""
    complexity: str     # "simple" | "complex"
    route_reason: str   # 人可读的判定理由


class PDFParser:
    """
    多层PDF解析器
    
    Layer 1: PDFPlumber 文本提取
    Layer 2: Tesseract OCR (扫描件)
    Layer 2.5: LayoutLMv3 布局分析 (可选)
    Layer 3: 规则 + 正则 元数据提取
    Layer 4: LLM 智能提取 (可选)
    
    Phase 1: 当 MINERU_ENABLED=True 时，复杂 PDF 走 MinerU 服务，
    简单 PDF 继续走现有管线。
    """
    
    def __init__(
        self, 
        use_ocr: bool = True, 
        use_llm: bool = False, 
        use_layout: bool = True,
        llm=None
    ):
        self.text_extractor = TextExtractor()
        self.ocr_engine = OCREngine() if use_ocr else None
        self.metadata_extractor = MetadataExtractor()
        self.llm_extractor = LLMMetadataExtractor(llm) if use_llm else None
        self.layout_analyzer = None
        if use_layout:
            try:
                from app.services.layout_analyzer import LayoutAnalyzer
                self.layout_analyzer = LayoutAnalyzer()
            except Exception as e:
                logger.warning(f"Layout analyzer not available: {e}")

        self._mineru_client = None
        self._markdown_processor = None
        self._sanity_gate = None

    def _ensure_mineru_deps(self):
        """延迟初始化 MinerU 相关依赖（仅在 MINERU_ENABLED 时需要）"""
        if self._mineru_client is not None:
            return
        from app.core.config import settings
        from app.services.mineru_client import MinerUClient
        from app.services.markdown_processor import MarkdownPostProcessor
        from app.services.parse_sanity import ParseSanityGate

        self._mineru_client = MinerUClient(
            base_url=settings.MINERU_API_URL,
            timeout=settings.PDF_PARSE_TIMEOUT,
            api_key=settings.MINERU_API_KEY,
        )
        self._markdown_processor = MarkdownPostProcessor()
        self._sanity_gate = ParseSanityGate()

    async def parse(self, pdf_path: str) -> PDFDocument:
        """解析 PDF 文档 -- 带路由逻辑。

        MINERU_ENABLED=False (默认): 全部走 legacy 管线，行为与基线一致。
        MINERU_ENABLED=True: 简单 PDF 走 legacy; 复杂 PDF 走 MinerU + 降级。
        """
        from app.core.config import settings

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        if not settings.MINERU_ENABLED:
            doc = await self._parse_legacy(pdf_path)
            doc.parser_route = "legacy"
            return doc

        cr = self._detect_complexity(pdf_path)

        if cr.complexity == "simple":
            doc = await self._parse_legacy(pdf_path)
            doc.parser_route = "legacy"
            doc.metadata["complexity"] = cr.complexity
            doc.metadata["route_reason"] = cr.route_reason
            return doc

        try:
            doc = await self._parse_with_mineru(pdf_path, cr.route_reason)
            doc.metadata["complexity"] = cr.complexity
            doc.metadata["route_reason"] = cr.route_reason
            return doc
        except Exception as e:
            logger.warning(f"MinerU failed, falling back to legacy: {e}")
            doc = await self._parse_legacy(pdf_path)
            doc.parser_route = "legacy"
            doc.metadata["complexity"] = cr.complexity
            doc.metadata["route_reason"] = cr.route_reason
            doc.metadata["fallback_reason"] = str(e)
            return doc

    def _detect_complexity(self, pdf_path: str) -> ComplexityResult:
        """轻量复杂度检测 -- 仅用 PyMuPDF (fitz) 页级元信息"""
        try:
            import fitz
        except ImportError:
            return ComplexityResult("complex", "fitz_unavailable")

        try:
            doc = fitz.open(pdf_path)
        except Exception:
            return ComplexityResult("complex", "fitz_open_failed")

        is_scanned = True
        has_images = False

        for page in doc:
            text_len = len(page.get_text("text"))
            image_count = len(page.get_images())
            if text_len > 50:
                is_scanned = False
            if image_count > 0:
                has_images = True

        page_count = doc.page_count
        doc.close()

        if is_scanned:
            return ComplexityResult("complex", "scanned_pdf")
        if has_images:
            return ComplexityResult("complex", "contains_images")
        if page_count > 3:
            return ComplexityResult("complex", "multi_page_document")
        return ComplexityResult("simple", "plain_text")

    async def _parse_with_mineru(self, pdf_path: str, route_reason: str) -> PDFDocument:
        """使用 MinerU 服务解析复杂 PDF，含 sanity gate 和降级"""
        self._ensure_mineru_deps()

        mineru_response = await self._mineru_client.parse(pdf_path)

        try:
            import fitz
            fitz_doc = fitz.open(pdf_path)
            fitz_page_count = fitz_doc.page_count
            fitz_doc.close()
        except Exception:
            fitz_page_count = max(len(mineru_response.pages), 1)

        sanity = self._sanity_gate.check(mineru_response.markdown, fitz_page_count)
        if not sanity.passed:
            logger.warning(f"MinerU sanity gate failed: {sanity.reason}")
            doc = await self._parse_legacy(pdf_path)
            doc.parser_route = "legacy"
            doc.metadata["fallback_reason"] = sanity.reason
            return doc

        cleaned_md = self._markdown_processor.process(mineru_response.markdown)
        md_metadata = self._markdown_processor.extract_metadata(cleaned_md)
        sections = self._markdown_processor.extract_sections(
            cleaned_md, mineru_response.pages
        )

        pages = []
        for p in mineru_response.pages:
            page_md = p.get("markdown", "")
            plain = self._markdown_processor.markdown_to_plain_text(page_md)
            pages.append(PDFPage(
                page_number=p.get("page_number", 1),
                text=plain,
            ))

        full_plain = self._markdown_processor.markdown_to_plain_text(cleaned_md)

        title = (
            md_metadata.get("title")
            or mineru_response.metadata.get("title")
        )
        abstract = md_metadata.get("abstract")

        doc = PDFDocument(
            file_path=pdf_path,
            title=title,
            abstract=abstract,
            pages=pages,
            full_text=full_plain,
            metadata={
                "title": title,
                "abstract": abstract,
                "mineru_elapsed_ms": mineru_response.elapsed_ms,
            },
            parser_route="mineru",
            parser_version=mineru_response.parser_version,
            raw_markdown=cleaned_md,
            sections=sections,
            has_tables=md_metadata.get("has_tables"),
            has_formulas=md_metadata.get("has_formulas"),
            has_figures=md_metadata.get("has_figures"),
        )

        logger.info(
            f"MinerU parsed: {doc.page_count} pages, "
            f"{len(sections)} sections, "
            f"tables={doc.has_tables}, formulas={doc.has_formulas}, "
            f"elapsed={mineru_response.elapsed_ms}ms"
        )
        return doc

    async def _parse_legacy(self, pdf_path: str) -> PDFDocument:
        """现有 legacy 解析管线 -- 内部逻辑与基线完全一致"""
        logger.info(f"Parsing PDF (legacy): {pdf_path}")

        pages = self.text_extractor.extract(pdf_path)

        total_text = " ".join(p.text for p in pages)
        if len(total_text.strip()) < 100 and self.ocr_engine:
            logger.info("Text too short, trying OCR...")
            pages = self.ocr_engine.recognize(pdf_path)
            total_text = " ".join(p.text for p in pages)

        layout_data = None
        if self.layout_analyzer:
            try:
                layouts = await self.layout_analyzer.analyze_pdf(pdf_path)
                if layouts:
                    layout_data = layouts
                    for page_layout in layouts:
                        idx = page_layout.page_number - 1
                        if 0 <= idx < len(pages):
                            pages[idx].layout = {
                                "regions": [
                                    {
                                        "type": r.region_type.value,
                                        "text": r.text,
                                        "bbox": r.bbox,
                                        "confidence": r.confidence,
                                        "order": r.order
                                    }
                                    for r in page_layout.regions
                                ]
                            }
                    logger.info(f"Layout analysis completed for {len(layouts)} pages")
            except Exception as e:
                logger.warning(f"Layout analysis failed: {e}")

        metadata = self.metadata_extractor.extract(total_text)

        if layout_data:
            layout_metadata = self._extract_metadata_from_layout(layout_data)
            layout_title = layout_metadata.get("title")
            current_title = metadata.get("title")
            if layout_title and (not current_title or not self.metadata_extractor._is_likely_title(current_title)):
                metadata["title"] = layout_title

            layout_authors = layout_metadata.get("authors") or []
            current_authors = metadata.get("authors") or []
            if layout_authors and not self.metadata_extractor.is_reliable_authors(current_authors):
                metadata["authors"] = layout_authors

            layout_abstract = layout_metadata.get("abstract")
            current_abstract = metadata.get("abstract")
            if layout_abstract and not self.metadata_extractor.is_reliable_abstract(current_abstract):
                if self.metadata_extractor.is_reliable_abstract(layout_abstract):
                    metadata["abstract"] = layout_abstract

            for key, value in layout_metadata.items():
                if key in {"title", "authors", "abstract"}:
                    continue
                if value and not metadata.get(key):
                    metadata[key] = value

        if self.llm_extractor and not metadata.get("title"):
            llm_metadata = await self.llm_extractor.extract(total_text)
            metadata.update({k: v for k, v in llm_metadata.items() if v})

        doc = PDFDocument(
            file_path=pdf_path,
            title=metadata.get("title"),
            authors=metadata.get("authors", []),
            abstract=metadata.get("abstract"),
            keywords=metadata.get("keywords", []),
            pages=pages,
            full_text=total_text,
            metadata=metadata
        )

        logger.info(f"Parsed PDF (legacy): {doc.page_count} pages, title: {doc.title}")

        return doc

    def _extract_metadata_from_layout(self, layouts) -> Dict[str, Any]:
        """从布局分析结果中提取元数据"""
        from app.services.layout_analyzer import RegionType
        
        metadata = {}
        
        if not layouts:
            return metadata
        
        # 通常标题和作者在第一页
        first_page = layouts[0]
        
        # 提取标题
        title_regions = first_page.get_regions_by_type(RegionType.TITLE)
        if title_regions:
            metadata["title"] = " ".join(r.text for r in title_regions).strip()
        
        # 提取作者
        author_regions = first_page.get_regions_by_type(RegionType.AUTHOR)
        if author_regions:
            author_text = " ".join(r.text for r in author_regions)
            authors = re.split(r'[,;，；]|\sand\s', author_text)
            metadata["authors"] = [a.strip() for a in authors if a.strip() and len(a.strip()) > 1]
        
        # 提取摘要
        abstract_regions = first_page.get_regions_by_type(RegionType.ABSTRACT)
        if abstract_regions:
            metadata["abstract"] = " ".join(r.text for r in abstract_regions).strip()
        
        # 提取section结构
        sections = []
        for page_layout in layouts:
            section_headers = page_layout.get_regions_by_type(RegionType.SECTION_HEADER)
            for header in section_headers:
                sections.append({
                    "title": header.text,
                    "page": page_layout.page_number
                })
        if sections:
            metadata["sections"] = sections
        
        return metadata
    
    def parse_sync(self, pdf_path: str) -> PDFDocument:
        """同步解析方法"""
        return asyncio.run(self.parse(pdf_path))


# 默认解析器实例 (启用布局分析)
default_parser = PDFParser(use_ocr=False, use_llm=False, use_layout=True)


async def parse_pdf(pdf_path: str) -> PDFDocument:
    """便捷函数：解析PDF"""
    return await default_parser.parse(pdf_path)
