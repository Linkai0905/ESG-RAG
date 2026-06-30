# main.py
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from config import DEFAULT_ANCHOR_DATE, DEFAULT_COMPANY, RUNS_DIR, make_run_id
from graph import build_graph


def main():
    parser = argparse.ArgumentParser(
        description="ESG monthly report workflow: LangGraph + Browser Fetch + MinerU + Chroma"
    )

    parser.add_argument(
        "--company",
        default=DEFAULT_COMPANY,
        help="Company name. Default: 中国神华",
    )

    parser.add_argument(
        "--anchor-date",
        default=DEFAULT_ANCHOR_DATE,
        help="Anchor date. Default: 2026-06-29",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove the current run directory before execution",
    )

    args = parser.parse_args()

    run_id = make_run_id(args.company, args.anchor_date)
    run_dir = RUNS_DIR / run_id

    if args.reset and run_dir.exists():
        shutil.rmtree(run_dir)

    graph = build_graph()

    result = graph.invoke({
        "company": args.company,
        "anchor_date": args.anchor_date,
    })

    print("\n=== ESG workflow completed ===")
    print(f"Company: {result.get('company')}")
    print(f"Period: {result.get('period_start')} 至 {result.get('period_end')}")
    print(f"Run ID: {result.get('run_id')}")

    print("\n=== Metrics ===")
    print(json.dumps(result.get("metrics", {}), ensure_ascii=False, indent=2))

    errors = result.get("errors", [])
    if errors:
        print("\n=== Errors ===")
        print(json.dumps(errors, ensure_ascii=False, indent=2))

    print("\n=== Output Paths ===")
    print(json.dumps(result.get("output_paths", {}), ensure_ascii=False, indent=2))

    report_path = result.get("output_paths", {}).get("report")
    if report_path:
        print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
