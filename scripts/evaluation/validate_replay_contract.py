#!/usr/bin/env python3
"""Validate an evaluation replay contract JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from trading_evaluation import validate_replay_contract


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a trading-evaluation replay contract.")
    parser.add_argument("--input", required=True, type=Path, help="Path to a replay contract JSON file.")
    parser.add_argument("--output", type=Path, help="Optional path for the validation result JSON.")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("replay contract must be a JSON object")
    result = validate_replay_contract(payload).to_dict()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["validation_status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
