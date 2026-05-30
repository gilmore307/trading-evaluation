import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path("/root/projects/trading-execution/src")))
sys.path.insert(0, str(Path("/root/projects/trading-model/src")))

from trading_evaluation import build_candidate_policy_replay_execution_run, build_crypto_replay_execution_run
from trading_evaluation import replay_execution as replay_module
from models.model_05_alpha_confidence import train_after_cost_alpha_model
from models.model_05_alpha_confidence.contract import HORIZONS


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
                    "contract_id": "promotion_replay_candidate_policy",
                    "freeze_status": "frozen",
                    "missing_feed_acquisition_count": 0,
                    "feed_acquisition_plan_ref": str(plan_path),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (dataset_root / "replay_freeze_receipt.json").write_text(
            json.dumps(
                {
                    "contract_type": "replay_dataset_freeze_receipt",
                    "contract_id": "promotion_replay_candidate_policy",
                    "freeze_status": "frozen",
                    "dataset_manifest_ref": str(dataset_root / "dataset_manifest.json"),
                    "coverage_summary_ref": str(dataset_root / "coverage_summary.csv"),
                    "validation": {"validation_status": "passed"},
                    "safety": {
                        "provider_calls_performed": False,
                        "broker_execution_performed": False,
                        "account_mutation_performed": False,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return dataset_root

    def _equity_source_root(self, root: Path) -> Path:
        source_root = root / "alpaca_bars"
        bar_path = source_root / "AAPL" / "2021-01" / "runs" / "run" / "saved" / "equity_bar.csv"
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
                        "symbol": "AAPL",
                        "timeframe": "1Min",
                        "timestamp": "2021-01-04T09:30:00-05:00",
                        "bar_open": "100.0",
                        "bar_high": "101.0",
                        "bar_low": "99.0",
                        "bar_close": "100.5",
                        "bar_volume": "1000",
                        "bar_vwap": "",
                        "bar_trade_count": "",
                    },
                    {
                        "symbol": "AAPL",
                        "timeframe": "1Min",
                        "timestamp": "2021-01-04T15:59:00-05:00",
                        "bar_open": "100.5",
                        "bar_high": "102.0",
                        "bar_low": "100.0",
                        "bar_close": "101.5",
                        "bar_volume": "2000",
                        "bar_vwap": "",
                        "bar_trade_count": "",
                    },
                    {
                        "symbol": "AAPL",
                        "timeframe": "1Min",
                        "timestamp": "2021-01-05T15:59:00-05:00",
                        "bar_open": "101.5",
                        "bar_high": "104.0",
                        "bar_low": "101.0",
                        "bar_close": "103.0",
                        "bar_volume": "3000",
                        "bar_vwap": "",
                        "bar_trade_count": "",
                    },
                ]
            )
        return source_root

    def test_builds_crypto_replay_decision_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = self._dataset(Path(tmp))
            result = build_crypto_replay_execution_run(
                dataset_root=dataset_root,
                run_id="test_run",
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                after_cost_alpha_model=_after_cost_alpha_model(),
                max_decision_rows=2,
            )

            self.assertEqual(result.receipt["contract_type"], "evaluation_replay_execution_run")
            self.assertEqual(result.receipt["decision_row_count"], 2)
            self.assertEqual(result.receipt["completed_replay_month_count"], 1)
            self.assertIn(
                result.receipt["entry_threshold_calibration_status"],
                {
                    "selected_positive_validation_threshold",
                    "selected_best_available_nonpositive_validation_threshold",
                    "fallback_no_validation_threshold_candidate",
                },
            )
            self.assertTrue(Path(result.receipt["entry_threshold_calibration_ref"]).exists())
            self.assertFalse(result.receipt["side_effects"]["account_mutation_performed"])
            rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["contract_type"], "evaluation_replay_decision_row")
            self.assertEqual(rows[0]["target_ref"], "SOL")
            self.assertIn(rows[0]["validation_status"], {"passed", "failed"})
            self.assertIn("feature_momentum_7d", rows[0])
            self.assertEqual(rows[0]["model_inference_mode"], "trading_model_layer_generators")
            self.assertIn("model_05_alpha_confidence", rows[0]["model_layer_refs"])
            self.assertIn("model_08_underlying_action", rows[0]["model_layer_refs"])
            self.assertIn("model_05_alpha_confidence", rows[0]["model_layer_diagnostics"])
            self.assertIn("model_07_position_projection", rows[0]["model_layer_diagnostics"])
            self.assertIn("model_08_underlying_action", rows[0]["model_layer_diagnostics"])
            self.assertIn(rows[0]["entry_threshold_calibration_role"], {"validation", "test"})
            self.assertIn("entry_minimum_trade_intensity", rows[0])
            progress_rows = [json.loads(line) for line in result.progress_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(progress_rows[0]["contract_type"], "evaluation_replay_progress")
            self.assertEqual(progress_rows[0]["stage_id"], "model_group.replay")
            self.assertEqual(progress_rows[0]["month"], "2021-01")
            self.assertEqual(progress_rows[0]["status"], "completed")

    def test_candidate_policy_replay_includes_materialized_equity_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = self._dataset(root)
            equity_source_root = self._equity_source_root(root)
            result = build_candidate_policy_replay_execution_run(
                dataset_root=dataset_root,
                run_id="test_candidate_policy",
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                after_cost_alpha_model=_after_cost_alpha_model(),
                equity_source_root=equity_source_root,
                equity_symbols=["AAPL"],
                max_decision_rows=1,
            )

            self.assertEqual(result.receipt["execution_scope"], "candidate_policy_replay_materialized_market_data")
            self.assertEqual(result.receipt["asset_class_counts"]["us_equity"], 1)
            rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["target_ref"], "AAPL")
            self.assertEqual(rows[0]["asset_class"], "us_equity")
            self.assertEqual(rows[0]["account_sleeve_id"], "equity_options_account")
            self.assertEqual(rows[0]["asset_expression_route"], "direct_underlying_fallback")
            self.assertEqual(rows[0]["option_surface_status"], "optionable_chain_missing")

    def test_option_expression_plan_selects_loaded_contract_candidate(self):
        plan = replay_module._option_expression_plan_for_bar(
            bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
            candidate_model_ref="storage://trading-manager/model_group/test_fold",
            timestamp="2021-01-04T16:00:00-05:00",
            layer_outputs={
                "target_candidate_id": "replay_aapl_test",
                "target_context_state": {"model_ref": "target-context-ref"},
                "market_context_state": {"1_market_liquidity_support_score": 0.85},
                "event_failure_risk_vector": {},
                "underlying_action_plan": {
                    "model_ref": "underlying-action-ref",
                    "planned_underlying_action_type": "open",
                    "action_side": "long",
                    "handoff_to_layer_9": {
                        "underlying_path_direction": "bullish",
                        "expected_holding_time_minutes": 1440,
                        "expected_entry_price": 100.0,
                        "expected_target_price": 110.0,
                        "target_price_high": 110.0,
                        "expected_favorable_move_pct": 0.06,
                        "expected_adverse_move_pct": 0.02,
                        "path_quality_score": 0.80,
                    },
                },
            },
            option_candidates=[
                {
                    "contract_ref": "AAPL_20210115_C_100",
                    "option_right": "CALL",
                    "expiration": "2021-01-15",
                    "strike": 100.0,
                    "dte": 11,
                    "bid_price": 2.1,
                    "ask_price": 2.2,
                    "mid_price": 2.15,
                    "delta": 0.45,
                    "theta": -0.02,
                    "vega": 0.12,
                    "volume": 500,
                    "open_interest": 2000,
                    "spread_pct_mid": 0.0465,
                    "quote_age_seconds": 10,
                }
            ],
        )

        self.assertEqual(plan["asset_expression_route"], "listed_option_contract")
        self.assertEqual(plan["option_surface_status"], "optionable_chain_available")
        self.assertEqual(plan["selected_expression_type"], "long_call")
        self.assertEqual(plan["selected_contract"]["contract_ref"], "AAPL_20210115_C_100")

    def test_cli_writes_replay_execution_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = self._dataset(root)
            output_dir = root / "out"
            progress_path = root / "progress" / "replay_progress.jsonl"
            artifact_path = _write_after_cost_alpha_model(root)
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
                    "--candidate-model-ref",
                    "storage://trading-manager/model_group/test_fold",
                    "--after-cost-alpha-model-json",
                    str(artifact_path),
                    "--max-decision-rows",
                    "1",
                    "--progress-path",
                    str(progress_path),
                    "--exclude-equity",
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
            self.assertTrue(progress_path.exists())

    def test_rejects_deterministic_placeholder_candidate_model_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = self._dataset(Path(tmp))

            with self.assertRaisesRegex(ValueError, "deterministic placeholder"):
                build_crypto_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="bad_candidate_ref",
                    candidate_model_ref="trading-model://candidate_policy_replay/current_deterministic_crypto_policy",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    max_decision_rows=1,
                )

    def test_cli_requires_candidate_model_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = self._dataset(root)
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/run_replay_execution.py",
                    "--dataset-root",
                    str(dataset_root),
                    "--run-id",
                    "missing_ref",
                    "--max-decision-rows",
                    "1",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={"PYTHONPATH": "src"},
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--candidate-model-ref", result.stderr)


def _write_after_cost_alpha_model(root: Path) -> Path:
    path = root / "after_cost_alpha_model.json"
    path.write_text(json.dumps(_after_cost_alpha_model(), sort_keys=True), encoding="utf-8")
    return path


def _after_cost_alpha_model() -> dict[str, object]:
    training_rows = [_training_row(direction=-0.6, realized_return=-0.03), _training_row(direction=0.0, realized_return=0.0), _training_row(direction=0.6, realized_return=0.03)]
    try:
        return {
            "artifacts_by_horizon": {
                horizon: train_after_cost_alpha_model(
                    training_rows,
                    horizon=horizon,
                    label_field=f"after_cost_return_{horizon}",
                    iterations=25,
                )
                for horizon in HORIZONS
            }
        }
    except RuntimeError as error:
        raise unittest.SkipTest(str(error)) from error


def _training_row(*, direction: float, realized_return: float) -> dict[str, object]:
    return {
        "market_context_state": {
            "1_market_risk_stress_score": 0.20,
            "1_market_liquidity_support_score": 0.85,
            "1_state_quality_score": 0.90,
        },
        "sector_context_state": {
            "2_sector_context_support_quality_score": 0.80,
            "2_state_quality_score": 0.88,
        },
        "target_context_state": _target_state(direction=direction),
        "event_failure_risk_vector": {},
        "quality_calibration_state": {
            "sample_support_score": 0.85,
            "walk_forward_reliability_score": 0.80,
            "model_ensemble_agreement_score": 0.85,
            "model_disagreement_score": 0.10,
            "out_of_distribution_score": 0.10,
            "data_quality_score": 0.90,
        },
        **{f"after_cost_return_{horizon}": realized_return for horizon in HORIZONS},
    }


def _target_state(*, direction: float) -> dict[str, object]:
    state: dict[str, object] = {"3_state_quality_score": 0.90}
    for horizon in HORIZONS:
        state.update(
            {
                f"3_target_direction_score_{horizon}": direction,
                f"3_target_trend_quality_score_{horizon}": 0.75,
                f"3_target_path_stability_score_{horizon}": 0.80,
                f"3_target_noise_score_{horizon}": 0.20,
                f"3_target_transition_risk_score_{horizon}": 0.15,
                f"3_context_direction_alignment_score_{horizon}": 0.70 if direction >= 0 else -0.70,
                f"3_context_support_quality_score_{horizon}": 0.80,
                f"3_tradability_score_{horizon}": 0.85,
                f"3_beta_dependency_score_{horizon}": 0.20,
            }
        )
    return state


if __name__ == "__main__":
    unittest.main()
