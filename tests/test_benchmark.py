import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import validate_benchmark_contract


VALID_CONTRACT = {
    "contract_id": "primary_benchmark_pending_review",
    "target_symbol": "XYZ",
    "start_date": "2018-01-01",
    "end_date": "2021-12-31",
    "min_trading_days": 756,
    "market_condition_tags": ["trend_up", "drawdown", "high_volatility", "range_bound", "event_shock"],
    "data_snapshot_ref": "storage://benchmark/data_snapshot/pending_review",
    "cost_model_ref": "storage://benchmark/cost_model/pending_review",
    "baseline_refs": ["baseline://buy_and_hold", "baseline://no_trade"],
    "training_universe_symbols": ["AAOI", "SPY"],
    "excluded_training_windows": [{"start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"}],
    "guardrail_refs": ["benchmark://guardrail/liquidity_regime"],
}


class BenchmarkContractTests(unittest.TestCase):
    def test_valid_contract_passes(self):
        result = validate_benchmark_contract(VALID_CONTRACT)
        self.assertEqual(result.validation_status, "passed")
        self.assertEqual(result.errors, ())
        self.assertEqual(result.contract.target_symbol, "XYZ")

    def test_training_symbol_overlap_fails(self):
        payload = dict(VALID_CONTRACT, target_symbol="AAOI")
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("target_symbol must not appear in training_universe_symbols", result.errors)

    def test_short_or_simple_window_fails(self):
        payload = dict(
            VALID_CONTRACT,
            min_trading_days=60,
            market_condition_tags=["trend_up"],
        )
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("min_trading_days must be at least one trading year", result.errors)
        self.assertIn("market_condition_tags must cover at least four distinct market conditions", result.errors)

    def test_cli_outputs_validation_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(VALID_CONTRACT), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/validate_benchmark_contract.py",
                    "--input",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(result["contract_type"], "evaluation_benchmark_contract_validation")
        self.assertEqual(result["validation_status"], "passed")


if __name__ == "__main__":
    unittest.main()

