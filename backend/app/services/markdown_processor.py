"""
Markdown 后处理器

清洗 MinerU 输出的 Markdown，提取结构化元数据，
并提供 Markdown → 纯文本转换（用于交给现有 SemanticChunker）。

Phase 2 新增: MarkdownSectionSplitter -- 将 Markdown 切分为带有文本跨度、
稳定锚点和父子层级的 SectionNode 树，供 HierarchicalChunker 使用。
"""
import re
import unicodedata
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


@dataclass
class SectionNode:
    """Hierarchical section representation with text spans and stable anchors."""
    title: str
    level: int
    path: str
    anchor: str
    text: str
    char_start: int
    char_end: int
    page_start: int
    page_end: int
    children: List["SectionNode"] = field(default_factory=list)


def _slugify(text: str, max_len: int = 128) -> str:
    """Generate a stable, URL-safe slug from a section path."""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_>]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len]


class MarkdownSectionSplitter:
    """Split raw Markdown into a hierarchical SectionNode tree.

    Uses heading regex to find section boundaries, builds a tree based on
    heading level, and maps headings to page numbers via pre-computed
    SectionInfo objects (doc.sections) from the parsing stage.
    """

    _HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    def split(
        self,
        markdown: str,
        existing_sections: Optional[List[SectionInfo]] = None,
    ) -> List[SectionNode]:
        """Parse markdown into a tree of SectionNode objects.

        Args:
            markdown: full cleaned markdown (doc.raw_markdown).
            existing_sections: pre-computed SectionInfo list (doc.sections) with
                correct page numbers. Used for page mapping. If None, all pages
                default to 1.

        Returns:
            Flat list of *leaf* SectionNodes (sections with no children).
            These serve as parent chunk candidates for HierarchicalChunker.
        """
        if not markdown or not markdown.strip():
            return []

        headings = list(self._HEADING_RE.finditer(markdown))

        if not headings:
            node = SectionNode(
                title="(document)",
                level=0,
                path="(document)",
                anchor="sec-document",
                text=markdown,
                char_start=0,
                char_end=len(markdown),
                page_start=1,
                page_end=1,
                children=[],
            )
            return [node]

        page_map = self._build_page_map(existing_sections)

        raw_sections: List[SectionNode] = []
        for i, match in enumerate(headings):
            level = len(match.group(1))
            title = match.group(2).strip()
            char_start = match.start()
            char_end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
            text = markdown[char_start:char_end]

            page_start, page_end = self._lookup_pages(title, level, page_map)
            raw_sections.append(SectionNode(
                title=title,
                level=level,
                path=title,
                anchor="",
                text=text,
                char_start=char_start,
                char_end=char_end,
                page_start=page_start,
                page_end=page_end,
                children=[],
            ))

        root_nodes = self._build_tree(raw_sections)
        self._assign_paths_and_anchors(root_nodes, prefix="")

        leaves: List[SectionNode] = []
        self._collect_leaves(root_nodes, leaves)
        return leaves

    def _build_page_map(
        self, existing_sections: Optional[List[SectionInfo]]
    ) -> Dict[str, List[SectionInfo]]:
        """Create (title_lower, level) -> [SectionInfo, ...] lookup.

        Multiple sections with the same title/level are stored in document
        order and consumed sequentially via _lookup_pages.
        """
        if not existing_sections:
            return {}
        mapping: Dict[str, List[SectionInfo]] = {}
        for sec in existing_sections:
            key = f"{sec.title.strip().lower()}|{sec.level}"
            mapping.setdefault(key, []).append(sec)
        return mapping

    def _lookup_pages(
        self, title: str, level: int,
        page_map: Dict[str, List[SectionInfo]],
    ) -> tuple:
        key = f"{title.strip().lower()}|{level}"
        entries = page_map.get(key)
        if entries:
            sec = entries.pop(0)
            return sec.page_start, sec.page_end or sec.page_start
        return 1, 1

    def _build_tree(self, sections: List[SectionNode]) -> List[SectionNode]:
        """Stack-based tree builder: lower-level headings nest under higher ones."""
        root: List[SectionNode] = []
        stack: List[SectionNode] = []

        for sec in sections:
            while stack and stack[-1].level >= sec.level:
                stack.pop()

            if stack:
                stack[-1].children.append(sec)
            else:
                root.append(sec)
            stack.append(sec)

        return root

    def _assign_paths_and_anchors(
        self, nodes: List[SectionNode], prefix: str,
    ) -> None:
        seen_anchors: Dict[str, int] = {}

        def _walk(current_nodes: List[SectionNode], current_prefix: str) -> None:
            for node in current_nodes:
                node.path = (
                    f"{current_prefix} > {node.title}".strip(" >")
                    if current_prefix else node.title
                )
                base = f"sec-{_slugify(node.path)}"
                count = seen_anchors.get(base, 0) + 1
                seen_anchors[base] = count
                node.anchor = base if count == 1 else f"{base}-{count}"
                _walk(node.children, node.path)

        _walk(nodes, prefix)

    def _collect_leaves(
        self, nodes: List[SectionNode], leaves: List[SectionNode]
    ) -> None:
        for node in nodes:
            if node.children:
                self._collect_leaves(node.children, leaves)
            else:
                leaves.append(node)


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
        try:
            from app.core.config import settings
            populate_anchors = settings.HIERARCHICAL_CHUNKING_ENABLED
        except Exception:
            populate_anchors = False

        sections: List[SectionInfo] = []
        page_boundaries = self._build_page_boundaries(markdown, pages_info)
        path_stack: List[tuple] = []
        seen_anchors: Dict[str, int] = {}

        for m in re.finditer(r"^(#{1,3})\s+(.+)$", markdown, re.MULTILINE):
            level = len(m.group(1))
            title = m.group(2).strip()
            if not title:
                continue
            char_pos = m.start()
            page_start = self._char_pos_to_page(char_pos, page_boundaries)
            anchor: Optional[str] = None
            if populate_anchors:
                while path_stack and path_stack[-1][0] >= level:
                    path_stack.pop()
                if path_stack:
                    full_path = f"{path_stack[-1][1]} > {title}"
                else:
                    full_path = title
                path_stack.append((level, full_path))
                base = f"sec-{_slugify(full_path)}"
                count = seen_anchors.get(base, 0) + 1
                seen_anchors[base] = count
                anchor = base if count == 1 else f"{base}-{count}"
            sections.append(
                SectionInfo(
                    title=title,
                    level=level,
                    page_start=page_start,
                    page_end=None,
                    anchor=anchor,
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
