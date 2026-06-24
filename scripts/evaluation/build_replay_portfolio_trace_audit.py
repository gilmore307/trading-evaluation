#!/usr/bin/env python3
"""Build a finite-capital M04-to-M05 replay trigger trace audit."""

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
    DEFAULT_TARGET_ALLOCATION_FRACTION,
    DEFAULT_PORTFOLIO_MAX_POSITIONS,
    DEFAULT_REPLAY_INITIAL_CAPITAL_USD,
    DEFAULT_SWITCH_MINIMUM_RANK_SCORE_DELTA,
    build_candidate_policy_portfolio_trace_audit,
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
    parser.add_argument("--candidate-model-ref", required=True)
    parser.add_argument("--after-cost-alpha-model-json", type=Path, required=True)
    parser.add_argument(
        "--replay-contract-ref",
        default="trading-evaluation/replays/promotion_replay_candidate_policy.json",
    )
    parser.add_argument("--calibration-window-month-count", type=int, default=DEFAULT_CALIBRATION_WINDOW_MONTH_COUNT)
    parser.add_argument("--calibration-max-decision-rows", type=int)
    parser.add_argument("--initial-capital-usd", type=float, default=DEFAULT_REPLAY_INITIAL_CAPITAL_USD)
    parser.add_argument("--replay-month", help="Audit one replay month from feed_acquisition_plan.csv.")
    parser.add_argument("--exclude-crypto", action="store_true", help="Audit only the materialized equity/option sleeve.")
    parser.add_argument("--exclude-equity", action="store_true", help="Audit only the fixed crypto sleeve.")
    parser.add_argument(
        "--equity-source-root",
        type=Path,
        default=Path("/root/projects/trading-storage/storage/01_source_data/monthly_backfill/alpaca_bars"),
    )
    parser.add_argument(
        "--equity-symbol",
        action="append",
        dest="equity_symbols",
        help="Limit materialized Alpaca equity audit to one symbol. Repeat for multiple symbols.",
    )
    parser.add_argument("--candidate-handoff-database-url", help="Load M02 target-candidate handoff rows from PostgreSQL.")
    parser.add_argument("--candidate-handoff-schema", default="trading_data")
    parser.add_argument("--candidate-handoff-table", default="model_02_target_state_data_acquisition")
    parser.add_argument(
        "--candidate-universe-path",
        type=Path,
        help="Load the fixed historical replay candidate universe CSV. Defaults to the storage repo shared artifact.",
    )
    parser.add_argument("--max-trace-timestamps", type=int, default=20)
    parser.add_argument("--max-positions", type=int, default=DEFAULT_PORTFOLIO_MAX_POSITIONS)
    parser.add_argument("--default-target-allocation-fraction", type=float, default=DEFAULT_TARGET_ALLOCATION_FRACTION)
    parser.add_argument(
        "--switch-minimum-rank-score-delta",
        type=float,
        default=DEFAULT_SWITCH_MINIMUM_RANK_SCORE_DELTA,
    )
    args = parser.parse_args(argv)

    after_cost_alpha_model = json.loads(args.after_cost_alpha_model_json.read_text(encoding="utf-8"))
    result = build_candidate_policy_portfolio_trace_audit(
        dataset_root=args.dataset_root,
        output_dir=args.output_dir,
        run_id=args.run_id,
        candidate_model_ref=args.candidate_model_ref,
        after_cost_alpha_model=after_cost_alpha_model,
        after_cost_alpha_model_ref=str(args.after_cost_alpha_model_json),
        replay_contract_ref=args.replay_contract_ref,
        calibration_window_month_count=args.calibration_window_month_count,
        calibration_max_decision_rows=args.calibration_max_decision_rows,
        initial_capital_usd=args.initial_capital_usd,
        include_crypto=not args.exclude_crypto,
        include_equity=not args.exclude_equity,
        equity_source_root=args.equity_source_root,
        equity_symbols=args.equity_symbols,
        replay_month=args.replay_month,
        candidate_handoff_database_url=args.candidate_handoff_database_url,
        candidate_handoff_schema=args.candidate_handoff_schema,
        candidate_handoff_table=args.candidate_handoff_table,
        candidate_universe_path=args.candidate_universe_path,
        max_trace_timestamps=args.max_trace_timestamps,
        max_positions=args.max_positions,
        default_target_allocation_fraction=args.default_target_allocation_fraction,
        switch_minimum_rank_score_delta=args.switch_minimum_rank_score_delta,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
