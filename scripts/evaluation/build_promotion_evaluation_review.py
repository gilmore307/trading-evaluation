#!/usr/bin/env python3
"""Build promotion evaluation review and eligibility decision artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading_evaluation.promotion_review import build_promotion_review_result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settlement-run-json", required=True, type=Path)
    parser.add_argument("--settlement-run-ref", required=True)
    parser.add_argument("--benchmark-contract-ref", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--candidate-label", default="model_a")
    parser.add_argument("--comparison-label", default="model_b")
    parser.add_argument("--comparison-result-ref")
    parser.add_argument("--candidate-config-ref")
    parser.add_argument("--first-run-evidence-ref")
    parser.add_argument("--first-model-bootstrap", action="store_true")
    args = parser.parse_args(argv)

    settlement_run = json.loads(args.settlement_run_json.read_text(encoding="utf-8"))
    if not isinstance(settlement_run, dict):
        raise SystemExit("settlement run must be a JSON object")
    result = build_promotion_review_result(
        settlement_run=settlement_run,
        settlement_run_ref=args.settlement_run_ref,
        benchmark_contract_ref=args.benchmark_contract_ref,
        output_dir=args.output_dir,
        candidate_label=args.candidate_label,
        comparison_label=args.comparison_label,
        comparison_result_ref=args.comparison_result_ref,
        candidate_config_ref=args.candidate_config_ref,
        first_run_evidence_ref=args.first_run_evidence_ref,
        first_model_bootstrap=args.first_model_bootstrap,
    )
    print(
        json.dumps(
            {
                "contract_type": "promotion_evaluation_review_result",
                "review_ref": str(result.review_path),
                "eligibility_decision_ref": str(result.eligibility_decision_path),
                "recommendation": result.review["recommendation"],
                "decision_status": result.eligibility_decision["decision_status"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
