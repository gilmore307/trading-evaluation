import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import is_training_fold_blocked_by_benchmark, validate_benchmark_contract


VALID_CONTRACT = {
    "contract_id": "primary_benchmark_pending_review",
    "start_date": "2018-01-01",
    "end_date": "2021-12-31",
    "min_trading_days": 756,
    "market_condition_tags": ["trend_up", "drawdown", "high_volatility", "range_bound", "event_shock"],
    "data_snapshot_ref": "storage://benchmark/data_snapshot/pending_review",
    "cost_model_ref": "storage://benchmark/cost_model/pending_review",
    "baseline_refs": ["baseline://buy_and_hold", "baseline://no_trade"],
    "training_universe_symbols": ["AAOI", "SPY", "XYZ"],
    "benchmark_components": [
        {
            "component_id": "component_a",
            "target_symbol": "XYZ",
            "asset_class": "equity_single_name",
            "theme_bucket": "hot_thematic_growth",
            "component_role": "primary",
            "start_date": "2018-01-01",
            "end_date": "2021-12-31",
            "weight": 0.5,
            "market_condition_tags": ["trend_up", "drawdown", "range_bound"],
            "target_context_ref": "target-context-review://XYZ",
        },
        {
            "component_id": "component_b",
            "target_symbol": "QRS",
            "asset_class": "crypto_spot",
            "theme_bucket": "crypto_high_volatility",
            "component_role": "primary",
            "start_date": "2018-01-01",
            "end_date": "2021-12-31",
            "weight": 0.5,
            "market_condition_tags": ["high_volatility", "event_shock"],
            "target_context_ref": "target-context-review://QRS",
        },
    ],
    "excluded_training_windows": [
        {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
        {"target_symbol": "QRS", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
    ],
    "guardrail_refs": ["benchmark://guardrail/liquidity_regime"],
}


class BenchmarkContractTests(unittest.TestCase):
    def test_valid_contract_passes(self):
        result = validate_benchmark_contract(VALID_CONTRACT)
        self.assertEqual(result.validation_status, "passed")
        self.assertEqual(result.errors, ())
        self.assertEqual([component.target_symbol for component in result.contract.benchmark_components], ["XYZ", "QRS"])

    def test_missing_component_training_exclusion_fails(self):
        payload = dict(VALID_CONTRACT)
        payload["excluded_training_windows"] = [
            {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"}
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("excluded_training_windows must cover every benchmark component target/window (component_b:QRS)", result.errors)

    def test_same_target_training_universe_allowed_when_benchmark_window_is_excluded(self):
        payload = dict(VALID_CONTRACT)
        payload["training_universe_symbols"] = ["XYZ"]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "passed")

    def test_non_etf_component_requires_target_context_ref(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [dict(VALID_CONTRACT["benchmark_components"][0], target_context_ref="")]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("benchmark component component_a target_context_ref is required for non-ETF target routing", result.errors)

    def test_stress_component_can_model_missing_layer2_context(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(
                VALID_CONTRACT["benchmark_components"][0],
                component_role="stress_edge_case",
                data_availability_tags=["missing_layer2_context", "sparse_bars"],
                target_context_ref="",
                stress_exception_ref="benchmark-stress://missing-layer2/thematic-single-name",
                weight=0.10,
            ),
            dict(VALID_CONTRACT["benchmark_components"][1], weight=0.90),
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "passed")

    def test_quote_only_crypto_stress_component_is_allowed_with_exception(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(VALID_CONTRACT["benchmark_components"][0], weight=0.90),
            dict(
                VALID_CONTRACT["benchmark_components"][1],
                component_role="stress_edge_case",
                data_availability_tags=["quote_only_no_trades"],
                stress_exception_ref="benchmark-stress://crypto-quote-only",
                weight=0.10,
            ),
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "passed")

    def test_stress_weight_is_capped(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(
                VALID_CONTRACT["benchmark_components"][0],
                component_role="stress_edge_case",
                data_availability_tags=["missing_layer2_context"],
                target_context_ref="",
                stress_exception_ref="benchmark-stress://missing-layer2",
                weight=0.20,
            )
        ]
        payload["excluded_training_windows"] = [
            {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"}
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("stress component weight must not exceed 15% of the benchmark panel", result.errors)

    def test_critical_data_stress_tags_must_be_explicit_stress_components(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(
                VALID_CONTRACT["benchmark_components"][1],
                data_availability_tags=["quote_only_no_trades"],
            )
        ]
        payload["excluded_training_windows"] = [
            {"target_symbol": "QRS", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"}
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn(
            "benchmark component component_b critical data stress tags require a stress component_role",
            result.errors,
        )

    def test_same_target_fold_overlap_is_blocked(self):
        result = validate_benchmark_contract(VALID_CONTRACT)
        self.assertTrue(
            is_training_fold_blocked_by_benchmark(
                result.contract,
                target_symbol="XYZ",
                fold_start_date="2020-01-01",
                fold_end_date="2020-06-30",
            )
        )
        self.assertFalse(
            is_training_fold_blocked_by_benchmark(
                result.contract,
                target_symbol="XYZ",
                fold_start_date="2022-01-01",
                fold_end_date="2022-06-30",
            )
        )
        self.assertFalse(
            is_training_fold_blocked_by_benchmark(
                result.contract,
                target_symbol="ABC",
                fold_start_date="2020-01-01",
                fold_end_date="2020-06-30",
            )
        )

    def test_short_or_simple_window_fails(self):
        payload = dict(
            VALID_CONTRACT,
            min_trading_days=60,
            market_condition_tags=["trend_up"],
            benchmark_components=[
                {
                    "component_id": "component_a",
                    "target_symbol": "XYZ",
                    "asset_class": "equity_single_name",
                    "theme_bucket": "hot_thematic_growth",
                    "component_role": "primary",
                    "start_date": "2018-01-01",
                    "end_date": "2021-12-31",
                    "weight": 1.0,
                    "market_condition_tags": ["trend_up"],
                    "target_context_ref": "target-context-review://XYZ",
                }
            ],
            excluded_training_windows=[
                {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"}
            ],
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
