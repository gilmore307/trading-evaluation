import csv
import json
import tempfile
import unittest
from pathlib import Path

from trading_evaluation.replay_acquisition import build_task_payload, run_acquisition


class ReplayAcquisitionRunnerTests(unittest.TestCase):
    def test_runner_plans_missing_items_without_provider_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = root / "replay" / "contract"
            dataset_root.mkdir(parents=True)
            plan_path = dataset_root / "feed_acquisition_plan.csv"
            fields = [
                "acquisition_id",
                "contract_id",
                "source_id",
                "feed",
                "month",
                "start_date",
                "end_date_exclusive",
                "timeframe",
                "acquisition_mode",
                "output_root",
                "expected_output_ref",
                "coverage_status",
                "coverage_receipt_path",
                "params_json",
                "notes",
            ]
            with plan_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "acquisition_id": "rplacq_test_gdelt",
                        "contract_id": "contract",
                        "source_id": "gdelt_news",
                        "feed": "05_feed_gdelt_news",
                        "month": "2026-01",
                        "start_date": "2026-01-01",
                        "end_date_exclusive": "2026-02-01",
                        "timeframe": "event_time",
                        "acquisition_mode": "one_shot_candidate_policy_replay_acquisition",
                        "output_root": str(root / "data" / "gdelt"),
                        "expected_output_ref": "storage://test",
                        "coverage_status": "missing",
                        "coverage_receipt_path": str(root / "receipt.json"),
                        "params_json": json.dumps({"start_date": "2026-01-01", "end_date": "2026-02-01", "max_rows": 250}),
                        "notes": "test",
                    }
                )
            summary = run_acquisition(dataset_root=dataset_root, data_root=root / "data", run_id="dry", source_ids={"gdelt_news"})
            self.assertEqual(summary.selected_count, 1)
            self.assertEqual(summary.executed_count, 0)
            self.assertFalse(summary.provider_calls_allowed)
            task_key = Path(summary.items[0].task_key_path)
            self.assertTrue(task_key.exists())
            payload = json.loads(task_key.read_text(encoding="utf-8"))
            self.assertEqual(payload["feed"], "05_feed_gdelt_news")
            self.assertEqual(payload["manager_controls"]["allowed_providers"], ["gdelt_bigquery"])
            self.assertFalse(payload["manager_controls"]["allow_live_provider_calls"])
            self.assertFalse(payload["manager_controls"]["autonomous_historical_provider_acquisition"])
            self.assertFalse(summary.manager_request_route_used)

    def test_liquidity_task_budget_scales_by_acquisition_windows(self):
        payload = build_task_payload(
            type(
                "Item",
                (),
                {
                    "acquisition_id": "a",
                    "feed": "02_feed_alpaca_liquidity",
                    "source_id": "alpaca_liquidity",
                    "params": {"limit": 100, "max_pages": 3, "acquisition_windows": [{"label": "a"}, {"label": "b"}]},
                    "output_root": "/tmp/out",
                },
            )()
        )
        self.assertEqual(payload["manager_controls"]["max_requests"], 12)
        self.assertEqual(payload["manager_controls"]["max_rows"], 1200)
        self.assertFalse(payload["manager_controls"]["allow_live_provider_calls"])

    def test_execute_task_payload_allows_provider_gate(self):
        payload = build_task_payload(
            type(
                "Item",
                (),
                {
                    "acquisition_id": "a",
                    "feed": "05_feed_gdelt_news",
                    "source_id": "gdelt_news",
                    "params": {"max_rows": 100},
                    "output_root": "/tmp/out",
                },
            )(),
            allow_provider_calls=True,
        )
        self.assertTrue(payload["manager_controls"]["allow_live_provider_calls"])
        self.assertTrue(payload["manager_controls"]["autonomous_historical_provider_acquisition"])


if __name__ == "__main__":
    unittest.main()
