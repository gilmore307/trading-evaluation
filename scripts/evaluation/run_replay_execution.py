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

from trading_evaluation import (
    DEFAULT_CALIBRATION_WINDOW_MONTH_COUNT,
    DEFAULT_POSITION_MIN_NOTIONAL_FRACTION,
    DEFAULT_PORTFOLIO_MAX_POSITIONS,
    DEFAULT_REPLAY_INITIAL_CAPITAL_USD,
    build_candidate_policy_replay_execution_run,
)


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
    parser.add_argument("--calibration-window-month-count", type=int, default=DEFAULT_CALIBRATION_WINDOW_MONTH_COUNT)
    parser.add_argument("--initial-capital-usd", type=float, default=DEFAULT_REPLAY_INITIAL_CAPITAL_USD)
    parser.add_argument("--replay-month", help="Run one replay month from feed_acquisition_plan.csv without requiring a full frozen dataset.")
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
    parser.add_argument("--option-feature-table", default="model_05_option_expression_feature_generation")
    parser.add_argument("--option-contract-path-table", default="model_05_option_expression_data_acquisition_contract_path")
    parser.add_argument("--candidate-handoff-database-url", help="Load Layer 2 target-candidate handoff rows from PostgreSQL.")
    parser.add_argument("--candidate-handoff-schema", default="trading_data")
    parser.add_argument("--candidate-handoff-table", default="model_02_sector_context_data_acquisition")
    parser.add_argument(
        "--candidate-universe-path",
        type=Path,
        help="Load the fixed historical replay candidate universe CSV. Defaults to the storage repo shared artifact.",
    )
    parser.add_argument("--portfolio-max-positions", type=int, default=DEFAULT_PORTFOLIO_MAX_POSITIONS)
    parser.add_argument("--portfolio-position-notional-fraction", type=float, default=DEFAULT_POSITION_MIN_NOTIONAL_FRACTION)
    parser.add_argument("--portfolio-switch-minimum-rank-score-delta", type=float, default=0.05)
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
        initial_capital_usd=args.initial_capital_usd,
        include_crypto=not args.exclude_crypto,
        include_equity=not args.exclude_equity,
        equity_source_root=args.equity_source_root,
        equity_symbols=args.equity_symbols,
        replay_month=args.replay_month,
        option_feature_database_url=args.option_feature_database_url,
        option_feature_schema=args.option_feature_schema,
        option_feature_table=args.option_feature_table,
        option_contract_path_table=args.option_contract_path_table,
        candidate_handoff_database_url=args.candidate_handoff_database_url,
        candidate_handoff_schema=args.candidate_handoff_schema,
        candidate_handoff_table=args.candidate_handoff_table,
        candidate_universe_path=args.candidate_universe_path,
        portfolio_max_positions=args.portfolio_max_positions,
        portfolio_position_notional_fraction=args.portfolio_position_notional_fraction,
        portfolio_switch_minimum_rank_score_delta=args.portfolio_switch_minimum_rank_score_delta,
    )
    print(json.dumps(result.receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
