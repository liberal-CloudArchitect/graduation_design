#!/usr/bin/env python3
"""
Phase 1 验收检查

比较 Phase 1 candidate 报告与 Phase 0 baseline 报告，
按照 Phase 1 详细实施方案 v2 中定义的验收标准进行检查。

验收标准:
  9a. ParseBench: avg_parse_score >= 0.73
  9b. AnswerBench parse-sensitive 子集: avg_coverage_ratio >= 0.0625 (子集 baseline)
  9c. 回归门槛: Recall@10/20, consistency_ratio 不退化

用法:
    python -m tests.eval_baseline.validate_phase1 \
        --baseline reports/baseline_20260307_235542.json \
        --candidate reports/phase1_candidate.json
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


PARSE_SENSITIVE_QUERY_IDS = [
    "AB-007",
    "AB-011", "AB-012", "AB-013", "AB-014", "AB-015",
    "AB-016",
    "AB-017", "AB-018", "AB-019", "AB-020",
]

PARSE_SENSITIVE_SUBSET_BASELINE = 0.0625

PHASE1_ACCEPTANCE = {
    "avg_parse_score": {"min": 0.73, "label": "ParseBench avg_parse_score"},
    "parse_sensitive_coverage": {
        "min": PARSE_SENSITIVE_SUBSET_BASELINE,
        "label": "AnswerBench parse-sensitive subset coverage",
    },
}

REGRESSION_GATES = {
    "avg_recall_at_10": 0.9067,
    "avg_recall_at_20": 0.9733,
    "avg_consistency_ratio": 0.9895,
}


def load_report(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_parse_sensitive_coverage(report: Dict[str, Any]) -> float:
    """从 AnswerBench per_query 结果中计算 parse-sensitive 子集的 avg coverage。"""
    ab = report.get("answer_bench", {})
    per_query = ab.get("per_query", [])

    subset_coverages = []
    for item in per_query:
        qid = item.get("query_id", "")
        if qid in PARSE_SENSITIVE_QUERY_IDS:
            cov = item.get("coverage_ratio", 0.0)
            subset_coverages.append(cov)

    if not subset_coverages:
        return 0.0

    return sum(subset_coverages) / len(subset_coverages)


def validate(
    baseline: Dict[str, Any],
    candidate: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], bool]:
    """Run all Phase 1 acceptance and regression checks."""
    results = []
    all_pass = True

    # 9a. ParseBench
    pb = candidate.get("parse_bench", {})
    parse_score = pb.get("avg_parse_score", 0.0)
    gate = PHASE1_ACCEPTANCE["avg_parse_score"]
    passed = parse_score >= gate["min"]
    if not passed:
        all_pass = False
    results.append({
        "check": gate["label"],
        "value": round(parse_score, 4),
        "threshold": gate["min"],
        "passed": passed,
    })

    # 9b. Parse-sensitive subset
    subset_cov = compute_parse_sensitive_coverage(candidate)
    gate = PHASE1_ACCEPTANCE["parse_sensitive_coverage"]
    passed = subset_cov >= gate["min"]
    if not passed:
        all_pass = False
    results.append({
        "check": gate["label"],
        "value": round(subset_cov, 4),
        "threshold": gate["min"],
        "passed": passed,
    })

    # 9c. Regression gates
    rb_c = candidate.get("retrieval_bench", {}).get("aggregated", {})
    ab_c = candidate.get("answer_bench", {}).get("aggregated", {})
    candidate_flat = {**rb_c, **ab_c}

    for metric, baseline_val in REGRESSION_GATES.items():
        cand_val = candidate_flat.get(metric)
        if cand_val is None:
            results.append({
                "check": f"Regression: {metric}",
                "value": None,
                "threshold": baseline_val,
                "passed": False,
                "note": "metric not found in candidate",
            })
            all_pass = False
            continue

        passed = cand_val >= baseline_val
        if not passed:
            all_pass = False
        results.append({
            "check": f"Regression: {metric}",
            "value": round(cand_val, 4),
            "threshold": round(baseline_val, 4),
            "passed": passed,
        })

    return results, all_pass


def print_results(results: List[Dict[str, Any]], all_pass: bool):
    header = f"{'Check':<55} {'Value':>8} {'Threshold':>10} {'Status':>8}"
    print("=" * len(header))
    print("Phase 1 Acceptance Validation")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    for r in results:
        val = f"{r['value']:.4f}" if r["value"] is not None else "N/A"
        thr = f"{r['threshold']:.4f}" if isinstance(r["threshold"], float) else str(r["threshold"])
        status = "\033[92mPASS\033[0m" if r["passed"] else "\033[91mFAIL\033[0m"
        print(f"{r['check']:<55} {val:>8} {thr:>10} {status:>8}")
        if r.get("note"):
            print(f"{'':>55} {r['note']}")

    print("=" * len(header))
    if all_pass:
        print("\n\033[92m*** Phase 1 ACCEPTED ***\033[0m")
    else:
        print("\n\033[91m*** Phase 1 NOT YET ACCEPTED ***\033[0m")


def main():
    parser = argparse.ArgumentParser(description="Phase 1 acceptance validation")
    parser.add_argument("--baseline", required=True, help="Path to Phase 0 baseline report")
    parser.add_argument("--candidate", required=True, help="Path to Phase 1 candidate report")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()

    baseline = load_report(Path(args.baseline))
    candidate = load_report(Path(args.candidate))

    results, all_pass = validate(baseline, candidate)

    if args.json:
        output = {
            "phase": "phase1",
            "checks": results,
            "all_pass": all_pass,
            "baseline_path": args.baseline,
            "candidate_path": args.candidate,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\nBaseline:  {args.baseline}")
        print(f"Candidate: {args.candidate}\n")
        print_results(results, all_pass)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
