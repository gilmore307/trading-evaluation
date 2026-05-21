import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import prepare_replay_dataset


VALID_DATASET_CONTRACT = {
    "contract_id": "promotion_replay_dataset_test",
    "replay_mode": "candidate_policy_replay",
    "start_date": "2021-01-01",
    "end_date": "2026-01-01",
    "min_trading_days": 1255,
    "market_condition_tags": ["trend_up", "drawdown", "high_volatility", "event_shock"],
    "candidate_policy_ref": "trading-model://layer_03_target_candidate_universe_policy/default",
    "replay_route_ref": "trading-execution://historical_clock/realtime_decision_path",
    "data_snapshot_ref": "storage://replay/promotion_replay/data_snapshot/pending_materialization",
    "cost_model_ref": "storage://replay/promotion_replay/cost_model/pending_review",
    "baseline_refs": ["baseline://active_model"],
    "guardrail_refs": ["replay://guardrail/liquidity_regime"],
    "selection_metric_refs": ["metric://net_return_after_costs"],
    "excluded_training_windows": [
        {
            "start_date": "2021-01-01",
            "end_date": "2026-01-01",
            "reason": "promotion replay holdout",
        }
    ],
}


class ReplayDatasetPreparationTests(unittest.TestCase):
    def test_prepare_replay_dataset_writes_candidate_policy_replay_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "data"
            receipt_path = (
                data_root
                / "replay"
                / "alpaca_bars"
                / "promotion_replay_dataset_test"
                / "2021-01"
                / "completion_receipt.json"
            )
            receipt_path.parent.mkdir(parents=True)
            receipt_path.write_text(json.dumps({"runs": [{"status": "succeeded"}]}) + "\n", encoding="utf-8")

            prepared = prepare_replay_dataset(
                VALID_DATASET_CONTRACT,
                output_root=root / "storage" / "replay",
                data_root=data_root,
                prepared_at_utc="2026-05-20T00:00:00Z",
            )

            self.assertEqual(prepared.manifest["contract_type"], "replay_dataset_preparation_manifest")
            self.assertEqual(prepared.manifest["replay_mode"], "candidate_policy_replay")
            self.assertEqual(prepared.manifest["replay_window_count"], 1)
            self.assertEqual(prepared.manifest["feed_acquisition_count"], 360)
            self.assertEqual(prepared.manifest["available_feed_acquisition_count"], 1)
            self.assertEqual(prepared.manifest["missing_feed_acquisition_count"], 359)
            self.assertFalse(prepared.manifest["safety"]["provider_calls_performed"])
            self.assertFalse(prepared.manifest["safety"]["manager_request_route_used"])
            self.assertFalse(prepared.manifest["safety"]["acquisition_requests_allow_live_provider_calls"])

            with prepared.replay_window_manifest_path.open(newline="", encoding="utf-8") as handle:
                replay_rows = list(csv.DictReader(handle))
            self.assertEqual(replay_rows[0]["candidate_policy_ref"], VALID_DATASET_CONTRACT["candidate_policy_ref"])

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
            self.assertEqual(
                bars_row["output_root"],
                str(data_root / "replay" / "alpaca_bars" / "promotion_replay_dataset_test" / "2021-01"),
            )
            params = json.loads(bars_row["params_json"])
            self.assertEqual(params["candidate_policy_ref"], VALID_DATASET_CONTRACT["candidate_policy_ref"])
            self.assertEqual(params["replay_acquisition_policy"], "candidate_policy_replay_monthly_surface")
            self.assertIn(
                "candidate_universe_materializes_point_in_time_during_replay",
                prepared.manifest["known_deferred_requirements"],
            )

    def test_prepare_replay_dataset_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract_path = root / "contract.json"
            contract_path.write_text(json.dumps(VALID_DATASET_CONTRACT), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/prepare_replay_dataset.py",
                    "--contract",
                    str(contract_path),
                    "--output-root",
                    str(root / "storage" / "replay"),
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
            self.assertEqual(payload["preparation_status"], "prepared_candidate_policy_replay_acquisition_bundle")
            self.assertEqual(payload["feed_acquisition_count"], 360)


if __name__ == "__main__":
    unittest.main()
