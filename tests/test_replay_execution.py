import csv
import copy
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


class ReplayExecutionTests(unittest.TestCase):
    def test_equity_market_close_timestamp_uses_new_york_dst_offset(self):
        self.assertEqual(replay_module._equity_market_close_timestamp("2021-01-04"), "2021-01-04T16:00:00-05:00")
        self.assertEqual(replay_module._equity_market_close_timestamp("2021-04-14"), "2021-04-14T16:00:00-04:00")

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
                    "pre_replay_target_refs": ["SOL"],
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

    def _candidate_universe(self, root: Path, symbols: list[str]) -> Path:
        path = root / "historical_candidate_universe.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "symbol",
                    "target_ref",
                    "asset_class",
                    "instrument_type",
                    "replay_candidate_status",
                ],
            )
            writer.writeheader()
            for symbol in symbols:
                writer.writerow(
                    {
                        "symbol": symbol,
                        "target_ref": symbol,
                        "asset_class": "us_equity",
                        "instrument_type": "common_stock_or_optionable_underlying",
                        "replay_candidate_status": "active",
                    }
                )
        return path

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
            self.assertEqual(
                result.receipt["runtime_artifact_policy"]["component_output_contract_owner"],
                "trading-execution",
            )
            self.assertIn(
                "execution_order_intent",
                result.receipt["runtime_artifact_policy"]["component_output_contracts"],
            )
            self.assertEqual(
                result.receipt["runtime_artifact_policy"]["evaluation_decision_rows_role"],
                "settlement_view_over_component_outputs",
            )
            self.assertFalse(result.receipt["runtime_artifact_policy"]["replay_specific_component_contracts_allowed"])
            self.assertEqual(result.receipt["initial_capital_usd"], 25000.0)
            self.assertEqual(result.receipt["initial_capital"]["currency"], "USD")
            self.assertEqual(result.receipt["initial_capital"]["role"], "replay_equity_path_and_return_normalization")
            self.assertFalse(result.receipt["initial_capital"]["broker_or_account_state"])
            self.assertEqual(result.receipt["decision_row_count"], 2)
            self.assertEqual(result.receipt["max_decision_rows"], 2)
            self.assertEqual(result.receipt["replay_completion_scope"], "bounded_diagnostic")
            self.assertIn(
                "missing selected-contract paths are data-coverage diagnostics",
                " ".join(result.receipt["notes"]),
            )
            self.assertEqual(result.receipt["completed_replay_month_count"], 1)
            self.assertEqual(result.receipt["replay_time_pointer_policy"]["pointer_field"], "replay_time_pointer")
            self.assertEqual(
                result.receipt["replay_time_pointer_policy"]["policy_ref"],
                "replay_time_pointer_excludes_future_decision_inputs",
            )
            self.assertIn(
                result.receipt["entry_threshold_calibration_status"],
                {
                    "selected_positive_validation_threshold",
                    "fallback_insufficient_validation_observations",
                    "fallback_degenerate_validation_alpha_scores",
                    "fallback_no_positive_validation_threshold_candidate",
                    "fallback_no_validation_threshold_candidate",
                },
            )
            self.assertTrue(Path(result.receipt["entry_threshold_calibration_ref"]).exists())
            self.assertFalse(result.receipt["side_effects"]["account_mutation_performed"])
            rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["contract_type"], "evaluation_replay_decision_row")
            self.assertEqual(rows[0]["replay_time_pointer"], rows[0]["timestamp"])
            self.assertEqual(rows[0]["point_in_time_policy"], "replay_time_pointer_excludes_future_decision_inputs")
            self.assertEqual(rows[0]["target_ref"], "SOL")
            self.assertEqual(rows[0]["decision_expression_type"], "crypto_spot")
            self.assertEqual(rows[0]["decision_instrument_scope"], "crypto_spot")
            self.assertIn(rows[0]["validation_status"], {"passed", "failed"})
            self.assertIn("feature_momentum_7d", rows[0])
            self.assertEqual(rows[0]["model_evidence_mode"], "component_input_model_evidence_generators")
            self.assertIn("model_04_event_failure_risk", rows[0]["model_layer_refs"])
            self.assertIn("model_05_alpha_confidence", rows[0]["model_layer_refs"])
            self.assertIn("model_04_unified_decision", rows[0]["model_layer_refs"])
            self.assertIn("model_04_event_failure_risk", rows[0]["model_layer_diagnostics"])
            self.assertIn("model_05_alpha_confidence", rows[0]["model_layer_diagnostics"])
            self.assertIn("model_04_unified_decision", rows[0]["model_layer_diagnostics"])
            self.assertIn("model_05_alpha_confidence", rows[0]["model_evidence_chain"])
            self.assertIn("model_05_option_expression", rows[0]["model_evidence_chain"])
            self.assertIn("model_06_residual_event_governance", rows[0]["model_evidence_chain"])
            self.assertIn(rows[0]["entry_threshold_calibration_role"], {"validation", "test"})
            self.assertIn("entry_minimum_trade_intensity", rows[0])
            progress_rows = [json.loads(line) for line in result.progress_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(progress_rows[0]["contract_type"], "evaluation_replay_progress")
            self.assertEqual(progress_rows[0]["stage_id"], "model_group.replay")
            self.assertEqual(progress_rows[0]["month"], "2021-01")
            self.assertEqual(progress_rows[0]["status"], "completed")
            self.assertEqual(progress_rows[0]["initial_capital_usd"], 25000.0)

    def test_entry_calibration_rejects_tiny_validation_windows(self):
        selected = replay_module._select_entry_thresholds([_calibration_row(index=0, alpha_confidence=0.72)])

        self.assertEqual(selected["status"], "fallback_insufficient_validation_observations")
        self.assertEqual(selected["thresholds"]["minimum_entry_alpha_confidence"], 0.5)
        self.assertEqual(selected["thresholds"]["minimum_trade_intensity"], 0.05)

    def test_entry_calibration_rejects_constant_alpha_scores(self):
        rows = [_calibration_row(index=index, alpha_confidence=0.529398) for index in range(72)]

        selected = replay_module._select_entry_thresholds(rows)

        self.assertEqual(selected["status"], "fallback_degenerate_validation_alpha_scores")
        self.assertEqual(selected["diagnostics"]["alpha_unique_value_count"], 1)

    def test_entry_calibration_never_selects_below_neutral_alpha_threshold(self):
        rows = [_calibration_row(index=index, alpha_confidence=0.56 + (index % 8) * 0.01) for index in range(72)]

        selected = replay_module._select_entry_thresholds(rows)

        self.assertEqual(selected["status"], "selected_positive_validation_threshold")
        self.assertGreaterEqual(selected["thresholds"]["minimum_entry_alpha_confidence"], 0.5)

    def test_replay_rejects_degenerate_after_cost_alpha_artifact(self):
        artifact = _after_cost_alpha_model()
        for horizon_artifact in artifact["artifacts_by_horizon"].values():
            horizon_artifact["booster_model"] = "tree\nTree=0\nnum_leaves=1\nleaf_value=0.5\n"

        with self.assertRaisesRegex(ValueError, "degenerate_after_cost_alpha_artifact"):
            replay_module._validate_after_cost_alpha_model_for_replay(artifact)

    def test_candidate_policy_replay_does_not_prefetch_option_features_for_materialized_equity_rows(self):
        original_plan_builder = replay_module._option_expression_plan_for_bar
        original_bulk_feature_loader = replay_module._load_option_candidate_features
        original_point_feature_loader = replay_module._load_option_candidate_features_for_timestamp
        try:
            replay_module._load_option_candidate_features = lambda **_: self.fail("bulk option feature loader must not run")
            replay_module._load_option_candidate_features_for_timestamp = (
                lambda **_: self.fail("point option feature loader must not run without an M04 option-expression signal")
            )
            replay_module._option_expression_plan_for_bar = lambda **_: None
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
                    option_feature_database_url="",
                )
                self.assertEqual(result.receipt["decision_row_count"], 1)
        finally:
            replay_module._option_expression_plan_for_bar = original_plan_builder
            replay_module._load_option_candidate_features = original_bulk_feature_loader
            replay_module._load_option_candidate_features_for_timestamp = original_point_feature_loader

    def test_option_expression_plan_requires_features_only_after_model_four_signal(self):
        with self.assertRaisesRegex(ValueError, "replay_option_feature_acquisition_required"):
            replay_module._option_expression_plan_for_bar(
                bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                timestamp="2021-01-04T16:00:00-05:00",
                layer_outputs=_current_layer_outputs(),
                option_candidates=[],
            )

        self.assertIsNone(
            replay_module._option_expression_plan_for_bar(
                bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                timestamp="2021-01-04T16:00:00-05:00",
                layer_outputs=_current_layer_outputs(alpha_score=0.25),
                option_candidates=[],
            )
        )

    def test_option_expression_signal_requires_entry_ready_long_trade(self):
        self.assertTrue(replay_module._option_expression_signal_required(_current_layer_outputs()))
        self.assertFalse(replay_module._option_expression_signal_required(_current_layer_outputs(alpha_score=0.25)))
        self.assertFalse(replay_module._option_expression_signal_required(_current_layer_outputs(trade_intensity=0.01)))
        self.assertFalse(
            replay_module._option_expression_signal_required(
                _current_layer_outputs(action_type="open_short", action_side="short", direction="bearish", action_direction=-0.2, expected_return=-0.03)
            )
        )
        self.assertFalse(
            replay_module._option_expression_signal_required(
                _current_layer_outputs(action_type="no_trade", action_side="none", direction="neutral", action_direction=0.0, expected_return=0.0)
            )
        )

    def test_replay_option_feature_acquisition_payload_can_report_multiple_missing_points(self):
        message = replay_module._replay_option_feature_acquisition_message(
            [
                replay_module._replay_option_feature_requirement_sample(
                    target="AAPL",
                    timestamp="2021-05-19T16:00:00-04:00",
                ),
                replay_module._replay_option_feature_requirement_sample(
                    target="AAPL",
                    timestamp="2021-05-21T16:00:00-04:00",
                ),
            ]
        )

        payload = json.loads(message.split(": ", 1)[1])
        self.assertEqual(payload["missing_count"], 2)
        self.assertEqual(len(payload["sample"]), 2)
        self.assertEqual(payload["sample"][0]["maximum_permitted_source_end"], "2021-05-19T16:00:00-04:00")
        self.assertEqual(payload["sample"][1]["timestamp"], "2021-05-21T16:00:00-04:00")

    def test_replay_option_feature_acquisition_payload_can_reference_full_requirements_artifact(self):
        message = replay_module._replay_option_feature_acquisition_message(
            [
                replay_module._replay_option_feature_requirement_sample(
                    target="AAPL",
                    timestamp="2021-05-19T16:00:00-04:00",
                )
            ],
            artifact_ref=Path("/tmp/option_feature_requirements.jsonl"),
        )

        payload = json.loads(message.split(": ", 1)[1])
        self.assertEqual(payload["requirements_artifact_ref"], "/tmp/option_feature_requirements.jsonl")

    def test_candidate_layer_outputs_uses_after_cost_alpha_model_for_prediction_score(self):
        original_generators = replay_module._trading_model_generators
        seen_policy_states: list[dict[str, object]] = []

        def event_failure(rows):
            row = list(rows)[0]
            return [
                {
                    "event_failure_risk_vector_ref": "efrv_test",
                    "4_resolved_event_failure_risk_status": "no_reviewed_event_failure_risk",
                    "event_failure_risk_vector": {
                        "4_event_entry_block_pressure_score_1D": 0.0,
                        "4_event_response_direction_score_1D": 0.0,
                    },
                    "event_failure_risk_diagnostics": {"horizon_reason_codes": {"1D": ["no_reviewed_event_failure_risk"]}},
                    "target_candidate_id": row["target_candidate_id"],
                }
            ]

        def alpha_confidence(rows, *, after_cost_alpha_model):
            row = list(rows)[0]
            score = float(after_cost_alpha_model["score"])
            return [
                {
                    "alpha_confidence_vector_ref": f"acv_{score}",
                    "alpha_confidence_vector": {"5_after_cost_alpha_score_1D": score},
                    "alpha_confidence_diagnostics": {"after_cost_alpha_score": {"1D": {"score": score}}},
                    "target_candidate_id": row["target_candidate_id"],
                }
            ]

        def unified_decision(rows):
            row = list(rows)[0]
            seen_policy_states.append(dict(row["policy_gate_state"]))
            return [
                {
                    "unified_decision_vector_ref": "udv_test",
                    "unified_decision_vector": {
                        "4_resolved_decision_horizon": "1D",
                        "4_resolved_underlying_action_type": "open_long",
                        "4_resolved_action_side": "long",
                        "4_resolved_action_confidence_score": 0.9,
                        "4_action_confidence_score_1D": 0.9,
                        "4_trade_intensity_score_1D": 0.2,
                        "4_action_direction_score_1D": 0.5,
                        "4_expected_return_score_1D": 0.04,
                    },
                    "direct_underlying_intent": {
                        "underlying_action_type": "open_long",
                        "action_side": "long",
                        "dominant_horizon": "1D",
                        "expected_target_price": 105.0,
                        "thesis_invalidation_price": 98.0,
                        "handoff_to_model_05": {
                            "underlying_path_direction": "bullish",
                            "expected_entry_price": 100.0,
                            "expected_target_price": 105.0,
                            "stop_loss_price": 98.0,
                            "thesis_invalidation_price": 98.0,
                        },
                        "reason_codes": [],
                    },
                    "unified_decision_diagnostics": {
                        "hard_gate_reason_codes": [],
                        "horizon_scores": {
                            "1D": {
                                "trade_intensity_score": 0.2,
                                "entry_quality_score": 0.7,
                                "action_confidence_score": 0.9,
                                "action_direction_score": 0.5,
                                "expected_return_score": 0.04,
                                "downside_risk_score": 0.1,
                            }
                        },
                    },
                }
            ]

        try:
            replay_module._trading_model_generators = lambda: {
                "model_04_event_failure_risk": event_failure,
                "model_05_alpha_confidence": alpha_confidence,
                "model_04_unified_decision": unified_decision,
                "model_05_option_expression": lambda rows: [],
                "model_06_residual_event_governance": lambda rows: [],
            }
            target_rows = [
                {"timestamp": "2021-01-04T16:00:00-05:00", "bar_close": 100.0, "bar_volume": 1000.0},
                {"timestamp": "2021-01-05T16:00:00-05:00", "bar_close": 101.0, "bar_volume": 1100.0},
            ]
            calibration = {"selected_thresholds": {"minimum_entry_alpha_confidence": 0.5, "minimum_trade_intensity": 0.0}}
            low = replay_module._candidate_layer_outputs(
                target="AAPL",
                target_rows=target_rows,
                index=0,
                market_universe=[{"reference_price": 100.0}],
                reference_price=100.0,
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                after_cost_alpha_model={"score": 0.25},
                entry_calibration=calibration,
            )
            high = replay_module._candidate_layer_outputs(
                target="AAPL",
                target_rows=target_rows,
                index=0,
                market_universe=[{"reference_price": 100.0}],
                reference_price=100.0,
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                after_cost_alpha_model={"score": 0.82},
                entry_calibration=calibration,
            )

            self.assertEqual(low["prediction_score"], 0.25)
            self.assertEqual(high["prediction_score"], 0.82)
            self.assertEqual(
                low["model_layer_diagnostics"]["model_05_alpha_confidence"]["alpha_gate_status"],
                "below_entry_threshold",
            )
            self.assertEqual(high["model_layer_diagnostics"]["model_05_alpha_confidence"]["alpha_gate_status"], "passed")
            self.assertEqual(seen_policy_states[0]["allow_new_exposure"], "false")
            self.assertNotIn("new_exposure_permission_score", seen_policy_states[1])
        finally:
            replay_module._trading_model_generators = original_generators

    def test_option_expression_plan_continues_when_option_source_unavailable(self):
        plan = replay_module._option_expression_plan_for_bar(
            bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
            candidate_model_ref="storage://trading-manager/model_group/test_fold",
            timestamp="2021-01-04T16:00:00-05:00",
            layer_outputs=_current_layer_outputs(),
            option_candidates=[
                {
                    "option_symbol": "__OPTION_SOURCE_UNAVAILABLE__",
                    "snapshot_type": "source_unavailable",
                    "option_surface_status": "option_source_unavailable",
                }
            ],
        )

        self.assertEqual(plan["asset_expression_route"], "option_expression_unfilled")
        self.assertEqual(plan["option_surface_status"], "option_source_unavailable")
        self.assertEqual(plan["selected_contract"], None)

        self.assertIsNone(
            replay_module._option_expression_plan_for_bar(
                bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                timestamp="2021-01-04T16:00:00-05:00",
                layer_outputs=_current_layer_outputs(action_type="no_trade", action_side="none", direction="neutral"),
                option_candidates=[],
            )
        )

    def test_candidate_policy_replay_requires_layer_two_candidate_handoff_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = self._dataset(root)
            equity_source_root = self._equity_source_root(root)

            with self.assertRaisesRegex(ValueError, "Layer 2 target-candidate handoff"):
                build_candidate_policy_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="test_candidate_handoff_required",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=equity_source_root,
                    include_crypto=False,
                    option_feature_database_url="",
                )

    def test_candidate_policy_replay_uses_layer_two_candidate_handoff_symbols(self):
        original_loader = replay_module._load_layer_two_candidate_handoff_rows
        original_feature_loader = replay_module._load_option_candidate_features
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            replay_module._load_layer_two_candidate_handoff_rows = lambda **_: [
                {
                    "etf_symbol": "XLK",
                    "as_of_date": "2021-01-04",
                    "available_time": "2021-01-05T09:30:00-05:00",
                    "holding_symbol": "AAPL",
                    "holding_name": "Apple Inc.",
                }
            ]
            replay_module._load_option_candidate_features = lambda **_: {
                ("AAPL", "2021-01-04T16:00:00-05:00"): [{"contract_ref": "AAPL_2021-01-15_C_100"}]
            }
            replay_module._option_expression_plan_for_bar = lambda **_: {
                "model_ref": "storage://trading-manager/model_group/test_fold/model_05_option_expression/test",
                "target_ref": "AAPL",
                "asset_expression_route": "option_expression_unfilled",
                "option_surface_status": "optionable_chain_available",
            }
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dataset_root = self._dataset(root)
                equity_source_root = self._equity_source_root(root)
                result = build_candidate_policy_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="test_candidate_handoff_symbols",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=equity_source_root,
                    include_crypto=False,
                    max_decision_rows=1,
                    option_feature_database_url="",
                )

                self.assertEqual(result.receipt["candidate_handoff_status"], "available")
                self.assertEqual(result.receipt["candidate_handoff_source"], "layer_02_target_candidate_handoff")
                self.assertEqual(result.receipt["candidate_handoff_symbols"], ["AAPL"])
                rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(rows[0]["target_ref"], "AAPL")
        finally:
            replay_module._load_layer_two_candidate_handoff_rows = original_loader
            replay_module._load_option_candidate_features = original_feature_loader
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_candidate_policy_replay_uses_fixed_historical_candidate_universe(self):
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            replay_module._option_expression_plan_for_bar = lambda **_: None
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dataset_root = self._dataset(root)
                equity_source_root = self._equity_source_root(root)
                candidate_universe_path = self._candidate_universe(root, ["AAPL"])

                result = build_candidate_policy_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="test_fixed_candidate_universe",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=equity_source_root,
                    include_crypto=False,
                    max_decision_rows=1,
                    option_feature_database_url="",
                    candidate_universe_path=candidate_universe_path,
                )

                self.assertEqual(result.receipt["candidate_handoff_status"], "available")
                self.assertEqual(
                    result.receipt["candidate_handoff_source"],
                    "fixed_current_snapshot_historical_candidate_universe",
                )
                self.assertEqual(result.receipt["candidate_handoff_symbols"], ["AAPL"])
                self.assertEqual(result.receipt["candidate_handoff_artifact_ref"], str(candidate_universe_path))
                self.assertIsNone(result.receipt["candidate_handoff_table_ref"])
        finally:
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_candidate_policy_replay_rejects_partial_candidate_bar_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = self._dataset(root)
            equity_source_root = self._equity_source_root(root)
            candidate_universe_path = self._candidate_universe(root, ["AAPL", "MSFT"])

            with self.assertRaisesRegex(ValueError, "missing materialized candidate bars for 1 of 2 symbols"):
                build_candidate_policy_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="test_partial_candidate_bars",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=equity_source_root,
                    include_crypto=False,
                    max_decision_rows=1,
                    option_feature_database_url="",
                    candidate_universe_path=candidate_universe_path,
                )

    def test_load_equity_bars_uses_sql_retained_month_when_receipt_has_no_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            month_root = root / "alpaca_bars" / "MSFT" / "2021-01"
            month_root.mkdir(parents=True)
            (month_root / "completion_receipt.json").write_text(
                json.dumps({"runs": [{"status": "succeeded", "outputs": []}]}) + "\n",
                encoding="utf-8",
            )
            calls: list[dict[str, object]] = []

            def fake_sql_loader(**kwargs):
                calls.append(dict(kwargs))
                return {
                    "MSFT": [
                        {
                            "symbol": "MSFT",
                            "asset_class": "us_equity",
                            "source_id": "alpaca_bars",
                            "timeframe": "1Day",
                            "timestamp": "2021-01-04T16:00:00-05:00",
                            "date": "2021-01-04",
                            "bar_open": 200.0,
                            "bar_high": 201.0,
                            "bar_low": 199.0,
                            "bar_close": 200.5,
                            "bar_volume": 1000.0,
                        },
                        {
                            "symbol": "MSFT",
                            "asset_class": "us_equity",
                            "source_id": "alpaca_bars",
                            "timeframe": "1Day",
                            "timestamp": "2021-01-05T16:00:00-05:00",
                            "date": "2021-01-05",
                            "bar_open": 200.5,
                            "bar_high": 203.0,
                            "bar_low": 200.0,
                            "bar_close": 202.5,
                            "bar_volume": 1100.0,
                        },
                    ]
                }

            original_loader = replay_module._load_equity_bars_from_sql_bulk
            try:
                replay_module._load_equity_bars_from_sql_bulk = fake_sql_loader
                rows = replay_module._load_equity_bars(equity_source_root=root / "alpaca_bars", equity_symbols=["MSFT"])
            finally:
                replay_module._load_equity_bars_from_sql_bulk = original_loader

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["symbol_windows"], {"MSFT": [("2021-01-01", "2021-02-01")]})
            self.assertEqual(set(rows), {"MSFT"})
            self.assertEqual(len(rows["MSFT"]), 2)
            self.assertEqual(rows["MSFT"][0]["bar_close"], 200.5)

    def test_target_market_universe_rows_selects_current_target(self):
        universe = (
            {"target_ref": "AAPL", "reference_price": 100.0},
            {"target_ref": "MSFT", "reference_price": 200.0},
        )
        self.assertEqual(replay_module._target_market_universe_rows(market_universe=universe, target="msft"), (universe[1],))
        self.assertEqual(replay_module._target_market_universe_rows(market_universe=universe, target="missing"), universe)

    def test_entry_calibration_validation_months_use_only_decidable_rows(self):
        bars_by_target = {
            "AAPL": [
                {"timestamp": "2021-01-04T16:00:00-05:00"},
                {"timestamp": "2021-01-05T16:00:00-05:00"},
                {"timestamp": "2021-02-01T16:00:00-05:00"},
            ],
            "MSFT": [
                {"timestamp": "2021-02-01T16:00:00-05:00"},
                {"timestamp": "2021-02-02T16:00:00-05:00"},
                {"timestamp": "2021-03-01T16:00:00-05:00"},
            ],
            "TSLA": [
                {"timestamp": "2021-04-01T16:00:00-04:00"},
            ],
        }

        self.assertEqual(
            replay_module._entry_calibration_validation_months(
                bars_by_target=bars_by_target,
                validation_month_count=2,
            ),
            ("2021-01", "2021-02"),
        )

    def test_fixed_candidate_handoff_prunes_symbols_with_completed_empty_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for month in range(1, 13):
                month_root = root / "alpaca_bars" / "MSFT" / f"2021-{month:02d}"
                month_root.mkdir(parents=True)
                (month_root / "completion_receipt.json").write_text(
                    json.dumps({"runs": [{"status": "succeeded", "outputs": [], "row_counts": {"equity_bar": 0}}]}) + "\n",
                    encoding="utf-8",
                )
            handoff = {
                "status": "available",
                "source": "fixed_current_snapshot_historical_candidate_universe",
                "candidate_symbols": ("AAPL", "MSFT"),
                "row_count": 2,
            }

            pruned = replay_module._prune_fixed_candidate_handoff_no_history_symbols(
                candidate_handoff=handoff,
                bars_by_target={"AAPL": [{"asset_class": "us_equity"}]},
                equity_source_root=root / "alpaca_bars",
                replay_month="2021-01",
            )

            self.assertEqual(pruned["candidate_symbols"], ("AAPL",))
            self.assertEqual(pruned["excluded_no_historical_bar_symbols"], ("MSFT",))
            self.assertEqual(pruned["row_count"], 2)

    def test_candidate_policy_replay_runs_one_month_from_feed_plan_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = root / "dataset"
            dataset_root.mkdir(parents=True)
            bar_path = (
                root
                / "source"
                / "replay"
                / "alpaca_bars"
                / "promotion_replay_candidate_policy"
                / "aapl"
                / "2021-01"
                / "runs"
                / "run"
                / "saved"
                / "equity_bar.csv"
            )
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
                            "timeframe": "1Day",
                            "timestamp": "2021-01-04T16:00:00-05:00",
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
                            "timeframe": "1Day",
                            "timestamp": "2021-01-05T16:00:00-05:00",
                            "bar_open": "100.5",
                            "bar_high": "103.0",
                            "bar_low": "100.0",
                            "bar_close": "102.5",
                            "bar_volume": "1100",
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
            source_ids = [
                "alpaca_bars",
                "alpaca_liquidity",
                "alpaca_news",
                "gdelt_news",
                "trading_economics_calendar_web",
            ]
            with plan_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["source_id", "month", "target_ref", "coverage_status", "coverage_receipt_path"],
                )
                writer.writeheader()
                for source_id in source_ids:
                    writer.writerow(
                        {
                            "source_id": source_id,
                            "month": "2021-01",
                            "target_ref": "AAPL" if source_id.startswith("alpaca") else "",
                            "coverage_status": "available",
                            "coverage_receipt_path": str(receipt_path if source_id == "alpaca_bars" else root / f"{source_id}.json"),
                        }
                    )
            (dataset_root / "dataset_manifest.json").write_text(
                json.dumps(
                    {
                        "contract_type": "replay_dataset_preparation_manifest",
                        "contract_id": "promotion_replay_candidate_policy",
                        "freeze_status": "not_frozen",
                        "missing_feed_acquisition_count": 100,
                        "pre_replay_target_refs": ["AAPL"],
                        "feed_acquisition_plan_ref": str(plan_path),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            original_plan_builder = replay_module._option_expression_plan_for_bar
            try:
                replay_module._option_expression_plan_for_bar = lambda **_: None
                result = build_candidate_policy_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="test_month_replay",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    replay_month="2021-01",
                    include_crypto=False,
                    equity_symbols=["AAPL"],
                    max_decision_rows=1,
                    option_feature_database_url="",
                )
                self.assertEqual(result.receipt["decision_row_count"], 1)
                self.assertEqual(result.receipt["max_decision_rows"], 1)
                self.assertEqual(result.receipt["replay_completion_scope"], "bounded_diagnostic")
            finally:
                replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_equity_feed_plan_uses_sql_retained_bars_when_csv_payload_is_absent(self):
        original_sql_loader = replay_module._load_equity_bars_from_sql
        try:
            replay_module._load_equity_bars_from_sql = lambda **kwargs: [
                {
                    "symbol": kwargs["symbol"],
                    "asset_class": "us_equity",
                    "source_id": "alpaca_bars",
                    "timeframe": "1Day",
                    "timestamp": "2021-01-04T16:00:00-05:00",
                    "date": "2021-01-04",
                    "bar_open": 100.0,
                    "bar_high": 101.0,
                    "bar_low": 99.0,
                    "bar_close": 100.5,
                    "bar_volume": 1000.0,
                }
            ]
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dataset_root = root / "dataset"
                dataset_root.mkdir(parents=True)
                receipt_path = root / "completion_receipt.json"
                receipt_path.write_text(
                    json.dumps({"runs": [{"status": "succeeded", "row_counts": {"equity_bar": 1}, "outputs": []}]}) + "\n",
                    encoding="utf-8",
                )
                plan_path = dataset_root / "feed_acquisition_plan.csv"
                with plan_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(
                        handle,
                        fieldnames=[
                            "source_id",
                            "month",
                            "start_date",
                            "end_date_exclusive",
                            "target_ref",
                            "coverage_status",
                            "coverage_receipt_path",
                        ],
                    )
                    writer.writeheader()
                    writer.writerow(
                        {
                            "source_id": "alpaca_bars",
                            "month": "2021-01",
                            "start_date": "2021-01-01",
                            "end_date_exclusive": "2021-02-01",
                            "target_ref": "AAPL",
                            "coverage_status": "available",
                            "coverage_receipt_path": str(receipt_path),
                        }
                    )

                rows = replay_module._load_equity_bars_from_plan(
                    plan_path=plan_path,
                    replay_month="2021-01",
                    equity_symbols=["AAPL"],
                )

                self.assertEqual(list(rows), ["AAPL"])
                self.assertEqual(rows["AAPL"][0]["timestamp"], "2021-01-04T16:00:00-05:00")
                self.assertEqual(rows["AAPL"][0]["source_id"], "alpaca_bars")
        finally:
            replay_module._load_equity_bars_from_sql = original_sql_loader

    def test_candidate_policy_replay_uses_m05_option_path_return(self):
        original_feature_loader = replay_module._load_option_candidate_features
        original_point_feature_loader = replay_module._load_option_candidate_features_for_timestamp
        original_path_loader = replay_module._load_option_contract_path_bars
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            replay_module._load_option_candidate_features = lambda **_: {
                ("AAPL", "2021-01-04T16:00:00-05:00"): [
                    {
                        "contract_ref": "AAPL_2021-01-15_P_100",
                        "option_right": "PUT",
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
                ]
            }
            replay_module._load_option_candidate_features_for_timestamp = lambda **_: [
                {
                    "contract_ref": "AAPL_2021-01-15_P_100",
                    "option_right": "PUT",
                }
            ]
            replay_module._load_option_contract_path_bars = lambda **_: {
                "AAPL_2021-01-15_P_100": [
                    {"option_symbol": "AAPL_2021-01-15_P_100", "timestamp": "2021-01-04T16:00:00-05:00", "bar_close": 2.0},
                    {"option_symbol": "AAPL_2021-01-15_P_100", "timestamp": "2021-01-05T16:00:00-05:00", "bar_close": 3.0},
                ]
            }
            replay_module._option_expression_plan_for_bar = lambda **_: {
                "model_ref": "storage://trading-manager/model_group/test_fold/model_05_option_expression/test",
                "target_ref": "AAPL",
                "asset_expression_route": "listed_option_contract",
                "option_surface_status": "optionable_chain_available",
                "selected_expression_type": "long_put",
                "selected_contract": {
                    "contract_ref": "AAPL_2021-01-15_P_100",
                    "mid_price": 2.15,
                },
            }
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dataset_root = self._dataset(root)
                equity_source_root = self._equity_source_root(root)
                result = build_candidate_policy_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="test_candidate_policy_option_path",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=equity_source_root,
                    equity_symbols=["AAPL"],
                    max_decision_rows=1,
                    option_feature_database_url="postgresql://example/unused",
                )

                rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(rows[0]["asset_expression_route"], "listed_option_contract")
                self.assertEqual(rows[0]["replay_time_pointer"], "2021-01-04T16:00:00-05:00")
                self.assertEqual(rows[0]["point_in_time_policy"], "replay_time_pointer_excludes_future_decision_inputs")
                self.assertEqual(rows[0]["asset_class"], "us_option")
                self.assertEqual(rows[0]["decision_expression_type"], "long_put")
                self.assertEqual(rows[0]["decision_instrument_scope"], "listed_option_contract")
                self.assertEqual(rows[0]["selected_option_contract_ref"], "AAPL_2021-01-15_P_100")
                self.assertEqual(rows[0]["option_contract_path_status"], "available")
                self.assertEqual(rows[0]["return_source"], "m05_option_expression_contract_path")
                self.assertEqual(rows[0]["option_entry_price"], 2.0)
                self.assertEqual(rows[0]["option_exit_price"], 3.0)
                self.assertEqual(result.receipt["option_contract_path_symbol_count"], 1)
                self.assertEqual(result.receipt["option_contract_path_bar_count"], 2)
                self.assertEqual(result.receipt["option_replay_coverage"]["contract_path_coverage_status"], "complete")
                self.assertEqual(result.receipt["option_replay_coverage"]["selected_option_path_available_count"], 1)
        finally:
            replay_module._load_option_candidate_features = original_feature_loader
            replay_module._load_option_candidate_features_for_timestamp = original_point_feature_loader
            replay_module._load_option_contract_path_bars = original_path_loader
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_candidate_policy_replay_rejects_selected_option_when_contract_path_missing(self):
        original_feature_loader = replay_module._load_option_candidate_features
        original_point_feature_loader = replay_module._load_option_candidate_features_for_timestamp
        original_path_loader = replay_module._load_option_contract_path_bars
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            replay_module._load_option_candidate_features = lambda **_: {
                ("AAPL", "2021-01-04T16:00:00-05:00"): [
                    {
                        "contract_ref": "AAPL_2021-01-15_P_100",
                        "option_right": "PUT",
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
                ]
            }
            replay_module._load_option_candidate_features_for_timestamp = lambda **_: [
                {
                    "contract_ref": "AAPL_2021-01-15_P_100",
                    "option_right": "PUT",
                }
            ]
            replay_module._load_option_contract_path_bars = lambda **_: {}
            replay_module._option_expression_plan_for_bar = lambda **_: {
                "model_ref": "storage://trading-manager/model_group/test_fold/model_05_option_expression/test",
                "target_ref": "AAPL",
                "asset_expression_route": "listed_option_contract",
                "option_surface_status": "optionable_chain_available",
                "selected_expression_type": "long_put",
                "selected_contract": {
                    "contract_ref": "AAPL_2021-01-15_P_100",
                    "mid_price": 2.15,
                },
            }
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result = build_candidate_policy_replay_execution_run(
                    dataset_root=self._dataset(root),
                    run_id="test_candidate_policy_missing_option_path",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=self._equity_source_root(root),
                    equity_symbols=["AAPL"],
                    max_decision_rows=1,
                    option_feature_database_url="postgresql://example/unused",
                )

                rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(rows[0]["selected_option_contract_ref"], "AAPL_2021-01-15_P_100")
                self.assertEqual(rows[0]["option_contract_path_status"], "missing")
                self.assertEqual(rows[0]["return_source"], "option_contract_path_missing")
                self.assertEqual(rows[0]["replay_rejection_reason"], "option_contract_path_missing")
                self.assertEqual(rows[0]["fill_status"], "simulated_rejected")
                self.assertIsNone(rows[0]["outcome_label"])
                self.assertEqual(rows[0]["realized_return"], 0.0)
                self.assertEqual(rows[0]["cost"], 0.0)
        finally:
            replay_module._load_option_candidate_features = original_feature_loader
            replay_module._load_option_candidate_features_for_timestamp = original_point_feature_loader
            replay_module._load_option_contract_path_bars = original_path_loader
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_option_expression_plan_selects_loaded_contract_candidate(self):
        plan = replay_module._option_expression_plan_for_bar(
            bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
            candidate_model_ref="storage://trading-manager/model_group/test_fold",
            timestamp="2021-01-04T16:00:00-05:00",
                layer_outputs=_current_layer_outputs(),
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

    def test_option_expression_plan_rejects_future_option_candidate_evidence(self):
        with self.assertRaisesRegex(ValueError, "replay_option_feature_future_data_rejected"):
            replay_module._option_expression_plan_for_bar(
                bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                timestamp="2021-01-04T10:00:00-05:00",
                layer_outputs=_current_layer_outputs(),
                option_candidates=[
                    {
                        "contract_ref": "AAPL_2021-01-15_C_100",
                        "snapshot_time": "2021-01-04T10:00:00-05:00",
                        "option_quote_available_time": "2021-01-04T10:01:00-05:00",
                    }
                ],
            )

    def test_option_contract_path_return_uses_entry_and_exit_prices(self):
        result = replay_module._option_contract_path_return(
            selected_option_contract_ref="AAPL_2021-01-15_C_100",
            entry_timestamp="2021-01-04T16:00:00-05:00",
            exit_timestamp="2021-01-05T16:00:00-05:00",
            option_contract_paths_by_symbol={
                "AAPL_2021-01-15_C_100": [
                    {"timestamp": "2021-01-04T15:59:00-05:00", "bar_close": 1.9},
                    {"timestamp": "2021-01-04T16:00:00-05:00", "bar_close": 2.0},
                    {"timestamp": "2021-01-05T15:59:00-05:00", "bar_close": 3.0},
                    {"timestamp": "2021-01-05T16:01:00-05:00", "bar_close": 3.2},
                ]
            },
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["entry_price"], 2.0)
        self.assertEqual(result["exit_price"], 3.0)
        self.assertAlmostEqual(result["gross_return"], 0.5)

    def test_option_replay_coverage_summary_marks_partial_feature_coverage(self):
        summary = replay_module._option_replay_coverage_summary(
            bars_by_target={
                "AAPL": [
                    {"asset_class": "us_equity", "timestamp": "2021-01-04T16:00:00-05:00"},
                    {"asset_class": "us_equity", "timestamp": "2021-01-05T16:00:00-05:00"},
                    {"asset_class": "us_equity", "timestamp": "2021-01-06T16:00:00-05:00"},
                ],
                "SOL": [{"asset_class": "crypto_spot", "timestamp": "2021-01-04T16:00:00-05:00"}],
            },
            option_candidates_by_underlying_time={("AAPL", "2021-01-04T16:00:00-05:00"): [{}]},
            option_contract_paths_by_symbol={"AAPL_2021-01-15_C_100": [{"bar_close": 2.0}]},
            decision_rows=[
                {
                    "target_ref": "AAPL",
                    "replay_time_pointer": "2021-01-04T16:00:00-05:00",
                    "asset_expression_route": "listed_option_contract",
                    "selected_option_contract_ref": "AAPL_2021-01-15_C_100",
                    "option_contract_path_status": "available",
                }
            ],
        )

        self.assertEqual(summary["feature_snapshot_coverage_status"], "complete")
        self.assertEqual(summary["expected_option_signal_snapshot_count"], 1)
        self.assertEqual(summary["missing_equity_decision_snapshot_count"], 0)
        self.assertEqual(summary["selected_option_decision_count"], 1)
        self.assertEqual(summary["contract_path_coverage_status"], "complete")

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
                    "--initial-capital-usd",
                    "31000",
                    "--exclude-equity",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={"PYTHONPATH": "src:/root/projects/trading-execution/src:/root/projects/trading-model/src"},
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["replay_execution_run_id"], "cli_run")
            self.assertEqual(payload["initial_capital_usd"], 31000.0)
            self.assertEqual(payload["initial_capital"]["currency"], "USD")
            self.assertEqual(payload["decision_row_count"], 1)
            self.assertTrue((output_dir / "decision_rows.jsonl").exists())
            self.assertTrue(progress_path.exists())

    def test_replay_rejects_nonpositive_initial_capital(self):
        with tempfile.TemporaryDirectory() as tmp:
            dataset_root = self._dataset(Path(tmp))

            with self.assertRaisesRegex(ValueError, "initial_capital_usd"):
                build_crypto_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="bad_initial_capital",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    max_decision_rows=1,
                    initial_capital_usd=0,
                )

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
                env={"PYTHONPATH": "src:/root/projects/trading-execution/src:/root/projects/trading-model/src"},
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--candidate-model-ref", result.stderr)


def _write_after_cost_alpha_model(root: Path) -> Path:
    path = root / "after_cost_alpha_model.json"
    path.write_text(json.dumps(_after_cost_alpha_model(), sort_keys=True), encoding="utf-8")
    return path


def _calibration_row(*, index: int, alpha_confidence: float) -> dict[str, object]:
    return {
        "target_ref": "AAPL",
        "timestamp": f"2021-01-{(index % 28) + 1:02d}T16:00:00-05:00",
        "replay_month": "2021-01",
        "alpha_confidence": alpha_confidence,
        "trade_intensity": 0.02 + (index % 5) * 0.002,
        "action_confidence": 0.80,
        "action_direction": 0.60,
        "expected_return_score": 0.04,
        "gross_return": 0.01,
        "return_after_cost": 0.008,
    }


def _after_cost_alpha_model() -> dict[str, object]:
    global _AFTER_COST_ALPHA_MODEL
    try:
        return copy.deepcopy(_AFTER_COST_ALPHA_MODEL)
    except NameError:
        from models.model_05_alpha_confidence.contract import HORIZONS
        from models.model_05_alpha_confidence.training import train_after_cost_alpha_model

        training_rows = []
        for index in range(16):
            positive = index % 2 == 1
            direction = 0.55 if positive else -0.55
            training_rows.append(
                {
                    "after_cost_return": 0.03 if positive else -0.03,
                    "market_context_state": {
                        "1_market_risk_stress_score": 0.15 + index * 0.01,
                        "1_market_liquidity_support_score": 0.75,
                        "1_state_quality_score": 0.80,
                    },
                    "sector_context_state": {
                        "2_sector_context_support_quality_score": 0.60,
                        "2_state_quality_score": 0.75,
                    },
                    "target_context_state": {
                        "3_target_direction_score_10min": direction,
                        "3_target_direction_score_1h": direction,
                        "3_target_direction_score_1D": direction,
                        "3_target_direction_score_1W": direction,
                        "3_target_trend_quality_score_10min": 0.70,
                        "3_target_trend_quality_score_1h": 0.70,
                        "3_target_trend_quality_score_1D": 0.70,
                        "3_target_trend_quality_score_1W": 0.70,
                        "3_state_quality_score": 0.80,
                    },
                    "event_failure_risk_vector": {},
                    "quality_calibration_state": {
                        "data_quality_score": 0.80,
                        "model_ensemble_agreement_score": 0.70,
                        "model_disagreement_score": 0.10,
                        "out_of_distribution_score": 0.05,
                    },
                }
            )
        _AFTER_COST_ALPHA_MODEL = {
            "contract_type": "current_replay_after_cost_alpha_model_bundle",
            "artifacts_by_horizon": {
                horizon: train_after_cost_alpha_model(training_rows, horizon=horizon, iterations=2)
                for horizon in HORIZONS
            },
        }
        return copy.deepcopy(_AFTER_COST_ALPHA_MODEL)


def _current_layer_outputs(
    *,
    action_type: str = "open_long",
    action_side: str = "long",
    direction: str = "bullish",
    alpha_score: float = 0.82,
    trade_intensity: float = 0.12,
    action_direction: float = 0.18,
    expected_return: float = 0.04,
) -> dict[str, object]:
    alpha_gate_status = "passed" if alpha_score >= 0.50 else "below_entry_threshold"
    return {
        "target_candidate_id": "replay_aapl_test",
        "target_context_state": {"model_ref": "target-context-ref"},
        "market_context_state": {"1_market_liquidity_support_score": 0.85},
        "event_state_vector": {"model_ref": "event-state-ref"},
        "prediction_score": alpha_score,
        "unified_decision_vector": {
            "model_ref": "unified-decision-ref",
            "unified_decision_vector_ref": "udv_test",
            "unified_decision_confidence_score": alpha_score,
            "minimum_entry_confidence": 0.50,
        },
        "direct_underlying_intent": {
            "model_ref": "unified-decision-ref",
            "underlying_action_type": action_type,
            "action_side": action_side,
            "trade_intensity_score": trade_intensity,
            "handoff_to_model_05": {
                "underlying_path_direction": direction,
                "expected_holding_time_minutes": 1440,
                "expected_entry_price": 100.0,
                "expected_target_price": 110.0,
                "target_price_high": 110.0,
                "expected_favorable_move_pct": 0.06,
                "expected_adverse_move_pct": 0.02,
                "path_quality_score": 0.80,
            },
        },
        "model_layer_diagnostics": {
            "entry_thresholds": {
                "minimum_entry_alpha_confidence": 0.50,
                "minimum_trade_intensity": 0.05,
            },
            "model_05_alpha_confidence": {
                "resolved_alpha_score": alpha_score,
                "alpha_gate_status": alpha_gate_status,
            },
            "model_04_unified_decision": {
                "resolved_underlying_action_type": action_type,
                "resolved_action_side": action_side,
                "dominant_horizon_scores": {
                    "trade_intensity_score": trade_intensity,
                    "action_direction_score": action_direction,
                    "expected_return_score": expected_return,
                    "minimum_trade_intensity": 0.05,
                },
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
