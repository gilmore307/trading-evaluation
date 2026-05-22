#!/usr/bin/env python3
"""Freeze a prepared replay dataset after local coverage validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading_evaluation import freeze_replay_dataset


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze a prepared replay dataset.")
    parser.add_argument(
        "--dataset-root",
        required=True,
        type=Path,
        help="Prepared replay dataset root containing dataset_manifest.json and coverage_summary.csv.",
    )
    parser.add_argument(
        "--freeze-reason",
        default="accepted_candidate_policy_replay_source_coverage",
        help="Reason written into the freeze receipt.",
    )
    args = parser.parse_args(argv)

    frozen = freeze_replay_dataset(args.dataset_root, freeze_reason=args.freeze_reason)
    print(json.dumps(frozen.freeze_receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
