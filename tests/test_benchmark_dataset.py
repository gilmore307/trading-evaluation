import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import prepare_benchmark_dataset


VALID_DATASET_CONTRACT = {
    "contract_id": "primary_benchmark_dataset_test",
    "start_date": "2018-01-01",
    "end_date": "2018-02-01",
    "min_trading_days": 252,
    "market_condition_tags": ["trend_up", "drawdown", "high_volatility", "event_shock"],
    "data_snapshot_ref": "storage://benchmark/data_snapshot/pending_materialization",
    "cost_model_ref": "storage://benchmark/cost_model/pending_review",
    "baseline_refs": ["baseline://buy_and_hold"],
    "training_universe_symbols": ["XYZ", "QRS"],
    "benchmark_components": [
        {
            "component_id": "component_xyz",
            "target_symbol": "XYZ",
            "asset_class": "equity_single_name",
            "theme_bucket": "hot_thematic_growth",
            "component_role": "primary",
            "start_date": "2018-01-01",
            "end_date": "2018-02-01",
            "weight": 0.9,
            "market_condition_tags": ["trend_up", "drawdown", "high_volatility"],
            "data_availability_tags": ["full_ohlcv"],
            "event_coverage_tags": ["earnings_crossing", "product_cycle_repricing"],
            "sector_coverage_tags": [
                "consumer_discretionary",
                "consumer_staples",
                "entertainment_media",
                "semiconductors",
                "storage_memory",
                "healthcare",
                "energy",
                "financials",
                "retail",
                "restaurants",
            ],
            "target_context_ref": "target-context-review://XYZ",
        },
        {
            "component_id": "component_qrs",
            "target_symbol": "QRS",
            "asset_class": "crypto_spot",
            "theme_bucket": "crypto_high_volatility",
            "component_role": "stress_edge_case",
            "start_date": "2018-01-01",
            "end_date": "2018-02-01",
            "weight": 0.1,
            "market_condition_tags": ["high_volatility", "event_shock"],
            "data_availability_tags": ["missing_quote_order_book_context"],
            "event_coverage_tags": ["crypto_cycle_event"],
            "sector_coverage_tags": ["crypto"],
            "target_context_ref": "target-context-review://QRS",
            "stress_exception_ref": "benchmark-stress://crypto/missing-quote-order-book-context",
        },
    ],
    "excluded_training_windows": [
        {"target_symbol": "XYZ", "start_date": "2018-01-01", "end_date": "2018-02-01", "reason": "primary benchmark"},
        {"target_symbol": "QRS", "start_date": "2018-01-01", "end_date": "2018-02-01", "reason": "primary benchmark"},
    ],
    "guardrail_refs": ["benchmark://guardrail/liquidity_regime"],
}


class BenchmarkDatasetPreparationTests(unittest.TestCase):
    def test_prepare_benchmark_dataset_writes_one_shot_acquisition_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "data"
            receipt_path = data_root / "monthly_backfill" / "alpaca_bars" / "XYZ" / "2018-01" / "completion_receipt.json"
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps({"runs": [{"status": "succeeded"}]}) + "\n", encoding="utf-8")

            prepared = prepare_benchmark_dataset(
                VALID_DATASET_CONTRACT,
                output_root=root / "storage" / "benchmark",
                data_root=data_root,
                prepared_at_utc="2026-05-19T00:00:00Z",
            )

            self.assertEqual(prepared.manifest["contract_type"], "benchmark_dataset_preparation_manifest")
            self.assertEqual(prepared.manifest["component_count"], 2)
            self.assertEqual(prepared.manifest["feed_acquisition_count"], 6)
            self.assertEqual(prepared.manifest["available_feed_acquisition_count"], 1)
            self.assertEqual(prepared.manifest["deferred_feed_acquisition_count"], 0)
            self.assertEqual(prepared.manifest["missing_feed_acquisition_count"], 5)
            self.assertFalse(prepared.manifest["safety"]["provider_calls_performed"])
            self.assertFalse(prepared.manifest["safety"]["manager_request_route_used"])
            self.assertFalse(prepared.manifest["safety"]["acquisition_requests_allow_live_provider_calls"])

            with prepared.feed_acquisition_plan_path.open(newline="", encoding="utf-8") as handle:
                acquisition_rows = list(csv.DictReader(handle))
            self.assertEqual(
                {row["source_id"] for row in acquisition_rows},
                {
                    "alpaca_bars",
                    "alpaca_liquidity",
                    "alpaca_news",
                    "gdelt_news",
                    "trading_economics_calendar_web",
                    "okx_crypto_market_data",
                },
            )
            self.assertIn("available", {row["coverage_status"] for row in acquisition_rows})
            self.assertIn("missing", {row["coverage_status"] for row in acquisition_rows})

            bars_row = next(row for row in acquisition_rows if row["source_id"] == "alpaca_bars")
            self.assertEqual(bars_row["feed"], "01_feed_alpaca_bars")
            self.assertEqual(bars_row["output_root"], str(data_root / "monthly_backfill" / "alpaca_bars" / "XYZ" / "2018-01"))
            self.assertEqual(json.loads(bars_row["params_json"])["symbol"], "XYZ")
            liquidity_row = next(row for row in acquisition_rows if row["source_id"] == "alpaca_liquidity")
            liquidity_params = json.loads(liquidity_row["params_json"])
            self.assertEqual(liquidity_params["benchmark_liquidity_acquisition_policy"], "full_hourly_regular_session_windows_per_component_month")
            self.assertTrue(liquidity_params["fail_on_incomplete_pagination"])
            self.assertGreaterEqual(len(liquidity_params["acquisition_windows"]), 100)
            self.assertTrue(liquidity_params["acquisition_windows"][0]["label"].endswith("_0930_1030_et"))
            self.assertIn(
                "thetadata_option_selection_snapshot_expands_from_model_buy_point_decisions",
                prepared.manifest["known_deferred_requirements"],
            )
            gdelt_params = json.loads(next(row for row in acquisition_rows if row["source_id"] == "gdelt_news")["params_json"])
            self.assertIn("XYZ", gdelt_params["query_terms"])
            te_params = json.loads(next(row for row in acquisition_rows if row["source_id"] == "trading_economics_calendar_web")["params_json"])
            self.assertTrue(te_params["allow_live_fetch"])
            self.assertFalse((prepared.manifest_path.parent / "task_keys").exists())

    def test_prepare_benchmark_dataset_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract_path = root / "contract.json"
            contract_path.write_text(json.dumps(VALID_DATASET_CONTRACT), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/prepare_benchmark_dataset.py",
                    "--contract",
                    str(contract_path),
                    "--output-root",
                    str(root / "storage" / "benchmark"),
                    "--data-root",
                    str(root / "data"),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={"PYTHONPATH": "src"},
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["preparation_status"], "prepared_one_shot_acquisition_bundle")
            self.assertEqual(payload["feed_acquisition_count"], 6)


if __name__ == "__main__":
    unittest.main()
