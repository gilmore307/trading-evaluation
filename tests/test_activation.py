import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import (
    build_model_activation_record,
    build_promotion_eligibility_decision,
    validate_model_activation_record,
)


class ActivationTests(unittest.TestCase):
    def test_builds_activation_from_eligible_decision(self):
        decision = build_promotion_eligibility_decision(
            fold_id="fold_2016-01_2016-06",
            candidate_model_ref="storage://models/candidate",
            benchmark_contract_ref="benchmark://primary",
            settlement_run_ref="storage://settlement/run",
            decision_status="eligible",
            decision_reason="passed frozen benchmark",
        )

        record = build_model_activation_record(
            promotion_eligibility_decision=decision,
            activated_model_id="market_regime_model",
            activated_config_ref="storage://models/market_regime/new",
            active_model_config_ref="storage://evaluation/active/market_regime_model",
            rollback_ref="storage://models/market_regime/old",
            activation_scope="shadow",
        )

        self.assertEqual(record["contract_type"], "model_activation_record")
        self.assertFalse(record["broker_execution_performed"])
        self.assertFalse(record["account_mutation_performed"])
        self.assertEqual(validate_model_activation_record(record).validation_status, "passed")

    def test_rejects_activation_from_non_eligible_decision(self):
        decision = build_promotion_eligibility_decision(
            fold_id="fold_2016-01_2016-06",
            candidate_model_ref="storage://models/candidate",
            benchmark_contract_ref="benchmark://primary",
            settlement_run_ref="storage://settlement/run",
            decision_status="review_required",
            decision_reason="guardrail needs review",
        )

        with self.assertRaisesRegex(ValueError, "requires an eligible"):
            build_model_activation_record(
                promotion_eligibility_decision=decision,
                activated_model_id="market_regime_model",
                activated_config_ref="storage://models/market_regime/new",
                active_model_config_ref="storage://evaluation/active/market_regime_model",
                rollback_ref="storage://models/market_regime/old",
                activation_scope="shadow",
            )

    def test_cli_builds_activation_record(self):
        with tempfile.TemporaryDirectory() as directory:
            decision_path = Path(directory) / "eligibility.json"
            decision_path.write_text(Path("tests/fixtures/promotion_eligibility_eligible.json").read_text(encoding="utf-8"), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/build_model_activation_record.py",
                    "--promotion-eligibility-json",
                    str(decision_path),
                    "--activated-model-id",
                    "market_regime_model",
                    "--activated-config-ref",
                    "storage://models/market_regime/new",
                    "--active-model-config-ref",
                    "storage://evaluation/active/market_regime_model",
                    "--rollback-ref",
                    "storage://models/market_regime/old",
                    "--activation-scope",
                    "shadow",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["contract_type"], "model_activation_record")
        self.assertEqual(payload["promotion_eligibility_decision_ref"], "promelig_fixture")


if __name__ == "__main__":
    unittest.main()
