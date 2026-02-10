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
    
    @property
    def page_count(self) -> int:
        return len(self.pages)


class TextExtractor:
    """Layer 1: 基础文本提取 (PDFPlumber)"""
    
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
                    text = page.extract_text() or ""
                    pages.append(PDFPage(
                        page_number=i + 1,
                        text=text
                    ))
        except Exception as e:
            logger.error(f"PDFPlumber extraction failed: {e}")
            return self._fallback_extract(pdf_path)
        
        return pages
    
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
            r'^(.+?)\n\n',  # 第一行通常是标题
            r'Title[:\s]+(.+?)(?:\n|$)',
        ]
        self.author_patterns = [
            r'(?:Authors?|By)[:\s]+(.+?)(?:\n|$)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(?:,|\sand|\n)',
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
    ]

    def _is_likely_title(self, text: str) -> bool:
        """判断文本是否可能是标题（而非版权声明等）"""
        lower = text.lower()
        # 包含过多非标题关键词则排除
        hit_count = sum(1 for kw in self._NON_TITLE_KEYWORDS if kw in lower)
        if hit_count >= 2:
            return False
        # 过长一般不是标题
        if len(text) > 200:
            return False
        # 全是小写且很长，通常不是标题
        if text == text.lower() and len(text) > 80:
            return False
        return True

    def _extract_title(self, text: str) -> Optional[str]:
        """提取标题"""
        # 尝试用 PDF metadata 标记模式
        for pattern in self.title_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip()
                if 10 < len(title) < 300 and self._is_likely_title(title):
                    return title
        
        # 备用：从前 30 行中找最可能的标题行
        lines = text.split('\n')
        for line in lines[:30]:
            line = line.strip()
            if 10 < len(line) < 200 and self._is_likely_title(line):
                return line
        
        return None
    
    def _extract_authors(self, text: str) -> List[str]:
        """提取作者"""
        authors = []
        for pattern in self.author_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # 分割多个作者
                parts = re.split(r'[,;，；]|\sand\s', match)
                for part in parts:
                    part = part.strip()
                    if part and len(part) > 2 and len(part) < 50:
                        authors.append(part)
        
        return list(set(authors))[:10]  # 最多10个作者
    
    def _extract_abstract(self, text: str) -> Optional[str]:
        """提取摘要"""
        for pattern in self.abstract_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                if len(abstract) > 50:
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


class PDFParser:
    """
    多层PDF解析器
    
    Layer 1: PDFPlumber 文本提取
    Layer 2: Tesseract OCR (扫描件)
    Layer 2.5: LayoutLMv3 布局分析 (可选)
    Layer 3: 规则 + 正则 元数据提取
    Layer 4: LLM 智能提取 (可选)
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
    
    async def parse(self, pdf_path: str) -> PDFDocument:
        """
        解析PDF文档
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            PDFDocument对象
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        logger.info(f"Parsing PDF: {pdf_path}")
        
        # Step 1: 提取文本
        pages = self.text_extractor.extract(pdf_path)
        
        # Step 2: 如果文本太少，尝试OCR
        total_text = " ".join(p.text for p in pages)
        if len(total_text.strip()) < 100 and self.ocr_engine:
            logger.info("Text too short, trying OCR...")
            pages = self.ocr_engine.recognize(pdf_path)
            total_text = " ".join(p.text for p in pages)
        
        # Step 2.5: LayoutLMv3 布局分析
        layout_data = None
        if self.layout_analyzer:
            try:
                layouts = await self.layout_analyzer.analyze_pdf(pdf_path)
                if layouts:
                    layout_data = layouts
                    # 将布局信息附加到页面
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
        
        # Step 3: 提取元数据 (结合布局信息增强)
        metadata = self.metadata_extractor.extract(total_text)
        
        # 如果有布局数据，用布局增强元数据
        if layout_data:
            layout_metadata = self._extract_metadata_from_layout(layout_data)
            # 布局提取的元数据优先级更高
            for key, value in layout_metadata.items():
                if value and not metadata.get(key):
                    metadata[key] = value
        
        # Step 4: LLM增强（可选）
        if self.llm_extractor and not metadata.get("title"):
            llm_metadata = await self.llm_extractor.extract(total_text)
            metadata.update({k: v for k, v in llm_metadata.items() if v})
        
        # 构建结果
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
        
        logger.info(f"Parsed PDF: {doc.page_count} pages, title: {doc.title}")
        
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
