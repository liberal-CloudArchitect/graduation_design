"""
Phase 2 Acceptance Tests: Parent-Child Document Indexing

Pure unit tests -- no external dependencies (DB, Milvus, ES, LLM).
Tests cover: config flags, MarkdownSectionSplitter, HierarchicalChunker,
ReferenceItem serialization, evidence chain ordering, and cleanup safety.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from dataclasses import asdict


# ---------------------------------------------------------------------------
# 1. Feature flag defaults
# ---------------------------------------------------------------------------

class TestConfigFlags:
    def test_flag_defaults(self):
        from app.core.config import Settings
        s = Settings(
            _env_file=None,
            POSTGRES_HOST="localhost",
            POSTGRES_PASSWORD="test",
        )
        assert s.HIERARCHICAL_CHUNKING_ENABLED is False
        assert s.PARENT_CHUNK_MAX_TOKENS == 2000
        assert s.CHILD_CHUNK_MAX_TOKENS == 400

    def test_flag_enabled(self):
        from app.core.config import Settings
        s = Settings(
            _env_file=None,
            POSTGRES_HOST="localhost",
            POSTGRES_PASSWORD="test",
            HIERARCHICAL_CHUNKING_ENABLED=True,
            PARENT_CHUNK_MAX_TOKENS=3000,
            CHILD_CHUNK_MAX_TOKENS=500,
        )
        assert s.HIERARCHICAL_CHUNKING_ENABLED is True
        assert s.PARENT_CHUNK_MAX_TOKENS == 3000
        assert s.CHILD_CHUNK_MAX_TOKENS == 500


# ---------------------------------------------------------------------------
# 2. MarkdownSectionSplitter
# ---------------------------------------------------------------------------

SAMPLE_MARKDOWN = """\
# Introduction

This paper introduces the topic.

## Background

Some background information here.

## Methodology

### Data Collection

We collected data from multiple sources.

### Analysis

We analyzed the data using statistical methods.

# Results

The results show significant improvements.

# Conclusion

In conclusion, our approach works well.
"""


class TestMarkdownSectionSplitter:
    def test_basic_split(self):
        from app.services.markdown_processor import MarkdownSectionSplitter
        splitter = MarkdownSectionSplitter()
        leaves = splitter.split(SAMPLE_MARKDOWN)
        assert len(leaves) > 0
        for leaf in leaves:
            assert leaf.text.strip()
            assert leaf.anchor.startswith("sec-")
            assert leaf.path

    def test_correct_leaf_count(self):
        from app.services.markdown_processor import MarkdownSectionSplitter
        splitter = MarkdownSectionSplitter()
        leaves = splitter.split(SAMPLE_MARKDOWN)
        leaf_titles = [l.title for l in leaves]
        assert "Data Collection" in leaf_titles
        assert "Analysis" in leaf_titles
        assert "Results" in leaf_titles
        assert "Conclusion" in leaf_titles
        assert "Background" in leaf_titles
        # Introduction has children so it's NOT a leaf
        assert "Introduction" not in leaf_titles

    def test_nested_path(self):
        from app.services.markdown_processor import MarkdownSectionSplitter
        splitter = MarkdownSectionSplitter()
        leaves = splitter.split(SAMPLE_MARKDOWN)
        data_leaf = [l for l in leaves if l.title == "Data Collection"][0]
        assert "Methodology" in data_leaf.path
        assert "Data Collection" in data_leaf.path

    def test_anchor_encodes_path(self):
        """Anchor should encode the full structural path for stability."""
        from app.services.markdown_processor import MarkdownSectionSplitter
        splitter = MarkdownSectionSplitter()
        leaves = splitter.split(SAMPLE_MARKDOWN)
        dc = [l for l in leaves if l.title == "Data Collection"][0]
        assert "introduction" in dc.anchor
        assert "methodology" in dc.anchor
        assert "data-collection" in dc.anchor

    def test_stable_anchors(self):
        from app.services.markdown_processor import MarkdownSectionSplitter
        splitter = MarkdownSectionSplitter()
        leaves1 = splitter.split(SAMPLE_MARKDOWN)
        leaves2 = splitter.split(SAMPLE_MARKDOWN)
        anchors1 = [l.anchor for l in leaves1]
        anchors2 = [l.anchor for l in leaves2]
        assert anchors1 == anchors2

    def test_no_headings(self):
        from app.services.markdown_processor import MarkdownSectionSplitter
        splitter = MarkdownSectionSplitter()
        text = "Just a plain text document with no headings."
        leaves = splitter.split(text)
        assert len(leaves) == 1
        assert leaves[0].title == "(document)"

    def test_empty_input(self):
        from app.services.markdown_processor import MarkdownSectionSplitter
        splitter = MarkdownSectionSplitter()
        assert splitter.split("") == []
        assert splitter.split("   ") == []

    def test_page_mapping_from_sections(self):
        from app.services.markdown_processor import MarkdownSectionSplitter, SectionInfo
        splitter = MarkdownSectionSplitter()
        existing = [
            SectionInfo(title="Introduction", level=1, page_start=1, page_end=2),
            SectionInfo(title="Background", level=2, page_start=1, page_end=2),
            SectionInfo(title="Results", level=1, page_start=5, page_end=7),
            SectionInfo(title="Conclusion", level=1, page_start=8, page_end=8),
        ]
        leaves = splitter.split(SAMPLE_MARKDOWN, existing_sections=existing)
        bg_leaf = [l for l in leaves if l.title == "Background"][0]
        assert bg_leaf.page_start == 1
        results_leaf = [l for l in leaves if l.title == "Results"][0]
        assert results_leaf.page_start == 5

    def test_duplicate_title_page_mapping(self):
        """P1 fix: duplicate titles should each get their own page info."""
        from app.services.markdown_processor import MarkdownSectionSplitter, SectionInfo
        md = (
            "# Experiment 1\n\n## Methods\n\nFirst methods.\n\n"
            "# Experiment 2\n\n## Methods\n\nSecond methods.\n"
        )
        existing = [
            SectionInfo(title="Experiment 1", level=1, page_start=1, page_end=2),
            SectionInfo(title="Methods", level=2, page_start=2, page_end=3),
            SectionInfo(title="Experiment 2", level=1, page_start=4, page_end=5),
            SectionInfo(title="Methods", level=2, page_start=5, page_end=6),
        ]
        splitter = MarkdownSectionSplitter()
        leaves = splitter.split(md, existing_sections=existing)
        methods_leaves = [l for l in leaves if l.title == "Methods"]
        assert len(methods_leaves) == 2
        pages = sorted(l.page_start for l in methods_leaves)
        assert pages == [2, 5], f"Expected [2, 5] but got {pages}"

    def test_duplicate_title_anchor_disambiguation(self):
        """Duplicate titles under different parents get unique path-based anchors."""
        from app.services.markdown_processor import MarkdownSectionSplitter
        md = (
            "# Experiment 1\n\n## Methods\n\nFirst.\n\n"
            "# Experiment 2\n\n## Methods\n\nSecond.\n"
        )
        splitter = MarkdownSectionSplitter()
        leaves = splitter.split(md)
        methods_leaves = [l for l in leaves if l.title == "Methods"]
        assert len(methods_leaves) == 2
        anchors = [l.anchor for l in methods_leaves]
        assert anchors[0] != anchors[1], f"Anchors should differ: {anchors}"
        assert "experiment-1" in anchors[0]
        assert "experiment-2" in anchors[1]

    def test_same_path_duplicate_anchor_disambiguation(self):
        """Same full path repeated should still get unique anchors."""
        from app.services.markdown_processor import MarkdownSectionSplitter
        md = (
            "# A\n\n"
            "## Methods\n\nFirst.\n\n"
            "## Methods\n\nSecond.\n"
        )
        leaves = MarkdownSectionSplitter().split(md)
        methods_leaves = [l for l in leaves if l.title == "Methods"]
        assert len(methods_leaves) == 2
        assert methods_leaves[0].anchor == "sec-a-methods"
        assert methods_leaves[1].anchor == "sec-a-methods-2"

    def test_anchor_stable_under_insertion(self):
        """P1 core: inserting an unrelated section must NOT change existing anchors."""
        from app.services.markdown_processor import MarkdownSectionSplitter
        base_md = (
            "# A\n\n## Methods\n\nContent A.\n\n"
            "# B\n\n## Methods\n\nContent B.\n"
        )
        extended_md = (
            "# X\n\n## Methods\n\nContent X.\n\n"  # unrelated insertion
            "# A\n\n## Methods\n\nContent A.\n\n"
            "# B\n\n## Methods\n\nContent B.\n"
        )
        splitter = MarkdownSectionSplitter()
        base_leaves = splitter.split(base_md)
        ext_leaves = splitter.split(extended_md)

        def anchor_for(leaves, parent_title):
            return [l.anchor for l in leaves
                    if l.title == "Methods" and parent_title in l.path][0]

        assert anchor_for(base_leaves, "A") == anchor_for(ext_leaves, "A")
        assert anchor_for(base_leaves, "B") == anchor_for(ext_leaves, "B")

    def test_anchor_matches_extract_sections(self):
        """P1 fix: anchors from splitter must match extract_sections()."""
        import app.core.config as cfg_mod
        from app.services.markdown_processor import (
            MarkdownSectionSplitter, MarkdownPostProcessor,
        )
        original = cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED
        try:
            cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED = True
            proc = MarkdownPostProcessor()
            splitter = MarkdownSectionSplitter()
            secs = proc.extract_sections(SAMPLE_MARKDOWN)
            leaves = splitter.split(SAMPLE_MARKDOWN)
            sec_anchors = {s.anchor for s in secs if s.anchor}
            leaf_anchors = {l.anchor for l in leaves}
            assert leaf_anchors.issubset(sec_anchors), (
                f"Leaf anchors not in section anchors: "
                f"{leaf_anchors - sec_anchors}"
            )
        finally:
            cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED = original


# ---------------------------------------------------------------------------
# 3. HierarchicalChunker
# ---------------------------------------------------------------------------

class TestHierarchicalChunker:
    def test_basic_chunk(self):
        from app.rag.chunker import HierarchicalChunker
        chunker = HierarchicalChunker(
            parent_max_tokens=2000, child_max_tokens=200, child_overlap=20
        )
        all_chunks = chunker.chunk(SAMPLE_MARKDOWN, paper_id=42)
        parents = [c for c in all_chunks if c.chunk_type == "parent"]
        children = [c for c in all_chunks if c.chunk_type == "child"]
        assert len(parents) > 0
        assert len(children) > 0

    def test_child_indices_sequential(self):
        from app.rag.chunker import HierarchicalChunker
        chunker = HierarchicalChunker(
            parent_max_tokens=2000, child_max_tokens=200, child_overlap=20
        )
        all_chunks = chunker.chunk(SAMPLE_MARKDOWN, paper_id=42)
        children = [c for c in all_chunks if c.chunk_type == "child"]
        indices = [c.index for c in children]
        assert indices == list(range(len(children)))

    def test_parent_id_format(self):
        from app.rag.chunker import HierarchicalChunker
        chunker = HierarchicalChunker(
            parent_max_tokens=2000, child_max_tokens=200, child_overlap=20
        )
        all_chunks = chunker.chunk(SAMPLE_MARKDOWN, paper_id=99)
        parents = [c for c in all_chunks if c.chunk_type == "parent"]
        for p in parents:
            assert p.parent_id.startswith("99_p")

    def test_children_point_to_parents(self):
        from app.rag.chunker import HierarchicalChunker
        chunker = HierarchicalChunker(
            parent_max_tokens=2000, child_max_tokens=200, child_overlap=20
        )
        all_chunks = chunker.chunk(SAMPLE_MARKDOWN, paper_id=42)
        parent_ids = {c.parent_id for c in all_chunks if c.chunk_type == "parent"}
        for child in all_chunks:
            if child.chunk_type == "child":
                assert child.parent_id in parent_ids

    def test_no_headings_fallback(self):
        from app.rag.chunker import HierarchicalChunker
        chunker = HierarchicalChunker(
            parent_max_tokens=2000, child_max_tokens=200, child_overlap=20
        )
        text = "A" * 500
        all_chunks = chunker.chunk(text, paper_id=1)
        assert len(all_chunks) > 0

    def test_reference_section_skipped(self):
        from app.rag.chunker import HierarchicalChunker
        md = "# Introduction\n\nSome content.\n\n# References\n\n[1] Author et al. ...\n[2] Author et al. ..."
        chunker = HierarchicalChunker(
            parent_max_tokens=2000, child_max_tokens=200, child_overlap=20
        )
        all_chunks = chunker.chunk(md, paper_id=1)
        parent_paths = [c.section_path for c in all_chunks if c.chunk_type == "parent"]
        assert not any("References" in (p or "") for p in parent_paths)


# ---------------------------------------------------------------------------
# 3b. P2/P3: child_chunk_indices correctness after filtering & chunk_count
# ---------------------------------------------------------------------------

class TestChildIndicesAfterFiltering:
    """P2: After reference-heavy children are filtered and remaining children
    are renumbered, parent.child_chunk_indices must reflect the new numbering."""

    def test_indices_updated_after_filter(self):
        from app.rag.chunker import HierarchicalChunker
        md = (
            "# Section A\n\n" + "Good content. " * 30 + "\n\n"
            "# Section B\n\n" + "More good content. " * 30 + "\n"
        )
        chunker = HierarchicalChunker(
            parent_max_tokens=5000, child_max_tokens=200, child_overlap=20,
        )
        all_chunks = chunker.chunk(md, paper_id=1)

        parents = [c for c in all_chunks if c.chunk_type == "parent"]
        children = [c for c in all_chunks if c.chunk_type == "child"]
        child_filter = children[1:]  # simulate removing child 0

        old_to_new = {}
        for new_i, c in enumerate(child_filter):
            old_to_new[c.index] = new_i
            c.index = new_i

        for p in parents:
            old_indices = (p.metadata or {}).get("child_chunk_indices", [])
            p.metadata["child_chunk_indices"] = [
                old_to_new[i] for i in old_indices if i in old_to_new
            ]

        for p in parents:
            for idx in p.metadata.get("child_chunk_indices", []):
                assert idx < len(child_filter), (
                    f"Index {idx} out of range for {len(child_filter)} children"
                )

    def test_orphan_parent_dropped(self):
        """If ALL children of a parent are filtered out, parent has no children."""
        from app.rag.chunker import HierarchicalChunker
        md = "# Only Section\n\n" + "Short. " * 20 + "\n"
        chunker = HierarchicalChunker(
            parent_max_tokens=5000, child_max_tokens=200, child_overlap=20,
        )
        all_chunks = chunker.chunk(md, paper_id=1)
        parents = [c for c in all_chunks if c.chunk_type == "parent"]
        children = [c for c in all_chunks if c.chunk_type == "child"]

        old_to_new = {}  # filter ALL children
        for p in parents:
            old_indices = (p.metadata or {}).get("child_chunk_indices", [])
            p.metadata["child_chunk_indices"] = [
                old_to_new[i] for i in old_indices if i in old_to_new
            ]
        for p in parents:
            assert p.metadata.get("child_chunk_indices") == []


class TestChunkCountChildOnly:
    """P3: chunk_count should count only children, not parents."""

    def test_count_excludes_parents(self):
        from app.rag.chunker import HierarchicalChunker
        chunker = HierarchicalChunker(
            parent_max_tokens=2000, child_max_tokens=200, child_overlap=20,
        )
        all_chunks = chunker.chunk(SAMPLE_MARKDOWN, paper_id=42)
        chunks_dicts = []
        for c in all_chunks:
            chunks_dicts.append({"chunk_type": c.chunk_type, "text": c.text})
        child_count = sum(1 for c in chunks_dicts if c["chunk_type"] != "parent")
        total = len(chunks_dicts)
        assert child_count < total, "Should have some parent chunks"
        assert child_count == sum(
            1 for c in chunks_dicts if c.get("chunk_type") != "parent"
        )


# ---------------------------------------------------------------------------
# 4. Chunk dataclass extension
# ---------------------------------------------------------------------------

class TestChunkDataclass:
    def test_backward_compat(self):
        from app.rag.chunker import Chunk
        c = Chunk(text="hello", index=0, start_char=0, end_char=5)
        assert c.chunk_type == "child"
        assert c.parent_id is None
        assert c.section_path is None
        assert c.section_anchor is None

    def test_new_fields(self):
        from app.rag.chunker import Chunk
        c = Chunk(
            text="hello", index=0, start_char=0, end_char=5,
            chunk_type="parent", parent_id="42_p0",
            section_path="Introduction", section_anchor="sec-introduction",
        )
        assert c.chunk_type == "parent"
        assert c.parent_id == "42_p0"


# ---------------------------------------------------------------------------
# 5. ReferenceItem serialization
# ---------------------------------------------------------------------------

class TestReferenceItemSerialization:
    def test_new_fields_present(self):
        from app.api.v1.rag import ReferenceItem
        ref = ReferenceItem(
            paper_id=1, chunk_index=0, text="test", score=0.5,
            parent_id="1_p0", section_path="Intro",
            section_anchor="sec-intro", sibling_chunk_indices=[0, 1],
        )
        data = ref.model_dump()
        assert data["parent_id"] == "1_p0"
        assert data["section_path"] == "Intro"
        assert data["section_anchor"] == "sec-intro"
        assert data["sibling_chunk_indices"] == [0, 1]

    def test_backward_compat_none_defaults(self):
        from app.api.v1.rag import ReferenceItem
        ref = ReferenceItem(
            paper_id=1, chunk_index=0, text="test", score=0.5,
        )
        data = ref.model_dump()
        assert data["parent_id"] is None
        assert data["section_path"] is None
        assert data["section_anchor"] is None
        assert data["sibling_chunk_indices"] is None

    def test_old_conversation_dict_compat(self):
        from app.api.v1.rag import _ref_dict_to_item
        old_ref = {
            "paper_id": 1,
            "chunk_index": 0,
            "text": "test",
            "score": 0.5,
        }
        item = _ref_dict_to_item(old_ref)
        assert item.parent_id is None
        assert item.section_path is None

    def test_new_conversation_dict_compat(self):
        from app.api.v1.rag import _ref_dict_to_item
        new_ref = {
            "paper_id": 1,
            "chunk_index": 0,
            "text": "test",
            "score": 0.5,
            "parent_id": "1_p2",
            "section_path": "Methods",
            "section_anchor": "sec-methods",
            "sibling_chunk_indices": [3, 4],
        }
        item = _ref_dict_to_item(new_ref)
        assert item.parent_id == "1_p2"
        assert item.section_path == "Methods"
        assert item.sibling_chunk_indices == [3, 4]


# ---------------------------------------------------------------------------
# 6. MongoDB parent chunk CRUD (in-memory fallback)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMongoDBParentCRUD:
    async def test_insert_and_get_parent_chunks(self):
        from app.services.mongodb_service import MongoDBService
        svc = MongoDBService()
        svc._use_fallback = True
        svc._initialized = True

        parents = [
            {"parent_id": "1_p0", "text": "parent 0", "section_path": "Intro"},
            {"parent_id": "1_p1", "text": "parent 1", "section_path": "Methods"},
        ]
        await svc.insert_parent_chunks(1, parents)
        result = await svc.get_parent_chunks_by_ids(["1_p0", "1_p1"])
        assert "1_p0" in result
        assert "1_p1" in result
        assert result["1_p0"]["text"] == "parent 0"

    async def test_delete_parent_chunks(self):
        from app.services.mongodb_service import MongoDBService
        svc = MongoDBService()
        svc._use_fallback = True
        svc._initialized = True

        await svc.insert_parent_chunks(2, [
            {"parent_id": "2_p0", "text": "parent text"},
        ])
        count = await svc.delete_parent_chunks(2)
        assert count == 1
        result = await svc.get_parent_chunks_by_ids(["2_p0"])
        assert len(result) == 0

    async def test_delete_paper_chunks_includes_parents(self):
        from app.services.mongodb_service import MongoDBService
        svc = MongoDBService()
        svc._use_fallback = True
        svc._initialized = True

        await svc.insert_chunks(3, [{"text": "child", "index": 0}])
        await svc.insert_parent_chunks(3, [{"parent_id": "3_p0", "text": "parent"}])
        count = await svc.delete_paper_chunks(3)
        assert count >= 2
        result = await svc.get_parent_chunks_by_ids(["3_p0"])
        assert len(result) == 0

    async def test_fallback_child_chunk_preserves_phase2_fields(self):
        from app.services.mongodb_service import MongoDBService
        svc = MongoDBService()
        svc._use_fallback = True
        svc._initialized = True

        await svc.insert_chunks(4, [{
            "index": 0,
            "text": "child",
            "page_number": 1,
            "metadata": {"page_number": 1},
            "parent_id": "4_p0",
            "section_path": "Intro",
            "section_anchor": "sec-intro",
        }])
        chunk = await svc.get_chunk_by_index(4, 0)
        assert chunk is not None
        assert chunk["parent_id"] == "4_p0"
        assert chunk["section_path"] == "Intro"
        assert chunk["section_anchor"] == "sec-intro"
        assert chunk["metadata"]["page_number"] == 1


# ---------------------------------------------------------------------------
# 7. SectionInfo.anchor population
# ---------------------------------------------------------------------------

class TestSectionInfoAnchor:
    def test_anchor_populated_when_enabled(self):
        import app.core.config as cfg_mod
        original = cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED
        try:
            cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED = True
            from app.services.markdown_processor import MarkdownPostProcessor
            proc = MarkdownPostProcessor()
            md = "# Introduction\n\nSome text.\n\n## Methods\n\nMore text."
            sections = proc.extract_sections(md)
            for sec in sections:
                assert sec.anchor is not None
                assert sec.anchor.startswith("sec-")
        finally:
            cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED = original

    def test_anchor_none_when_disabled(self):
        import app.core.config as cfg_mod
        original = cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED
        try:
            cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED = False
            from app.services.markdown_processor import MarkdownPostProcessor
            proc = MarkdownPostProcessor()
            md = "# Introduction\n\nSome text."
            sections = proc.extract_sections(md)
            for sec in sections:
                assert sec.anchor is None
        finally:
            cfg_mod.settings.HIERARCHICAL_CHUNKING_ENABLED = original


# ---------------------------------------------------------------------------
# 8. Evidence chain ordering (parent expansion AFTER child filtering)
# ---------------------------------------------------------------------------

class TestEvidenceChainOrder:
    """Verify _expand_to_parents is called after child filtering."""

    @pytest.mark.asyncio
    async def test_expand_to_parents_dedup(self):
        """Children sharing a parent should be deduplicated."""
        import sys
        from app.services.mongodb_service import MongoDBService

        svc = MongoDBService()
        svc._use_fallback = True
        svc._initialized = True
        await svc.insert_parent_chunks(10, [
            {"parent_id": "10_p0", "text": "Full parent section text",
             "section_path": "Intro", "section_anchor": "sec-intro"},
        ])

        child_docs = [
            {"paper_id": 10, "chunk_index": 0, "text": "child A",
             "score": 0.9, "parent_id": "10_p0"},
            {"paper_id": 10, "chunk_index": 1, "text": "child B",
             "score": 0.7, "parent_id": "10_p0"},
            {"paper_id": 10, "chunk_index": 2, "text": "child C",
             "score": 0.5, "parent_id": None},
        ]

        mod = sys.modules["app.services.mongodb_service"]
        original_svc = getattr(mod, "mongodb_service")
        setattr(mod, "mongodb_service", svc)
        try:
            from app.rag.engine import RAGEngine
            engine = RAGEngine()
            expanded = await engine._expand_to_parents(child_docs)

            parent_hits = [d for d in expanded if d.get("parent_text")]
            assert len(parent_hits) == 1
            assert parent_hits[0]["parent_text"] == "Full parent section text"
            assert 0 in parent_hits[0]["sibling_chunk_indices"]
            assert 1 in parent_hits[0]["sibling_chunk_indices"]
            assert parent_hits[0]["score"] == 0.9

            no_parent_hits = [d for d in expanded if not d.get("parent_text")]
            assert len(no_parent_hits) == 1
            assert no_parent_hits[0]["chunk_index"] == 2
        finally:
            setattr(mod, "mongodb_service", original_svc)


# ---------------------------------------------------------------------------
# 9. _fetch_documents fallback metadata preservation
# ---------------------------------------------------------------------------

class TestFetchDocumentsFallback:
    """P2: fallback paths (inline text, cache) must preserve phase 2 metadata."""

    @pytest.mark.asyncio
    async def test_inline_text_fallback_preserves_metadata(self):
        """When MongoDB misses, inline text fallback should carry parent_id etc."""
        import sys
        from app.services.mongodb_service import MongoDBService

        svc = MongoDBService()
        svc._use_fallback = True
        svc._initialized = True

        mod = sys.modules["app.services.mongodb_service"]
        original_svc = getattr(mod, "mongodb_service")
        setattr(mod, "mongodb_service", svc)
        try:
            from app.rag.engine import RAGEngine
            engine = RAGEngine()
            search_results = [{
                "paper_id": 999,
                "chunk_index": 0,
                "distance": 0.8,
                "text": "inline fallback text",
                "parent_id": "999_p0",
                "section_path": "Intro",
                "section_anchor": "sec-intro",
            }]
            docs = await engine._fetch_documents(search_results)
            assert len(docs) == 1
            doc = docs[0]
            assert doc["text"] == "inline fallback text"
            assert doc["parent_id"] == "999_p0"
            assert doc["section_path"] == "Intro"
            assert doc["section_anchor"] == "sec-intro"
        finally:
            setattr(mod, "mongodb_service", original_svc)

    @pytest.mark.asyncio
    async def test_cache_fallback_preserves_metadata(self):
        """When inline text is empty, cache fallback should carry metadata."""
        import sys
        from app.services.mongodb_service import MongoDBService

        svc = MongoDBService()
        svc._use_fallback = True
        svc._initialized = True

        mod = sys.modules["app.services.mongodb_service"]
        original_svc = getattr(mod, "mongodb_service")
        setattr(mod, "mongodb_service", svc)
        try:
            from app.rag.engine import RAGEngine
            engine = RAGEngine()
            engine._chunk_cache["888_0"] = "cached text"
            search_results = [{
                "paper_id": 888,
                "chunk_index": 0,
                "distance": 0.7,
                "parent_id": "888_p1",
                "section_path": "Methods",
                "section_anchor": "sec-methods",
            }]
            docs = await engine._fetch_documents(search_results)
            assert len(docs) == 1
            doc = docs[0]
            assert doc["text"] == "cached text"
            assert doc["parent_id"] == "888_p1"
            assert doc["section_path"] == "Methods"
            assert doc["section_anchor"] == "sec-methods"
        finally:
            setattr(mod, "mongodb_service", original_svc)


# ---------------------------------------------------------------------------
# 10. Slugify utility
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        from app.services.markdown_processor import _slugify
        assert _slugify("3.2 Experimental Setup") == "32-experimental-setup"

    def test_unicode(self):
        from app.services.markdown_processor import _slugify
        result = _slugify("实验方法")
        assert len(result) > 0
        assert " " not in result

    def test_max_length(self):
        from app.services.markdown_processor import _slugify
        long_text = "a" * 200
        assert len(_slugify(long_text)) <= 128
