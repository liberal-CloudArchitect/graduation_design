#!/usr/bin/env python3
"""
Baseline vs Candidate Comparator

比较两次评测报告，输出差值表格和回归检测结果。
可在 CI 中运行，任一核心指标跌破门槛则返回非零退出码。

用法:
    python -m tests.eval_baseline.compare \\
        --baseline reports/baseline_20260303_120000.json \\
        --candidate reports/baseline_20260310_120000.json

    # 仅输出 JSON（适合 CI 集成）
    python -m tests.eval_baseline.compare --baseline ... --candidate ... --json
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Regression thresholds
# ---------------------------------------------------------------------------

REGRESSION_RULES: Dict[str, Dict[str, Any]] = {
    # 检索质量 — 不得低于基线
    "avg_recall_at_10": {"direction": "higher_better", "min_delta": 0.0},
    "avg_recall_at_20": {"direction": "higher_better", "min_delta": 0.0},
    "avg_ndcg_at_10": {"direction": "higher_better", "min_delta": 0.0},
    "avg_keyword_hit_rate": {"direction": "higher_better", "min_delta": 0.0},
    # 回答质量 — 不得低于基线
    "avg_coverage_ratio": {"direction": "higher_better", "min_delta": 0.0},
    "avg_consistency_ratio": {"direction": "higher_better", "min_delta": 0.0},
    "avg_structure_completeness": {"direction": "higher_better", "min_delta": 0.0},
    # 解析质量 — 不得低于基线
    "avg_parse_score": {"direction": "higher_better", "min_delta": 0.0},
    # 延迟 — 增幅不超过 20%（匹配 extract_flat_metrics 输出的实际 key）
    "retrieval_p95": {"direction": "lower_better", "max_increase_ratio": 0.20},
    "answer_p95": {"direction": "lower_better", "max_increase_ratio": 0.20},
    "latency_p95": {"direction": "lower_better", "max_increase_ratio": 0.20},
}


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------

def load_report(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_flat_metrics(report: Dict[str, Any]) -> Dict[str, float]:
    """Extract a flat dict of comparable metrics from a report."""
    flat: Dict[str, float] = {}

    # Retrieval bench
    rb = report.get("retrieval_bench", {})
    for k, v in rb.get("aggregated", {}).items():
        flat[k] = v
    for k, v in rb.get("latency", {}).items():
        flat[f"retrieval_{k}"] = v

    # Answer bench
    ab = report.get("answer_bench", {})
    for k, v in ab.get("aggregated", {}).items():
        flat[k] = v
    for k, v in ab.get("latency", {}).items():
        flat[f"answer_{k}"] = v

    # Parse bench
    pb = report.get("parse_bench", {})
    if "avg_parse_score" in pb:
        flat["avg_parse_score"] = pb["avg_parse_score"]

    # Latency bench (standalone)
    lb = report.get("latency_bench", {})
    for k, v in lb.get("aggregated", {}).items():
        flat[f"latency_{k}"] = v

    return flat


def compare(
    baseline: Dict[str, float],
    candidate: Dict[str, float],
) -> List[Dict[str, Any]]:
    """Compare two flat metric dicts and produce per-metric comparison rows."""
    all_keys = sorted(set(baseline.keys()) | set(candidate.keys()))
    rows = []

    for key in all_keys:
        b_val = baseline.get(key)
        c_val = candidate.get(key)

        if b_val is None or c_val is None:
            rows.append({
                "metric": key,
                "baseline": b_val,
                "candidate": c_val,
                "delta": None,
                "delta_pct": None,
                "status": "SKIP",
                "reason": "metric missing in one report",
            })
            continue

        delta = c_val - b_val
        delta_pct = (delta / b_val * 100) if b_val != 0 else (0.0 if delta == 0 else float("inf"))

        status, reason = _check_regression(key, b_val, c_val, delta, delta_pct)

        rows.append({
            "metric": key,
            "baseline": round(b_val, 4),
            "candidate": round(c_val, 4),
            "delta": round(delta, 4),
            "delta_pct": round(delta_pct, 2),
            "status": status,
            "reason": reason,
        })

    return rows


def _check_regression(
    key: str,
    b_val: float,
    c_val: float,
    delta: float,
    delta_pct: float,
) -> Tuple[str, str]:
    """Check a single metric against regression rules."""
    rule = REGRESSION_RULES.get(key)
    if rule is None:
        # No rule defined — informational only
        return ("INFO", "")

    direction = rule.get("direction", "higher_better")

    if direction == "higher_better":
        min_delta = rule.get("min_delta", 0.0)
        if delta < -abs(min_delta):
            return ("FAIL", f"regression: {delta:+.4f} (must be >= {-abs(min_delta)})")
        if delta < 0:
            return ("WARN", f"slight drop: {delta:+.4f}")
        return ("PASS", f"improved: {delta:+.4f}")

    elif direction == "lower_better":
        max_ratio = rule.get("max_increase_ratio", 0.20)
        if b_val > 0 and (c_val - b_val) / b_val > max_ratio:
            return ("FAIL", f"latency increase {delta_pct:+.1f}% exceeds {max_ratio*100:.0f}%")
        return ("PASS", "")

    return ("INFO", "")


def has_regression(rows: List[Dict[str, Any]]) -> bool:
    return any(r["status"] == "FAIL" for r in rows)


# ---------------------------------------------------------------------------
# Pretty print
# ---------------------------------------------------------------------------

def print_summary(rows: List[Dict[str, Any]]):
    header = f"{'Metric':<35} {'Baseline':>10} {'Candidate':>10} {'Delta':>10} {'Pct':>8} {'Status':>6}"
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for r in rows:
        b = f"{r['baseline']:.4f}" if r["baseline"] is not None else "N/A"
        c = f"{r['candidate']:.4f}" if r["candidate"] is not None else "N/A"
        d = f"{r['delta']:+.4f}" if r["delta"] is not None else "N/A"
        p = f"{r['delta_pct']:+.1f}%" if r["delta_pct"] is not None else "N/A"
        s = r["status"]

        # Color hints for terminal
        if s == "FAIL":
            status_str = f"\033[91m{s}\033[0m"
        elif s == "WARN":
            status_str = f"\033[93m{s}\033[0m"
        elif s == "PASS":
            status_str = f"\033[92m{s}\033[0m"
        else:
            status_str = s

        print(f"{r['metric']:<35} {b:>10} {c:>10} {d:>10} {p:>8} {status_str:>6}")

        if r.get("reason"):
            print(f"{'':>35} {r['reason']}")

    print("=" * len(header))

    fail_count = sum(1 for r in rows if r["status"] == "FAIL")
    warn_count = sum(1 for r in rows if r["status"] == "WARN")
    pass_count = sum(1 for r in rows if r["status"] == "PASS")

    print(f"\nSummary: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")

    if fail_count > 0:
        print("\n*** REGRESSION DETECTED — candidate has metrics below baseline ***")
    else:
        print("\nNo regression detected.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Compare baseline vs candidate eval reports")
    parser.add_argument("--baseline", required=True, help="Path to baseline report JSON")
    parser.add_argument("--candidate", required=True, help="Path to candidate report JSON")
    parser.add_argument("--json", action="store_true", help="Output comparison as JSON only")
    args = parser.parse_args()

    baseline_report = load_report(Path(args.baseline))
    candidate_report = load_report(Path(args.candidate))

    baseline_flat = extract_flat_metrics(baseline_report)
    candidate_flat = extract_flat_metrics(candidate_report)

    rows = compare(baseline_flat, candidate_flat)

    if args.json:
        output = {
            "comparison": rows,
            "has_regression": has_regression(rows),
            "baseline_path": args.baseline,
            "candidate_path": args.candidate,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\nBaseline:  {args.baseline}")
        print(f"Candidate: {args.candidate}\n")
        print_summary(rows)

    if has_regression(rows):
        sys.exit(1)


if __name__ == "__main__":
    main()
