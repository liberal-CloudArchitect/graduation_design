(mineru) root@autodl-container-5jqgz9cnpj-b3bf0e7a:~/autodl-tmp/graduation_design/backend# MINERU_URL=http://127.0.0.1:8010 \
python tests/run_phase_checks.py

==> Phase 1 component tests
    /root/miniconda3/envs/mineru/bin/pytest tests/test_phase1_components.py -q
...............................                                                                                                                             [100%]
======================================================================== warnings summary =========================================================================
tests/test_phase1_components.py::TestMarkdownPostProcessor::test_extract_sections
  /root/autodl-tmp/graduation_design/backend/tests/../app/core/config.py:9: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
31 passed, 1 warning in 0.21s
    [OK] Phase 1 component tests

==> Phase 1 MinerU acceptance
    /root/miniconda3/envs/mineru/bin/python tests/test_phase1_acceptance.py

============================================================================
  Phase 1 验收测试 — MinerU PDF 解析集成
============================================================================
MinerU Service: http://127.0.0.1:8010
Test PDFs found: 27
  dual_column: 3 files
  formula_heavy: 5 files
  table_heavy: 8 files
  scan: 10 files
  simple: 1 files

--- Test 1: MinerU Service Health Check ─────────────────────────
  Status:           ok
  Parse Backend:    mineru_official
  Configured Backend: hybrid-http-client
  Model Loaded:     True
  GPU Total MB:     32109
  GPU Used MB:      22257
  GPU Free MB:      9851
  Pipeline Device:  cuda
  Active Jobs:      0
  Waiting Jobs:     0
  Max Concurrent:   2
  vLLM Healthy:     True
  vLLM URL:         http://127.0.0.1:30000
  Parser Version:   N/A
  Backend Error:    None
  [PASS] Service is healthy

--- Test 2: PDF Parsing Quality (by category) ───────────────────

  [1/27] Parsing [dual_column] He_2016_Deep_Residual_Learning_CVPR.pdf ... OK (19586ms) score=85 md=45535ch secs=14 tbl=0 formula_blk=2 formula_inl=79 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [2/27] Parsing [dual_column] Huang_2017_DenseNet_CVPR.pdf ... OK (23604ms) score=85 md=48123ch secs=13 tbl=0 formula_blk=2 formula_inl=140 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [3/27] Parsing [dual_column] Xie_2017_ResNeXt_CVPR.pdf ... OK (21287ms) score=85 md=45815ch secs=17 tbl=0 formula_blk=4 formula_inl=126 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [4/27] Parsing [formula_heavy] Devlin_2018_BERT.pdf ... OK (21604ms) score=85 md=67650ch secs=35 tbl=0 formula_blk=6 formula_inl=109 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [5/27] Parsing [formula_heavy] Ho_2020_DDPM.pdf ... OK (24106ms) score=85 md=71217ch secs=24 tbl=0 formula_blk=19 formula_inl=193 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [6/27] Parsing [formula_heavy] Kingma_2013_Auto-Encoding_Variational_Bayes.pdf ... OK (22594ms) score=85 md=60642ch secs=23 tbl=0 formula_blk=37 formula_inl=261 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [7/27] Parsing [formula_heavy] Kingma_2014_Adam.pdf ... OK (17538ms) score=85 md=53709ch secs=21 tbl=0 formula_blk=28 formula_inl=284 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [8/27] Parsing [formula_heavy] Vaswani_2017_Attention_Is_All_You_Need.pdf ... OK (18133ms) score=85 md=42933ch secs=26 tbl=0 formula_blk=7 formula_inl=76 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [9/27] Parsing [table_heavy] Camelot_assam.pdf ... OK (14573ms) score=50 md=3876ch secs=0 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [10/27] Parsing [table_heavy] Camelot_birdisland.pdf ... OK (28808ms) score=65 md=12294ch secs=6 tbl=0 formula_blk=0 formula_inl=50 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [11/27] Parsing [table_heavy] Camelot_budget.pdf ... OK (24894ms) score=50 md=6890ch secs=0 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [12/27] Parsing [table_heavy] Camelot_diesel_engines.pdf ... OK (31588ms) score=65 md=104047ch secs=82 tbl=0 formula_blk=0 formula_inl=129 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [13/27] Parsing [table_heavy] Camelot_multiple_tables.pdf ... OK (2917ms) score=50 md=823ch secs=0 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [14/27] Parsing [table_heavy] Camelot_table_region.pdf ... OK (8380ms) score=50 md=2410ch secs=0 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [15/27] Parsing [table_heavy] Camelot_vertical_header.pdf ... OK (14921ms) score=65 md=18933ch secs=4 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [16/27] Parsing [table_heavy] PDFPlumber_ca_warn_report.pdf ... OK (40486ms) score=50 md=98709ch secs=0 tbl=0 formula_blk=0 formula_inl=2 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [17/27] Parsing [scan] OCRmyPDF_3small.pdf ... OK (4127ms) score=78 md=659ch secs=2 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [18/27] Parsing [scan] OCRmyPDF_c02-22.pdf ... OK (4289ms) score=78 md=1262ch secs=1 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [19/27] Parsing [scan] OCRmyPDF_cardinal.pdf ... OK (18139ms) score=85 md=16088ch secs=15 tbl=0 formula_blk=0 formula_inl=3 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [20/27] Parsing [scan] OCRmyPDF_ccitt.pdf ... OK (10315ms) score=85 md=4451ch secs=6 tbl=0 formula_blk=0 formula_inl=1 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [21/27] Parsing [scan] OCRmyPDF_jbig2.pdf ... OK (10520ms) score=85 md=4451ch secs=6 tbl=0 formula_blk=0 formula_inl=1 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [22/27] Parsing [scan] OCRmyPDF_linn.pdf ... OK (10148ms) score=85 md=4451ch secs=6 tbl=0 formula_blk=0 formula_inl=1 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [23/27] Parsing [scan] OCRmyPDF_multipage.pdf ... OK (7030ms) score=78 md=7521ch secs=1 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [24/27] Parsing [scan] OCRmyPDF_poster.pdf ... OK (10958ms) score=85 md=4633ch secs=6 tbl=0 formula_blk=0 formula_inl=1 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [25/27] Parsing [scan] OCRmyPDF_tagged.pdf ... OK (3106ms) score=68 md=274ch secs=3 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[none]
    (cooling down 30s for GPU memory)

  [26/27] Parsing [scan] OCRmyPDF_toc.pdf ... OK (1591ms) score=45 md=134ch secs=0 tbl=0 formula_blk=0 formula_inl=0 garble=0.000 issues=[LOW_CHARS_PER_PAGE(67)]
    (cooling down 30s for GPU memory)

  [27/27] Parsing [simple] test_arxiv.pdf ... OK (18050ms) score=80 md=42938ch secs=26 tbl=0 formula_blk=7 formula_inl=76 garble=0.000 issues=[none]

--- Test 3: Acceptance Criteria Evaluation ──────────────────────

  Parse success rate: 27/27 (100.0%)

  [Criterion 1] Complex PDF avg quality score: 73.0/100 [PASS] (target ≥ 50)
    dual_column: avg=85.0 (n=3)
    formula_heavy: avg=85.0 (n=5)
    table_heavy: avg=55.6 (n=8)
    scan: avg=77.2 (n=10)

  [Criterion 2] Formula detection rate: 5/5 (100.0%) [PASS] (target ≥ 50%)
    Total LaTeX blocks: 97, inline: 923

  [Criterion 3] Table detection rate: 0/8 (0.0%) [WARN] (target ≥ 50%)
    Total Markdown tables detected: 0

  [Criterion 4] Parse latency: avg=16048ms, p95=31588ms, max=40486ms [PASS] (timeout=180s)

  [Criterion 5] Fallback mechanism: 0 failures, all handled=yes [PASS]

  [Criterion 6] API response compatibility: [PASS]

--- Test 4: Content Quality Spot Checks ─────────────────────────

  Spot check: Vaswani_2017_Attention_Is_All_You_Need
    Length: 42933 chars
    Contains 'attention': True
    Contains 'transformer': True
    Block equations: 7
    First equation preview: $$
\operatorname {A t t e n t i o n} (Q, K, V) = \operatorname {s o f t m a x} \left(\frac {Q K ^ {T}}{\sqrt {d _ {k}}}\...

  Spot check: Xie_2017_ResNeXt_CVPR
    Length: 45815 chars
    Contains 'residual': True

--- Test 5: Markdown Structure Validation ───────────────────────
    All structure checks passed

============================================================================
  Phase 1 验收总结
============================================================================
  [PASS] 1. 复杂论文解析质量 — avg_score=73.0
  [PASS] 2. 公式还原 (LaTeX) — rate=100.0%
  [WARN] 3. 表格还原 (Markdown) — rate=0.0%
  [PASS] 4. 解析性能 — p95=31588ms
  [PASS] 5. 降级机制 — failures=0
  [PASS] 6. API 兼容性 — response structure OK

  Overall: 5/6 criteria passed

  △ Phase 1 基本可用 — 建议修复 WARN 项后进入阶段 2

--- Detailed Results Table ──────────────────────────────────────
  File                                          Cat            Score    Time Secs Tbl   Eq  Garble Issues
  ─────────────────────────────────────────────────────────────────────────────────────────────────────────
  Devlin_2018_BERT                              formula_heavy     85  21604ms   35   0  115  0.000 -
  He_2016_Deep_Residual_Learning_CVPR           dual_column       85  19586ms   14   0   81  0.000 -
  Ho_2020_DDPM                                  formula_heavy     85  24106ms   24   0  212  0.000 -
  Huang_2017_DenseNet_CVPR                      dual_column       85  23604ms   13   0  142  0.000 -
  Kingma_2013_Auto-Encoding_Variational_Bayes   formula_heavy     85  22594ms   23   0  298  0.000 -
  Kingma_2014_Adam                              formula_heavy     85  17538ms   21   0  312  0.000 -
  OCRmyPDF_cardinal                             scan              85  18139ms   15   0    3  0.000 -
  OCRmyPDF_ccitt                                scan              85  10315ms    6   0    1  0.000 -
  OCRmyPDF_jbig2                                scan              85  10520ms    6   0    1  0.000 -
  OCRmyPDF_linn                                 scan              85  10148ms    6   0    1  0.000 -
  OCRmyPDF_poster                               scan              85  10958ms    6   0    1  0.000 -
  Vaswani_2017_Attention_Is_All_You_Need        formula_heavy     85  18133ms   26   0   83  0.000 -
  Xie_2017_ResNeXt_CVPR                         dual_column       85  21287ms   17   0  130  0.000 -
  test_arxiv                                    simple            80  18050ms   26   0   83  0.000 -
  OCRmyPDF_3small                               scan              78   4127ms    2   0    0  0.000 -
  OCRmyPDF_c02-22                               scan              78   4289ms    1   0    0  0.000 -
  OCRmyPDF_multipage                            scan              78   7030ms    1   0    0  0.000 -
  OCRmyPDF_tagged                               scan              68   3106ms    3   0    0  0.000 -
  Camelot_birdisland                            table_heavy       65  28808ms    6   0   50  0.000 -
  Camelot_diesel_engines                        table_heavy       65  31588ms   82   0  129  0.000 -
  Camelot_vertical_header                       table_heavy       65  14921ms    4   0    0  0.000 -
  Camelot_assam                                 table_heavy       50  14573ms    0   0    0  0.000 -
  Camelot_budget                                table_heavy       50  24894ms    0   0    0  0.000 -
  Camelot_multiple_tables                       table_heavy       50   2917ms    0   0    0  0.000 -
  Camelot_table_region                          table_heavy       50   8380ms    0   0    0  0.000 -
  PDFPlumber_ca_warn_report                     table_heavy       50  40486ms    0   0    2  0.000 -
  OCRmyPDF_toc                                  scan              45   1591ms    0   0    0  0.000 LOW_CHARS_PER_PAGE(67)

  Results saved to: /root/autodl-tmp/graduation_design/backend/tests/phase1_acceptance_results.json
    [OK] Phase 1 MinerU acceptance

==> Phase 2 acceptance tests
    /root/miniconda3/envs/mineru/bin/pytest tests/test_phase2_acceptance.py -q
F.............F...........FFFF....FFFFF...                                                                                                                  [100%]
============================================================================ FAILURES =============================================================================
_______________________________________________________________ TestConfigFlags.test_flag_defaults ________________________________________________________________

self = <test_phase2_acceptance.TestConfigFlags object at 0x7f75edbe3550>

    def test_flag_defaults(self):
>       from app.core.config import Settings

tests/test_phase2_acceptance.py:19: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
app/core/__init__.py:3: in <module>
    from app.core.security import (
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    Security utilities - JWT authentication
    """
    from datetime import datetime, timedelta
    from typing import Optional, Union
>   from jose import JWTError, jwt
E   ModuleNotFoundError: No module named 'jose'

app/core/security.py:6: ModuleNotFoundError
________________________________________________ TestMarkdownSectionSplitter.test_anchor_matches_extract_sections _________________________________________________

self = <test_phase2_acceptance.TestMarkdownSectionSplitter object at 0x7f75edbe3220>

    def test_anchor_matches_extract_sections(self):
        """P1 fix: anchors from splitter must match extract_sections()."""
>       import app.core.config as cfg_mod
E       ImportError: cannot import name 'core' from 'app' (/root/autodl-tmp/graduation_design/backend/app/__init__.py)

tests/test_phase2_acceptance.py:232: ImportError
_____________________________________________________ TestReferenceItemSerialization.test_new_fields_present ______________________________________________________

self = <test_phase2_acceptance.TestReferenceItemSerialization object at 0x7f75ec77d300>

    def test_new_fields_present(self):
>       from app.api.v1.rag import ReferenceItem

tests/test_phase2_acceptance.py:431: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    RAG API - RAG问答路由
    """
    from typing import List, Optional, Dict
    from fastapi import APIRouter, Depends, HTTPException, status, Query
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
>   from sqlalchemy.ext.asyncio import AsyncSession
E   ModuleNotFoundError: No module named 'sqlalchemy'

app/api/v1/rag.py:8: ModuleNotFoundError
________________________________________________ TestReferenceItemSerialization.test_backward_compat_none_defaults ________________________________________________

self = <test_phase2_acceptance.TestReferenceItemSerialization object at 0x7f75edbe36a0>

    def test_backward_compat_none_defaults(self):
>       from app.api.v1.rag import ReferenceItem

tests/test_phase2_acceptance.py:444: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    RAG API - RAG问答路由
    """
    from typing import List, Optional, Dict
    from fastapi import APIRouter, Depends, HTTPException, status, Query
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
>   from sqlalchemy.ext.asyncio import AsyncSession
E   ModuleNotFoundError: No module named 'sqlalchemy'

app/api/v1/rag.py:8: ModuleNotFoundError
________________________________________________ TestReferenceItemSerialization.test_old_conversation_dict_compat _________________________________________________

self = <test_phase2_acceptance.TestReferenceItemSerialization object at 0x7f75edbe3df0>

    def test_old_conversation_dict_compat(self):
>       from app.api.v1.rag import _ref_dict_to_item

tests/test_phase2_acceptance.py:455: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    RAG API - RAG问答路由
    """
    from typing import List, Optional, Dict
    from fastapi import APIRouter, Depends, HTTPException, status, Query
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
>   from sqlalchemy.ext.asyncio import AsyncSession
E   ModuleNotFoundError: No module named 'sqlalchemy'

app/api/v1/rag.py:8: ModuleNotFoundError
________________________________________________ TestReferenceItemSerialization.test_new_conversation_dict_compat _________________________________________________

self = <test_phase2_acceptance.TestReferenceItemSerialization object at 0x7f75ec77d750>

    def test_new_conversation_dict_compat(self):
>       from app.api.v1.rag import _ref_dict_to_item

tests/test_phase2_acceptance.py:467: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    RAG API - RAG问答路由
    """
    from typing import List, Optional, Dict
    from fastapi import APIRouter, Depends, HTTPException, status, Query
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
>   from sqlalchemy.ext.asyncio import AsyncSession
E   ModuleNotFoundError: No module named 'sqlalchemy'

app/api/v1/rag.py:8: ModuleNotFoundError
____________________________________________________ TestSectionInfoAnchor.test_anchor_populated_when_enabled _____________________________________________________

self = <test_phase2_acceptance.TestSectionInfoAnchor object at 0x7f75ec77ff40>

    def test_anchor_populated_when_enabled(self):
>       import app.core.config as cfg_mod
E       ImportError: cannot import name 'core' from 'app' (/root/autodl-tmp/graduation_design/backend/app/__init__.py)

tests/test_phase2_acceptance.py:562: ImportError
______________________________________________________ TestSectionInfoAnchor.test_anchor_none_when_disabled _______________________________________________________

self = <test_phase2_acceptance.TestSectionInfoAnchor object at 0x7f75ec77fb80>

    def test_anchor_none_when_disabled(self):
>       import app.core.config as cfg_mod
E       ImportError: cannot import name 'core' from 'app' (/root/autodl-tmp/graduation_design/backend/app/__init__.py)

tests/test_phase2_acceptance.py:577: ImportError
_______________________________________________________ TestEvidenceChainOrder.test_expand_to_parents_dedup _______________________________________________________

self = <test_phase2_acceptance.TestEvidenceChainOrder object at 0x7f75ec77f490>

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
>           from app.rag.engine import RAGEngine

tests/test_phase2_acceptance.py:625: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    RAG Engine - Core Implementation
    
    统一的 RAG 引擎，负责文档向量化、混合检索、重排序和生成流程。
    支持记忆增强、流式输出、对话历史、extra_context 注入和 paper_ids 筛选。
    """
    from typing import List, Optional, Dict, Any, AsyncGenerator, Tuple
    from loguru import logger
    import json
    import re
>   from sqlalchemy import select
E   ModuleNotFoundError: No module named 'sqlalchemy'

app/rag/engine.py:11: ModuleNotFoundError
_____________________________________________ TestFetchDocumentsFallback.test_inline_text_fallback_preserves_metadata _____________________________________________

self = <test_phase2_acceptance.TestFetchDocumentsFallback object at 0x7f75ec77cd90>

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
>           from app.rag.engine import RAGEngine

tests/test_phase2_acceptance.py:664: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    RAG Engine - Core Implementation
    
    统一的 RAG 引擎，负责文档向量化、混合检索、重排序和生成流程。
    支持记忆增强、流式输出、对话历史、extra_context 注入和 paper_ids 筛选。
    """
    from typing import List, Optional, Dict, Any, AsyncGenerator, Tuple
    from loguru import logger
    import json
    import re
>   from sqlalchemy import select
E   ModuleNotFoundError: No module named 'sqlalchemy'

app/rag/engine.py:11: ModuleNotFoundError
________________________________________________ TestFetchDocumentsFallback.test_cache_fallback_preserves_metadata ________________________________________________

self = <test_phase2_acceptance.TestFetchDocumentsFallback object at 0x7f75ec77caf0>

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
>           from app.rag.engine import RAGEngine

tests/test_phase2_acceptance.py:699: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

    """
    RAG Engine - Core Implementation
    
    统一的 RAG 引擎，负责文档向量化、混合检索、重排序和生成流程。
    支持记忆增强、流式输出、对话历史、extra_context 注入和 paper_ids 筛选。
    """
    from typing import List, Optional, Dict, Any, AsyncGenerator, Tuple
    from loguru import logger
    import json
    import re
>   from sqlalchemy import select
E   ModuleNotFoundError: No module named 'sqlalchemy'

app/rag/engine.py:11: ModuleNotFoundError
======================================================================== warnings summary =========================================================================
tests/test_phase2_acceptance.py::TestConfigFlags::test_flag_defaults
  /root/autodl-tmp/graduation_design/backend/app/core/config.py:9: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.12/migration/
    class Settings(BaseSettings):

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
===================================================================== short test summary info =====================================================================
FAILED tests/test_phase2_acceptance.py::TestConfigFlags::test_flag_defaults - ModuleNotFoundError: No module named 'jose'
FAILED tests/test_phase2_acceptance.py::TestMarkdownSectionSplitter::test_anchor_matches_extract_sections - ImportError: cannot import name 'core' from 'app' (/root/autodl-tmp/graduation_design/backend/app/__init__.py)
FAILED tests/test_phase2_acceptance.py::TestReferenceItemSerialization::test_new_fields_present - ModuleNotFoundError: No module named 'sqlalchemy'
FAILED tests/test_phase2_acceptance.py::TestReferenceItemSerialization::test_backward_compat_none_defaults - ModuleNotFoundError: No module named 'sqlalchemy'
FAILED tests/test_phase2_acceptance.py::TestReferenceItemSerialization::test_old_conversation_dict_compat - ModuleNotFoundError: No module named 'sqlalchemy'
FAILED tests/test_phase2_acceptance.py::TestReferenceItemSerialization::test_new_conversation_dict_compat - ModuleNotFoundError: No module named 'sqlalchemy'
FAILED tests/test_phase2_acceptance.py::TestSectionInfoAnchor::test_anchor_populated_when_enabled - ImportError: cannot import name 'core' from 'app' (/root/autodl-tmp/graduation_design/backend/app/__init__.py)
FAILED tests/test_phase2_acceptance.py::TestSectionInfoAnchor::test_anchor_none_when_disabled - ImportError: cannot import name 'core' from 'app' (/root/autodl-tmp/graduation_design/backend/app/__init__.py)
FAILED tests/test_phase2_acceptance.py::TestEvidenceChainOrder::test_expand_to_parents_dedup - ModuleNotFoundError: No module named 'sqlalchemy'
FAILED tests/test_phase2_acceptance.py::TestFetchDocumentsFallback::test_inline_text_fallback_preserves_metadata - ModuleNotFoundError: No module named 'sqlalchemy'
FAILED tests/test_phase2_acceptance.py::TestFetchDocumentsFallback::test_cache_fallback_preserves_metadata - ModuleNotFoundError: No module named 'sqlalchemy'
11 failed, 31 passed, 1 warning in 0.51s
    [FAIL] Phase 2 acceptance tests (exit=1)
(mineru) root@autodl-container-5jqgz9cnpj-b3bf0e7a:~/autodl-tmp/graduation_design/backend# pip install sqlalchemy
Looking in indexes: http://mirrors.aliyun.com/pypi/simple
Collecting sqlalchemy
  Downloading http://mirrors.aliyun.com/pypi/packages/5c/ad/6c4395649a212a6c603a72c5b9ab5dce3135a1546cfdffa3c427e71fd535/sqlalchemy-2.0.48-cp310-cp310-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (3.2 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3.2/3.2 MB 3.3 MB/s  0:00:01
Collecting greenlet>=1 (from sqlalchemy)
  Downloading http://mirrors.aliyun.com/pypi/packages/ad/55/9f1ebb5a825215fadcc0f7d5073f6e79e3007e3282b14b22d6aba7ca6cb8/greenlet-3.3.2-cp310-cp310-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl (591 kB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 591.7/591.7 kB 6.8 MB/s  0:00:00
Requirement already satisfied: typing-extensions>=4.6.0 in /root/miniconda3/envs/mineru/lib/python3.10/site-packages (from sqlalchemy) (4.15.0)
Installing collected packages: greenlet, sqlalchemy
Successfully installed greenlet-3.3.2 sqlalchemy-2.0.48
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
(mineru) root@autodl-container-5jqgz9cnpj-b3bf0e7a:~/autodl-tmp/graduation_design/backend# 