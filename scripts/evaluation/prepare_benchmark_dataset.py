#!/usr/bin/env python3
"""Prepare a storage-side one-shot benchmark acquisition bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading_evaluation import prepare_benchmark_dataset


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare benchmark dataset manifests for one-shot acquisition.")
    parser.add_argument("--contract", required=True, type=Path, help="Path to a benchmark contract JSON file.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/root/projects/trading-storage/storage/benchmark_datasets"),
        help="Storage-owned runtime root for benchmark dataset preparation outputs.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("/root/projects/trading-storage/storage/source_data"),
        help="Trading-data storage root used for local coverage scan.",
    )
    parser.add_argument(
        "--source-contract-ref",
        default="trading-evaluation/benchmarks/promotion_benchmark_candidate_policy_replay.json",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.contract.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("benchmark contract must be a JSON object")
    prepared = prepare_benchmark_dataset(
        payload,
        output_root=args.output_root,
        data_root=args.data_root,
        source_contract_ref=args.source_contract_ref,
    )
    print(json.dumps(prepared.manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
