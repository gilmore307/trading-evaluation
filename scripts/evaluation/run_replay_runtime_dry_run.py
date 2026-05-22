#!/usr/bin/env python3
"""Run one side-effect-free Replay pass through trading-execution components."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, "/root/projects/trading-execution/src")

from trading_evaluation import build_replay_runtime_dry_run


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-sleeve-id", default="crypto_spot_account")
    parser.add_argument("--target-ref", default="SOL")
    parser.add_argument("--generated-at-utc")
    parser.add_argument("--output-path", type=Path)
    args = parser.parse_args(argv)

    payload = build_replay_runtime_dry_run(
        account_sleeve_id=args.account_sleeve_id,
        target_ref=args.target_ref,
        alpha_confidence_vector={"alpha_confidence_score": 0.90},
        trade_risk_cap={
            "max_loss_usd": 25.0,
            "max_loss_pct": 0.02,
            "time_stop_at": "2026-01-05T20:00:00Z",
            "cap_enforcement_mode": "broker_native_stop",
            "cap_failure_action": "reject_order",
            "model_invalidation_price": 120.0,
            "hard_stop_price": 119.0,
            "planned_quantity": 1.5,
            "planned_limit_price": 130.0,
        },
        market_snapshot={"reference_price": 129.0},
        replay_fill_policy={"slippage_bps": 10, "fee_bps": 5},
        generated_at_utc=args.generated_at_utc,
    )
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output_path:
        args.output_path.parent.mkdir(parents=True, exist_ok=True)
        args.output_path.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
