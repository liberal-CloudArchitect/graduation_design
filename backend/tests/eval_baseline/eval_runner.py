#!/usr/bin/env python3
"""
Baseline Evaluator — 基线评测运行器

通过 HTTP API 调用后端服务，运行全部评测集并输出 JSON 报表。

用法:
    # 1. 确保后端服务已启动
    # 2. 运行评测
    python -m tests.eval_baseline.eval_runner --base-url http://127.0.0.1:8000 --output reports/

    # 仅运行某个评测集
    python -m tests.eval_baseline.eval_runner --bench retrieval --base-url http://127.0.0.1:8000

    # LatencyBench（连续 3 轮取均值）
    python -m tests.eval_baseline.eval_runner --bench latency --rounds 3
"""
import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
    # Package execution: python -m tests.eval_baseline.eval_runner
    from .eval_metrics import (
        aggregate_answer_metrics,
        aggregate_retrieval_metrics,
        answer_coverage_keyword,
        citation_consistency,
        has_structured_output,
        keyword_hit_rate,
        latency_stats,
        ndcg_at_k,
        parse_quality_score,
        recall_at_k,
    )
except ImportError:
    # Script execution fallback: python tests/eval_baseline/eval_runner.py
    from eval_metrics import (
        aggregate_answer_metrics,
        aggregate_retrieval_metrics,
        answer_coverage_keyword,
        citation_consistency,
        has_structured_output,
        keyword_hit_rate,
        latency_stats,
        ndcg_at_k,
        parse_quality_score,
        recall_at_k,
    )

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "reports"

PDF_DIR = SCRIPT_DIR.parent / "test_doc"

RETRIEVAL_BENCH_PATH = SCRIPT_DIR / "retrieval_bench" / "retrieval_bench.json"
ANSWER_BENCH_PATH = SCRIPT_DIR / "answer_bench" / "answer_bench.json"
PARSE_BENCH_PATH = SCRIPT_DIR / "parse_bench" / "parse_bench_manifest.json"
HIGH_VALUE_PATH = SCRIPT_DIR / "high_value_queries.json"


class APIClient:
    """Thin wrapper around httpx for backend API calls."""

    def __init__(self, base_url: str, timeout: float = 240):
        self.base_url = base_url.rstrip("/")
        self.api = f"{self.base_url}/api/v1"
        self.token: Optional[str] = None
        self.timeout = timeout
        self.max_retries = int(os.getenv("EVAL_MAX_RETRIES", "3"))
        self.retry_backoff_s = float(os.getenv("EVAL_RETRY_BACKOFF", "2"))

    async def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def register_and_login(self, suffix: str = "") -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        email = f"eval_{ts}{suffix}@example.com"
        password = "EvalPass_123456"
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=60) as c:
                    await c.post(
                        f"{self.api}/auth/register",
                        json={"email": email, "username": f"eval_{ts}", "password": password},
                    )
                    resp = await c.post(
                        f"{self.api}/auth/login",
                        json={"email": email, "password": password},
                    )
                    resp.raise_for_status()
                    self.token = resp.json()["access_token"]
                    return self.token
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError) as e:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"register/login failed after {attempt} attempts: {e}") from e
                await asyncio.sleep(self.retry_backoff_s * attempt)
        raise RuntimeError("register/login failed unexpectedly")

    async def create_project(self, name: str) -> int:
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=60) as c:
                    resp = await c.post(
                        f"{self.api}/projects",
                        headers=await self._headers(),
                        json={"name": name, "description": "Baseline eval run"},
                    )
                    resp.raise_for_status()
                    return resp.json()["id"]
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError) as e:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"create_project failed after {attempt} attempts: {e}") from e
                await asyncio.sleep(self.retry_backoff_s * attempt)
        raise RuntimeError("create_project failed unexpectedly")

    async def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as c:
                    resp = await c.get(
                        f"{self.api}/projects/{project_id}",
                        headers=await self._headers(),
                    )
                    if resp.status_code == 404:
                        return None
                    resp.raise_for_status()
                    return resp.json()
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError) as e:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"get_project failed after {attempt} attempts: {e}") from e
                await asyncio.sleep(self.retry_backoff_s * attempt)
        raise RuntimeError("get_project failed unexpectedly")

    async def upload_pdf(self, project_id: int, pdf_path: str) -> Optional[int]:
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=180) as c:
                    with open(pdf_path, "rb") as f:
                        resp = await c.post(
                            f"{self.api}/papers/upload?project_id={project_id}",
                            headers={"Authorization": f"Bearer {self.token}"},
                            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
                        )
                    if resp.status_code < 300:
                        return resp.json().get("id")
                    # non-2xx: treat as retryable unless last attempt
                    if attempt >= self.max_retries:
                        print(
                            f"[setup] WARN: upload failed after {attempt} attempts for "
                            f"{os.path.basename(pdf_path)} status={resp.status_code} body={resp.text}"
                        )
                        return None
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException, httpx.HTTPError) as e:
                if attempt >= self.max_retries:
                    print(
                        f"[setup] WARN: upload timeout/http error after {attempt} attempts for "
                        f"{os.path.basename(pdf_path)}: {e}"
                    )
                    return None
            await asyncio.sleep(self.retry_backoff_s * attempt)
        return None

    async def wait_processing(self, project_id: int, paper_ids: List[int], deadline_s: int = 600):
        start = time.time()
        # Large PDF batches can make list endpoint slow under load.
        # Keep polling resilient to transient read timeouts.
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout) as c:
            while time.time() - start < deadline_s:
                try:
                    resp = await c.get(
                        f"{self.api}/papers?project_id={project_id}&page_size=100",
                        headers=await self._headers(),
                    )
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException) as e:
                    elapsed = int(time.time() - start)
                    print(f"[setup] WARN: wait_processing timeout at {elapsed}s: {e}")
                    await asyncio.sleep(5)
                    continue
                except httpx.HTTPError as e:
                    elapsed = int(time.time() - start)
                    print(f"[setup] WARN: wait_processing HTTP error at {elapsed}s: {e}")
                    await asyncio.sleep(5)
                    continue

                if resp.status_code >= 300:
                    if resp.status_code == 422:
                        print(f"[setup] WARN: list papers validation error: {resp.text}")
                    else:
                        print(f"[setup] WARN: list papers failed status={resp.status_code}")
                    await asyncio.sleep(5)
                    continue
                items = resp.json().get("items", [])
                statuses = {
                    it["id"]: it.get("status", "unknown")
                    for it in items
                    if it["id"] in paper_ids
                }
                if all(s in ("completed", "failed") for s in statuses.values()):
                    return statuses
                await asyncio.sleep(5)
        return {}

    async def rag_ask(self, question: str, project_id: int, top_k: int = 8) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    t0 = time.time()
                    resp = await c.post(
                        f"{self.api}/rag/ask",
                        headers=await self._headers(),
                        json={"question": question, "project_id": project_id, "top_k": top_k},
                    )
                    elapsed_ms = (time.time() - t0) * 1000
                    if resp.status_code >= 300:
                        return {"error": resp.text, "latency_ms": elapsed_ms}
                    data = resp.json()
                    data["latency_ms"] = elapsed_ms
                    return data
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException) as e:
                if attempt >= self.max_retries:
                    return {
                        "error": f"timeout after {attempt} attempts: {e}",
                        "latency_ms": self.timeout * 1000,
                    }
                await asyncio.sleep(self.retry_backoff_s * attempt)
            except httpx.HTTPError as e:
                if attempt >= self.max_retries:
                    return {"error": f"http error after {attempt} attempts: {e}", "latency_ms": 0}
                await asyncio.sleep(self.retry_backoff_s * attempt)
        return {"error": "unknown request failure", "latency_ms": 0}

    async def rag_search(self, question: str, project_id: int, top_k: int = 20) -> Dict[str, Any]:
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as c:
                    t0 = time.time()
                    resp = await c.post(
                        f"{self.api}/rag/search",
                        headers=await self._headers(),
                        json={"question": question, "project_id": project_id, "top_k": top_k},
                    )
                    elapsed_ms = (time.time() - t0) * 1000
                    if resp.status_code >= 300:
                        return {"error": resp.text, "latency_ms": elapsed_ms}
                    data = resp.json()
                    data["latency_ms"] = elapsed_ms
                    return data
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException) as e:
                if attempt >= self.max_retries:
                    return {
                        "error": f"timeout after {attempt} attempts: {e}",
                        "latency_ms": self.timeout * 1000,
                    }
                await asyncio.sleep(self.retry_backoff_s * attempt)
            except httpx.HTTPError as e:
                if attempt >= self.max_retries:
                    return {"error": f"http error after {attempt} attempts: {e}", "latency_ms": 0}
                await asyncio.sleep(self.retry_backoff_s * attempt)
        return {"error": "unknown request failure", "latency_ms": 0}

    async def get_paper(self, paper_id: int) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                resp = await c.get(
                    f"{self.api}/papers/{paper_id}",
                    headers=await self._headers(),
                )
                if resp.status_code < 300:
                    return resp.json()
        except Exception as e:
            print(f"[api] WARN: Failed to fetch paper {paper_id}: {e}")
        return {}


class BaselineEvaluator:
    """Orchestrates benchmark runs and produces a unified JSON report."""

    def __init__(
        self,
        api: APIClient,
        output_dir: Path,
        rounds: int = 1,
        resume: bool = True,
        checkpoint_path: Optional[Path] = None,
        reuse_project_id: Optional[int] = None,
    ):
        self.api = api
        self.output_dir = output_dir
        self.rounds = rounds
        self.resume = resume
        self.checkpoint_path = checkpoint_path or (output_dir / "eval_checkpoint.json")
        self.project_id: Optional[int] = reuse_project_id
        self.paper_map: Dict[str, int] = {}       # filename → paper_id
        self.key_to_filename: Dict[str, str] = {}  # retrieval key → filename
        self.state: Dict[str, Any] = {
            "version": 1,
            "meta": {
                "base_url": self.api.base_url,
                "rounds": self.rounds,
                "updated_at": datetime.now().isoformat(),
            },
            "project": {
                "project_id": self.project_id,
                "paper_map": {},
                "key_to_filename": {},
            },
            "progress": {},
        }
        self._load_checkpoint_if_any()

    def _load_checkpoint_if_any(self):
        if not self.resume:
            return
        if not self.checkpoint_path.exists():
            return
        try:
            data = _load_json(self.checkpoint_path)
            if data.get("meta", {}).get("base_url") != self.api.base_url:
                print("[checkpoint] Skip loading checkpoint due to base_url mismatch.")
                return
            self.state = data
            proj = self.state.get("project", {})
            if not self.project_id:
                self.project_id = proj.get("project_id")
            self.paper_map = {k: int(v) for k, v in (proj.get("paper_map") or {}).items()}
            self.key_to_filename = dict(proj.get("key_to_filename") or {})
            print(
                f"[checkpoint] Loaded: project_id={self.project_id}, "
                f"papers={len(self.paper_map)}, progress_keys={list(self.state.get('progress', {}).keys())}"
            )
        except Exception as e:
            print(f"[checkpoint] WARN: failed to load checkpoint: {e}")

    def _save_checkpoint(self):
        self.state.setdefault("meta", {})
        self.state["meta"]["base_url"] = self.api.base_url
        self.state["meta"]["rounds"] = self.rounds
        self.state["meta"]["updated_at"] = datetime.now().isoformat()
        self.state["project"] = {
            "project_id": self.project_id,
            "paper_map": self.paper_map,
            "key_to_filename": self.key_to_filename,
        }
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _bench_state(self, name: str) -> Dict[str, Any]:
        progress = self.state.setdefault("progress", {})
        return progress.setdefault(name, {})

    def _reset_checkpoint_state(self):
        self.project_id = None
        self.paper_map = {}
        self.state["project"] = {
            "project_id": None,
            "paper_map": {},
            "key_to_filename": self.key_to_filename,
        }
        self.state["progress"] = {}

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    async def setup(self, benches: List[str]):
        """Register, login, create project, upload all PDFs needed by requested benches."""
        pdfs_to_upload: Dict[str, Path] = {}

        if any(b in benches for b in ("retrieval", "answer", "latency", "all")):
            retrieval_bench = _load_json(RETRIEVAL_BENCH_PATH)
            paper_index = retrieval_bench.get("paper_index", {})
            for key, filename in paper_index.items():
                self.key_to_filename[key] = filename
                pdf_path = PDF_DIR / filename
                if pdf_path.exists():
                    pdfs_to_upload[filename] = pdf_path

        if any(b in benches for b in ("parse", "all")):
            manifest = _load_json(PARSE_BENCH_PATH)
            for item in manifest.get("items", []):
                rel = item.get("pdf_relative_path", "")
                filename = item.get("pdf_filename", "")
                pdf_path = SCRIPT_DIR.parent / rel
                if pdf_path.exists() and filename not in pdfs_to_upload:
                    pdfs_to_upload[filename] = pdf_path

        print("[setup] Registering and logging in...")
        await self.api.register_and_login()

        if self.project_id and self.paper_map:
            project = await self.api.get_project(self.project_id)
            if project:
                print(f"[setup] Reusing existing project_id={self.project_id} with {len(self.paper_map)} papers")
                await self.api.wait_processing(self.project_id, list(self.paper_map.values()))
                self._save_checkpoint()
                return
            print(
                "[setup] Checkpoint project is not accessible for the current login; "
                "clearing stale state and starting a fresh run."
            )
            self._reset_checkpoint_state()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.project_id = await self.api.create_project(f"baseline_eval_{ts}")
        print(f"[setup] Project ID: {self.project_id}")

        paper_ids = []
        for filename, pdf_path in pdfs_to_upload.items():
            pid = await self.api.upload_pdf(self.project_id, str(pdf_path))
            if pid:
                self.paper_map[filename] = pid
                paper_ids.append(pid)
                print(f"[setup] Uploaded {filename} -> paper_id={pid}")
            else:
                print(f"[setup] WARN: Upload failed for {filename}")

        if paper_ids:
            print(f"[setup] Waiting for paper processing ({len(paper_ids)} papers)...")
            await self.api.wait_processing(self.project_id, paper_ids)

        print(f"[setup] Done. {len(self.paper_map)} papers uploaded.")
        self._save_checkpoint()

    def _resolve_paper_id(self, key: str) -> Optional[int]:
        """Resolve a retrieval bench key (like 'gao_2024') to a paper_id."""
        filename = self.key_to_filename.get(key)
        if filename:
            return self.paper_map.get(filename)
        return None

    async def llm_precheck(self):
        """
        Fail-fast health check for LLM path before long benchmark runs.
        Uses current project_id and a lightweight query.
        """
        if not self.project_id:
            raise RuntimeError("LLM precheck requires a valid project_id")
        print("[precheck] Running LLM connectivity precheck...")
        result = await self.api.rag_ask(
            question="Health check: please briefly confirm retrieval-augmented QA is available.",
            project_id=self.project_id,
            top_k=1,
        )
        if "error" in result:
            raise RuntimeError(f"LLM precheck failed: {result['error']}")
        answer = (result.get("answer") or "").strip()
        if not answer:
            raise RuntimeError("LLM precheck failed: empty answer")
        print("[precheck] LLM precheck passed.")

    # ------------------------------------------------------------------
    # RetrievalBench
    # ------------------------------------------------------------------

    async def run_retrieval_bench(self) -> Dict[str, Any]:
        print("[retrieval_bench] Running...")
        bench = _load_json(RETRIEVAL_BENCH_PATH)
        items = bench.get("items", [])
        st = self._bench_state("retrieval_bench")
        if st.get("done") and st.get("report"):
            print("[retrieval_bench] Resume hit: already completed, using checkpointed report.")
            return st["report"]
        per_query = st.get("per_query", [])
        latencies = st.get("latencies", [])
        start_idx = int(st.get("next_index", len(per_query)))
        for idx in range(start_idx, len(items)):
            item = items[idx]
            query = item["query"]
            relevant_keys = item.get("relevant_papers", [])
            relevant_pids = [
                pid for pid in (self._resolve_paper_id(k) for k in relevant_keys) if pid
            ]
            relevant_keywords = item.get("relevant_keywords", [])

            result = await self.api.rag_search(query, self.project_id, top_k=20)
            latencies.append(result.get("latency_ms", 0))

            if "error" in result:
                per_query.append({
                    "id": item["id"],
                    "error": result["error"],
                    "recall_at_10": 0.0,
                    "recall_at_20": 0.0,
                    "ndcg_at_10": 0.0,
                    "keyword_hit_rate": 0.0,
                })
                st["per_query"] = per_query
                st["latencies"] = latencies
                st["next_index"] = idx + 1
                self._save_checkpoint()
                continue

            refs = result.get("references", [])
            retrieved_pids = [r.get("paper_id") for r in refs if r.get("paper_id") is not None]
            retrieved_texts = [r.get("text", "") for r in refs]

            metrics = {
                "id": item["id"],
                "category": item.get("category"),
                "recall_at_10": recall_at_k(retrieved_pids, relevant_pids, 10),
                "recall_at_20": recall_at_k(retrieved_pids, relevant_pids, 20),
                "ndcg_at_10": ndcg_at_k(retrieved_pids, relevant_pids, 10),
                "keyword_hit_rate": keyword_hit_rate(retrieved_texts, relevant_keywords, 10),
                "retrieved_count": len(refs),
            }
            per_query.append(metrics)
            st["per_query"] = per_query
            st["latencies"] = latencies
            st["next_index"] = idx + 1
            self._save_checkpoint()

        agg = aggregate_retrieval_metrics(per_query)
        lat = latency_stats(latencies)

        report = {
            "bench": "retrieval_bench",
            "query_count": len(items),
            "aggregated": agg,
            "latency": lat,
            "per_query": per_query,
        }
        st["done"] = True
        st["report"] = report
        self._save_checkpoint()
        print(f"[retrieval_bench] Done. avg_recall@10={agg.get('avg_recall_at_10', 'N/A')}")
        return report

    # ------------------------------------------------------------------
    # AnswerBench
    # ------------------------------------------------------------------

    async def run_answer_bench(self) -> Dict[str, Any]:
        print("[answer_bench] Running...")
        bench = _load_json(ANSWER_BENCH_PATH)
        items = bench.get("items", [])
        st = self._bench_state("answer_bench")
        if st.get("done") and st.get("report"):
            prev_agg = (st.get("report") or {}).get("aggregated", {})
            if prev_agg.get("avg_coverage_ratio") is not None:
                print("[answer_bench] Resume hit: already completed, using checkpointed report.")
                return st["report"]
            print("[answer_bench] Checkpoint report incomplete (avg_coverage_ratio is null), rerunning.")
            st["done"] = False
            st["next_index"] = 0
            st["per_query"] = []
            st["latencies"] = []
            st.pop("report", None)
            self._save_checkpoint()
        per_query = st.get("per_query", [])
        latencies = st.get("latencies", [])
        start_idx = int(st.get("next_index", len(per_query)))
        for idx in range(start_idx, len(items)):
            item = items[idx]
            question = item["question"]
            expected_points = item.get("expected_answer_points", [])

            result = await self.api.rag_ask(question, self.project_id, top_k=8)
            latencies.append(result.get("latency_ms", 0))

            if "error" in result:
                per_query.append({
                    "id": item["id"],
                    "category": item.get("category"),
                    "error": result["error"],
                    "coverage_ratio": 0.0,
                    "covered_points": 0,
                    "total_points": len(expected_points),
                    "consistency_ratio": 0.0,
                    "total_citations": 0,
                    "valid_citations": 0,
                    "structure_completeness": 0.0,
                    "answer_length": 0,
                })
                st["per_query"] = per_query
                st["latencies"] = latencies
                st["next_index"] = idx + 1
                self._save_checkpoint()
                continue

            answer = result.get("answer", "")
            refs = result.get("references", [])

            cov = answer_coverage_keyword(answer, expected_points)
            cit = citation_consistency(answer, len(refs))
            struct = has_structured_output(answer)

            metrics = {
                "id": item["id"],
                "category": item.get("category"),
                "coverage_ratio": cov["coverage_ratio"],
                "covered_points": cov["covered_points"],
                "total_points": cov["total_points"],
                "consistency_ratio": cit["consistency_ratio"],
                "total_citations": cit["total_citations"],
                "valid_citations": cit["valid_citations"],
                "structure_completeness": struct["structure_completeness"],
                "answer_length": len(answer),
            }
            per_query.append(metrics)
            st["per_query"] = per_query
            st["latencies"] = latencies
            st["next_index"] = idx + 1
            self._save_checkpoint()

        agg = aggregate_answer_metrics(per_query)
        lat = latency_stats(latencies)

        report = {
            "bench": "answer_bench",
            "query_count": len(items),
            "aggregated": agg,
            "latency": lat,
            "per_query": per_query,
        }
        st["done"] = True
        st["report"] = report
        self._save_checkpoint()
        print(f"[answer_bench] Done. avg_coverage={agg.get('avg_coverage_ratio', 'N/A')}")
        return report

    # ------------------------------------------------------------------
    # ParseBench
    # ------------------------------------------------------------------

    async def run_parse_bench(self) -> Dict[str, Any]:
        print("[parse_bench] Running...")
        manifest = _load_json(PARSE_BENCH_PATH)
        items = manifest.get("items", [])
        st = self._bench_state("parse_bench")
        if st.get("done") and st.get("report"):
            print("[parse_bench] Resume hit: already completed, using checkpointed report.")
            return st["report"]
        per_doc = st.get("per_doc", [])
        start_idx = int(st.get("next_index", len(per_doc)))
        for idx in range(start_idx, len(items)):
            item = items[idx]
            expected = item.get("expected", {})
            pdf_filename = item.get("pdf_filename", "")

            matched_pid = self.paper_map.get(pdf_filename)
            if matched_pid is None:
                per_doc.append({
                    "id": item["id"],
                    "category": item.get("category"),
                    "error": f"paper not uploaded or not matched: {pdf_filename}",
                })
                st["per_doc"] = per_doc
                st["next_index"] = idx + 1
                self._save_checkpoint()
                continue

            parsed = await self._get_paper_metadata(matched_pid, pdf_filename)
            score = parse_quality_score(parsed, expected)
            score["id"] = item["id"]
            score["category"] = item.get("category")
            per_doc.append(score)
            st["per_doc"] = per_doc
            st["next_index"] = idx + 1
            self._save_checkpoint()

        overall_scores = [d["overall_score"] for d in per_doc if "overall_score" in d]
        avg_score = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0

        category_scores: Dict[str, List[float]] = {}
        for d in per_doc:
            cat = d.get("category")
            if cat and "overall_score" in d:
                category_scores.setdefault(cat, []).append(d["overall_score"])
        category_avg = {
            cat: round(sum(v) / len(v), 4) for cat, v in category_scores.items()
        }

        report = {
            "bench": "parse_bench",
            "doc_count": len(items),
            "avg_parse_score": round(avg_score, 4),
            "category_avg": category_avg,
            "per_doc": per_doc,
        }
        st["done"] = True
        st["report"] = report
        self._save_checkpoint()
        print(f"[parse_bench] Done. avg_score={avg_score:.4f}, categories={category_avg}")
        return report

    async def _get_paper_metadata(self, paper_id: int, pdf_filename: str = "") -> Dict[str, Any]:
        """Fetch paper metadata from API and infer structural properties from chunks."""
        data = await self.api.get_paper(paper_id)
        if not data:
            return {}

        parsed: Dict[str, Any] = {
            "title": data.get("title", ""),
            "has_abstract": bool(data.get("abstract")),
            "abstract": data.get("abstract", ""),
            "page_count": data.get("page_count", 0),
            "section_count": 0,
            "section_names": [],
            "has_tables": False,
            "has_formulas": False,
            "has_figures": False,
        }

        try:
            search_result = await self.api.rag_search(
                f"sections tables formulas of {pdf_filename}",
                self.project_id,
                top_k=30,
            )
            refs = search_result.get("references", [])
            all_text = "\n".join(r.get("text", "") for r in refs)

            import re
            section_headers = re.findall(
                r"(?:^|\n)\s*(?:\d+\.?\s+)?([A-Z][A-Za-z\s]{2,40})(?:\n|$)",
                all_text,
            )
            parsed["section_names"] = list(dict.fromkeys(section_headers))[:20]
            parsed["section_count"] = len(parsed["section_names"])

            table_indicators = ["|", "Table ", "TABLE ", "表 "]
            parsed["has_tables"] = any(ind in all_text for ind in table_indicators)

            formula_indicators = ["\\(", "\\)", "\\frac", "\\sum", "∑", "∫", "≤", "≥", "="]
            formula_count = sum(1 for ind in formula_indicators if ind in all_text)
            parsed["has_formulas"] = formula_count >= 2

            fig_indicators = ["Figure ", "Fig. ", "Fig ", "图 "]
            parsed["has_figures"] = any(ind in all_text for ind in fig_indicators)

        except Exception as e:
            print(f"[parse_bench] WARN: structural inference failed for {paper_id}: {e}")

        return parsed

    # ------------------------------------------------------------------
    # LatencyBench (standalone)
    # ------------------------------------------------------------------

    async def run_latency_bench(self) -> Dict[str, Any]:
        """
        Independent LatencyBench: measures P50/P95/P99 latency.
        Runs queries from retrieval+answer benchmarks over N rounds (default 3)
        to achieve stable measurements as required by the plan.
        """
        rounds = max(1, self.rounds)
        print(f"[latency_bench] Running {rounds} round(s)...")

        retrieval_bench = _load_json(RETRIEVAL_BENCH_PATH)
        answer_bench = _load_json(ANSWER_BENCH_PATH)

        retrieval_queries = [it["query"] for it in retrieval_bench.get("items", [])[:20]]
        answer_queries = [it["question"] for it in answer_bench.get("items", [])[:15]]

        st = self._bench_state("latency_bench")
        if st.get("done") and st.get("report"):
            print("[latency_bench] Resume hit: already completed, using checkpointed report.")
            return st["report"]
        all_retrieval_latencies: List[float] = st.get("all_retrieval_latencies", [])
        all_answer_latencies: List[float] = st.get("all_answer_latencies", [])
        per_round: List[Dict[str, Any]] = st.get("per_round", [])
        start_round = int(st.get("next_round", len(per_round)))
        for r in range(start_round, rounds):
            print(f"[latency_bench] Round {r + 1}/{rounds}...")
            round_retrieval = []
            round_answer = []

            for q in retrieval_queries:
                result = await self.api.rag_search(q, self.project_id, top_k=20)
                lat = result.get("latency_ms", 0)
                round_retrieval.append(lat)
                all_retrieval_latencies.append(lat)

            for q in answer_queries:
                result = await self.api.rag_ask(q, self.project_id, top_k=8)
                lat = result.get("latency_ms", 0)
                round_answer.append(lat)
                all_answer_latencies.append(lat)

            per_round.append({
                "round": r + 1,
                "retrieval_latency": latency_stats(round_retrieval),
                "answer_latency": latency_stats(round_answer),
            })
            st["all_retrieval_latencies"] = all_retrieval_latencies
            st["all_answer_latencies"] = all_answer_latencies
            st["per_round"] = per_round
            st["next_round"] = r + 1
            self._save_checkpoint()
            print(
                f"[latency_bench]   retrieval_p95="
                f"{latency_stats(round_retrieval).get('p95', 'N/A'):.0f}ms, "
                f"answer_p95={latency_stats(round_answer).get('p95', 'N/A'):.0f}ms"
            )

        combined = all_retrieval_latencies + all_answer_latencies
        agg = latency_stats(combined)
        retrieval_agg = latency_stats(all_retrieval_latencies)
        answer_agg = latency_stats(all_answer_latencies)

        report = {
            "bench": "latency_bench",
            "rounds": rounds,
            "total_queries": len(combined),
            "aggregated": agg,
            "retrieval_latency": retrieval_agg,
            "answer_latency": answer_agg,
            "per_round": per_round,
        }
        st["done"] = True
        st["report"] = report
        self._save_checkpoint()
        print(
            f"[latency_bench] Done. overall_p95={agg.get('p95', 'N/A'):.0f}ms "
            f"(retrieval_p95={retrieval_agg.get('p95', 'N/A'):.0f}ms, "
            f"answer_p95={answer_agg.get('p95', 'N/A'):.0f}ms)"
        )
        return report

    # ------------------------------------------------------------------
    # Full run
    # ------------------------------------------------------------------

    async def run_all(self) -> Dict[str, Any]:
        """Run all benchmarks and produce a unified report."""
        await self.setup(["all"])

        retrieval_report = await self.run_retrieval_bench()
        answer_report = await self.run_answer_bench()
        parse_report = await self.run_parse_bench()
        latency_report = await self.run_latency_bench()

        full_report = {
            "meta": {
                "timestamp": datetime.now().isoformat(),
                "project_id": self.project_id,
                "paper_count": len(self.paper_map),
                "latency_rounds": self.rounds,
                "base_url": self.api.base_url,
            },
            "retrieval_bench": retrieval_report,
            "answer_bench": answer_report,
            "parse_bench": parse_report,
            "latency_bench": latency_report,
        }

        return full_report

    def save_report(self, report: Dict[str, Any]):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"baseline_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[report] Saved to {path}")
        self._save_checkpoint()
        return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Baseline Evaluator")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    parser.add_argument(
        "--bench",
        choices=["retrieval", "answer", "parse", "latency", "all"],
        default="all",
        help="Which benchmark to run",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="Latency bench rounds for stable measurement (default: 3)",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=float(os.getenv("EVAL_HTTP_TIMEOUT", "240")),
        help="HTTP timeout for rag requests in seconds (default: 240 or EVAL_HTTP_TIMEOUT)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable checkpoint resume and start a fresh run",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=None,
        help="Optional checkpoint JSON path (default: <output>/eval_checkpoint.json)",
    )
    parser.add_argument(
        "--reuse-project-id",
        type=int,
        default=None,
        help="Reuse an existing project id instead of creating a new one",
    )
    parser.add_argument(
        "--skip-llm-precheck",
        action="store_true",
        help="Skip LLM connectivity precheck before running benchmarks",
    )
    args = parser.parse_args()

    api = APIClient(args.base_url, timeout=args.http_timeout)
    evaluator = BaselineEvaluator(
        api,
        Path(args.output),
        rounds=args.rounds,
        resume=not args.no_resume,
        checkpoint_path=Path(args.checkpoint_path) if args.checkpoint_path else None,
        reuse_project_id=args.reuse_project_id,
    )

    if args.bench == "all":
        if not args.skip_llm_precheck:
            await evaluator.setup(["all"])
            await evaluator.llm_precheck()
            retrieval_report = await evaluator.run_retrieval_bench()
            answer_report = await evaluator.run_answer_bench()
            parse_report = await evaluator.run_parse_bench()
            latency_report = await evaluator.run_latency_bench()
            report = {
                "meta": {
                    "timestamp": datetime.now().isoformat(),
                    "project_id": evaluator.project_id,
                    "paper_count": len(evaluator.paper_map),
                    "latency_rounds": evaluator.rounds,
                    "base_url": api.base_url,
                },
                "retrieval_bench": retrieval_report,
                "answer_bench": answer_report,
                "parse_bench": parse_report,
                "latency_bench": latency_report,
            }
        else:
            report = await evaluator.run_all()
    else:
        await evaluator.setup([args.bench])
        if not args.skip_llm_precheck:
            await evaluator.llm_precheck()
        if args.bench == "retrieval":
            report = {"retrieval_bench": await evaluator.run_retrieval_bench()}
        elif args.bench == "answer":
            report = {"answer_bench": await evaluator.run_answer_bench()}
        elif args.bench == "parse":
            report = {"parse_bench": await evaluator.run_parse_bench()}
        elif args.bench == "latency":
            report = {"latency_bench": await evaluator.run_latency_bench()}

        report["meta"] = {
            "timestamp": datetime.now().isoformat(),
            "project_id": evaluator.project_id,
            "paper_count": len(evaluator.paper_map),
            "latency_rounds": args.rounds,
            "base_url": api.base_url,
        }

    evaluator.save_report(report)


if __name__ == "__main__":
    asyncio.run(main())
