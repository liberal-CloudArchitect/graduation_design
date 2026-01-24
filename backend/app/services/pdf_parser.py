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
    
    def _extract_title(self, text: str) -> Optional[str]:
        """提取标题"""
        for pattern in self.title_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                title = match.group(1).strip()
                if len(title) > 10 and len(title) < 300:
                    return title
        
        # 备用：取第一行
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 300:
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
    Layer 3: 规则 + 正则 元数据提取
    Layer 4: LLM 智能提取 (可选)
    """
    
    def __init__(self, use_ocr: bool = True, use_llm: bool = False, llm=None):
        self.text_extractor = TextExtractor()
        self.ocr_engine = OCREngine() if use_ocr else None
        self.metadata_extractor = MetadataExtractor()
        self.llm_extractor = LLMMetadataExtractor(llm) if use_llm else None
    
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
        
        # Step 3: 提取元数据
        metadata = self.metadata_extractor.extract(total_text)
        
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
    
    def parse_sync(self, pdf_path: str) -> PDFDocument:
        """同步解析方法"""
        return asyncio.run(self.parse(pdf_path))


# 默认解析器实例
default_parser = PDFParser(use_ocr=False, use_llm=False)


async def parse_pdf(pdf_path: str) -> PDFDocument:
    """便捷函数：解析PDF"""
    return await default_parser.parse(pdf_path)
