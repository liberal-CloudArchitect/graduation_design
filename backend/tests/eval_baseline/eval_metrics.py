"""
Evaluation Metrics — 基线评测指标计算模块

提供 IR 检索质量指标、回答质量指标、PDF 解析质量指标和延迟统计指标。
所有指标函数为纯函数，不依赖外部服务。
"""
import math
import re
import statistics
from typing import List, Dict, Any, Optional, Set


# ---------------------------------------------------------------------------
# 1. 检索质量指标
# ---------------------------------------------------------------------------

def recall_at_k(
    retrieved_paper_ids: List[int],
    relevant_paper_ids: List[int],
    k: int = 10,
) -> float:
    """
    Recall@K: Top-K 检索结果中包含相关文档的比例。

    Args:
        retrieved_paper_ids: 检索返回的 paper_id 列表（按排序）
        relevant_paper_ids: 标注的相关 paper_id 列表
        k: 截断位置

    Returns:
        0.0 ~ 1.0
    """
    if not relevant_paper_ids:
        return 1.0
    top_k = set(retrieved_paper_ids[:k])
    relevant = set(relevant_paper_ids)
    hits = top_k & relevant
    return len(hits) / len(relevant)


def ndcg_at_k(
    retrieved_paper_ids: List[int],
    relevant_paper_ids: List[int],
    k: int = 10,
) -> float:
    """
    nDCG@K: 考虑排序位置的检索质量。
    使用二元相关度（相关=1，不相关=0）。

    Args:
        retrieved_paper_ids: 检索返回的 paper_id 列表（按排序）
        relevant_paper_ids: 标注的相关 paper_id 列表
        k: 截断位置

    Returns:
        0.0 ~ 1.0
    """
    if not relevant_paper_ids:
        return 1.0

    relevant = set(relevant_paper_ids)

    def dcg(ids: List[int], topk: int) -> float:
        score = 0.0
        for i, pid in enumerate(ids[:topk]):
            rel = 1.0 if pid in relevant else 0.0
            score += rel / math.log2(i + 2)  # log2(rank+1), rank is 1-based
        return score

    actual_dcg = dcg(retrieved_paper_ids, k)

    ideal_order = sorted(
        retrieved_paper_ids[:k],
        key=lambda pid: (pid in relevant,),
        reverse=True,
    )
    n_relevant = min(len(relevant), k)
    ideal_ids = list(relevant)[:n_relevant] + [
        pid for pid in retrieved_paper_ids[:k] if pid not in relevant
    ]
    ideal_dcg = dcg(ideal_ids[:k], k)

    if ideal_dcg == 0:
        return 0.0
    return actual_dcg / ideal_dcg


def keyword_hit_rate(
    retrieved_texts: List[str],
    relevant_keywords: List[str],
    k: int = 10,
) -> float:
    """
    Top-K 检索文本中命中标注关键词的比例。

    Args:
        retrieved_texts: 检索返回的文本列表
        relevant_keywords: 标注的相关关键词列表
        k: 截断位置

    Returns:
        0.0 ~ 1.0
    """
    if not relevant_keywords:
        return 1.0
    combined = " ".join(retrieved_texts[:k]).lower()
    hits = sum(1 for kw in relevant_keywords if kw.lower() in combined)
    return hits / len(relevant_keywords)


# ---------------------------------------------------------------------------
# 2. 回答质量指标
# ---------------------------------------------------------------------------

_CITATION_RE = re.compile(r"\[(\d+)\]")


def citation_consistency(
    answer: str,
    evidence_count: int,
) -> Dict[str, Any]:
    """
    引用一致性：检查回答中引用编号是否在有效范围内。

    Args:
        answer: LLM 生成的回答文本
        evidence_count: 实际提供的证据数量

    Returns:
        {
            "total_citations": int,
            "valid_citations": int,
            "invalid_citations": int,
            "consistency_ratio": float (0.0 ~ 1.0),
            "citation_ids": list[int],
        }
    """
    found = _CITATION_RE.findall(answer)
    citation_ids = [int(c) for c in found]
    valid = [c for c in citation_ids if 1 <= c <= evidence_count]
    total = len(citation_ids)

    return {
        "total_citations": total,
        "valid_citations": len(valid),
        "invalid_citations": total - len(valid),
        "consistency_ratio": len(valid) / total if total > 0 else 1.0,
        "citation_ids": citation_ids,
    }


def answer_coverage_keyword(
    answer: str,
    expected_points: List[str],
) -> Dict[str, Any]:
    """
    答案完整度（关键词匹配版）：检查标准答案要点在回答中的覆盖度。
    简单实现，基于字符串包含检查。复杂场景应使用 LLM 评分。

    Args:
        answer: LLM 生成的回答文本
        expected_points: 标准答案要点列表

    Returns:
        {
            "total_points": int,
            "covered_points": int,
            "coverage_ratio": float,
            "point_details": [{"point": str, "covered": bool}],
        }
    """
    if not expected_points:
        return {
            "total_points": 0,
            "covered_points": 0,
            "coverage_ratio": 1.0,
            "point_details": [],
        }

    answer_lower = answer.lower()
    details = []
    covered = 0

    for point in expected_points:
        tokens = [t.strip().lower() for t in re.split(r"[,;，；/]", point) if t.strip()]
        hit = any(token in answer_lower for token in tokens) if tokens else False
        if hit:
            covered += 1
        details.append({"point": point, "covered": hit})

    return {
        "total_points": len(expected_points),
        "covered_points": covered,
        "coverage_ratio": covered / len(expected_points),
        "point_details": details,
    }


def has_structured_output(answer: str) -> Dict[str, bool]:
    """
    检查回答是否包含要求的结构化输出段落。

    Returns:
        各段落的存在性
    """
    sections = {
        "has_conclusion": bool(re.search(r"##\s*结论", answer)),
        "has_analysis": bool(re.search(r"##\s*依据[与和]分析", answer)),
        "has_limitations": bool(re.search(r"##\s*局限[与和]?不确定性", answer)),
        "has_references": bool(re.search(r"##\s*参考来源", answer)),
    }
    sections["structure_completeness"] = sum(sections.values()) / len(sections)
    return sections


# ---------------------------------------------------------------------------
# 3. PDF 解析质量指标
# ---------------------------------------------------------------------------

def parse_quality_score(
    parsed: Dict[str, Any],
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    """
    PDF 解析质量评分。

    对齐标注字段与评分项：title、abstract、section_count、page_count、
    has_tables、has_formulas、has_figures、known_sections、abstract_min_length。
    只有当 parsed 提供对应字段且 expected 声明了预期值时才纳入评分，
    缺失字段不惩罚。

    Args:
        parsed: 实际解析结果
        expected: 标注的期望结果

    Returns:
        {"overall_score": float, "scored_items": int, "details": dict}
    """
    scores: List[float] = []
    details: Dict[str, Any] = {}

    # ---- 标题匹配 (权重 1) ----
    parsed_title = (parsed.get("title") or "").strip().lower()
    expected_title = (expected.get("title") or "").strip().lower()
    if expected_title:
        title_match = (
            expected_title in parsed_title
            or parsed_title in expected_title
            or _fuzzy_title_match(parsed_title, expected_title)
        )
        scores.append(1.0 if title_match else 0.0)
        details["title_match"] = title_match
        details["parsed_title"] = parsed.get("title", "")
    else:
        details["title_match"] = None

    # ---- 摘要检测 (权重 1) ----
    if "has_abstract" in expected:
        has_abstract = bool(parsed.get("abstract") or parsed.get("has_abstract"))
        abstract_ok = has_abstract == expected["has_abstract"]
        scores.append(1.0 if abstract_ok else 0.0)
        details["abstract_detected"] = has_abstract
        details["abstract_expected"] = expected["has_abstract"]

    # ---- 摘要最小长度 (权重 0.5) ----
    min_len = expected.get("abstract_min_length")
    if min_len and min_len > 0:
        abstract_text = parsed.get("abstract") or ""
        length_ok = len(abstract_text) >= min_len
        scores.append(1.0 if length_ok else max(0, len(abstract_text) / min_len))
        details["abstract_length"] = len(abstract_text)
        details["abstract_min_length_expected"] = min_len

    # ---- 章节数量 (权重 1) ----
    if "section_count_approx" in expected:
        parsed_count = parsed.get("section_count", 0)
        expected_count = expected["section_count_approx"]
        diff = abs(parsed_count - expected_count)
        section_score = max(0, 1.0 - diff / max(expected_count, 1))
        scores.append(section_score)
        details["section_count_parsed"] = parsed_count
        details["section_count_expected"] = expected_count
        details["section_count_diff"] = diff

    # ---- 已知章节匹配 (权重 1) ----
    known_sections = expected.get("known_sections")
    if known_sections and "section_names" in parsed:
        parsed_names = [s.lower() for s in (parsed.get("section_names") or [])]
        hits = sum(
            1 for s in known_sections
            if any(s.lower() in pn or pn in s.lower() for pn in parsed_names)
        )
        sec_name_score = hits / len(known_sections) if known_sections else 1.0
        scores.append(sec_name_score)
        details["known_section_hits"] = hits
        details["known_section_total"] = len(known_sections)

    # ---- 页数 (权重 1) ----
    if "page_count_approx" in expected:
        parsed_pages = parsed.get("page_count", 0)
        expected_pages = expected["page_count_approx"]
        page_diff = abs(parsed_pages - expected_pages)
        page_score = max(0, 1.0 - page_diff / max(expected_pages, 1))
        scores.append(page_score)
        details["page_count_parsed"] = parsed_pages
        details["page_count_expected"] = expected_pages

    # ---- 表格检测 (权重 1) ----
    if "has_tables" in expected and "has_tables" in parsed:
        table_ok = bool(parsed["has_tables"]) == expected["has_tables"]
        scores.append(1.0 if table_ok else 0.0)
        details["has_tables_parsed"] = bool(parsed["has_tables"])
        details["has_tables_expected"] = expected["has_tables"]

    # ---- 公式检测 (权重 1) ----
    if "has_formulas" in expected and "has_formulas" in parsed:
        formula_ok = bool(parsed["has_formulas"]) == expected["has_formulas"]
        scores.append(1.0 if formula_ok else 0.0)
        details["has_formulas_parsed"] = bool(parsed["has_formulas"])
        details["has_formulas_expected"] = expected["has_formulas"]

    # ---- 图片检测 (权重 0.5) ----
    if "has_figures" in expected and "has_figures" in parsed:
        fig_ok = bool(parsed["has_figures"]) == expected["has_figures"]
        scores.append(1.0 if fig_ok else 0.0)
        details["has_figures_parsed"] = bool(parsed["has_figures"])
        details["has_figures_expected"] = expected["has_figures"]

    overall = statistics.mean(scores) if scores else 0.0

    return {
        "overall_score": round(overall, 4),
        "scored_items": len(scores),
        "details": details,
    }


def _fuzzy_title_match(a: str, b: str, threshold: float = 0.6) -> bool:
    """简单的标题模糊匹配：基于词集交集占比。"""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    return overlap / max(len(words_a), len(words_b)) >= threshold


# ---------------------------------------------------------------------------
# 4. 延迟统计指标
# ---------------------------------------------------------------------------

def latency_stats(latencies_ms: List[float]) -> Dict[str, float]:
    """
    计算延迟统计指标。

    Args:
        latencies_ms: 每次请求的延迟（毫秒）列表

    Returns:
        {"count", "mean", "median", "p50", "p95", "p99", "min", "max"}
    """
    if not latencies_ms:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "min": 0.0,
            "max": 0.0,
        }

    sorted_lat = sorted(latencies_ms)
    n = len(sorted_lat)

    def percentile(pct: float) -> float:
        idx = int(math.ceil(pct / 100.0 * n)) - 1
        return sorted_lat[max(0, min(idx, n - 1))]

    return {
        "count": n,
        "mean": round(statistics.mean(sorted_lat), 2),
        "median": round(statistics.median(sorted_lat), 2),
        "p50": round(percentile(50), 2),
        "p95": round(percentile(95), 2),
        "p99": round(percentile(99), 2),
        "min": round(sorted_lat[0], 2),
        "max": round(sorted_lat[-1], 2),
    }


# ---------------------------------------------------------------------------
# 5. 聚合指标
# ---------------------------------------------------------------------------

def aggregate_retrieval_metrics(
    per_query_results: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    聚合多条查询的检索指标。

    Args:
        per_query_results: 每条查询的指标字典列表
            [{"recall_at_10": 0.8, "ndcg_at_10": 0.7, "keyword_hit_rate": 0.6}, ...]

    Returns:
        {"avg_recall_at_10", "avg_ndcg_at_10", "avg_keyword_hit_rate"}
    """
    if not per_query_results:
        return {}

    keys = per_query_results[0].keys()
    agg = {}
    for k in keys:
        values = [r[k] for r in per_query_results if isinstance(r.get(k), (int, float))]
        if values:
            agg[f"avg_{k}"] = round(statistics.mean(values), 4)
    return agg


def aggregate_answer_metrics(
    per_query_results: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    聚合多条查询的回答质量指标。

    Args:
        per_query_results: 每条查询的指标字典列表

    Returns:
        聚合后的指标
    """
    if not per_query_results:
        return {}

    agg = {}
    for key in ["coverage_ratio", "consistency_ratio", "structure_completeness"]:
        values = [r[key] for r in per_query_results if isinstance(r.get(key), (int, float))]
        if values:
            agg[f"avg_{key}"] = round(statistics.mean(values), 4)
    return agg
