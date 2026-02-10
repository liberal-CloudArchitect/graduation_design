---
name: Fix Project Subpages
overview: "Fix 4 major issues across the project detail subpages: empty visualization charts, knowledge graph timeout, trend analysis data gaps, and memory system serialization errors."
todos:
  - id: fix-paper-keywords
    content: Fix process_paper_async() to save keywords and publication_date from PDF parsing to the Paper model
    status: completed
  - id: fix-trend-timeline
    content: Fix TrendAnalyzer.get_timeline() to use paper.publication_date instead of non-existent paper.year; add abstract-based keyword fallback in get_keyword_frequency() and get_field_distribution()
    status: completed
  - id: fix-memory-numpy
    content: Add numpy type sanitization helper in DynamicMemoryEngine; apply to list_memories(), get_stats(), retrieve(), get_memory_by_id()
    status: completed
  - id: fix-kg-timeout
    content: Increase KG API call timeout to 300s in frontend; optimize backend KG build to try fast regex fallback first
    status: completed
  - id: fix-viz-empty-state
    content: Add appropriate empty state messages in Visualization component when no keywords data
    status: completed
isProject: false
---

# Fix Project Subpage Issues

## Problem Analysis

After thorough investigation, the project detail page has 4 interconnected issues. Here is the root cause analysis and fix plan for each:

---

## Issue 1: Visualization - Word Cloud, Bar Chart, Distribution Chart Are Empty

**Root cause**: In [backend/app/api/v1/papers.py](backend/app/api/v1/papers.py) `process_paper_async()` (line 84-92), after parsing the PDF, the code saves `title`, `authors`, `abstract`, and `page_count` but **never saves `keywords` or `publication_date**` to the database:

```python
paper.title = doc.title or os.path.basename(file_path)
paper.authors = ", ".join(doc.authors) if doc.authors else None
paper.abstract = doc.abstract
paper.page_count = doc.page_count
# keywords is NEVER set!
# publication_date is NEVER set!
```

The PDF parser ([backend/app/services/pdf_parser.py](backend/app/services/pdf_parser.py)) correctly extracts `doc.keywords` via regex patterns, but the result is discarded. Since the visualization page, trend analysis, and distribution all depend on `Paper.keywords`, they all show empty.

**Fix**:

1. In `process_paper_async()`, add `paper.keywords = doc.keywords` to save extracted keywords
2. Add fallback keyword extraction from abstracts using TF-IDF when the keyword field is empty, so visualization works even for papers with no explicit keyword section
3. In `TrendAnalyzer.get_timeline()`, use `paper.publication_date` (the actual DB field) instead of the non-existent `paper.year`

---

## Issue 2: Knowledge Graph - Content KG Construction Fails (Timeout)

**Root cause**: The frontend `authAxios` in [frontend/src/services/axios.ts](frontend/src/services/axios.ts) has a global `timeout: 30000` (30 seconds). The `build_knowledge_graph` skill makes an LLM API call that takes 3-4 minutes (confirmed by terminal logs: 23:23:56 start -> 23:26:45 complete). The frontend request times out at 30s with `ECONNABORTED`.

**Fix**:

1. In [frontend/src/pages/Project/KnowledgeGraph/index.tsx](frontend/src/pages/Project/KnowledgeGraph/index.tsx), override the timeout for the KG API call to 5 minutes (300000ms)
2. In the backend [backend/app/api/v1/agents.py](backend/app/api/v1/agents.py) `build_project_knowledge_graph()`, try the fast regex/co-occurrence fallback first if LLM call is too slow, and attempt LLM only if regex produces poor results

---

## Issue 3: Trend Analysis - Data Issues

**Root cause**: Same as Issue 1 -- keywords are empty so hotspots and bursts return empty arrays. Timeline only works because it falls back to `paper.created_at.year`, but since all papers were uploaded the same day, it only shows one data point.

Additionally, in [backend/app/services/trend_analyzer.py](backend/app/services/trend_analyzer.py) `get_timeline()` line 200-201:

```python
if hasattr(paper, 'year') and paper.year:
    year = paper.year
```

The `Paper` model has no `year` attribute -- it has `publication_date` (a `Date` field). This always falls through to `created_at`.

**Fix**: Same as Issue 1 (save keywords + use `publication_date`). Additionally add abstract-based keyword extraction as a fallback for hotspots/bursts.

---

## Issue 4: Memory System - "Not Connected" + 500 Error

**Root cause**: Two distinct bugs:

**Bug A** - 500 error on `/memory/list` (terminal line 224-287): Milvus returns `numpy.float32` for the `importance` field, and `numpy.int64` for integer fields. FastAPI's `jsonable_encoder` cannot serialize numpy types:

```
ValueError: [TypeError("'numpy.float32' object is not iterable")]
```

In [backend/app/rag/memory_engine/dynamic_memory.py](backend/app/rag/memory_engine/dynamic_memory.py) `list_memories()` line 421-429, the values from Milvus are used directly without type conversion:

```python
items.append({
    "importance": entity.get("importance", 1.0),  # numpy.float32!
    "access_count": entity.get("access_count", 0),  # numpy.int64!
    ...
})
```

**Bug B** - "Not connected" display: The `get_stats()` method has the same numpy serialization issue. `get_collection_stats()` might return `row_count` as a string or numpy type, causing inconsistencies in the response that the frontend then misinterprets.

**Fix**: Add a `_sanitize_milvus_value()` helper in `DynamicMemoryEngine` to convert all numpy types to native Python types. Apply it in `list_memories()`, `get_stats()`, `retrieve()`, and `get_memory_by_id()`.

---

## Files to Modify


| File                                                  | Change                                                                                                                                           |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `backend/app/api/v1/papers.py`                        | Save keywords + publication_date in `process_paper_async()`                                                                                      |
| `backend/app/services/trend_analyzer.py`              | Fix `get_timeline()` to use `publication_date`; add abstract-based keyword fallback for `get_keyword_frequency()` and `get_field_distribution()` |
| `backend/app/rag/memory_engine/dynamic_memory.py`     | Add numpy type sanitization in `list_memories()`, `get_stats()`, `retrieve()`, `get_memory_by_id()`                                              |
| `frontend/src/pages/Project/KnowledgeGraph/index.tsx` | Increase timeout for KG API call to 300s                                                                                                         |
| `frontend/src/pages/Project/Visualization/index.tsx`  | Add empty state fallback message for keywords section                                                                                            |
| `backend/app/api/v1/agents.py`                        | Optimize KG build: try fast fallback first, then LLM                                                                                             |


