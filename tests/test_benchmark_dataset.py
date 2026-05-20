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
    def test_prepare_benchmark_dataset_writes_manifests_and_fail_closed_task_keys(self):
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
            self.assertEqual(prepared.manifest["feed_task_count"], 4)
            self.assertEqual(prepared.manifest["available_feed_task_count"], 1)
            self.assertEqual(prepared.manifest["deferred_feed_task_count"], 1)
            self.assertEqual(prepared.manifest["missing_feed_task_count"], 2)
            self.assertFalse(prepared.manifest["safety"]["provider_calls_performed"])
            self.assertFalse(prepared.manifest["safety"]["task_keys_allow_live_provider_calls"])

            with prepared.feed_task_plan_path.open(newline="", encoding="utf-8") as handle:
                task_rows = list(csv.DictReader(handle))
            self.assertEqual({row["source_id"] for row in task_rows}, {"alpaca_bars", "alpaca_liquidity", "alpaca_news", "okx_crypto_market_data"})
            self.assertIn("available", {row["coverage_status"] for row in task_rows})
            self.assertIn("deferred", {row["coverage_status"] for row in task_rows})
            self.assertIn("missing", {row["coverage_status"] for row in task_rows})

            task_key_path = prepared.task_key_root / "alpaca_bars" / "XYZ" / "2018-01" / "task_key.json"
            task_key = json.loads(task_key_path.read_text(encoding="utf-8"))
            self.assertEqual(task_key["feed"], "01_feed_alpaca_bars")
            self.assertEqual(task_key["params"]["symbol"], "XYZ")
            self.assertEqual(
                task_key["output_root"],
                str(data_root / "monthly_backfill" / "alpaca_bars" / "XYZ" / "2018-01"),
            )
            self.assertFalse(task_key["manager_controls"]["allow_live_provider_calls"])
            self.assertTrue(task_key["manager_controls"]["provider_dispatch_gate_required"])

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
            self.assertEqual(payload["preparation_status"], "prepared_not_dispatched")
            self.assertEqual(payload["feed_task_count"], 4)


if __name__ == "__main__":
    unittest.main()
