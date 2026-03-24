#!/usr/bin/env python3
"""Smoke test for a running MinerU service.

Checks:
1. ``GET /health`` responds and includes key fields.
2. Optionally ``POST /parse`` succeeds for one PDF and returns the expected
   response contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List


HEALTH_REQUIRED_KEYS = [
    "status",
    "parse_backend",
    "configured_backend",
]

PARSE_REQUIRED_KEYS = [
    "markdown",
    "pages",
    "metadata",
    "parser_version",
    "elapsed_ms",
]


def _headers(api_key: str) -> Dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _assert_keys(payload: Dict, required_keys: List[str], label: str) -> None:
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise RuntimeError(f"{label} missing required keys: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test a MinerU service")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8010",
        help="MinerU service base URL",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Optional MinerU API key",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        help="Optional PDF path for /parse smoke testing",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    try:
        import httpx

        with httpx.Client(timeout=args.timeout) as client:
            health = client.get(f"{base_url}/health", headers=_headers(args.api_key))
            health.raise_for_status()
            health_payload = health.json()
            _assert_keys(health_payload, HEALTH_REQUIRED_KEYS, "health")
            print("[OK] /health")
            print(json.dumps(health_payload, ensure_ascii=False, indent=2))

            if args.pdf:
                if not args.pdf.exists():
                    raise FileNotFoundError(f"PDF not found: {args.pdf}")

                with args.pdf.open("rb") as fh:
                    parse = client.post(
                        f"{base_url}/parse",
                        files={"file": (args.pdf.name, fh, "application/pdf")},
                        headers=_headers(args.api_key),
                    )
                parse.raise_for_status()
                parse_payload = parse.json()
                _assert_keys(parse_payload, PARSE_REQUIRED_KEYS, "parse")
                print("[OK] /parse")
                print(
                    json.dumps(
                        {
                            "parser_version": parse_payload.get("parser_version"),
                            "elapsed_ms": parse_payload.get("elapsed_ms"),
                            "markdown_length": len(parse_payload.get("markdown", "")),
                            "page_count": len(parse_payload.get("pages", [])),
                            "metadata": parse_payload.get("metadata", {}),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
    except ModuleNotFoundError as exc:
        print(
            f"[FAIL] {exc}. Install service dependencies first, for example: "
            f"`pip install -r requirements.txt`",
            file=sys.stderr,
        )
        return 1
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
