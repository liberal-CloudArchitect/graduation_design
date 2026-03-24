#!/usr/bin/env python3
"""
Run phase-oriented backend checks in a predictable order.

Default flow:
  1. phase1 component tests
  2. phase1 MinerU acceptance test
  3. phase2 parent-child indexing acceptance tests

The phase1 acceptance step requires a reachable MinerU service. Use
MINERU_URL or MINERU_API_URL to point at it.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parent.parent


def pytest_command(test_path: str) -> List[str]:
    pytest_bin = shutil.which("pytest")
    if pytest_bin:
        return [pytest_bin, test_path, "-q"]
    return [sys.executable, "-m", "pytest", test_path, "-q"]


def run_step(label: str, command: List[str]) -> int:
    print(f"\n==> {label}")
    print("    " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print(f"    [FAIL] {label} (exit={result.returncode})")
    else:
        print(f"    [OK] {label}")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phase-oriented backend checks")
    parser.add_argument("--phase1-only", action="store_true", help="Run only phase 1 checks")
    parser.add_argument("--phase2-only", action="store_true", help="Run only phase 2 checks")
    parser.add_argument(
        "--skip-acceptance",
        action="store_true",
        help="Skip the remote MinerU acceptance step for phase 1",
    )
    args = parser.parse_args()

    if args.phase1_only and args.phase2_only:
        parser.error("--phase1-only and --phase2-only cannot be combined")

    steps: List[tuple[str, List[str]]] = []

    if not args.phase2_only:
        steps.append((
            "Phase 1 component tests",
            pytest_command("tests/test_phase1_components.py"),
        ))
        if not args.skip_acceptance:
            steps.append((
                "Phase 1 MinerU acceptance",
                [sys.executable, "tests/test_phase1_acceptance.py"],
            ))

    if not args.phase1_only:
        steps.append((
            "Phase 2 acceptance tests",
            pytest_command("tests/test_phase2_acceptance.py"),
        ))

    failures = 0
    for label, command in steps:
        failures += 1 if run_step(label, command) != 0 else 0
        if failures:
            break

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
