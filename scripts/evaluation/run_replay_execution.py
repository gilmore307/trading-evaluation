#!/usr/bin/env python3
"""Run side-effect-free Replay execution over frozen source artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, "/root/projects/trading-execution/src")
sys.path.insert(0, "/root/projects/trading-model/src")

from trading_evaluation import build_crypto_replay_execution_run


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("/root/projects/trading-storage/storage/05_replay_datasets/promotion_replay_candidate_policy"),
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--candidate-model-ref",
        default="trading-model://candidate_policy_replay/current_deterministic_crypto_policy",
    )
    parser.add_argument(
        "--replay-contract-ref",
        default="trading-evaluation/replays/promotion_replay_candidate_policy.json",
    )
    parser.add_argument("--max-decision-rows", type=int)
    parser.add_argument("--progress-path", type=Path)
    args = parser.parse_args(argv)

    result = build_crypto_replay_execution_run(
        dataset_root=args.dataset_root,
        output_dir=args.output_dir,
        run_id=args.run_id,
        candidate_model_ref=args.candidate_model_ref,
        replay_contract_ref=args.replay_contract_ref,
        max_decision_rows=args.max_decision_rows,
        progress_path=args.progress_path,
    )
    print(json.dumps(result.receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
