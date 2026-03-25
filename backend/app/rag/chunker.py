"""
Text Chunker - 语义文本分块器
"""
from typing import List, Optional
import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """文本块"""
    text: str
    index: int
    start_char: int
    end_char: int
    metadata: dict = None
    chunk_type: str = "child"
    parent_id: Optional[str] = None
    section_path: Optional[str] = None
    section_anchor: Optional[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SemanticChunker:
    """
    语义文本分块器
    
    支持多种分割策略，优先保持语义完整性
    """
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or [
            "\n\n",      # 段落分隔
            "\n",        # 换行
            "。",        # 中文句号
            ".",         # 英文句号
            "；",        # 中文分号
            ";",         # 英文分号
            "，",        # 中文逗号
            ",",         # 英文逗号
            " ",         # 空格
            ""           # 字符级别
        ]
    
    def split_text(self, text: str, metadata: Optional[dict] = None) -> List[Chunk]:
        """
        将文本分割成多个块
        
        Args:
            text: 输入文本
            metadata: 附加元数据
            
        Returns:
            Chunk列表
        """
        if not text or not text.strip():
            return []
        
        # 清理文本
        text = self._clean_text(text)
        
        # 递归分割
        chunks_text = self._split_recursive(text, self.separators)
        
        # 合并小块
        merged = self._merge_small_chunks(chunks_text)
        
        # 创建Chunk对象
        chunks = []
        current_pos = 0
        for i, chunk_text in enumerate(merged):
            start = text.find(chunk_text, current_pos)
            if start == -1:
                start = current_pos
            end = start + len(chunk_text)
            
            chunk = Chunk(
                text=chunk_text,
                index=i,
                start_char=start,
                end_char=end,
                metadata=metadata.copy() if metadata else {}
            )
            chunks.append(chunk)
            current_pos = end - self.chunk_overlap
        
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """清理文本，保留有意义的段落结构"""
        # 移除特殊控制字符（保留 \n 和 \t）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        # 规范化段落分隔：将3个以上连续换行压缩为2个（保留段落结构）
        text = re.sub(r'\n{3,}', '\n\n', text)
        # 行内多余空白压缩为单个空格（不影响换行）
        text = re.sub(r'[^\S\n]+', ' ', text)
        # 移除每行首尾空白
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        return text.strip()
    
    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        """递归分割文本"""
        if not separators:
            # 没有分隔符了，按字符数分割
            return self._split_by_chars(text)
        
        separator = separators[0]
        
        if separator == "":
            # 空分隔符，按字符数分割
            return self._split_by_chars(text)
        
        # 按当前分隔符分割
        splits = text.split(separator)
        
        # 处理每个分割结果
        result = []
        for split in splits:
            if not split.strip():
                continue
            
            if len(split) <= self.chunk_size:
                result.append(split)
            else:
                # 递归使用下一个分隔符
                sub_splits = self._split_recursive(split, separators[1:])
                result.extend(sub_splits)
        
        return result
    
    def _split_by_chars(self, text: str) -> List[str]:
        """按字符数分割"""
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunks.append(text[start:end])
            if end >= len(text):
                break
            new_start = end - self.chunk_overlap
            if new_start <= start:
                break
            start = new_start
        return chunks
    
    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        """合并过小的块"""
        if not chunks:
            return []
        
        merged = []
        current = chunks[0]
        
        for i in range(1, len(chunks)):
            chunk = chunks[i]
            
            # 如果当前块太小，与下一个合并
            if len(current) < self.chunk_size // 2:
                current = current + " " + chunk
            # 如果合并后不超过限制，合并
            elif len(current) + len(chunk) + 1 <= self.chunk_size:
                current = current + " " + chunk
            else:
                merged.append(current.strip())
                current = chunk
        
        if current.strip():
            merged.append(current.strip())
        
        return merged


class OverlapChunker:
    """
    重叠分块器 - 简单按固定大小分块，带重叠
    """
    
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def split_text(self, text: str) -> List[str]:
        """分割文本"""
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            
            if chunk.strip():
                chunks.append(chunk.strip())
            
            start = end - self.overlap
            
        return chunks


class SentenceChunker:
    """
    句子分块器 - 按句子分割，确保语义完整
    """
    
    def __init__(self, max_sentences: int = 5, max_chars: int = 512):
        self.max_sentences = max_sentences
        self.max_chars = max_chars
        # 句子结束标记
        self.sentence_endings = re.compile(r'([。！？.!?])\s*')
    
    def split_text(self, text: str) -> List[str]:
        """按句子分割"""
        # 分割成句子
        sentences = self.sentence_endings.split(text)
        
        # 重新组合句子（标点符号会被分开）
        combined = []
        i = 0
        while i < len(sentences):
            if i + 1 < len(sentences) and len(sentences[i + 1]) == 1:
                combined.append(sentences[i] + sentences[i + 1])
                i += 2
            else:
                if sentences[i].strip():
                    combined.append(sentences[i])
                i += 1
        
        # 按句子数量和字符数分组
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in combined:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # 检查是否需要新建块
            if (len(current_chunk) >= self.max_sentences or 
                current_length + len(sentence) > self.max_chars):
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_length = len(sentence)
            else:
                current_chunk.append(sentence)
                current_length += len(sentence) + 1
        
        # 添加最后一个块
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks


class HierarchicalChunker:
    """Parent-child document chunker (Phase 2).

    Splits markdown into section-level parent chunks and sub-sentence child
    chunks.  Parent chunks are stored in MongoDB only (never embedded); child
    chunks are indexed in Milvus/ES/MongoDB with a ``parent_id`` pointer.
    """

    _REFERENCE_SECTION_RE = re.compile(
        r"^\s*#{0,3}\s*(references?|参考文献|bibliography)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    def __init__(
        self,
        parent_max_tokens: int = 2000,
        child_max_tokens: int = 400,
        child_overlap: int = 50,
    ):
        from app.services.markdown_processor import MarkdownSectionSplitter
        self.splitter = MarkdownSectionSplitter()
        self.child_chunker = SemanticChunker(
            chunk_size=child_max_tokens, chunk_overlap=child_overlap
        )
        self.parent_max_tokens = parent_max_tokens

    def chunk(
        self,
        markdown: str,
        paper_id: int,
        existing_sections=None,
    ) -> List[Chunk]:
        section_roots = self.splitter.split_tree(markdown, existing_sections)
        sections = list(self._iter_sections(section_roots))
        all_chunks: List[Chunk] = []
        child_seq = 0

        for p_seq, section in enumerate(sections):
            if self._is_reference_section(section.text):
                continue

            parent_id = f"{paper_id}_p{p_seq}"
            parent_text = section.text
            child_source_text = self._extract_child_source_text(section)
            parent_segments = self._split_text_with_spans(parent_text)

            if not parent_text.strip():
                continue

            parents = []
            for seg_idx, (seg_text, _, _) in enumerate(parent_segments):
                actual_parent_id = (
                    parent_id if len(parent_segments) == 1
                    else f"{parent_id}_{seg_idx}"
                )
                parent = Chunk(
                    text=seg_text,
                    index=-1,
                    start_char=section.char_start,
                    end_char=section.char_end,
                    metadata={
                        "page_start": section.page_start,
                        "page_end": section.page_end,
                        "parent_id": actual_parent_id,
                    },
                    chunk_type="parent",
                    parent_id=actual_parent_id,
                    section_path=section.path,
                    section_anchor=section.anchor,
                )
                parent.metadata["child_chunk_indices"] = []
                parents.append(parent)
                all_chunks.append(parent)

            if not child_source_text.strip():
                continue

            if len(child_source_text.strip()) < 20 and section.children:
                continue

            children = self.child_chunker.split_text(child_source_text)
            for child in children:
                assigned_parent = self._assign_parent_for_child(
                    parents=parents,
                    parent_segments=parent_segments,
                    child=child,
                )
                child.chunk_type = "child"
                child.parent_id = assigned_parent.parent_id
                child.section_path = section.path
                child.section_anchor = section.anchor
                child.index = child_seq
                child_page = self._estimate_page_number(
                    section=section,
                    chunk_start=child.start_char,
                    chunk_end=child.end_char,
                    source_len=len(child_source_text),
                )
                child.metadata = {
                    **(child.metadata or {}),
                    "page_number": child_page,
                    "page_start": child_page,
                    "page_end": child_page,
                    "parent_id": assigned_parent.parent_id,
                }
                assigned_parent.metadata["child_chunk_indices"].append(child_seq)
                child_seq += 1
                all_chunks.append(child)

        if not all_chunks:
            fallback = self.child_chunker.split_text(markdown)
            for i, c in enumerate(fallback):
                c.index = i
            return fallback

        return all_chunks

    def _iter_sections(self, nodes: List["SectionNode"]):
        """Yield section nodes in pre-order."""
        for node in nodes:
            yield node
            if node.children:
                yield from self._iter_sections(node.children)

    def _extract_child_source_text(self, section) -> str:
        """Return the section's own body text before the first child heading."""
        if not section.text:
            return ""

        if not section.children:
            return section.text

        direct_child_starts = [
            child.char_start for child in section.children
            if child.char_start > section.char_start
        ]
        if not direct_child_starts:
            return section.text

        body_end = min(direct_child_starts) - section.char_start
        if body_end <= 0:
            return ""
        return section.text[:body_end]

    def _estimate_page_number(
        self,
        section,
        chunk_start: int,
        chunk_end: int,
        source_len: int,
    ) -> int:
        """Estimate a chunk page number from its relative position in section text."""
        page_start = int(section.page_start or 1)
        page_end = int(section.page_end or page_start)
        if page_end <= page_start or source_len <= 0:
            return page_start

        span_pages = page_end - page_start + 1
        midpoint = (chunk_start + chunk_end) / 2.0
        ratio = midpoint / max(1, source_len)
        ratio = max(0.0, min(1.0, ratio))
        offset = min(span_pages - 1, int(ratio * span_pages))
        return page_start + offset

    def _split_text_with_spans(self, text: str) -> List[tuple[str, int, int]]:
        """Split parent text while keeping spans in the original section text."""
        if len(text) <= self.parent_max_tokens:
            return [(text, 0, len(text))]

        paragraphs = re.split(r"\n{2,}", text)
        segments: List[str] = []
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > self.parent_max_tokens:
                segments.append(current.strip())
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current.strip():
            segments.append(current.strip())

        if not segments:
            return [(text, 0, len(text))]

        spans: List[tuple[str, int, int]] = []
        cursor = 0
        for segment in segments:
            if len(segment) > self.parent_max_tokens:
                hard_parts = self._split_long_segment(segment)
                hard_cursor = cursor
                for hard_part in hard_parts:
                    start = text.find(hard_part, hard_cursor)
                    if start < 0:
                        start = hard_cursor
                    end = start + len(hard_part)
                    spans.append((hard_part, start, end))
                    hard_cursor = end
                cursor = hard_cursor
                continue
            start = text.find(segment, cursor)
            if start < 0:
                start = cursor
            end = start + len(segment)
            spans.append((segment, start, end))
            cursor = end
        return spans

    def _split_long_segment(self, text: str) -> List[str]:
        """Hard-split a single oversized paragraph to enforce parent_max_tokens."""
        return [
            text[i:i + self.parent_max_tokens]
            for i in range(0, len(text), self.parent_max_tokens)
            if text[i:i + self.parent_max_tokens].strip()
        ]

    def _assign_parent_for_child(self, parents, parent_segments, child: Chunk) -> Chunk:
        """Attach a child chunk to the parent segment that contains its midpoint."""
        if len(parents) == 1:
            return parents[0]

        midpoint = (child.start_char + child.end_char) / 2.0
        for parent, (_, seg_start, seg_end) in zip(parents, parent_segments):
            if seg_start <= midpoint <= seg_end:
                return parent

        return parents[-1]

    def _maybe_split_oversized(self, text: str) -> List[str]:
        """Split a section that exceeds parent_max_tokens at paragraph boundaries."""
        if len(text) <= self.parent_max_tokens:
            return [text]

        paragraphs = re.split(r"\n{2,}", text)
        parts: List[str] = []
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > self.parent_max_tokens:
                parts.append(current.strip())
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current.strip():
            parts.append(current.strip())
        return parts if parts else [text]

    def _is_reference_section(self, text: str) -> bool:
        snippet = text[:400]
        return bool(self._REFERENCE_SECTION_RE.search(snippet))


# 默认分块器实例（使用配置中的参数）
def _get_default_chunker() -> SemanticChunker:
    try:
        from app.core.config import settings
        return SemanticChunker(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP
        )
    except Exception:
        return SemanticChunker()

default_chunker = _get_default_chunker()


def chunk_text(
    text: str, 
    chunk_size: Optional[int] = None, 
    overlap: Optional[int] = None
) -> List[Chunk]:
    """
    便捷函数：分割文本
    
    Args:
        text: 输入文本
        chunk_size: 块大小（默认使用配置值）
        overlap: 重叠大小（默认使用配置值）
        
    Returns:
        Chunk列表
    """
    try:
        from app.core.config import settings
        cs = chunk_size or settings.CHUNK_SIZE
        ov = overlap or settings.CHUNK_OVERLAP
    except Exception:
        cs = chunk_size or 1024
        ov = overlap or 128
    
    chunker = SemanticChunker(chunk_size=cs, chunk_overlap=ov)
    return chunker.split_text(text)
