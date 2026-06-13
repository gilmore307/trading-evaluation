import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trading_evaluation.replay_acquisition import build_task_payload, fixed_candidate_alpaca_bar_items, run_acquisition


class ReplayAcquisitionRunnerTests(unittest.TestCase):
    def _write_minimal_plan(self, dataset_root: Path, root: Path) -> Path:
        dataset_root.mkdir(parents=True, exist_ok=True)
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
                    "acquisition_id": "rplacq_contract_alpaca_bars_aapl_2021_01",
                    "contract_id": "contract",
                    "source_id": "alpaca_bars",
                    "feed": "01_feed_alpaca_bars",
                    "month": "2021-01",
                    "start_date": "2021-01-01",
                    "end_date_exclusive": "2021-02-01",
                    "timeframe": "1Day",
                    "acquisition_mode": "one_shot_candidate_policy_replay_acquisition",
                    "output_root": str(root / "storage" / "monthly_backfill" / "alpaca_bars" / "AAPL" / "2021-01"),
                    "expected_output_ref": "storage://test",
                    "coverage_status": "available",
                    "coverage_receipt_path": str(root / "receipt.json"),
                    "params_json": json.dumps({"start": "2021-01-01", "end": "2021-02-01"}),
                    "notes": "test",
                }
            )
        return plan_path

    def _write_candidate_universe(self, root: Path, symbols: list[str]) -> Path:
        path = root / "historical_candidate_universe.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["symbol", "target_ref", "asset_class", "replay_candidate_status"])
            writer.writeheader()
            for symbol in symbols:
                writer.writerow(
                    {
                        "symbol": symbol,
                        "target_ref": symbol,
                        "asset_class": "us_equity",
                        "replay_candidate_status": "active",
                    }
                )
        return path

    def test_fixed_candidate_alpaca_items_expand_universe_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = root / "replay" / "contract"
            self._write_minimal_plan(dataset_root, root)
            universe = self._write_candidate_universe(root, ["AAPL", "MSFT"])
            items = fixed_candidate_alpaca_bar_items(
                contract_id="contract",
                plan_items=[],
                candidate_universe_path=universe,
                storage_source_root=root / "storage",
            )
            self.assertEqual(items, [])

            plan_items = []
            with (dataset_root / "feed_acquisition_plan.csv").open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    plan_items.append(
                        type(
                            "Item",
                            (),
                            {
                                "month": row["month"],
                                "params": json.loads(row["params_json"]),
                            },
                        )()
                    )
            items = fixed_candidate_alpaca_bar_items(
                contract_id="contract",
                plan_items=plan_items,
                candidate_universe_path=universe,
                storage_source_root=root / "storage",
            )
            self.assertEqual(len(items), 2)
            self.assertEqual({item.params["symbol"] for item in items}, {"AAPL", "MSFT"})
            self.assertTrue(all(item.coverage_status == "missing" for item in items))

    def test_runner_includes_fixed_candidate_bars_without_provider_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = root / "replay" / "contract"
            self._write_minimal_plan(dataset_root, root)
            universe = self._write_candidate_universe(root, ["AAPL", "MSFT"])

            summary = run_acquisition(
                dataset_root=dataset_root,
                data_root=root / "data",
                run_id="candidate_bars",
                source_ids={"alpaca_bars"},
                include_fixed_candidate_alpaca_bars=True,
                candidate_universe_path=universe,
                storage_source_root=root / "storage",
            )

            self.assertEqual(summary.selected_count, 2)
            self.assertEqual(summary.executed_count, 0)
            self.assertFalse(summary.provider_calls_allowed)
            symbols = {
                json.loads(Path(item.task_key_path).read_text(encoding="utf-8"))["params"]["symbol"]
                for item in summary.items
            }
            self.assertEqual(symbols, {"AAPL", "MSFT"})

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

    def test_runner_filters_one_replay_month(self):
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
                for month in ("2021-01", "2021-02"):
                    writer.writerow(
                        {
                            "acquisition_id": f"rplacq_alpaca_bars_{month}",
                            "contract_id": "contract",
                            "source_id": "alpaca_bars",
                            "feed": "01_feed_alpaca_bars",
                            "month": month,
                            "start_date": f"{month}-01",
                            "end_date_exclusive": "2021-02-01" if month == "2021-01" else "2021-03-01",
                            "timeframe": "1Day",
                            "acquisition_mode": "one_shot_candidate_policy_replay_acquisition",
                            "output_root": str(root / "data" / month),
                            "expected_output_ref": "storage://test",
                            "coverage_status": "missing",
                            "coverage_receipt_path": str(root / "receipt.json"),
                            "params_json": json.dumps({"start_date": f"{month}-01"}),
                            "notes": "test",
                        }
                    )

            summary = run_acquisition(dataset_root=dataset_root, data_root=root / "data", run_id="dry", months={"2021-01"})

            self.assertEqual(summary.selected_count, 1)
            self.assertEqual(summary.items[0].month, "2021-01")
            self.assertIn("2021-01", summary.items[0].task_key_path)

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

    def test_trading_economics_execute_retries_transient_failure(self):
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
                        "acquisition_id": "rplacq_test_te",
                        "contract_id": "contract",
                        "source_id": "trading_economics_calendar_web",
                        "feed": "07_feed_trading_economics_calendar_web",
                        "month": "2026-01",
                        "start_date": "2026-01-01",
                        "end_date_exclusive": "2026-02-01",
                        "timeframe": "event_time",
                        "acquisition_mode": "one_shot_candidate_policy_replay_acquisition",
                        "output_root": str(root / "data" / "te"),
                        "expected_output_ref": "storage://test",
                        "coverage_status": "missing",
                        "coverage_receipt_path": str(root / "receipt.json"),
                        "params_json": json.dumps({"start_date": "2026-01-01", "end_date": "2026-02-01"}),
                        "notes": "test",
                    }
                )

            class Failed:
                returncode = 1

            class Succeeded:
                returncode = 0

            with patch("trading_evaluation.replay_acquisition.subprocess.run", side_effect=[Failed(), Succeeded()]) as run_mock:
                summary = run_acquisition(
                    dataset_root=dataset_root,
                    data_root=root / "data",
                    run_id="retry",
                    source_ids={"trading_economics_calendar_web"},
                    execute=True,
                    te_retry_delay_seconds=0,
                )

            self.assertEqual(run_mock.call_count, 2)
            self.assertEqual(summary.failed_count, 0)
            self.assertEqual(summary.succeeded_count, 1)
            self.assertEqual(summary.items[0].attempt_count, 2)
            self.assertIn("attempt_2", summary.items[0].command[-1])


if __name__ == "__main__":
    unittest.main()
