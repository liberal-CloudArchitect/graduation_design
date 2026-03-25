"""
Phase 2 runtime regressions.

These tests focus on the enabled hierarchical chunking runtime path, not the
pure unit coverage already present in test_phase2_acceptance.py.
"""
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock


class TestMongoParentFallback:
    @pytest.mark.asyncio
    async def test_parent_chunk_write_failure_switches_to_fallback(self):
        from app.services.mongodb_service import MongoDBService

        class BrokenParentCollection:
            async def insert_many(self, docs):
                raise RuntimeError("mongo unavailable")

        svc = MongoDBService()
        svc.db = SimpleNamespace(paper_parent_chunks=BrokenParentCollection())
        svc._initialized = True
        svc._use_fallback = False

        parent_chunks = [
            {
                "parent_id": "7_p0",
                "text": "parent section",
                "section_path": "Intro",
                "section_anchor": "sec-intro",
                "child_chunk_indices": [0, 1],
                "page_range": [2, 4],
            }
        ]

        ids = await svc.insert_parent_chunks(7, parent_chunks)

        assert ids == ["7_p0"]
        assert svc._use_fallback is True
        stored = await svc.get_parent_chunks_by_ids(["7_p0"])
        assert stored["7_p0"]["text"] == "parent section"
        assert stored["7_p0"]["section_anchor"] == "sec-intro"


class TestEvidencePipelineConsistency:
    @pytest.mark.asyncio
    async def test_search_enriched_uses_same_prepare_evidence_pipeline(self):
        from app.rag.engine import RAGEngine

        docs = [
            {
                "paper_id": 1,
                "chunk_index": 2,
                "text": "child text",
                "page_number": 5,
                "parent_id": "1_p0",
                "section_path": "Intro > Methods",
                "section_anchor": "sec-intro-methods",
                "sibling_chunk_indices": [2, 3],
            }
        ]
        prepare = AsyncMock(return_value=([], docs, {"final_doc_count": 1}))

        engine = RAGEngine()
        engine._prepare_evidence = prepare
        engine.llm = SimpleNamespace(
            ainvoke=AsyncMock(return_value=SimpleNamespace(content="answer"))
        )

        answer_result = await engine.answer("What changed?", project_id=10, paper_ids=[1])
        search_result = await engine.search_enriched(
            "What changed?", project_id=10, top_k=5, paper_ids=[1]
        )

        assert answer_result["references"] == docs
        assert search_result == docs
        assert prepare.await_count == 2
        assert prepare.await_args_list[0].kwargs["use_memory"] is True
        assert prepare.await_args_list[1].kwargs["use_memory"] is False
