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
            "weight": 0.9,
            "market_condition_tags": ["trend_up", "drawdown", "range_bound"],
            "event_coverage_tags": ["earnings_crossing", "product_cycle_repricing"],
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
            "weight": 0.1,
            "market_condition_tags": ["high_volatility", "event_shock"],
            "event_coverage_tags": ["crypto_cycle_event"],
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
            dict(VALID_CONTRACT["benchmark_components"][0], component_id="component_c", target_symbol="ABC", target_context_ref="target-context-review://ABC", weight=0.80),
            dict(VALID_CONTRACT["benchmark_components"][1], weight=0.10),
        ]
        payload["excluded_training_windows"] = [
            {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
            {"target_symbol": "ABC", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
            {"target_symbol": "QRS", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "passed")

    def test_crypto_missing_quote_order_book_stress_component_is_allowed_with_exception(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(VALID_CONTRACT["benchmark_components"][0], weight=0.90),
            dict(
                VALID_CONTRACT["benchmark_components"][1],
                component_role="stress_edge_case",
                data_availability_tags=["missing_quote_order_book_context"],
                stress_exception_ref="benchmark-stress://crypto-missing-quote-order-book",
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
            ),
            dict(VALID_CONTRACT["benchmark_components"][0], component_id="component_c", target_symbol="ABC", target_context_ref="target-context-review://ABC", weight=0.70),
            dict(VALID_CONTRACT["benchmark_components"][1], weight=0.10),
        ]
        payload["excluded_training_windows"] = [
            {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
            {"target_symbol": "ABC", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
            {"target_symbol": "QRS", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("stress component weight must not exceed 15% of the benchmark panel", result.errors)

    def test_critical_data_stress_tags_must_be_explicit_stress_components(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(VALID_CONTRACT["benchmark_components"][0], component_id="component_a", weight=0.90),
            dict(
                VALID_CONTRACT["benchmark_components"][1],
                weight=0.10,
                data_availability_tags=["missing_quote_order_book_context"],
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
                    "weight": 0.9,
                    "market_condition_tags": ["trend_up"],
                    "target_context_ref": "target-context-review://XYZ",
                }
            ],
            excluded_training_windows=[
                {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
                {"target_symbol": "QRS", "start_date": "2018-01-01", "end_date": "2021-12-31", "reason": "primary benchmark"},
            ],
        )
        payload["benchmark_components"].append(dict(VALID_CONTRACT["benchmark_components"][1], weight=0.1))
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

    def test_primary_benchmark_candidate_passes_validation(self):
        path = Path("benchmarks/primary_benchmark_candidate_20260519.json")
        result = validate_benchmark_contract(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(result.validation_status, "passed")
        self.assertEqual(sum(component.weight for component in result.contract.benchmark_components), 1.0)
        single_name_weight = sum(component.weight for component in result.contract.benchmark_components if component.asset_class == "equity_single_name")
        etf_weight = sum(component.weight for component in result.contract.benchmark_components if component.asset_class == "equity_etf")
        crypto_weight = sum(component.weight for component in result.contract.benchmark_components if component.asset_class.startswith("crypto"))
        self.assertGreaterEqual(single_name_weight, 0.55)
        self.assertLessEqual(etf_weight, 0.30)
        self.assertLessEqual(crypto_weight, 0.15)

    def test_stock_first_weight_policy_is_enforced(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(VALID_CONTRACT["benchmark_components"][0], asset_class="equity_etf", weight=0.60),
            dict(VALID_CONTRACT["benchmark_components"][1], weight=0.40),
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("equity_single_name component weight must be at least 55% of the benchmark panel", result.errors)
        self.assertIn("equity_etf component weight must not exceed 30% of the benchmark panel", result.errors)
        self.assertIn("crypto component weight must not exceed 15% of the benchmark panel", result.errors)

    def test_event_coverage_policy_is_enforced(self):
        payload = dict(VALID_CONTRACT)
        payload["benchmark_components"] = [
            dict(VALID_CONTRACT["benchmark_components"][0], event_coverage_tags=[], weight=0.90),
            dict(VALID_CONTRACT["benchmark_components"][1], event_coverage_tags=[], weight=0.10),
        ]
        result = validate_benchmark_contract(payload)
        self.assertEqual(result.validation_status, "failed")
        self.assertIn("earnings_crossing component weight must be at least 10% of the benchmark panel", result.errors)
        self.assertIn("event-driven component weight must be at least 25% of the benchmark panel", result.errors)


if __name__ == "__main__":
    unittest.main()
