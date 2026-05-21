#!/usr/bin/env python3
"""Build a fold_settlement_run from replay decision rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trading_evaluation.settlement import build_fold_settlement_run, load_decision_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-rows", required=True, type=Path, help="Replay decision rows as JSON, JSONL, or CSV.")
    parser.add_argument("--fold-id", required=True)
    parser.add_argument("--candidate-model-ref", required=True)
    parser.add_argument("--benchmark-contract-ref", required=True)
    parser.add_argument("--replay-result-ref", required=True)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--feature-column", action="append", dest="feature_columns")
    parser.add_argument("--min-decision-rows", type=int, default=20)
    parser.add_argument("--min-auroc", type=float, default=0.53)
    parser.add_argument("--output-path", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows = load_decision_rows(args.decision_rows)
    payload = build_fold_settlement_run(
        fold_id=args.fold_id,
        candidate_model_ref=args.candidate_model_ref,
        benchmark_contract_ref=args.benchmark_contract_ref,
        replay_result_ref=args.replay_result_ref,
        baseline_ref=args.baseline_ref,
        decision_rows=rows,
        feature_columns=args.feature_columns,
        min_decision_rows=args.min_decision_rows,
        min_auroc=args.min_auroc,
    )
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
