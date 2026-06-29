import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import (
    build_promotion_eligibility_decision,
    build_promotion_readiness_record,
    validate_promotion_readiness_record,
)


class PromotionTests(unittest.TestCase):
    def test_builds_readiness_from_eligible_decision(self):
        decision = build_promotion_eligibility_decision(
            fold_id="fold_2016-01_2017-06",
            candidate_model_ref="storage://models/candidate",
            replay_contract_ref="replay://primary",
            settlement_run_ref="storage://settlement/run",
            decision_status="eligible",
            decision_reason="passed frozen replay",
            metric_refs=["storage://metrics/fold"],
            guardrail_refs=["replay://guardrail/risk"],
            replay_validation_ref="storage://replay/validation/passed",
            replay_freeze_status="frozen",
            fold_stack_evidence_ref="storage://fold/complete_m01_m06",
            fold_stack_status="complete_m01_m06",
            guardrail_status="passed",
            incumbent_comparison_ref="storage://comparison/incumbent",
            incumbent_comparison_status="passed",
            agent_review_ref="agent-review://promotion-evaluation-review/passed",
            agent_review_recommendation="eligible_for_shadow",
            first_model_bootstrap=True,
            bootstrap_baseline_ref="storage://settlement/run",
        )

        record = build_promotion_readiness_record(
            promotion_eligibility_decision=decision,
            candidate_model_ref="storage://models/market_regime/new",
            candidate_config_ref="storage://configs/market_regime/new",
            rollback_ref="storage://models/market_regime/old",
        )

        self.assertEqual(record["contract_type"], "promotion_readiness_record")
        self.assertFalse(record["model_activation_performed"])
        self.assertFalse(record["active_model_config_written"])
        self.assertFalse(record["broker_execution_performed"])
        self.assertFalse(record["account_mutation_performed"])
        self.assertEqual(record["replay_freeze_status"], "frozen")
        self.assertEqual(record["fold_stack_status"], "complete_m01_m06")
        self.assertEqual(record["agent_review_recommendation"], "eligible_for_shadow")
        self.assertTrue(record["first_model_bootstrap"])
        self.assertEqual(record["bootstrap_baseline_ref"], "storage://settlement/run")
        self.assertEqual(record["frozen_model_config_ref"], "storage://configs/market_regime/new")
        self.assertEqual(record["historical_dataset_snapshot_ref"], "replay://primary#historical_dataset_snapshot")
        bundle = record["model_input_context_bundle"]
        self.assertEqual(bundle["contract_type"], "model_input_context_bundle")
        self.assertEqual(bundle["frozen_model_config_ref"], record["frozen_model_config_ref"])
        self.assertEqual(bundle["historical_dataset_snapshot_ref"], record["historical_dataset_snapshot_ref"])
        self.assertEqual(
            sorted(bundle["upstream_context_refs"]),
            [
                "model_02_target_state",
                "model_03_event_state",
                "model_04_unified_decision",
                "model_05_option_expression",
                "model_06_residual_event_governance",
            ],
        )
        self.assertEqual(validate_promotion_readiness_record(record).validation_status, "passed")

    def test_rejects_eligible_decision_without_gate_evidence(self):
        with self.assertRaisesRegex(ValueError, "replay_validation_ref is required"):
            build_promotion_eligibility_decision(
                fold_id="fold_2016-01_2017-06",
                candidate_model_ref="storage://models/candidate",
                replay_contract_ref="replay://primary",
                settlement_run_ref="storage://settlement/run",
                decision_status="eligible",
                decision_reason="missing gate evidence",
            )

    def test_rejects_readiness_from_non_eligible_decision(self):
        decision = build_promotion_eligibility_decision(
            fold_id="fold_2016-01_2017-06",
            candidate_model_ref="storage://models/candidate",
            replay_contract_ref="replay://primary",
            settlement_run_ref="storage://settlement/run",
            decision_status="review_required",
            decision_reason="guardrail needs review",
        )

        with self.assertRaisesRegex(ValueError, "requires an eligible"):
            build_promotion_readiness_record(
                promotion_eligibility_decision=decision,
                candidate_model_ref="storage://models/market_regime/new",
                candidate_config_ref="storage://configs/market_regime/new",
                rollback_ref="storage://models/market_regime/old",
            )

    def test_cli_builds_promotion_readiness_record(self):
        with tempfile.TemporaryDirectory() as directory:
            decision_path = Path(directory) / "eligibility.json"
            decision_path.write_text(Path("tests/fixtures/promotion_eligibility_eligible.json").read_text(encoding="utf-8"), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/build_promotion_readiness_record.py",
                    "--promotion-eligibility-json",
                    str(decision_path),
                    "--candidate-model-ref",
                    "storage://models/market_regime/new",
                    "--candidate-config-ref",
                    "storage://configs/market_regime/new",
                    "--historical-dataset-snapshot-ref",
                    "storage://snapshots/historical/unit",
                    "--rollback-ref",
                    "storage://models/market_regime/old",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["contract_type"], "promotion_readiness_record")
        self.assertEqual(payload["promotion_eligibility_decision_ref"], "promelig_fixture")
        self.assertEqual(payload["historical_dataset_snapshot_ref"], "storage://snapshots/historical/unit")


if __name__ == "__main__":
    unittest.main()
