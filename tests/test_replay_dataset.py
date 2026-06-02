import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import freeze_replay_dataset, prepare_replay_dataset


VALID_DATASET_CONTRACT = {
    "contract_id": "promotion_replay_dataset_test",
    "replay_mode": "candidate_policy_replay",
    "candidate_fold_id": "fold_2016-01_2016-06",
    "target_refs": ["AAPL"],
    "start_date": "2021-01-01",
    "end_date": "2026-01-01",
    "min_trading_days": 1255,
    "market_condition_tags": ["trend_up", "drawdown", "high_volatility", "event_shock"],
    "candidate_policy_ref": "trading-model://layer_03_target_candidate_universe_policy/default",
    "replay_route_ref": "trading-execution://execution_runtime_component_graph/replay",
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
                / "monthly_backfill"
                / "alpaca_bars"
                / "AAPL"
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
            self.assertEqual(prepared.manifest["candidate_fold_id"], "fold_2016-01_2016-06")
            self.assertEqual(prepared.manifest["target_refs"], ["AAPL"])
            self.assertEqual(prepared.manifest["replay_window_count"], 1)
            self.assertEqual(prepared.manifest["feed_acquisition_count"], 300)
            self.assertEqual(prepared.manifest["available_feed_acquisition_count"], 1)
            self.assertEqual(prepared.manifest["deferred_feed_acquisition_count"], 0)
            self.assertEqual(prepared.manifest["missing_feed_acquisition_count"], 299)
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
                },
            )
            self.assertIn("missing", {row["coverage_status"] for row in acquisition_rows})

            bars_row = next(row for row in acquisition_rows if row["source_id"] == "alpaca_bars")
            self.assertEqual(bars_row["feed"], "01_feed_alpaca_bars")
            self.assertEqual(bars_row["target_ref"], "AAPL")
            self.assertEqual(bars_row["asset_class"], "us_equity")
            self.assertEqual(bars_row["instrument_type"], "underlying_or_listed_option")
            self.assertEqual(
                bars_row["output_root"],
                str(data_root / "monthly_backfill" / "alpaca_bars" / "AAPL" / "2021-01"),
            )
            params = json.loads(bars_row["params_json"])
            self.assertEqual(params["candidate_policy_ref"], VALID_DATASET_CONTRACT["candidate_policy_ref"])
            self.assertEqual(params["replay_acquisition_policy"], "candidate_policy_replay_monthly_surface")
            self.assertEqual(params["target_refs"], ["AAPL"])
            self.assertEqual(params["instrument_route"], "live_equivalent_underlying_then_option_expression")
            self.assertEqual(bars_row["coverage_status"], "available")
            gdelt_row = next(row for row in acquisition_rows if row["source_id"] == "gdelt_news")
            gdelt_params = json.loads(gdelt_row["params_json"])
            self.assertEqual(gdelt_params["start_date"], "2021-01-01")
            self.assertEqual(gdelt_params["end_date"], "2021-02-01")
            te_row = next(row for row in acquisition_rows if row["source_id"] == "trading_economics_calendar_web")
            te_params = json.loads(te_row["params_json"])
            self.assertTrue(te_params["allow_live_fetch"])
            self.assertEqual(te_params["date_range_mode"], "custom")
            self.assertFalse(te_params["use_authenticated_cookies"])
            self.assertTrue(te_params["persist_failure_diagnostics"])
            self.assertFalse([row for row in acquisition_rows if row["source_id"] == "okx_crypto_market_data"])
            self.assertIn(
                "replay_dataset_requires_explicit_fold_target_scope",
                prepared.manifest["known_deferred_requirements"],
            )

    def test_prepare_replay_dataset_uses_canonical_trading_economics_monthly_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "data"
            canonical_receipt = (
                data_root
                / "monthly_backfill"
                / "trading_economics_calendar_web"
                / "2021-01"
                / "runs"
                / "canonical_te_run"
                / "completion_receipt.json"
            )
            canonical_receipt.parent.mkdir(parents=True)
            canonical_receipt.write_text(json.dumps({"runs": [{"status": "succeeded"}]}) + "\n", encoding="utf-8")

            prepared = prepare_replay_dataset(
                VALID_DATASET_CONTRACT,
                output_root=root / "storage" / "replay",
                data_root=data_root,
                prepared_at_utc="2026-05-20T00:00:00Z",
            )

            self.assertEqual(prepared.manifest["available_feed_acquisition_count"], 1)
            self.assertEqual(prepared.manifest["missing_feed_acquisition_count"], 299)
            with prepared.feed_acquisition_plan_path.open(newline="", encoding="utf-8") as handle:
                acquisition_rows = list(csv.DictReader(handle))
            te_jan = next(
                row
                for row in acquisition_rows
                if row["source_id"] == "trading_economics_calendar_web" and row["month"] == "2021-01"
            )
            self.assertEqual(te_jan["coverage_status"], "available")
            self.assertEqual(te_jan["output_root"], str(canonical_receipt.parents[2]))
            self.assertEqual(te_jan["coverage_receipt_path"], str(canonical_receipt))

    def test_prepare_replay_dataset_requires_explicit_target_refs(self):
        payload = dict(VALID_DATASET_CONTRACT)
        payload.pop("target_refs")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "requires explicit target_refs"):
                prepare_replay_dataset(
                    payload,
                    output_root=Path(tmp) / "storage" / "replay",
                    data_root=Path(tmp) / "data",
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
            self.assertEqual(payload["feed_acquisition_count"], 300)

    def test_freeze_replay_dataset_accepts_complete_and_candidate_deferred_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = Path(tmp) / "dataset"
            dataset_root.mkdir()
            manifest_path = dataset_root / "dataset_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "contract_type": "replay_dataset_preparation_manifest",
                        "contract_id": "promotion_replay_dataset_test",
                        "freeze_status": "not_frozen",
                        "target_refs": ["AAPL"],
                        "feed_acquisition_count": 480,
                        "available_feed_acquisition_count": 300,
                        "deferred_feed_acquisition_count": 180,
                        "missing_feed_acquisition_count": 0,
                        "known_deferred_requirements": [
                            "replay_dataset_requires_explicit_fold_target_scope"
                        ],
                        "artifact_refs": [],
                        "safety": {
                            "provider_calls_performed": False,
                            "sql_mutation_performed": False,
                            "replay_freeze_performed": False,
                            "model_training_performed": False,
                            "model_activation_performed": False,
                            "broker_execution_performed": False,
                            "account_mutation_performed": False,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (dataset_root / "coverage_summary.csv").write_text(
                "\n".join(
                    [
                        ",".join(
                            [
                                "contract_id",
                                "source_id",
                                "required_acquisition_count",
                                "available_acquisition_count",
                                "deferred_acquisition_count",
                                "missing_acquisition_count",
                                "coverage_status",
                                "notes",
                            ]
                        ),
                        "promotion_replay_dataset_test,gdelt_news,60,60,0,0,complete,ok",
                        "promotion_replay_dataset_test,trading_economics_calendar_web,60,60,0,0,complete,ok",
                        "promotion_replay_dataset_test,okx_crypto_market_data,180,180,0,0,complete,ok",
                        "promotion_replay_dataset_test,alpaca_bars,60,0,60,0,deferred,ok",
                        "promotion_replay_dataset_test,alpaca_liquidity,60,0,60,0,deferred,ok",
                        "promotion_replay_dataset_test,alpaca_news,60,0,60,0,deferred,ok",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            frozen = freeze_replay_dataset(
                dataset_root,
                frozen_at_utc="2026-05-22T00:00:00Z",
            )

            self.assertEqual(frozen.freeze_receipt["freeze_status"], "frozen")
            self.assertEqual(frozen.freeze_receipt["validation"]["validation_status"], "passed")
            self.assertFalse(frozen.freeze_receipt["safety"]["provider_calls_performed"])
            self.assertFalse(frozen.freeze_receipt["safety"]["broker_execution_performed"])
            updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_manifest["freeze_status"], "frozen")
            self.assertTrue(updated_manifest["safety"]["replay_freeze_performed"])

    def test_freeze_replay_dataset_rejects_shared_non_deferred_receipt_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = Path(tmp) / "dataset"
            dataset_root.mkdir()
            receipt_path = dataset_root / "shared" / "completion_receipt.json"
            receipt_path.parent.mkdir()
            receipt_path.write_text(json.dumps({"runs": [{"status": "succeeded"}]}) + "\n", encoding="utf-8")
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
                            "acquisition_id": f"rplacq_test_okx_btc_{month}",
                            "contract_id": "promotion_replay_dataset_test",
                            "source_id": "okx_crypto_market_data",
                            "feed": "04_feed_okx_crypto_market_data",
                            "month": month,
                            "start_date": f"{month}-01",
                            "end_date_exclusive": "2021-03-01",
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
                        "contract_id": "promotion_replay_dataset_test",
                        "freeze_status": "not_frozen",
                        "target_refs": ["AAPL"],
                        "missing_feed_acquisition_count": 0,
                        "feed_acquisition_plan_ref": str(plan_path),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (dataset_root / "coverage_summary.csv").write_text(
                "contract_id,source_id,required_acquisition_count,available_acquisition_count,deferred_acquisition_count,missing_acquisition_count,coverage_status,notes\n"
                "promotion_replay_dataset_test,okx_crypto_market_data,2,2,0,0,complete,ok\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "coverage_receipt_path is shared"):
                freeze_replay_dataset(dataset_root)

    def test_freeze_replay_dataset_rejects_missing_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = Path(tmp) / "dataset"
            dataset_root.mkdir()
            (dataset_root / "dataset_manifest.json").write_text(
                json.dumps(
                    {
                        "contract_type": "replay_dataset_preparation_manifest",
                        "contract_id": "promotion_replay_dataset_test",
                        "freeze_status": "not_frozen",
                        "target_refs": ["AAPL"],
                        "missing_feed_acquisition_count": 1,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (dataset_root / "coverage_summary.csv").write_text(
                "contract_id,source_id,required_acquisition_count,available_acquisition_count,deferred_acquisition_count,missing_acquisition_count,coverage_status,notes\n"
                "promotion_replay_dataset_test,gdelt_news,60,59,0,1,incomplete,missing\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                freeze_replay_dataset(dataset_root)

    def test_freeze_replay_dataset_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = Path(tmp) / "dataset"
            dataset_root.mkdir()
            (dataset_root / "dataset_manifest.json").write_text(
                json.dumps(
                    {
                        "contract_type": "replay_dataset_preparation_manifest",
                        "contract_id": "promotion_replay_dataset_test",
                        "freeze_status": "not_frozen",
                        "target_refs": ["AAPL"],
                        "missing_feed_acquisition_count": 0,
                        "deferred_feed_acquisition_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (dataset_root / "coverage_summary.csv").write_text(
                "contract_id,source_id,required_acquisition_count,available_acquisition_count,deferred_acquisition_count,missing_acquisition_count,coverage_status,notes\n"
                "promotion_replay_dataset_test,gdelt_news,60,60,0,0,complete,ok\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/freeze_replay_dataset.py",
                    "--dataset-root",
                    str(dataset_root),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={"PYTHONPATH": "src"},
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["contract_type"], "replay_dataset_freeze_receipt")
            self.assertEqual(payload["freeze_status"], "frozen")


if __name__ == "__main__":
    unittest.main()
