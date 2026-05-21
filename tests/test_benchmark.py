import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import is_training_fold_blocked_by_benchmark, validate_benchmark_contract


VALID_CONTRACT = {
    "contract_id": "promotion_benchmark_replay_fixture",
    "benchmark_mode": "candidate_policy_replay",
    "start_date": "2021-01-01",
    "end_date": "2026-01-01",
    "min_trading_days": 1255,
    "market_condition_tags": ["trend_up", "drawdown", "high_volatility", "event_shock"],
    "candidate_policy_ref": "trading-model://layer_03_target_candidate_universe_policy/default",
    "replay_route_ref": "trading-execution://historical_clock/realtime_decision_path",
    "data_snapshot_ref": "storage://benchmark/promotion_replay/data_snapshot/pending_materialization",
    "cost_model_ref": "storage://benchmark/promotion_replay/cost_model/pending_review",
    "baseline_refs": ["baseline://active_model", "baseline://no_trade"],
    "guardrail_refs": ["benchmark://guardrail/liquidity_regime"],
    "selection_metric_refs": ["metric://net_return_after_costs", "metric://max_drawdown", "metric://selection_hit_rate"],
    "excluded_training_windows": [
        {
            "start_date": "2021-01-01",
            "end_date": "2026-01-01",
            "reason": "promotion benchmark replay holdout",
        }
    ],
}


class BenchmarkContractTests(unittest.TestCase):
    def test_valid_candidate_policy_replay_contract_passes(self):
        result = validate_benchmark_contract(VALID_CONTRACT)
        self.assertEqual(result.validation_status, "passed")
        self.assertEqual(result.warnings, ())
        self.assertEqual(result.contract.benchmark_mode, "candidate_policy_replay")
        self.assertEqual(result.contract.candidate_policy_ref, VALID_CONTRACT["candidate_policy_ref"])

    def test_fixed_target_panel_fields_are_rejected(self):
        payload = dict(
            VALID_CONTRACT,
            target_symbol="XYZ",
            benchmark_components=[
                {
                    "component_id": "component_a",
                    "target_symbol": "XYZ",
                    "start_date": "2024-01-02",
                    "end_date": "2026-01-02",
                    "weight": 1.0,
                }
            ],
        )
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn(
            "target_symbol is not allowed for promotion replay; the model must select targets from the candidate policy",
            result.errors,
        )
        self.assertIn("benchmark_components are obsolete for promotion replay; use candidate_policy_ref", result.errors)

    def test_canonical_replay_window_is_required(self):
        payload = dict(VALID_CONTRACT, start_date="2024-01-02", end_date="2024-12-31", min_trading_days=251)
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("replay window must be the canonical 2021-01-01 to 2026-01-01 end-exclusive window", result.errors)
        self.assertIn("min_trading_days must be at least 1255 for the canonical replay window", result.errors)

    def test_two_year_replay_window_is_rejected(self):
        payload = dict(
            VALID_CONTRACT,
            start_date="2024-01-02",
            end_date="2026-01-02",
            min_trading_days=504,
            excluded_training_windows=[
                {
                    "start_date": "2024-01-02",
                    "end_date": "2026-01-02",
                    "reason": "minimum replay holdout",
                }
            ],
        )
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("replay window must be the canonical 2021-01-01 to 2026-01-01 end-exclusive window", result.errors)
        self.assertIn("min_trading_days must be at least 1255 for the canonical replay window", result.errors)

    def test_candidate_policy_and_replay_route_are_required(self):
        payload = dict(VALID_CONTRACT, candidate_policy_ref="", replay_route_ref="", selection_metric_refs=[])
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("candidate_policy_ref is required", result.errors)
        self.assertIn("replay_route_ref is required", result.errors)
        self.assertIn("selection_metric_refs must include at least one accepted performance metric", result.errors)

    def test_guardrail_refs_are_required(self):
        payload = dict(VALID_CONTRACT, guardrail_refs=[])
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("guardrail_refs must include at least one accepted guardrail replay", result.errors)

    def test_replay_holdout_must_cover_full_window(self):
        payload = dict(
            VALID_CONTRACT,
            excluded_training_windows=[
                {
                    "start_date": "2024-01-02",
                    "end_date": "2025-01-02",
                    "reason": "partial holdout",
                }
            ],
        )
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("excluded_training_windows must cover the full replay window", result.errors)

    def test_training_fold_overlap_is_blocked_by_replay_window(self):
        result = validate_benchmark_contract(VALID_CONTRACT)
        self.assertTrue(
            is_training_fold_blocked_by_benchmark(
                result.contract,
                fold_start_date="2023-01-01",
                fold_end_date="2023-06-30",
            )
        )
        self.assertFalse(
            is_training_fold_blocked_by_benchmark(
                result.contract,
                fold_start_date="2026-01-01",
                fold_end_date="2026-06-30",
            )
        )

    def test_cli_outputs_validation_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps(VALID_CONTRACT), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/validate_replay_contract.py",
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
