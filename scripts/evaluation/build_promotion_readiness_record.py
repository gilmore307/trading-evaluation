#!/usr/bin/env python3
"""Build an evaluation-owned promotion readiness record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading_evaluation.promotion import build_promotion_readiness_record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a promotion_readiness_record from an eligible evaluation decision.")
    parser.add_argument("--promotion-eligibility-json", required=True, type=Path)
    parser.add_argument("--candidate-model-ref", required=True)
    parser.add_argument("--candidate-config-ref", required=True)
    parser.add_argument("--historical-dataset-snapshot-ref")
    parser.add_argument("--rollback-ref", required=True)
    parser.add_argument("--execution-shadow-scope", default="paper_or_live_shadow")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    decision = json.loads(args.promotion_eligibility_json.read_text(encoding="utf-8"))
    if not isinstance(decision, dict):
        raise SystemExit("promotion eligibility decision must be a JSON object")
    record = build_promotion_readiness_record(
        promotion_eligibility_decision=decision,
        candidate_model_ref=args.candidate_model_ref,
        candidate_config_ref=args.candidate_config_ref,
        historical_dataset_snapshot_ref=args.historical_dataset_snapshot_ref,
        rollback_ref=args.rollback_ref,
        execution_shadow_scope=args.execution_shadow_scope,
    )
    text = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
