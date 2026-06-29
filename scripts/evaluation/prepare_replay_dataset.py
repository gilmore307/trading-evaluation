#!/usr/bin/env python3
"""Prepare a storage-side one-shot replay acquisition bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading_evaluation import prepare_replay_dataset


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare replay dataset manifests for one-shot acquisition.")
    parser.add_argument("--contract", required=True, type=Path, help="Path to a replay contract JSON file.")
    parser.add_argument("--candidate-fold-id", help="Fold id that this replay dataset is scoped to, for example fold_2016-01_2017-06.")
    parser.add_argument("--base-context-ref", help="Path to the M01/M02 base context artifact.")
    parser.add_argument("--start-date", help="Override replay start date for a fold-bound replay window.")
    parser.add_argument("--end-date", help="Override replay end-exclusive date for a fold-bound replay window.")
    parser.add_argument("--min-trading-days", type=int, help="Override minimum trading days for a fold-bound replay window.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/projects/trading-storage/storage/05_replay_datasets"),
        help="Storage-owned runtime root for replay dataset preparation outputs.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("/root/projects/trading-storage/storage/01_source_data"),
        help="Trading-data storage root used for local coverage scan.",
    )
    parser.add_argument(
        "--source-contract-ref",
        default="trading-evaluation/replays/promotion_replay_candidate_policy.json",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.contract.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("replay contract must be a JSON object")
    if args.candidate_fold_id:
        payload["candidate_fold_id"] = args.candidate_fold_id
    if args.base_context_ref:
        payload["base_context_ref"] = args.base_context_ref
    if args.start_date:
        payload["start_date"] = args.start_date
    if args.end_date:
        payload["end_date"] = args.end_date
    if args.start_date or args.end_date:
        start_date = str(payload.get("start_date") or "")
        end_date = str(payload.get("end_date") or "")
        if start_date and end_date:
            payload["excluded_training_windows"] = [
                {
                    "start_date": start_date,
                    "end_date": end_date,
                    "reason": "fold-bound replay holdout",
                }
            ]
    if args.min_trading_days is not None:
        payload["min_trading_days"] = args.min_trading_days
    prepared = prepare_replay_dataset(
        payload,
        output_root=args.output_root,
        data_root=args.data_root,
        source_contract_ref=args.source_contract_ref,
    )
    print(json.dumps(prepared.manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
