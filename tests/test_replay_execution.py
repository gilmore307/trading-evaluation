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

from trading_evaluation import (
    build_candidate_policy_portfolio_trace_audit,
    build_candidate_policy_replay_execution_run,
    build_crypto_replay_execution_run,
)
from trading_evaluation import replay_execution as replay_module


class ReplayExecutionTests(unittest.TestCase):
    def test_equity_market_close_timestamp_uses_new_york_dst_offset(self):
        self.assertEqual(replay_module._equity_market_close_timestamp("2021-01-04"), "2021-01-04T16:00:00-05:00")
        self.assertEqual(replay_module._equity_market_close_timestamp("2021-04-14"), "2021-04-14T16:00:00-04:00")

    def test_option_position_allocation_uses_target_notional_floor_not_cap(self):
        expensive_plan = {
            "selected_contract": {
                "contract_ref": "BEST_100C",
                "mid_price": 100.0,
                "contract_multiplier": 100.0,
            }
        }
        cheap_plan = {
            "selected_contract": {
                "contract_ref": "NEXT_30C",
                "mid_price": 30.0,
                "contract_multiplier": 100.0,
            }
        }

        expensive = replay_module._candidate_position_allocation(
            cash=25_000.0,
            minimum_position_notional_usd=5_000.0,
            option_expression_plan=expensive_plan,
            reference_price=100.0,
        )
        cheap = replay_module._candidate_position_allocation(
            cash=15_000.0,
            minimum_position_notional_usd=5_000.0,
            option_expression_plan=cheap_plan,
            reference_price=30.0,
        )

        self.assertEqual(expensive["quantity"], 1.0)
        self.assertEqual(expensive["notional"], 10_000.0)
        self.assertEqual(cheap["quantity"], 2.0)
        self.assertEqual(cheap["notional"], 6_000.0)

    def test_target_allocation_fraction_comes_from_model_output(self):
        context = replay_module._target_allocation_context(
            layer_outputs=_current_layer_outputs(target_allocation_fraction=0.40),
            total_portfolio_notional_usd=25_000.0,
            default_target_allocation_fraction=0.20,
        )

        self.assertEqual(context["target_allocation_fraction"], 0.40)
        self.assertEqual(context["target_allocation_notional_usd"], 10_000.0)
        self.assertEqual(context["target_allocation_fraction_source"], "model_05_handoff.target_allocation_fraction")
        self.assertEqual(context["allocation_contract_status"], "current")

    def test_target_allocation_fraction_below_slot_requires_explicit_partial_mode(self):
        context = replay_module._target_allocation_context(
            layer_outputs=_current_layer_outputs(target_allocation_fraction=0.03),
            total_portfolio_notional_usd=25_000.0,
            default_target_allocation_fraction=0.20,
        )
        partial_context = replay_module._target_allocation_context(
            layer_outputs=_current_layer_outputs(
                target_allocation_fraction=0.03,
                unified_decision_overrides={"allocation_mode": "partial_slot"},
            ),
            total_portfolio_notional_usd=25_000.0,
            default_target_allocation_fraction=0.20,
        )

        self.assertEqual(context["allocation_contract_status"], "below_minimum_actionable_slot_fraction")
        self.assertFalse(context["partial_target_allocation_allowed"])
        self.assertEqual(partial_context["allocation_contract_status"], "current")
        self.assertTrue(partial_context["partial_target_allocation_allowed"])

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
            self.assertIn("model_01_background_context", rows[0]["model_layer_refs"])
            self.assertIn("model_02_target_state", rows[0]["model_layer_refs"])
            self.assertIn("model_03_event_state", rows[0]["model_layer_refs"])
            self.assertIn("model_04_unified_decision", rows[0]["model_layer_refs"])
            self.assertIn("entry_utility", rows[0]["model_layer_diagnostics"])
            self.assertIn("model_04_unified_decision", rows[0]["model_layer_diagnostics"])
            m04_scores = rows[0]["model_layer_diagnostics"]["model_04_unified_decision"]["dominant_horizon_scores"]
            self.assertIn("materiality_adjusted_action_score", m04_scores)
            self.assertIn("no_trade_probability_score", m04_scores)
            self.assertIn("minimum_trade_intensity", m04_scores)
            self.assertIn("model_01_background_context", rows[0]["model_evidence_chain"])
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
        artifact = {
            "contract_type": "current_replay_split_entry_utility_model_bundle",
            "artifacts_by_horizon": {
                "1D": {"booster_model": "tree\nTree=0\nnum_leaves=2\nsplit_feature=0\n"},
            },
        }
        for horizon_artifact in artifact["artifacts_by_horizon"].values():
            horizon_artifact["booster_model"] = "tree\nTree=0\nnum_leaves=1\nleaf_value=0.5\n"

        with self.assertRaisesRegex(ValueError, "degenerate_entry_utility_artifact"):
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

    def test_option_expression_signal_requires_entry_ready_directional_trade(self):
        self.assertTrue(replay_module._option_expression_signal_required(_current_layer_outputs()))
        self.assertFalse(replay_module._option_expression_signal_required(_current_layer_outputs(alpha_score=0.25)))
        self.assertFalse(replay_module._option_expression_signal_required(_current_layer_outputs(trade_intensity=0.01)))
        self.assertFalse(replay_module._option_expression_signal_required(_current_layer_outputs(entry_style="limit_or_pullback")))
        self.assertFalse(replay_module._option_expression_signal_required(_current_layer_outputs(entry_style="wait_for_pullback")))
        self.assertFalse(
            replay_module._option_expression_signal_required(_current_layer_outputs(entry_style="wait_for_breakout_confirmation"))
        )
        self.assertTrue(
            replay_module._option_expression_signal_required(
                _current_layer_outputs(action_type="open_short", action_side="short", direction="bearish", action_direction=-0.2, expected_return=-0.03)
            )
        )
        self.assertFalse(
            replay_module._option_expression_signal_required(
                _current_layer_outputs(action_type="no_trade", action_side="none", direction="neutral", action_direction=0.0, expected_return=0.0)
            )
        )

    def test_bearish_option_expression_selects_long_put(self):
        plan = replay_module._option_expression_plan_for_bar(
            bar={"symbol": "AAPL", "asset_class": "us_equity", "bar_close": 100.0},
            candidate_model_ref="storage://trading-manager/model_group/test_fold",
            timestamp="2021-01-04T16:00:00-05:00",
            layer_outputs=_current_layer_outputs(
                action_type="open_short",
                action_side="short",
                direction="bearish",
                action_direction=-0.2,
                expected_return=-0.03,
                handoff_overrides={"expected_target_price": 92.0, "target_price_low": 92.0},
            ),
            option_candidates=[
                {
                    "contract_ref": "AAPL_2021-01-15_C_100",
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
                },
                {
                    "contract_ref": "AAPL_2021-01-15_P_100",
                    "option_right": "PUT",
                    "expiration": "2021-01-15",
                    "strike": 100.0,
                    "dte": 11,
                    "bid_price": 2.1,
                    "ask_price": 2.2,
                    "mid_price": 2.15,
                    "delta": -0.45,
                    "theta": -0.02,
                    "vega": 0.12,
                    "volume": 500,
                    "open_interest": 2000,
                    "spread_pct_mid": 0.0465,
                    "quote_age_seconds": 10,
                },
            ],
        )

        assert plan is not None
        self.assertEqual(plan["selected_expression_type"], "long_put")
        self.assertEqual(plan["selected_option_right"], "put")
        self.assertEqual(plan["selected_contract"]["contract_ref"], "AAPL_2021-01-15_P_100")

    def test_fixed_candidate_universe_can_emit_option_feature_requirements(self):
        with self.assertRaisesRegex(ValueError, "replay_option_feature_acquisition_required"):
            _decision_rows_for_option_requirement_policy(allow_option_feature_requirements=True)

    def test_portfolio_preselection_writes_runtime_trace_across_months(self):
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            replay_module._candidate_layer_outputs = lambda **_: _current_layer_outputs(target_allocation_fraction=0.20)
            replay_module._option_expression_plan_for_bar = lambda **_: {
                "selected_expression_type": "long_call",
                "selected_contract": {
                    "contract_ref": "AAPL_2021-02-19_C_100",
                    "mid_price": 1.0,
                    "contract_multiplier": 100.0,
                },
            }
            with tempfile.TemporaryDirectory() as tmp:
                trace_path = Path(tmp) / "replay_runtime_trace.jsonl"
                selected_keys, _, _, missing_requirements, _, summary = (
                    replay_module._select_candidate_policy_portfolio_replay_keys(
                        bars_by_target={
                            "AAPL": [
                                {
                                    "symbol": "AAPL",
                                    "asset_class": "us_equity",
                                    "source_id": "alpaca_bars",
                                    "timestamp": "2021-01-29T16:00:00-05:00",
                                    "date": "2021-01-29",
                                    "bar_open": 100.0,
                                    "bar_high": 101.0,
                                    "bar_low": 99.0,
                                    "bar_close": 100.0,
                                    "bar_volume": 1000.0,
                                },
                                {
                                    "symbol": "AAPL",
                                    "asset_class": "us_equity",
                                    "source_id": "alpaca_bars",
                                    "timestamp": "2021-02-01T16:00:00-05:00",
                                    "date": "2021-02-01",
                                    "bar_open": 101.0,
                                    "bar_high": 102.0,
                                    "bar_low": 100.0,
                                    "bar_close": 101.0,
                                    "bar_volume": 1000.0,
                                },
                                {
                                    "symbol": "AAPL",
                                    "asset_class": "us_equity",
                                    "source_id": "alpaca_bars",
                                    "timestamp": "2021-02-02T16:00:00-05:00",
                                    "date": "2021-02-02",
                                    "bar_open": 102.0,
                                    "bar_high": 103.0,
                                    "bar_low": 101.0,
                                    "bar_close": 102.0,
                                    "bar_volume": 1000.0,
                                },
                            ]
                        },
                        candidate_model_ref="storage://trading-manager/model_group/test_fold",
                        after_cost_alpha_model=_after_cost_alpha_model(),
                        entry_calibration=replay_module.EntryCalibration(
                            artifact={
                                "selected_thresholds": {
                                    "minimum_entry_alpha_confidence": 0.50,
                                    "minimum_trade_intensity": 0.05,
                                }
                            },
                            path=Path("entry_threshold_calibration.json"),
                        ),
                        option_candidates_by_underlying_time={
                            ("AAPL", "2021-01-29T16:00:00-05:00"): [{"contract_ref": "AAPL_2021-02-19_C_100"}],
                            ("AAPL", "2021-02-01T16:00:00-05:00"): [{"contract_ref": "AAPL_2021-02-19_C_100"}],
                        },
                        initial_capital_usd=25_000.0,
                        max_positions=1,
                        default_target_allocation_fraction=0.20,
                        switch_minimum_rank_score_delta=999.0,
                        runtime_trace_path=trace_path,
                        run_id="trace-test",
                    )
                )

                rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(selected_keys, {("AAPL", 0)})
            self.assertEqual(missing_requirements, [])
            self.assertEqual(summary["timestamp_count"], 2)
            self.assertIn("replay_clock_processed", [row["trace_event_type"] for row in rows])
            self.assertIn("replay_month_crossed", [row["trace_event_type"] for row in rows])
            self.assertEqual(rows[-1]["trace_event_type"], "replay_runtime_trace_finalized")
            month_crossed = next(row for row in rows if row["trace_event_type"] == "replay_month_crossed")
            self.assertEqual(month_crossed["completed_replay_month"], "2021-01")
            self.assertEqual(month_crossed["next_replay_month"], "2021-02")
            self.assertEqual(month_crossed["position_targets_after"], ["AAPL"])
        finally:
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_portfolio_preselection_stops_requirements_at_first_gap(self):
        original_layer_outputs = replay_module._candidate_layer_outputs
        try:
            replay_module._candidate_layer_outputs = lambda **_: _current_layer_outputs(target_allocation_fraction=0.20)
            with tempfile.TemporaryDirectory() as tmp:
                trace_path = Path(tmp) / "replay_runtime_trace.jsonl"
                _, _, _, missing_requirements, _, summary = replay_module._select_candidate_policy_portfolio_replay_keys(
                    bars_by_target={
                        "AAPL": [
                            {
                                "symbol": "AAPL",
                                "asset_class": "us_equity",
                                "source_id": "alpaca_bars",
                                "timestamp": "2021-01-04T16:00:00-05:00",
                                "date": "2021-01-04",
                                "bar_open": 100.0,
                                "bar_high": 101.0,
                                "bar_low": 99.0,
                                "bar_close": 100.0,
                                "bar_volume": 1000.0,
                            },
                            {
                                "symbol": "AAPL",
                                "asset_class": "us_equity",
                                "source_id": "alpaca_bars",
                                "timestamp": "2021-01-05T16:00:00-05:00",
                                "date": "2021-01-05",
                                "bar_open": 101.0,
                                "bar_high": 102.0,
                                "bar_low": 100.0,
                                "bar_close": 101.0,
                                "bar_volume": 1000.0,
                            },
                            {
                                "symbol": "AAPL",
                                "asset_class": "us_equity",
                                "source_id": "alpaca_bars",
                                "timestamp": "2021-01-06T16:00:00-05:00",
                                "date": "2021-01-06",
                                "bar_open": 102.0,
                                "bar_high": 103.0,
                                "bar_low": 101.0,
                                "bar_close": 102.0,
                                "bar_volume": 1000.0,
                            },
                        ]
                    },
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    entry_calibration=replay_module.EntryCalibration(
                        artifact={
                            "selected_thresholds": {
                                "minimum_entry_alpha_confidence": 0.50,
                                "minimum_trade_intensity": 0.05,
                            }
                        },
                        path=Path("entry_threshold_calibration.json"),
                    ),
                    option_candidates_by_underlying_time={},
                    initial_capital_usd=25_000.0,
                    max_positions=1,
                    default_target_allocation_fraction=0.20,
                    switch_minimum_rank_score_delta=999.0,
                    runtime_trace_path=trace_path,
                    run_id="trace-test",
                )

                rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(
                [row["timestamp"] for row in missing_requirements],
                ["2021-01-04T16:00:00-05:00"],
            )
            self.assertEqual(summary["missing_option_feature_requirement_count"], 1)
            self.assertEqual(
                [row["replay_time_pointer"] for row in rows if row["trace_event_type"] == "replay_option_feature_requirements_blocked"],
                ["2021-01-04T16:00:00-05:00"],
            )
        finally:
            replay_module._candidate_layer_outputs = original_layer_outputs

    def test_point_in_time_handoff_can_emit_option_feature_requirements(self):
        with self.assertRaisesRegex(ValueError, "replay_option_feature_acquisition_required"):
            _decision_rows_for_option_requirement_policy(allow_option_feature_requirements=True)

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
        self.assertEqual(payload["resolver_policy_ref"], "replay_on_demand_resolver_forward_only_asof")
        self.assertEqual(payload["requirement_kind"], "same_row_option_snapshot")
        self.assertEqual(len(payload["sample"]), 2)
        self.assertEqual(payload["sample"][0]["maximum_permitted_source_end"], "2021-05-19T16:00:00-04:00")
        self.assertEqual(payload["sample"][0]["resolver_policy_ref"], "replay_on_demand_resolver_forward_only_asof")
        self.assertEqual(payload["sample"][0]["replay_time_pointer"], "2021-05-19T16:00:00-04:00")
        self.assertEqual(payload["sample"][0]["source_window_end"], "2021-05-19T16:00:00-04:00")
        self.assertEqual(payload["sample"][0]["portfolio_capacity_policy"], replay_module.PORTFOLIO_CAPACITY_POLICY)
        self.assertEqual(payload["sample"][0]["max_positions"], str(replay_module.DEFAULT_PORTFOLIO_MAX_POSITIONS))
        self.assertEqual(payload["sample"][0]["switch_threshold_policy"], replay_module.PORTFOLIO_SWITCH_THRESHOLD_POLICY)
        self.assertEqual(
            payload["sample"][0]["switch_minimum_rank_score_delta"],
            str(replay_module.DEFAULT_SWITCH_MINIMUM_RANK_SCORE_DELTA),
        )
        self.assertEqual(payload["sample"][0]["future_source_rows_decision_visible"], "false")
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
                        "4_materiality_adjusted_action_score_1D": 0.42,
                        "4_no_trade_probability_score_1D": 0.1,
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
                        "horizon_decisions": {
                            "1D": {
                                "trade_intensity_score": 0.2,
                                "minimum_trade_intensity": 0.0,
                                "materiality_adjusted_action_score": 0.42,
                                "no_trade_probability_score": 0.1,
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
                low["model_layer_diagnostics"]["entry_utility"]["utility_gate_status"],
                "below_entry_threshold",
            )
            self.assertEqual(high["model_layer_diagnostics"]["entry_utility"]["utility_gate_status"], "passed")
            high_scores = high["model_layer_diagnostics"]["model_04_unified_decision"]["dominant_horizon_scores"]
            self.assertEqual(high_scores["materiality_adjusted_action_score"], 0.42)
            self.assertEqual(high_scores["no_trade_probability_score"], 0.1)
            self.assertEqual(high_scores["minimum_trade_intensity"], 0.0)
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

            with self.assertRaisesRegex(ValueError, "M02 target-candidate handoff"):
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
        original_point_feature_loader = replay_module._load_option_candidate_features_for_timestamp
        original_plan_builder = replay_module._option_expression_plan_for_bar
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_path_loader = replay_module._load_option_contract_path_bars
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
            replay_module._load_option_candidate_features_for_timestamp = lambda **_: [
                {"contract_ref": "AAPL_2021-01-15_C_100"}
            ]
            replay_module._option_expression_plan_for_bar = lambda **_: {
                "model_ref": "storage://trading-manager/model_group/test_fold/model_05_option_expression/test",
                "target_ref": "AAPL",
                "asset_expression_route": "listed_option_contract",
                "option_surface_status": "optionable_chain_available",
                "selected_expression_type": "long_call",
                "selected_contract": {
                    "contract_ref": "AAPL_2021-01-15_C_100",
                    "mid_price": 1.0,
                },
            }
            replay_module._candidate_layer_outputs = lambda **_: _current_layer_outputs()
            replay_module._load_option_contract_path_bars = lambda **_: {}
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
                    option_feature_database_url="postgresql://example/unused",
                )

                self.assertEqual(result.receipt["candidate_handoff_status"], "available")
                self.assertEqual(result.receipt["candidate_handoff_source"], "model_02_target_candidate_handoff")
                self.assertEqual(result.receipt["candidate_handoff_symbols"], ["AAPL"])
                rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(rows[0]["target_ref"], "AAPL")
                self.assertIn("model_05_option_expression", rows[0]["model_layer_refs"])
                self.assertIn("model_06_residual_event_governance", rows[0]["model_layer_refs"])
                self.assertIn("model_05_option_expression", rows[0]["model_layer_diagnostics"])
                self.assertIn("model_05_alpha_confidence", rows[0]["model_layer_diagnostics"])
                self.assertEqual(
                    rows[0]["model_layer_diagnostics"]["model_05_option_expression"]["selection_gate_status"],
                    "passed",
                )
                self.assertEqual(
                    rows[0]["model_layer_diagnostics"]["model_05_option_expression"]["selected_contract_ref"],
                    "AAPL_2021-01-15_C_100",
                )
                self.assertIn("model_06_residual_event_governance", rows[0]["model_layer_diagnostics"])
                self.assertEqual(
                    rows[0]["model_layer_diagnostics"]["model_06_residual_event_governance"]["action_surface_status"],
                    "measured",
                )
                self.assertEqual(
                    rows[0]["model_layer_diagnostics"]["model_06_residual_event_governance"]["intervention_action"],
                    "allow",
                )
        finally:
            replay_module._load_layer_two_candidate_handoff_rows = original_loader
            replay_module._load_option_candidate_features = original_feature_loader
            replay_module._load_option_candidate_features_for_timestamp = original_point_feature_loader
            replay_module._option_expression_plan_for_bar = original_plan_builder
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._load_option_contract_path_bars = original_path_loader

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
                self.assertEqual(
                    result.receipt["option_feature_requirement_policy"],
                    "fixed_historical_candidate_universe_allows_replay_option_feature_requirements",
                )
                self.assertEqual(
                    result.receipt["model_candidate_selection_trace_ref"],
                    str(result.model_candidate_selection_trace_path),
                )
                self.assertEqual(
                    result.receipt["model_candidate_selection_trace_summary"]["future_outcome_label_included"],
                    False,
                )
                trace_rows = [
                    json.loads(line)
                    for line in result.model_candidate_selection_trace_path.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual(trace_rows[0]["contract_type"], "evaluation_model_candidate_selection_trace_row")
                self.assertEqual(trace_rows[0]["target_ref"], "AAPL")
                self.assertTrue(trace_rows[0]["model_score_available"])
                self.assertEqual(trace_rows[0]["future_outcome_label_included"], False)
                self.assertEqual(trace_rows[0]["model_rank_within_timestamp"], 1)
                self.assertIn(
                    trace_rows[0]["model_candidate_trace_status"],
                    {
                        "selected_by_replay",
                        "scored_no_entry_intent",
                        "scored_no_option_expression_signal",
                        "option_expression_features_missing_or_not_built",
                    },
                )
        finally:
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_full_fixed_candidate_universe_rejects_target_scoped_model_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset_root = self._dataset(root)
            equity_source_root = self._equity_source_root(root)
            candidate_universe_path = self._candidate_universe(root, ["AAPL", "MSFT"])

            with self.assertRaisesRegex(ValueError, "requires a fold-scoped model_group candidate_model_ref"):
                build_candidate_policy_replay_execution_run(
                    dataset_root=dataset_root,
                    run_id="test_target_scoped_candidate_model_ref",
                    candidate_model_ref="storage://trading-manager/model_group/aapl/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=equity_source_root,
                    include_crypto=False,
                    max_decision_rows=1,
                    option_feature_database_url="",
                    candidate_universe_path=candidate_universe_path,
                )

    def test_portfolio_trace_audit_limits_m05_triggers_by_finite_capital(self):
        original_bars_loader = replay_module._load_candidate_policy_bars
        original_handoff = replay_module._candidate_handoff_for_replay
        original_calibration = replay_module._build_entry_calibration
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_feature_loader = replay_module._load_option_candidate_features
        original_point_feature_loader = replay_module._load_option_candidate_features_for_timestamp
        symbols = ("AAPL", "MSFT", "NVDA")

        def fake_bars(**_):
            rows = {}
            for offset, symbol in enumerate(symbols):
                price = 100.0 + offset
                rows[symbol] = [
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-04T16:00:00-05:00",
                        "date": "2021-01-04",
                        "bar_open": price,
                        "bar_high": price + 1.0,
                        "bar_low": price - 1.0,
                        "bar_close": price,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_open": price,
                        "bar_high": price + 2.0,
                        "bar_low": price - 1.0,
                        "bar_close": price + 1.0,
                        "bar_volume": 1200.0,
                    },
                ]
            return rows

        def fake_calibration(*, output_path, **_):
            artifact = {
                "contract_type": "validation_entry_threshold_calibration",
                "calibration_status": "test_fixed_thresholds",
                "selected_thresholds": {
                    "minimum_entry_alpha_confidence": 0.50,
                    "minimum_trade_intensity": 0.05,
                },
            }
            output_path.write_text(json.dumps(artifact, sort_keys=True) + "\n", encoding="utf-8")
            return replay_module.EntryCalibration(artifact=artifact, path=output_path)

        def fake_layer_outputs(*, target, **_):
            alpha_by_target = {"AAPL": 0.90, "MSFT": 0.84, "NVDA": 0.80}
            return _current_layer_outputs(alpha_score=alpha_by_target[target])

        try:
            replay_module._load_candidate_policy_bars = fake_bars
            replay_module._candidate_handoff_for_replay = lambda **_: {
                "status": "available",
                "source": "fixed_current_snapshot_historical_candidate_universe",
                "candidate_symbols": symbols,
                "row_count": len(symbols),
                "artifact_ref": "memory://test",
            }
            replay_module._build_entry_calibration = fake_calibration
            replay_module._candidate_layer_outputs = fake_layer_outputs
            replay_module._load_option_candidate_features = lambda **_: self.fail("portfolio trace audit must not load bulk M05 features")
            replay_module._load_option_candidate_features_for_timestamp = (
                lambda **_: self.fail("portfolio trace audit must not load point M05 features")
            )
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dataset_root = self._dataset(root)
                result = build_candidate_policy_portfolio_trace_audit(
                    dataset_root=dataset_root,
                    run_id="test_portfolio_trace_audit",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    include_crypto=False,
                    max_trace_timestamps=1,
                    max_positions=1,
                    default_target_allocation_fraction=1.0,
                    switch_minimum_rank_score_delta=999.0,
                )

                self.assertEqual(result.summary["contract_type"], "candidate_policy_portfolio_trace_audit")
                self.assertEqual(result.summary["timestamp_count"], 1)
                self.assertEqual(result.summary["candidate_count"], 3)
                self.assertEqual(result.summary["independent_m05_signal_count"], 3)
                self.assertEqual(result.summary["capital_selected_m05_count"], 1)
                self.assertEqual(result.summary["avoided_m05_request_count"], 2)
                self.assertEqual(result.summary["m05_request_avoidance_ratio"], 2 / 3)
                self.assertEqual(result.summary["side_effects"]["provider_calls_performed"], 0)
                self.assertFalse(result.summary["side_effects"]["account_mutation_performed"])
                rows = [json.loads(line) for line in result.trace_rows_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(rows[0]["selected_targets"], ["AAPL"])
                self.assertEqual(rows[0]["top_capital_rejected_targets"][:2], ["MSFT", "NVDA"])
                self.assertEqual(rows[0]["open_position_count_after"], 1)
        finally:
            replay_module._load_candidate_policy_bars = original_bars_loader
            replay_module._candidate_handoff_for_replay = original_handoff
            replay_module._build_entry_calibration = original_calibration
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._load_option_candidate_features = original_feature_loader
            replay_module._load_option_candidate_features_for_timestamp = original_point_feature_loader

    def test_candidate_policy_replay_requests_m05_for_ranked_affordable_equity_intents(self):
        original_bars_loader = replay_module._load_candidate_policy_bars
        original_handoff = replay_module._candidate_handoff_for_replay
        original_calibration = replay_module._build_entry_calibration
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_path_loader = replay_module._load_option_contract_path_bars
        symbols = ("AAPL", "MSFT")

        def fake_bars(**_):
            rows = {}
            for offset, symbol in enumerate(symbols):
                price = 100.0 + offset
                rows[symbol] = [
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-04T16:00:00-05:00",
                        "date": "2021-01-04",
                        "bar_open": price,
                        "bar_high": price + 1.0,
                        "bar_low": price - 1.0,
                        "bar_close": price,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_open": price,
                        "bar_high": price + 2.0,
                        "bar_low": price - 1.0,
                        "bar_close": price + 1.0,
                        "bar_volume": 1200.0,
                    },
                ]
            return rows

        def fake_calibration(*, output_path, **_):
            artifact = {
                "contract_type": "validation_entry_threshold_calibration",
                "calibration_status": "test_fixed_thresholds",
                "selected_thresholds": {
                    "minimum_entry_alpha_confidence": 0.50,
                    "minimum_trade_intensity": 0.05,
                },
            }
            output_path.write_text(json.dumps(artifact, sort_keys=True) + "\n", encoding="utf-8")
            return replay_module.EntryCalibration(artifact=artifact, path=output_path)

        def fake_layer_outputs(*, target, **_):
            alpha_by_target = {"AAPL": 0.90, "MSFT": 0.80}
            return _current_layer_outputs(alpha_score=alpha_by_target[target])

        try:
            replay_module._load_candidate_policy_bars = fake_bars
            replay_module._candidate_handoff_for_replay = lambda **_: {
                "status": "available",
                "source": "fixed_current_snapshot_historical_candidate_universe",
                "candidate_symbols": symbols,
                "row_count": len(symbols),
                "artifact_ref": "memory://test",
            }
            replay_module._build_entry_calibration = fake_calibration
            replay_module._candidate_layer_outputs = fake_layer_outputs
            replay_module._load_option_contract_path_bars = lambda **_: {}
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                dataset_root = self._dataset(root)
                with self.assertRaisesRegex(ValueError, "replay_option_feature_acquisition_required") as raised:
                    build_candidate_policy_replay_execution_run(
                        dataset_root=dataset_root,
                        run_id="test_ranked_affordable_requirements",
                        candidate_model_ref="storage://trading-manager/model_group/test_fold",
                        after_cost_alpha_model=_after_cost_alpha_model(),
                        include_crypto=False,
                        option_feature_database_url="",
                        portfolio_max_positions=1,
                        portfolio_default_target_allocation_fraction=1.0,
                        portfolio_switch_minimum_rank_score_delta=999.0,
                    )

                payload = json.loads(str(raised.exception).split(": ", 1)[1])
                self.assertEqual(payload["missing_count"], 2)
                self.assertEqual({item["target_ref"] for item in payload["sample"]}, {"AAPL", "MSFT"})
        finally:
            replay_module._load_candidate_policy_bars = original_bars_loader
            replay_module._candidate_handoff_for_replay = original_handoff
            replay_module._build_entry_calibration = original_calibration
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._load_option_contract_path_bars = original_path_loader

    def test_portfolio_selection_skips_unexecutable_m05_plan_before_capital(self):
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            replay_module._candidate_layer_outputs = lambda *, target, **_: _current_layer_outputs(
                alpha_score={"AAPL": 0.90, "MSFT": 0.80}[target],
                target_allocation_fraction=0.20,
            )

            def fake_option_plan(*, bar, **_):
                target = str(bar["symbol"])
                if target == "AAPL":
                    return {
                        "target_ref": target,
                        "asset_expression_route": "option_expression_unfilled",
                        "option_surface_status": "optionable_chain_available",
                        "selected_expression_type": "underlying_only_expression",
                        "selected_contract": None,
                    }
                return {
                    "target_ref": target,
                    "asset_expression_route": "listed_option_contract",
                    "option_surface_status": "optionable_chain_available",
                    "selected_expression_type": "long_call",
                    "selected_contract": {
                        "contract_ref": "MSFT_2021-01-15_C_100",
                        "mid_price": 1.0,
                    },
                }

            replay_module._option_expression_plan_for_bar = fake_option_plan
            bars_by_target = {
                symbol: [
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-04T16:00:00-05:00",
                        "date": "2021-01-04",
                        "bar_open": price,
                        "bar_high": price + 1.0,
                        "bar_low": price - 1.0,
                        "bar_close": price,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_open": price + 1.0,
                        "bar_high": price + 2.0,
                        "bar_low": price,
                        "bar_close": price + 1.0,
                        "bar_volume": 1200.0,
                    },
                ]
                for symbol, price in {"AAPL": 100.0, "MSFT": 101.0}.items()
            }
            calibration_artifact = {
                "selected_thresholds": {
                    "minimum_entry_alpha_confidence": 0.50,
                    "minimum_trade_intensity": 0.05,
                }
            }
            selected_keys, _, option_plans, missing_requirements, _, summary = replay_module._select_candidate_policy_portfolio_replay_keys(
                bars_by_target=bars_by_target,
                candidate_model_ref="storage://trading-manager/model_group/test_fold",
                after_cost_alpha_model=_after_cost_alpha_model(),
                entry_calibration=replay_module.EntryCalibration(
                    artifact=calibration_artifact,
                    path=Path("entry_threshold_calibration.json"),
                ),
                option_candidates_by_underlying_time={
                    ("AAPL", "2021-01-04T16:00:00-05:00"): [{"contract_ref": "AAPL_NO_CONTRACT"}],
                    ("MSFT", "2021-01-04T16:00:00-05:00"): [{"contract_ref": "MSFT_2021-01-15_C_100"}],
                },
                initial_capital_usd=25_000.0,
                max_positions=1,
                default_target_allocation_fraction=0.20,
                switch_minimum_rank_score_delta=999.0,
            )

            self.assertEqual(selected_keys, {("MSFT", 0)})
            self.assertEqual(missing_requirements, [])
            self.assertIsNone(option_plans[("AAPL", 0)]["selected_contract"])
            self.assertEqual(option_plans[("MSFT", 0)]["selected_contract"]["contract_ref"], "MSFT_2021-01-15_C_100")
            self.assertEqual(summary["independent_m05_signal_count"], 2)
            self.assertEqual(summary["unexecutable_m05_plan_count"], 1)
            self.assertEqual(summary["capital_selected_m05_count"], 1)
            self.assertEqual(summary["avoided_m05_request_count"], 1)
            self.assertEqual(summary["final_position_targets"], ["MSFT"])
        finally:
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_portfolio_selection_default_limits_initial_positions_to_five_risk_slots(self):
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            symbols = ("AAPL", "MSFT", "NVDA", "AMD", "META", "TSLA")

            def fake_layer_outputs(*, target, **_):
                score = {
                    "AAPL": 0.91,
                    "MSFT": 0.90,
                    "NVDA": 0.89,
                    "AMD": 0.88,
                    "META": 0.87,
                    "TSLA": 0.86,
                }[target]
                return _current_layer_outputs(alpha_score=score, target_allocation_fraction=0.20)

            def fake_option_plan(*, bar, **_):
                target = str(bar["symbol"])
                return {
                    "target_ref": target,
                    "asset_expression_route": "listed_option_contract",
                    "option_surface_status": "optionable_chain_available",
                    "selected_expression_type": "long_call",
                    "selected_contract": {
                        "contract_ref": f"{target}_2021-01-15_C_100",
                        "estimated_contract_cost_usd": 1_000.0,
                    },
                }

            replay_module._candidate_layer_outputs = fake_layer_outputs
            replay_module._option_expression_plan_for_bar = fake_option_plan
            bars_by_target = {
                symbol: [
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-04T16:00:00-05:00",
                        "date": "2021-01-04",
                        "bar_open": 100.0,
                        "bar_high": 101.0,
                        "bar_low": 99.0,
                        "bar_close": 100.0,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_open": 101.0,
                        "bar_high": 102.0,
                        "bar_low": 100.0,
                        "bar_close": 101.0,
                        "bar_volume": 1100.0,
                    },
                ]
                for symbol in symbols
            }

            selected_keys, _, _, missing_requirements, portfolio_diagnostics, summary = (
                replay_module._select_candidate_policy_portfolio_replay_keys(
                    bars_by_target=bars_by_target,
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    entry_calibration=replay_module.EntryCalibration(
                        artifact={
                            "selected_thresholds": {
                                "minimum_entry_alpha_confidence": 0.50,
                                "minimum_trade_intensity": 0.05,
                            }
                        },
                        path=Path("entry_threshold_calibration.json"),
                    ),
                    option_candidates_by_underlying_time={
                        (symbol, "2021-01-04T16:00:00-05:00"): [
                            {"contract_ref": f"{symbol}_2021-01-15_C_100"}
                        ]
                        for symbol in symbols
                    },
                    initial_capital_usd=25_000.0,
                    max_positions=replay_module.DEFAULT_PORTFOLIO_MAX_POSITIONS,
                    default_target_allocation_fraction=replay_module.DEFAULT_TARGET_ALLOCATION_FRACTION,
                    switch_minimum_rank_score_delta=999.0,
                )
            )

            self.assertEqual(missing_requirements, [])
            self.assertEqual(len(selected_keys), 5)
            self.assertEqual(summary["max_positions"], 5)
            self.assertEqual(summary["portfolio_capacity_policy"], replay_module.PORTFOLIO_CAPACITY_POLICY)
            self.assertEqual(summary["final_position_count"], 5)
            self.assertEqual(portfolio_diagnostics[("TSLA", 0)]["portfolio_replacement_evaluation_status"], "blocked_by_switch_threshold")
        finally:
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_portfolio_selection_rejects_low_allocation_without_partial_slot_mode(self):
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            def fake_layer_outputs(*, target, **_):
                return _current_layer_outputs(alpha_score=0.90, target_allocation_fraction=0.03)

            def fake_option_plan(*, bar, **_):
                target = str(bar["symbol"])
                return {
                    "target_ref": target,
                    "asset_expression_route": "listed_option_contract",
                    "option_surface_status": "optionable_chain_available",
                    "selected_expression_type": "long_call",
                    "selected_contract": {
                        "contract_ref": f"{target}_2021-01-15_C_100",
                        "estimated_contract_cost_usd": 800.0,
                    },
                }

            replay_module._candidate_layer_outputs = fake_layer_outputs
            replay_module._option_expression_plan_for_bar = fake_option_plan
            bars_by_target = {
                symbol: [
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-04T16:00:00-05:00",
                        "date": "2021-01-04",
                        "bar_open": 100.0,
                        "bar_high": 101.0,
                        "bar_low": 99.0,
                        "bar_close": 100.0,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": symbol,
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_open": 101.0,
                        "bar_high": 102.0,
                        "bar_low": 100.0,
                        "bar_close": 101.0,
                        "bar_volume": 1100.0,
                    },
                ]
                for symbol in ("AAPL", "MSFT")
            }

            selected_keys, _, _, missing_requirements, portfolio_diagnostics, summary = (
                replay_module._select_candidate_policy_portfolio_replay_keys(
                    bars_by_target=bars_by_target,
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    entry_calibration=replay_module.EntryCalibration(
                        artifact={
                            "selected_thresholds": {
                                "minimum_entry_alpha_confidence": 0.50,
                                "minimum_trade_intensity": 0.05,
                            }
                        },
                        path=Path("entry_threshold_calibration.json"),
                    ),
                    option_candidates_by_underlying_time={
                        (symbol, "2021-01-04T16:00:00-05:00"): [
                            {"contract_ref": f"{symbol}_2021-01-15_C_100"}
                        ]
                        for symbol in ("AAPL", "MSFT")
                    },
                    initial_capital_usd=25_000.0,
                    max_positions=replay_module.DEFAULT_PORTFOLIO_MAX_POSITIONS,
                    default_target_allocation_fraction=replay_module.DEFAULT_TARGET_ALLOCATION_FRACTION,
                    switch_minimum_rank_score_delta=999.0,
                )
            )

            self.assertEqual(missing_requirements, [])
            self.assertEqual(selected_keys, set())
            self.assertEqual(summary["portfolio_allocation_contract_violation_count"], 2)
            self.assertEqual(summary["final_position_count"], 0)
            self.assertEqual(
                portfolio_diagnostics[("AAPL", 0)]["portfolio_selection_reason"],
                "target_allocation_fraction_below_minimum_actionable_slot",
            )
        finally:
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._option_expression_plan_for_bar = original_plan_builder

    def test_portfolio_selection_replaces_weakest_when_cash_budget_is_full(self):
        original_layer_outputs = replay_module._candidate_layer_outputs
        original_plan_builder = replay_module._option_expression_plan_for_bar
        try:
            def fake_layer_outputs(*, target, **_):
                return _current_layer_outputs(
                    alpha_score={"AAPL": 0.60, "MSFT": 0.92}[target],
                    target_allocation_fraction=0.99,
                )

            def fake_option_plan(*, bar, **_):
                target = str(bar["symbol"])
                return {
                    "target_ref": target,
                    "asset_expression_route": "listed_option_contract",
                    "option_surface_status": "optionable_chain_available",
                    "selected_expression_type": "long_call",
                    "selected_contract": {
                        "contract_ref": f"{target}_2021-01-15_C_100",
                        "estimated_contract_cost_usd": 24_750.0,
                    },
                }

            replay_module._candidate_layer_outputs = fake_layer_outputs
            replay_module._option_expression_plan_for_bar = fake_option_plan
            bars_by_target = {
                "AAPL": [
                    {
                        "symbol": "AAPL",
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-04T16:00:00-05:00",
                        "date": "2021-01-04",
                        "bar_open": 100.0,
                        "bar_high": 101.0,
                        "bar_low": 99.0,
                        "bar_close": 100.0,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": "AAPL",
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_open": 101.0,
                        "bar_high": 102.0,
                        "bar_low": 100.0,
                        "bar_close": 101.0,
                        "bar_volume": 1100.0,
                    },
                    {
                        "symbol": "AAPL",
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-06T16:00:00-05:00",
                        "date": "2021-01-06",
                        "bar_open": 102.0,
                        "bar_high": 103.0,
                        "bar_low": 101.0,
                        "bar_close": 102.0,
                        "bar_volume": 1200.0,
                    },
                ],
                "MSFT": [
                    {
                        "symbol": "MSFT",
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_open": 200.0,
                        "bar_high": 201.0,
                        "bar_low": 199.0,
                        "bar_close": 200.0,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": "MSFT",
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-06T16:00:00-05:00",
                        "date": "2021-01-06",
                        "bar_open": 201.0,
                        "bar_high": 202.0,
                        "bar_low": 200.0,
                        "bar_close": 201.0,
                        "bar_volume": 1100.0,
                    },
                ],
            }

            selected_keys, _, _, missing_requirements, portfolio_diagnostics, summary = (
                replay_module._select_candidate_policy_portfolio_replay_keys(
                    bars_by_target=bars_by_target,
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    entry_calibration=replay_module.EntryCalibration(
                        artifact={
                            "selected_thresholds": {
                                "minimum_entry_alpha_confidence": 0.50,
                                "minimum_trade_intensity": 0.05,
                            }
                        },
                        path=Path("entry_threshold_calibration.json"),
                    ),
                    option_candidates_by_underlying_time={
                        ("AAPL", "2021-01-04T16:00:00-05:00"): [{"contract_ref": "AAPL_2021-01-15_C_100"}],
                        ("AAPL", "2021-01-05T16:00:00-05:00"): [{"contract_ref": "AAPL_2021-01-15_C_100"}],
                        ("MSFT", "2021-01-05T16:00:00-05:00"): [{"contract_ref": "MSFT_2021-01-15_C_100"}],
                    },
                    initial_capital_usd=25_000.0,
                    max_positions=0,
                    default_target_allocation_fraction=replay_module.DEFAULT_TARGET_ALLOCATION_FRACTION,
                    switch_minimum_rank_score_delta=0.00001,
                )
            )

            self.assertEqual(missing_requirements, [])
            self.assertEqual(selected_keys, {("AAPL", 0), ("MSFT", 0)})
            self.assertEqual(summary["portfolio_replacement_evaluated_count"], 2)
            self.assertEqual(summary["portfolio_replacement_triggered_count"], 1)
            self.assertEqual(summary["portfolio_replacement_blocked_by_threshold_count"], 1)
            self.assertEqual(summary["final_position_targets"], ["MSFT"])
            self.assertEqual(
                portfolio_diagnostics[("MSFT", 0)]["portfolio_replacement_evaluation_status"],
                "triggered",
            )
            self.assertEqual(portfolio_diagnostics[("MSFT", 0)]["portfolio_worst_held_target_before"], "AAPL")
            self.assertGreater(portfolio_diagnostics[("MSFT", 0)]["portfolio_switch_rank_score_delta"], 0.00001)
        finally:
            replay_module._candidate_layer_outputs = original_layer_outputs
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

    def test_load_equity_bars_filters_fallback_rows_to_replay_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "alpaca_bars"
            for month, first_close, second_close in (("2021-01", 100.5, 101.5), ("2021-02", 200.5, 201.5)):
                bar_path = source_root / "MSFT" / month / "runs" / "run" / "saved" / "equity_bar.csv"
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
                        ],
                    )
                    writer.writeheader()
                    writer.writerows(
                        [
                            {
                                "symbol": "MSFT",
                                "timeframe": "1Day",
                                "timestamp": f"{month}-01T16:00:00-05:00",
                                "bar_open": first_close,
                                "bar_high": first_close,
                                "bar_low": first_close,
                                "bar_close": first_close,
                                "bar_volume": 1000,
                            },
                            {
                                "symbol": "MSFT",
                                "timeframe": "1Day",
                                "timestamp": f"{month}-02T16:00:00-05:00",
                                "bar_open": second_close,
                                "bar_high": second_close,
                                "bar_low": second_close,
                                "bar_close": second_close,
                                "bar_volume": 1100,
                            },
                        ]
                    )

            rows = replay_module._load_equity_bars(
                equity_source_root=source_root,
                equity_symbols=["MSFT"],
                replay_month="2021-02",
            )

            self.assertEqual([row["timestamp"][:7] for row in rows["MSFT"]], ["2021-02", "2021-02"])
            self.assertEqual(rows["MSFT"][0]["bar_close"], 200.5)

    def test_write_replay_progress_preserves_existing_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay_progress.jsonl"
            replay_module._write_replay_progress_jsonl(
                path,
                [
                    {
                        "contract_type": "evaluation_replay_progress",
                        "status": "completed",
                        "month": "2021-01",
                        "replay_execution_run_id": "run_1",
                    }
                ],
            )
            replay_module._write_replay_progress_jsonl(
                path,
                [
                    {
                        "contract_type": "evaluation_replay_progress",
                        "status": "completed",
                        "month": "2021-02",
                        "replay_execution_run_id": "run_2",
                    }
                ],
            )

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([(row["replay_execution_run_id"], row["month"]) for row in rows], [("run_1", "2021-01"), ("run_2", "2021-02")])

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
                self.assertEqual(result.receipt["decision_row_count"], 0)
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

    def test_replay_month_coverage_accepts_current_candidate_policy_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "feed_acquisition_plan.csv"
            with plan_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["source_id", "month", "coverage_status"])
                writer.writeheader()
                for source_id in ("alpaca_bars", "gdelt_news", "trading_economics_calendar_web"):
                    writer.writerow(
                        {
                            "source_id": source_id,
                            "month": "2021-02",
                            "coverage_status": "available",
                        }
                    )

            replay_module._validate_replay_month_coverage(plan_path=plan_path, replay_month="2021-02")

    def test_candidate_policy_replay_uses_m05_option_path_return(self):
        original_feature_loader = replay_module._load_option_candidate_features
        original_point_feature_loader = replay_module._load_option_candidate_features_for_timestamp
        original_path_loader = replay_module._load_option_contract_path_bars
        original_plan_builder = replay_module._option_expression_plan_for_bar
        original_layer_outputs = replay_module._candidate_layer_outputs
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
            replay_module._candidate_layer_outputs = lambda **_: _current_layer_outputs()
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
                    include_crypto=False,
                    max_decision_rows=1,
                    option_feature_database_url="postgresql://example/unused",
                )

                rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(rows[0]["asset_expression_route"], "listed_option_contract")
                self.assertEqual(rows[0]["replay_time_pointer"], "2021-01-04T16:00:00-05:00")
                self.assertEqual(rows[0]["point_in_time_policy"], "replay_time_pointer_excludes_future_decision_inputs")
                self.assertEqual(rows[0]["asset_class"], "us_option")
                self.assertEqual(rows[0]["decision_expression_type"], "long_put")
                self.assertEqual(rows[0]["decision_intended_side"], "long")
                self.assertEqual(rows[0]["decision_intended_action"], "open_long")
                self.assertEqual(rows[0]["decision_instrument_scope"], "listed_option_contract")
                self.assertEqual(rows[0]["selected_option_contract_ref"], "AAPL_2021-01-15_P_100")
                self.assertEqual(rows[0]["selected_option_right"], "none")
                self.assertEqual(rows[0]["option_direction_consistency_status"], "mismatch")
                self.assertAlmostEqual(rows[0]["underlying_return"], (rows[0]["next_bar_close"] - rows[0]["bar_close"]) / rows[0]["bar_close"])
                self.assertAlmostEqual(rows[0]["directional_underlying_return"], rows[0]["underlying_return"])
                self.assertEqual(rows[0]["option_contract_path_status"], "available")
                self.assertEqual(rows[0]["return_source"], "m05_option_expression_contract_path")
                self.assertEqual(rows[0]["option_entry_price"], 2.0)
                self.assertEqual(rows[0]["option_exit_price"], 3.0)
                self.assertEqual(rows[0]["planned_order_quantity"], 24.0)
                self.assertEqual(rows[0]["planned_unit_cost_usd"], 215.0)
                self.assertEqual(rows[0]["planned_position_notional_usd"], 5160.0)
                self.assertEqual(rows[0]["target_allocation_fraction"], 0.20)
                self.assertEqual(rows[0]["target_allocation_fraction_source"], "model_05_handoff.target_allocation_fraction")
                self.assertEqual(rows[0]["total_portfolio_notional_usd"], 25000.0)
                self.assertEqual(
                    rows[0]["position_sizing_policy"],
                    "target_allocation_floor_option_contract_round_up",
                )
                self.assertEqual(result.receipt["option_contract_path_symbol_count"], 1)
                self.assertEqual(result.receipt["option_contract_path_bar_count"], 2)
                self.assertEqual(result.receipt["option_replay_coverage"]["contract_path_coverage_status"], "complete")
                self.assertEqual(result.receipt["option_replay_coverage"]["selected_option_path_available_count"], 1)
        finally:
            replay_module._load_option_candidate_features = original_feature_loader
            replay_module._load_option_candidate_features_for_timestamp = original_point_feature_loader
            replay_module._load_option_contract_path_bars = original_path_loader
            replay_module._option_expression_plan_for_bar = original_plan_builder
            replay_module._candidate_layer_outputs = original_layer_outputs
            replay_module._load_option_contract_path_bars = original_path_loader

    def test_candidate_policy_replay_rejects_selected_option_when_contract_path_missing(self):
        original_feature_loader = replay_module._load_option_candidate_features
        original_point_feature_loader = replay_module._load_option_candidate_features_for_timestamp
        original_path_loader = replay_module._load_option_contract_path_bars
        original_plan_builder = replay_module._option_expression_plan_for_bar
        original_layer_outputs = replay_module._candidate_layer_outputs
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
            replay_module._candidate_layer_outputs = lambda **_: _current_layer_outputs()
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                result = build_candidate_policy_replay_execution_run(
                    dataset_root=self._dataset(root),
                    run_id="test_candidate_policy_missing_option_path",
                    candidate_model_ref="storage://trading-manager/model_group/test_fold",
                    after_cost_alpha_model=_after_cost_alpha_model(),
                    equity_source_root=self._equity_source_root(root),
                    equity_symbols=["AAPL"],
                    include_crypto=False,
                    max_decision_rows=1,
                    option_feature_database_url="postgresql://example/unused",
                )

                rows = [json.loads(line) for line in result.decision_rows_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(rows[0]["selected_option_contract_ref"], "AAPL_2021-01-15_P_100")
                self.assertEqual(rows[0]["option_contract_path_status"], "missing")
                self.assertEqual(rows[0]["return_source"], "option_contract_path_missing")
                self.assertEqual(rows[0]["replay_rejection_reason"], "option_contract_path_missing")
                self.assertEqual(rows[0]["fill_status"], "simulated_rejected")
                self.assertEqual(rows[0]["path_conditioning_policy"], "upstream_selected_path_only")
                self.assertEqual(rows[0]["path_scope"], "selected_target:AAPL")
                self.assertEqual(rows[0]["candidate_set_scope"], "selected_target_selected_option_contract_path")
                self.assertEqual(rows[0]["miss_attribution_layer"], "model_05_option_expression")
                self.assertIsNone(rows[0]["outcome_label"])
                self.assertEqual(rows[0]["realized_return"], 0.0)
                self.assertEqual(rows[0]["cost"], 0.0)
        finally:
            replay_module._load_option_candidate_features = original_feature_loader
            replay_module._load_option_candidate_features_for_timestamp = original_point_feature_loader
            replay_module._load_option_contract_path_bars = original_path_loader
            replay_module._option_expression_plan_for_bar = original_plan_builder
            replay_module._candidate_layer_outputs = original_layer_outputs

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
        _AFTER_COST_ALPHA_MODEL = {
            "contract_type": "current_replay_entry_utility_model_bundle",
            "score_policy": "derive_from_current_m02_m03_state",
        }
        return copy.deepcopy(_AFTER_COST_ALPHA_MODEL)


def _current_layer_outputs(
    *,
    action_type: str = "open_long",
    action_side: str = "long",
    direction: str = "bullish",
    entry_style: str = "limit_near_mid",
    alpha_score: float = 0.82,
    trade_intensity: float = 0.12,
    action_confidence: float = 0.82,
    action_direction: float = 0.18,
    expected_return: float = 0.04,
    target_allocation_fraction: float = 0.20,
    unified_decision_overrides: dict[str, object] | None = None,
    direct_intent_overrides: dict[str, object] | None = None,
    handoff_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    alpha_gate_status = "passed" if alpha_score >= 0.50 else "below_entry_threshold"
    unified_decision_vector = {
        "model_ref": "unified-decision-ref",
        "unified_decision_vector_ref": "udv_test",
        "unified_decision_confidence_score": alpha_score,
        "minimum_entry_confidence": 0.50,
        "4_resolved_target_allocation_fraction": target_allocation_fraction,
    }
    unified_decision_vector.update(unified_decision_overrides or {})
    handoff_to_model_05 = {
        "underlying_path_direction": direction,
        "target_allocation_fraction": target_allocation_fraction,
        "expected_holding_time_minutes": 1440,
        "expected_entry_price": 100.0,
        "expected_target_price": 110.0,
        "target_price_high": 110.0,
        "expected_favorable_move_pct": 0.06,
        "expected_adverse_move_pct": 0.02,
        "path_quality_score": 0.80,
        "entry_price_assumption": entry_style,
    }
    handoff_to_model_05.update(handoff_overrides or {})
    direct_underlying_intent = {
        "model_ref": "unified-decision-ref",
        "underlying_action_type": action_type,
        "action_side": action_side,
        "target_allocation_fraction": target_allocation_fraction,
        "trade_intensity_score": trade_intensity,
        "entry_style": entry_style,
        "handoff_to_model_05": handoff_to_model_05,
    }
    direct_underlying_intent.update(direct_intent_overrides or {})
    return {
        "target_candidate_id": "replay_aapl_test",
        "target_context_state": {"model_ref": "target-context-ref"},
        "market_context_state": {"1_market_liquidity_support_score": 0.85},
        "event_state_vector": {"model_ref": "event-state-ref"},
        "prediction_score": alpha_score,
        "model_layer_refs": {
            "model_01_background_context": "background-ref",
            "model_02_target_state": "target-ref",
            "model_03_event_state": "event-ref",
            "model_04_unified_decision": "unified-ref",
        },
        "unified_decision_vector": unified_decision_vector,
        "direct_underlying_intent": direct_underlying_intent,
        "model_layer_diagnostics": {
            "entry_thresholds": {
                "minimum_entry_alpha_confidence": 0.50,
                "minimum_trade_intensity": 0.05,
            },
            "entry_utility": {
                "resolved_utility_score": alpha_score,
                "utility_gate_status": alpha_gate_status,
            },
            "model_04_unified_decision": {
                "resolved_underlying_action_type": action_type,
                "resolved_action_side": action_side,
                "dominant_horizon_scores": {
                    "trade_intensity_score": trade_intensity,
                    "action_confidence_score": action_confidence,
                    "action_direction_score": action_direction,
                    "expected_return_score": expected_return,
                    "minimum_trade_intensity": 0.05,
                },
            },
        },
    }


def _decision_rows_for_option_requirement_policy(*, allow_option_feature_requirements: bool) -> list[dict[str, object]]:
    original_layer_outputs = replay_module._candidate_layer_outputs
    original_runtime = replay_module.build_replay_runtime_dry_run
    try:
        replay_module._candidate_layer_outputs = lambda **_: _current_layer_outputs()
        replay_module.build_replay_runtime_dry_run = lambda **_: {
            "decision_records": {
                "entry_decision": {
                    "entry_decision_id": "entry-test",
                    "instrument_ref": "AAPL",
                    "asset_class": "us_equity",
                    "decision_status": "suitable",
                    "decision_action": "continue_to_expression_review",
                },
                "execution_order_intent": {"execution_order_intent_id": "intent-test"},
                "simulated_fill_event": {"simulated_fill_event_id": "fill-test", "fill_status": "simulated_rejected"},
            },
            "validation_status": "passed",
            "side_effects": {},
        }
        return replay_module._build_candidate_policy_decision_rows(
            bars_by_target={
                "AAPL": [
                    {
                        "symbol": "AAPL",
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-04T16:00:00-05:00",
                        "date": "2021-01-04",
                        "bar_close": 100.0,
                        "bar_volume": 1000.0,
                    },
                    {
                        "symbol": "AAPL",
                        "asset_class": "us_equity",
                        "source_id": "alpaca_bars",
                        "timestamp": "2021-01-05T16:00:00-05:00",
                        "date": "2021-01-05",
                        "bar_close": 101.0,
                        "bar_volume": 1000.0,
                    },
                ]
            },
            market_dates=["2021-01-04", "2021-01-05"],
            run_id="test-option-requirement-policy",
            candidate_model_ref="storage://trading-manager/model_group/test_fold",
            after_cost_alpha_model=_after_cost_alpha_model(),
            replay_contract_ref="test-contract",
            max_decision_rows=None,
            entry_calibration=replay_module.EntryCalibration(
                artifact={
                    "calibration_status": "selected_positive_validation_threshold",
                    "selected_thresholds": {
                        "minimum_entry_alpha_confidence": 0.5,
                        "minimum_trade_intensity": 0.05,
                    },
                    "validation_months": [],
                },
                path=Path("/tmp/test-entry-calibration.json"),
            ),
            option_candidates_by_underlying_time={},
            option_contract_paths_by_symbol={},
            option_feature_requirements_path=None,
            allow_option_feature_requirements=allow_option_feature_requirements,
        )
    finally:
        replay_module._candidate_layer_outputs = original_layer_outputs
        replay_module.build_replay_runtime_dry_run = original_runtime


if __name__ == "__main__":
    unittest.main()
