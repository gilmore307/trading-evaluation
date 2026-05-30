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

from trading_evaluation import build_candidate_policy_replay_execution_run


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
        required=True,
    )
    parser.add_argument("--after-cost-alpha-model-json", type=Path, required=True)
    parser.add_argument(
        "--replay-contract-ref",
        default="trading-evaluation/replays/promotion_replay_candidate_policy.json",
    )
    parser.add_argument("--max-decision-rows", type=int)
    parser.add_argument("--progress-path", type=Path)
    parser.add_argument("--calibration-window-month-count", type=int, default=1)
    parser.add_argument("--exclude-crypto", action="store_true", help="Run only the materialized equity/option sleeve.")
    parser.add_argument("--exclude-equity", action="store_true", help="Run only the fixed crypto sleeve.")
    parser.add_argument("--equity-source-root", type=Path, default=Path("/root/projects/trading-storage/storage/01_source_data/monthly_backfill/alpaca_bars"))
    parser.add_argument(
        "--equity-symbol",
        action="append",
        dest="equity_symbols",
        help="Limit materialized Alpaca equity replay to one symbol. Repeat for multiple symbols.",
    )
    parser.add_argument("--option-feature-database-url", help="Load point-in-time Layer 9 option feature rows from PostgreSQL.")
    parser.add_argument("--option-feature-schema", default="trading_data")
    parser.add_argument("--option-feature-table", default="m09_option_expression_feature_generation")
    args = parser.parse_args(argv)
    after_cost_alpha_model = json.loads(args.after_cost_alpha_model_json.read_text(encoding="utf-8"))

    result = build_candidate_policy_replay_execution_run(
        dataset_root=args.dataset_root,
        output_dir=args.output_dir,
        run_id=args.run_id,
        candidate_model_ref=args.candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        after_cost_alpha_model_ref=str(args.after_cost_alpha_model_json),
        replay_contract_ref=args.replay_contract_ref,
        max_decision_rows=args.max_decision_rows,
        progress_path=args.progress_path,
        calibration_window_month_count=args.calibration_window_month_count,
        include_crypto=not args.exclude_crypto,
        include_equity=not args.exclude_equity,
        equity_source_root=args.equity_source_root,
        equity_symbols=args.equity_symbols,
        option_feature_database_url=args.option_feature_database_url,
        option_feature_schema=args.option_feature_schema,
        option_feature_table=args.option_feature_table,
    )
    print(json.dumps(result.receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
