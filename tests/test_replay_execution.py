import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path("/root/projects/trading-execution/src")))

from trading_evaluation import build_crypto_replay_execution_run


class ReplayExecutionTests(unittest.TestCase):
    def _dataset(self, root: Path) -> Path:
        dataset_root = root / "dataset"
        dataset_root.mkdir()
        bar_path = dataset_root / "source" / "sol" / "2021-01" / "runs" / "run" / "saved" / "crypto_bar.csv"
        bar_path.parent.mkdir(parents=True)
        with bar_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "symbol",
                    "timeframe",
                    "timestamp",
                    "bar_open",
                    "bar_high",
                    "bar_low",
                    "bar_close",
                    "bar_volume",
                    "bar_vwap",
                    "bar_trade_count",
                ],
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "symbol": "SOL-USDT",
                        "timeframe": "1Day",
                        "timestamp": "2021-01-01T11:00:00-05:00",
                        "bar_open": "2.0",
                        "bar_high": "2.2",
                        "bar_low": "1.9",
                        "bar_close": "2.0",
                        "bar_volume": "1000",
                        "bar_vwap": "",
                        "bar_trade_count": "",
                    },
                    {
                        "symbol": "SOL-USDT",
                        "timeframe": "1Day",
                        "timestamp": "2021-01-02T11:00:00-05:00",
                        "bar_open": "2.0",
                        "bar_high": "2.4",
                        "bar_low": "1.9",
                        "bar_close": "2.3",
                        "bar_volume": "1500",
                        "bar_vwap": "",
                        "bar_trade_count": "",
                    },
                    {
                        "symbol": "SOL-USDT",
                        "timeframe": "1Day",
                        "timestamp": "2021-01-03T11:00:00-05:00",
                        "bar_open": "2.3",
                        "bar_high": "2.5",
                        "bar_low": "2.1",
                        "bar_close": "2.4",
                        "bar_volume": "1300",
                        "bar_vwap": "",
                        "bar_trade_count": "",
                    },
                ]
            )
        receipt_path = bar_path.parents[2] / "completion_receipt.json"
        receipt_path.write_text(
            json.dumps({"runs": [{"status": "succeeded", "outputs": [str(bar_path)]}]}) + "\n",
            encoding="utf-8",
        )
        plan_path = dataset_root / "feed_acquisition_plan.csv"
        with plan_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
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
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "acquisition_id": "rplacq_test_okx_sol_2021_01",
                    "contract_id": "promotion_replay_candidate_policy",
                    "source_id": "okx_crypto_market_data",
                    "feed": "04_feed_okx_crypto_market_data",
                    "month": "2021-01",
                    "start_date": "2021-01-01",
                    "end_date_exclusive": "2021-02-01",
                    "timeframe": "1Day",
                    "acquisition_mode": "one_shot_candidate_policy_replay_acquisition",
                    "output_root": str(receipt_path.parent),
                    "expected_output_ref": "storage://test",
                    "coverage_status": "available",
                    "coverage_receipt_path": str(receipt_path),
                    "params_json": "{}",
                    "notes": "test",
                }
            )
        (dataset_root / "dataset_manifest.json").write_text(
            json.dumps(
                {
                    "contract_type": "replay_dataset_preparation_manifest",
                    "freeze_status": "frozen",
                    "missing_feed_acquisition_count": 0,
                    "feed_acquisition_plan_ref": str(plan_path),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (dataset_root / "replay_freeze_receipt.json").write_text(
            json.dumps({"freeze_status": "frozen", "validation": {"validation_status": "passed"}}) + "\n",
            encoding="utf-8",
        )
        return dataset_root

    def test_builds_crypto_replay_decision_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = self._dataset(Path(tmp))
            result = build_crypto_replay_execution_run(
                dataset_root=dataset_root,
                run_id="test_run",
                max_decision_rows=2,
            )

            self.assertEqual(result.receipt["contract_type"], "evaluation_replay_execution_run")
            self.assertEqual(result.receipt["decision_row_count"], 2)
            self.assertFalse(result.receipt["side_effects"]["account_mutation_performed"])
            rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["contract_type"], "evaluation_replay_decision_row")
            self.assertEqual(rows[0]["target_ref"], "SOL")
            self.assertIn(rows[0]["validation_status"], {"passed", "failed"})
            self.assertIn("feature_momentum_7d", rows[0])

    def test_cli_writes_replay_execution_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = self._dataset(root)
            output_dir = root / "out"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/run_replay_execution.py",
                    "--dataset-root",
                    str(dataset_root),
                    "--output-dir",
                    str(output_dir),
                    "--run-id",
                    "cli_run",
                    "--max-decision-rows",
                    "1",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={"PYTHONPATH": "src"},
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["replay_execution_run_id"], "cli_run")
            self.assertEqual(payload["decision_row_count"], 1)
            self.assertTrue((output_dir / "decision_rows.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
