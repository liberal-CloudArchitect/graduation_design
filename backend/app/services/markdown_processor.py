"""
Markdown 后处理器

清洗 MinerU 输出的 Markdown，提取结构化元数据，
并提供 Markdown → 纯文本转换（用于交给现有 SemanticChunker）。
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SectionInfo:
    """章节信息 -- 固定 schema, 避免 Dict 字段漂移"""
    title: str
    level: int
    page_start: int
    page_end: Optional[int] = None
    anchor: Optional[str] = None


class MarkdownPostProcessor:
    """清洗 MinerU 输出的 Markdown"""

    def process(self, markdown: str) -> str:
        """清洗步骤:
        1. 合并跨行段落断行
        2. 标准化 LaTeX 公式分隔符
        3. 标准化 Markdown 表格格式
        4. 移除页眉页脚噪声
        """
        text = markdown

        text = self._remove_header_footer_noise(text)
        text = self._merge_broken_paragraphs(text)
        text = self._normalize_latex(text)
        text = self._normalize_tables(text)
        text = self._normalize_whitespace(text)

        return text

    def extract_metadata(self, markdown: str) -> Dict[str, Any]:
        """从 Markdown 结构中提取元数据"""
        return {
            "title": self._extract_title(markdown),
            "abstract": self._extract_abstract(markdown),
            "section_titles": self._extract_section_titles(markdown),
            "has_tables": self._has_tables(markdown),
            "has_formulas": self._has_formulas(markdown),
            "has_figures": self._has_figures(markdown),
        }

    def extract_sections(
        self, markdown: str, pages_info: Optional[List[Dict]] = None
    ) -> List[SectionInfo]:
        """从 Markdown 标题中提取章节列表 (SectionInfo)"""
        sections: List[SectionInfo] = []
        page_boundaries = self._build_page_boundaries(markdown, pages_info)

        for m in re.finditer(r"^(#{1,3})\s+(.+)$", markdown, re.MULTILINE):
            level = len(m.group(1))
            title = m.group(2).strip()
            if not title:
                continue
            char_pos = m.start()
            page_start = self._char_pos_to_page(char_pos, page_boundaries)
            sections.append(
                SectionInfo(
                    title=title,
                    level=level,
                    page_start=page_start,
                    page_end=None,
                    anchor=None,
                )
            )

        # Fill page_end from next section's page_start
        for i, sec in enumerate(sections):
            if i + 1 < len(sections):
                sec.page_end = sections[i + 1].page_start
            else:
                sec.page_end = sec.page_start

        return sections

    def markdown_to_plain_text(self, markdown: str) -> str:
        """将 Markdown 转为纯文本 (去除标记符号)。

        Phase 1 不改 chunker，MinerU 输出经此函数转为纯文本后
        交给现有 SemanticChunker 分块。
        """
        text = markdown

        # Remove headings markers but keep text
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

        # Convert bold/italic markers
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"_(.+?)_", r"\1", text)

        # Remove image syntax, keep alt text
        text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)

        # Remove link syntax, keep text
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)

        # Simplify table rows to text
        text = re.sub(r"\|", " ", text)
        # Remove table separator lines
        text = re.sub(r"^[\s\-:]+$", "", text, flags=re.MULTILINE)

        # Keep inline math as-is (LaTeX readable)
        # Keep block math as-is

        # Clean excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        return text.strip()

    # ---- private helpers ----

    def _remove_header_footer_noise(self, text: str) -> str:
        """Remove common header/footer patterns (page numbers, running headers)"""
        # Page numbers alone on a line
        text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
        # Running header/footer with page numbers
        text = re.sub(
            r"^.*Page\s+\d+\s+of\s+\d+.*$", "", text, flags=re.MULTILINE | re.IGNORECASE
        )
        return text

    def _merge_broken_paragraphs(self, text: str) -> str:
        """Merge lines that are broken mid-sentence (hyphenated line breaks)"""
        text = re.sub(r"-\n(\S)", r"\1", text)
        return text

    def _normalize_latex(self, text: str) -> str:
        """Standardize LaTeX delimiters"""
        # \( ... \) -> $ ... $
        text = re.sub(r"\\\((.+?)\\\)", r"$\1$", text)
        # \[ ... \] -> $$ ... $$
        text = re.sub(r"\\\[(.+?)\\\]", r"$$\1$$", text, flags=re.DOTALL)
        return text

    def _normalize_tables(self, text: str) -> str:
        """Clean up Markdown table formatting"""
        # Normalize separator rows
        text = re.sub(r"\|[\s:]*-{2,}[\s:]*", "| --- ", text)
        return text

    def _normalize_whitespace(self, text: str) -> str:
        """Collapse excessive blank lines"""
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        return text.strip()

    def _extract_title(self, markdown: str) -> Optional[str]:
        m = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
        return m.group(1).strip() if m else None

    def _extract_abstract(self, markdown: str) -> Optional[str]:
        m = re.search(
            r"(?:^#{1,3}\s+(?:Abstract|摘\s*要)\s*\n)([\s\S]+?)(?=\n#{1,3}\s+|\Z)",
            markdown,
            re.MULTILINE | re.IGNORECASE,
        )
        if m:
            abstract = m.group(1).strip()
            if len(abstract) > 50:
                return abstract[:2000]
        return None

    def _extract_section_titles(self, markdown: str) -> List[str]:
        return [
            m.group(2).strip()
            for m in re.finditer(r"^(#{1,3})\s+(.+)$", markdown, re.MULTILINE)
            if m.group(2).strip()
        ]

    def _has_tables(self, markdown: str) -> bool:
        return bool(re.search(r"\|.+\|.+\|", markdown))

    def _has_formulas(self, markdown: str) -> bool:
        return bool(
            re.search(r"\$\$.+?\$\$", markdown, re.DOTALL)
            or re.search(r"(?<!\$)\$(?!\$)(?!\s).+?(?<!\s)(?<!\$)\$(?!\$)", markdown)
        )

    def _has_figures(self, markdown: str) -> bool:
        return bool(re.search(r"!\[.*?\]\(.*?\)", markdown))

    def _build_page_boundaries(
        self, markdown: str, pages_info: Optional[List[Dict]]
    ) -> List[int]:
        """Build cumulative char-offset list for page boundaries."""
        if not pages_info:
            return []
        offsets = []
        cumulative = 0
        for p in sorted(pages_info, key=lambda x: x.get("page_number", 0)):
            offsets.append(cumulative)
            cumulative += len(p.get("markdown", "")) + 2  # +2 for join separator
        return offsets

    def _char_pos_to_page(self, char_pos: int, boundaries: List[int]) -> int:
        """Map a character position to a 1-based page number."""
        if not boundaries:
            return 1
        page = 1
        for i, offset in enumerate(boundaries):
            if char_pos >= offset:
                page = i + 1
            else:
                break
        return page
