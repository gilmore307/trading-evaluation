#!/usr/bin/env python3
"""Build an evaluation-owned model activation record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading_evaluation.activation import build_model_activation_record


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a model_activation_record from an eligible evaluation decision.")
    parser.add_argument("--promotion-eligibility-json", required=True, type=Path)
    parser.add_argument("--activated-model-id", required=True)
    parser.add_argument("--activated-config-ref", required=True)
    parser.add_argument("--active-model-config-ref", required=True)
    parser.add_argument("--rollback-ref", required=True)
    parser.add_argument("--activation-scope", required=True)
    parser.add_argument("--activated-by", default="trading-evaluation")
    parser.add_argument("--replaced-config-ref")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    decision = json.loads(args.promotion_eligibility_json.read_text(encoding="utf-8"))
    if not isinstance(decision, dict):
        raise SystemExit("promotion eligibility decision must be a JSON object")
    record = build_model_activation_record(
        promotion_eligibility_decision=decision,
        activated_model_id=args.activated_model_id,
        activated_config_ref=args.activated_config_ref,
        active_model_config_ref=args.active_model_config_ref,
        rollback_ref=args.rollback_ref,
        activation_scope=args.activation_scope,
        activated_by=args.activated_by,
        replaced_config_ref=args.replaced_config_ref,
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

