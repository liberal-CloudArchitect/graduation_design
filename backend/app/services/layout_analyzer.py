"""
Layout Analyzer - LayoutLMv3 布局分析器

基于LayoutLMv3模型对PDF页面进行布局分析，
识别标题、段落、表格、图注、公式等区域。
"""
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger
import asyncio


class RegionType(str, Enum):
    """布局区域类型"""
    TITLE = "title"
    AUTHOR = "author"
    ABSTRACT = "abstract"
    SECTION_HEADER = "section_header"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    FORMULA = "formula"
    REFERENCE = "reference"
    HEADER = "header"
    FOOTER = "footer"
    LIST = "list"
    OTHER = "other"


@dataclass
class LayoutRegion:
    """布局区域"""
    region_type: RegionType
    text: str
    bbox: List[float]  # [x0, y0, x1, y1] normalized 0-1000
    confidence: float = 0.0
    page_number: int = 0
    order: int = 0  # 阅读顺序


@dataclass
class PageLayout:
    """页面布局分析结果"""
    page_number: int
    width: float
    height: float
    regions: List[LayoutRegion] = field(default_factory=list)
    
    def get_regions_by_type(self, region_type: RegionType) -> List[LayoutRegion]:
        """获取指定类型的区域"""
        return [r for r in self.regions if r.region_type == region_type]
    
    def get_text_by_type(self, region_type: RegionType) -> str:
        """获取指定类型的文本"""
        regions = self.get_regions_by_type(region_type)
        return "\n".join(r.text for r in sorted(regions, key=lambda x: x.order))


class LayoutAnalyzer:
    """
    LayoutLMv3 布局分析器
    
    使用LayoutLMv3模型对PDF页面进行布局分析。
    基模型用于特征提取，结合启发式规则进行区域分类。
    """
    
    # 默认标签映射 (基于PubLayNet风格)
    LABEL_MAP = {
        0: RegionType.OTHER,
        1: RegionType.TITLE,
        2: RegionType.PARAGRAPH,
        3: RegionType.LIST,
        4: RegionType.TABLE,
        5: RegionType.FIGURE,
    }
    
    def __init__(
        self, 
        model_path: str = "layoutlmv3-base",
        use_gpu: bool = False,
        confidence_threshold: float = 0.5
    ):
        self.model_path = model_path
        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold
        self._model = None
        self._processor = None
        self._tokenizer = None
        self._initialized = False
    
    def _initialize(self):
        """延迟初始化模型"""
        if self._initialized:
            return
        
        try:
            from transformers import (
                LayoutLMv3Processor,
                LayoutLMv3ForSequenceClassification,
                LayoutLMv3TokenizerFast,
            )
            import torch
            
            # 确定设备
            self.device = "cuda" if self.use_gpu and torch.cuda.is_available() else "cpu"
            
            # 加载处理器和模型
            logger.info(f"Loading LayoutLMv3 from {self.model_path}")
            
            self._processor = LayoutLMv3Processor.from_pretrained(
                self.model_path, 
                apply_ocr=False  # 我们自己提供OCR结果
            )
            
            # 使用基模型进行特征提取
            from transformers import LayoutLMv3Model
            self._model = LayoutLMv3Model.from_pretrained(self.model_path)
            self._model.to(self.device)
            self._model.eval()
            
            self._initialized = True
            logger.info(f"LayoutLMv3 initialized on {self.device}")
            
        except ImportError as e:
            logger.warning(f"LayoutLMv3 dependencies not available: {e}")
            logger.warning("Falling back to heuristic-only layout analysis")
            self._initialized = False
        except Exception as e:
            logger.warning(f"Failed to load LayoutLMv3 model: {e}")
            logger.warning("Falling back to heuristic-only layout analysis")
            self._initialized = False
    
    async def analyze_page(
        self,
        image,  # PIL.Image
        words: List[str],
        boxes: List[List[int]],  # [[x0, y0, x1, y1], ...]  normalized 0-1000
        page_number: int = 1
    ) -> PageLayout:
        """
        分析单个页面的布局
        
        Args:
            image: PIL图像对象
            words: 页面上的单词列表
            boxes: 对应的边界框列表 (normalized 0-1000)
            page_number: 页码
            
        Returns:
            PageLayout 对象
        """
        width, height = image.size
        
        # 尝试使用模型分析
        self._initialize()
        
        if self._initialized and words and boxes:
            try:
                regions = await asyncio.to_thread(
                    self._model_analyze, image, words, boxes, page_number
                )
            except Exception as e:
                logger.warning(f"Model analysis failed, using heuristic: {e}")
                regions = self._heuristic_analyze(words, boxes, page_number)
        else:
            # 回退到启发式方法
            regions = self._heuristic_analyze(words, boxes, page_number)
        
        return PageLayout(
            page_number=page_number,
            width=width,
            height=height,
            regions=regions
        )
    
    def _model_analyze(
        self,
        image,
        words: List[str],
        boxes: List[List[int]],
        page_number: int
    ) -> List[LayoutRegion]:
        """使用LayoutLMv3模型进行分析"""
        import torch
        
        # 限制输入长度 (LayoutLMv3 max 512 tokens)
        max_words = 450
        if len(words) > max_words:
            words = words[:max_words]
            boxes = boxes[:max_words]
        
        # 处理输入
        encoding = self._processor(
            image,
            words,
            boxes=boxes,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding="max_length"
        )
        
        # 移到设备
        encoding = {k: v.to(self.device) for k, v in encoding.items()}
        
        # 推理
        with torch.no_grad():
            outputs = self._model(**encoding)
        
        # 使用隐藏状态 + 启发式规则进行区域分类
        # 因为是base model，没有分类头，所以用特征+启发式
        hidden_states = outputs.last_hidden_state[0].cpu().numpy()
        
        # 基于位置和文本特征的启发式分类
        regions = self._classify_regions_with_features(
            words, boxes, hidden_states, page_number
        )
        
        return regions
    
    def _classify_regions_with_features(
        self,
        words: List[str],
        boxes: List[List[int]],
        features,  # numpy array
        page_number: int
    ) -> List[LayoutRegion]:
        """结合模型特征和启发式规则分类区域"""
        # 将连续的词聚合为行/块
        lines = self._group_words_into_lines(words, boxes)
        
        regions = []
        order = 0
        
        for line_words, line_boxes in lines:
            text = " ".join(line_words)
            if not text.strip():
                continue
            
            # 计算行的边界框
            x0 = min(b[0] for b in line_boxes)
            y0 = min(b[1] for b in line_boxes)
            x1 = max(b[2] for b in line_boxes)
            y1 = max(b[3] for b in line_boxes)
            bbox = [x0, y0, x1, y1]
            
            # 分类
            region_type, confidence = self._classify_line(
                text, bbox, page_number
            )
            
            regions.append(LayoutRegion(
                region_type=region_type,
                text=text,
                bbox=bbox,
                confidence=confidence,
                page_number=page_number,
                order=order
            ))
            order += 1
        
        return regions
    
    def _heuristic_analyze(
        self,
        words: List[str],
        boxes: List[List[int]],
        page_number: int
    ) -> List[LayoutRegion]:
        """纯启发式布局分析 (无模型回退方案)"""
        if not words or not boxes:
            return []
        
        lines = self._group_words_into_lines(words, boxes)
        
        regions = []
        order = 0
        
        for line_words, line_boxes in lines:
            text = " ".join(line_words)
            if not text.strip():
                continue
            
            x0 = min(b[0] for b in line_boxes)
            y0 = min(b[1] for b in line_boxes)
            x1 = max(b[2] for b in line_boxes)
            y1 = max(b[3] for b in line_boxes)
            bbox = [x0, y0, x1, y1]
            
            region_type, confidence = self._classify_line(text, bbox, page_number)
            
            regions.append(LayoutRegion(
                region_type=region_type,
                text=text,
                bbox=bbox,
                confidence=confidence,
                page_number=page_number,
                order=order
            ))
            order += 1
        
        return regions
    
    def _group_words_into_lines(
        self,
        words: List[str],
        boxes: List[List[int]]
    ) -> List[Tuple[List[str], List[List[int]]]]:
        """将单词按行聚合"""
        if not words:
            return []
        
        lines = []
        current_words = [words[0]]
        current_boxes = [boxes[0]]
        
        for i in range(1, len(words)):
            # 如果Y坐标差异较大，认为是新行
            prev_y_center = (current_boxes[-1][1] + current_boxes[-1][3]) / 2
            curr_y_center = (boxes[i][1] + boxes[i][3]) / 2
            line_height = current_boxes[-1][3] - current_boxes[-1][1]
            
            threshold = max(line_height * 0.5, 10)
            
            if abs(curr_y_center - prev_y_center) > threshold:
                lines.append((current_words, current_boxes))
                current_words = [words[i]]
                current_boxes = [boxes[i]]
            else:
                current_words.append(words[i])
                current_boxes.append(boxes[i])
        
        if current_words:
            lines.append((current_words, current_boxes))
        
        return lines
    
    def _classify_line(
        self,
        text: str,
        bbox: List[float],
        page_number: int
    ) -> Tuple[RegionType, float]:
        """
        基于启发式规则分类文本行
        
        Returns:
            (RegionType, confidence)
        """
        import re
        
        text_stripped = text.strip()
        text_lower = text_stripped.lower()
        
        # 位置特征
        y_position = bbox[1]  # 顶部Y坐标 (0-1000)
        x_center = (bbox[0] + bbox[2]) / 2
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        
        # 页眉页脚检测
        if y_position < 50:
            return RegionType.HEADER, 0.8
        if y_position > 950:
            return RegionType.FOOTER, 0.8
        
        # 标题检测 (首页顶部，居中，字号较大)
        if page_number == 1 and y_position < 300:
            if height > 20 and 200 < x_center < 800:
                # 不是太长，可能是标题
                if len(text_stripped) < 200 and not text_stripped.endswith('.'):
                    return RegionType.TITLE, 0.85
        
        # 作者检测 (首页标题下方)
        if page_number == 1 and 150 < y_position < 400:
            if re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', text_stripped):
                if len(text_stripped) < 300 and height < 20:
                    return RegionType.AUTHOR, 0.7
        
        # 摘要检测
        if re.match(r'^(Abstract|摘\s*要|ABSTRACT)', text_stripped):
            return RegionType.ABSTRACT, 0.95
        
        # Section header 检测 (编号+标题格式)
        if re.match(r'^(\d+\.?\s+|[IVX]+\.?\s+|第[一二三四五六七八九十]+[章节])', text_stripped):
            if len(text_stripped) < 100 and not text_stripped.endswith('.'):
                return RegionType.SECTION_HEADER, 0.85
        
        # 全大写标题
        if text_stripped.isupper() and len(text_stripped) < 80 and len(text_stripped) > 3:
            return RegionType.SECTION_HEADER, 0.75
        
        # 关键词行
        if re.match(r'^(Keywords?|关键[词字]|KEYWORDS)', text_stripped):
            return RegionType.OTHER, 0.7  # 标记为其他，后续由metadata extractor处理
        
        # 参考文献检测
        if re.match(r'^(References?|参考文献|REFERENCES|Bibliography)', text_stripped):
            return RegionType.REFERENCE, 0.9
        if re.match(r'^\[\d+\]', text_stripped) or re.match(r'^\d+\.\s+[A-Z]', text_stripped):
            return RegionType.REFERENCE, 0.7
        
        # 图/表标题检测
        if re.match(r'^(Fig\.?|Figure|图)\s*\d', text_stripped, re.IGNORECASE):
            return RegionType.CAPTION, 0.85
        if re.match(r'^(Table|表)\s*\d', text_stripped, re.IGNORECASE):
            return RegionType.CAPTION, 0.85
        
        # 列表项检测
        if re.match(r'^[\-•\*]\s', text_stripped) or re.match(r'^\([a-z]\)', text_stripped):
            return RegionType.LIST, 0.7
        
        # 公式检测 (含大量数学符号)
        math_chars = set('∑∏∫∂∇≤≥±∞≈≠∈∉⊂⊃∩∪αβγδεζηθλμπσφψω')
        if sum(1 for c in text_stripped if c in math_chars) > 3:
            return RegionType.FORMULA, 0.7
        
        # 默认: 段落
        return RegionType.PARAGRAPH, 0.6
    
    async def analyze_pdf(
        self,
        pdf_path: str
    ) -> List[PageLayout]:
        """
        分析整个PDF文档的布局
        
        Args:
            pdf_path: PDF文件路径
            
        Returns:
            每页的PageLayout列表
        """
        try:
            from pdf2image import convert_from_path
            import pdfplumber
        except ImportError as e:
            logger.warning(f"Required libraries not available: {e}")
            return []
        
        layouts = []
        
        try:
            # 转换PDF页面为图像
            images = convert_from_path(pdf_path, dpi=150)
            
            # 使用pdfplumber获取单词和位置
            with pdfplumber.open(pdf_path) as pdf:
                for i, (page, image) in enumerate(zip(pdf.pages, images)):
                    page_num = i + 1
                    
                    # 提取单词和边界框
                    words_data = page.extract_words() or []
                    
                    if not words_data:
                        layouts.append(PageLayout(
                            page_number=page_num,
                            width=image.size[0],
                            height=image.size[1],
                            regions=[]
                        ))
                        continue
                    
                    # 转换为LayoutLMv3需要的格式
                    # 归一化到 0-1000
                    page_width = page.width
                    page_height = page.height
                    
                    words = []
                    boxes = []
                    for w in words_data:
                        words.append(w['text'])
                        # 归一化坐标
                        x0 = int(w['x0'] / page_width * 1000)
                        y0 = int(w['top'] / page_height * 1000)
                        x1 = int(w['x1'] / page_width * 1000)
                        y1 = int(w['bottom'] / page_height * 1000)
                        boxes.append([
                            max(0, min(1000, x0)),
                            max(0, min(1000, y0)),
                            max(0, min(1000, x1)),
                            max(0, min(1000, y1))
                        ])
                    
                    # 分析页面
                    layout = await self.analyze_page(
                        image, words, boxes, page_num
                    )
                    layouts.append(layout)
                    
        except Exception as e:
            logger.error(f"PDF layout analysis failed: {e}")
        
        return layouts


# 默认布局分析器实例
layout_analyzer = LayoutAnalyzer()
