"""Evaluation runner for CMART golden dataset.

Sends each query in the golden dataset to the /query endpoint and compares
the actual decision against the expected decision. Prints a per-case report
and a summary with pass rate and average latency.

Usage:
    uv run python scripts/run_evals.py \
        --host https://cmart-api-production.up.railway.app \
        --api-key <your-key>

Environment variables (used when flags are omitted):
    CMART_HOST     Base URL of the deployed API
    CMART_API_KEY  Bearer token for authentication
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

DATASET_PATH = Path(__file__).parent.parent / "tests" / "evaluation" / "golden_dataset.json"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run CMART evals against a live deployment.")
    parser.add_argument(
        "--host",
        default=os.getenv("CMART_HOST", "https://cmart-api-production.up.railway.app"),
        help="Base URL of the CMART API (default: CMART_HOST env or Railway URL)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("CMART_API_KEY", ""),
        help="Bearer API key (default: CMART_API_KEY env)",
    )
    parser.add_argument(
        "--dataset",
        default=str(DATASET_PATH),
        help="Path to golden_dataset.json",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )
    return parser.parse_args()


def _run(args: argparse.Namespace) -> None:
    if not args.api_key:
        print("Error: API key required. Pass --api-key or set CMART_API_KEY.", file=sys.stderr)
        sys.exit(1)

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    if not dataset:
        print("Golden dataset is empty.", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Content-Type": "application/json",
    }

    passed = 0
    failed = 0
    total_latency = 0
    errors = 0

    print(f"\n{BOLD}CMART Eval Runner{RESET}")
    print(f"Host:    {args.host}")
    print(f"Dataset: {args.dataset}")
    print(f"Cases:   {len(dataset)}\n")
    print(
        f"{'ID':<10} {'Expected':<10} {'Actual':<10} {'Reason':<28} "
        f"{'RS':<8} {'QC':<12} {'GC':<18} {'SA':<8} {'ms':<6} Result"
    )
    print("-" * 120)

    with httpx.Client(base_url=args.host, headers=headers, timeout=args.timeout) as client:
        for case in dataset:
            case_id = case["id"]
            query = case["query"]
            expected_decision = case["expected_decision"]

            try:
                response = client.post(
                    "/query",
                    json={
                        "query": query,
                        "user_id": "eval-runner",
                        "account_id": "eval",
                    },
                )
                response.raise_for_status()
                body = response.json()

                actual_decision = body.get("decision", "unknown")
                reason = body.get("reason", "")
                latency = body.get("latency_ms", 0)
                total_latency += latency

                sigs = body.get("signals") or {}
                rs = sigs.get("rs") or "-"
                qc = sigs.get("qc") or "-"
                gc = sigs.get("gc") or "-"
                sa = sigs.get("sa") or "-"

                if actual_decision == expected_decision:
                    passed += 1
                    result = PASS
                else:
                    failed += 1
                    result = FAIL

                print(
                    f"{case_id:<10} {expected_decision:<10} {actual_decision:<10} "
                    f"{reason:<28} {rs:<8} {qc:<12} {gc:<18} {sa:<8} {latency:<6} {result}"
                )

            except Exception as exc:
                errors += 1
                err = str(exc)[:28]
                row = (
                    f"{case_id:<10} {expected_decision:<10} {'ERROR':<10} {err:<28} "
                    f"{'-':<8} {'-':<12} {'-':<18} {'-':<8} {'':6} {FAIL}"
                )
                print(row)

    total = passed + failed + errors
    avg_latency = total_latency // max(passed + failed, 1)

    print("-" * 120)
    print(f"\n{BOLD}Results{RESET}")
    print(f"  Passed:      {passed}/{total}")
    print(f"  Failed:      {failed}/{total}")
    print(f"  Errors:      {errors}/{total}")
    print(f"  Pass rate:   {passed / total * 100:.1f}%")
    print(f"  Avg latency: {avg_latency}ms\n")

    if failed > 0 or errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    _run(_parse_args())
