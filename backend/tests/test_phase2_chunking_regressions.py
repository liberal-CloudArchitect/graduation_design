"""
Phase 2 chunking regressions.

These tests cover the two user-facing issues introduced by hierarchical
chunking:
1. non-leaf section body text must remain indexable;
2. child chunk page numbers should vary across a multi-page section.
"""

from app.rag.chunker import HierarchicalChunker
from app.services.markdown_processor import MarkdownSectionSplitter, SectionInfo


def test_split_tree_preserves_internal_sections():
    md = """\
# Introduction

Intro body paragraph.

## Background

Background body.

### Details

Details body.

## Methods

Methods body.
"""

    splitter = MarkdownSectionSplitter()
    roots = splitter.split_tree(md)
    leaves = splitter.split(md)

    intro = next(node for node in roots if node.title == "Introduction")
    assert intro.children, "Root tree should keep nested sections"
    assert intro.path == "Introduction"
    assert any(child.title == "Background" for child in intro.children)

    leaf_titles = [leaf.title for leaf in leaves]
    assert "Introduction" not in leaf_titles
    assert "Details" in leaf_titles
    assert "Methods" in leaf_titles


def test_hierarchical_chunker_keeps_non_leaf_body_text():
    md = """\
# Introduction

Intro body paragraph that must not be lost.

## Background

Background body.

## Methods

Methods body.
"""

    chunks = HierarchicalChunker(
        parent_max_tokens=2000,
        child_max_tokens=120,
        child_overlap=20,
    ).chunk(md, paper_id=11)

    intro_parents = [
        c for c in chunks
        if c.chunk_type == "parent" and c.section_path == "Introduction"
    ]
    assert intro_parents
    assert any("Intro body paragraph" in c.text for c in intro_parents)

    intro_children = [
        c for c in chunks
        if c.chunk_type == "child" and c.section_path == "Introduction"
    ]
    assert intro_children
    assert any("Intro body paragraph" in c.text for c in intro_children)


def test_hierarchical_chunker_spreads_pages_across_multi_page_sections():
    md = "# Long Section\n\n" + ("This is a long paragraph. " * 180)
    sections = [SectionInfo(title="Long Section", level=1, page_start=3, page_end=5)]

    chunks = HierarchicalChunker(
        parent_max_tokens=4000,
        child_max_tokens=160,
        child_overlap=20,
    ).chunk(md, paper_id=27, existing_sections=sections)

    child_pages = [
        c.metadata.get("page_number")
        for c in chunks
        if c.chunk_type == "child"
    ]

    assert child_pages
    assert min(child_pages) == 3
    assert max(child_pages) == 5
    assert len(set(child_pages)) >= 2


def test_hierarchical_chunker_respects_parent_max_tokens():
    md = "# Long Section\n\n" + ("Paragraph content. " * 220)

    chunks = HierarchicalChunker(
        parent_max_tokens=500,
        child_max_tokens=160,
        child_overlap=20,
    ).chunk(md, paper_id=31)

    parents = [c for c in chunks if c.chunk_type == "parent"]
    children = [c for c in chunks if c.chunk_type == "child"]
    assert len(parents) >= 2
    assert all(len(c.text) <= 500 for c in parents)
    assert children
    parent_ids = {c.parent_id for c in parents}
    assert all(c.parent_id in parent_ids for c in children)
    assert any(c.metadata.get("child_chunk_indices") for c in parents)
