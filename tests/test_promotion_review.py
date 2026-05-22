import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation import build_promotion_review_result


class PromotionEvaluationReviewTests(unittest.TestCase):
    def _settlement_run(self) -> dict:
        return {
            "contract_type": "fold_settlement_run",
            "fold_settlement_run_id": "settlement_fixture",
            "fold_id": "fold_2016-01_2016-06",
            "candidate_model_ref": "trading-model://candidate",
            "replay_contract_ref": "trading-evaluation/replays/promotion_replay_candidate_policy.json",
            "replay_result_ref": "storage://replay/run",
            "decision_status": "review_required",
            "gate_failures": ["auroc_below_minimum"],
            "metric_refs": ["settlement_fixture:metrics"],
            "metrics": {
                "decision_row_count": 100,
                "net_return_total": 1.5,
                "baseline_return_total": 0.0,
                "excess_return_total": 1.5,
                "max_drawdown": -0.25,
                "hit_rate": 0.45,
                "payoff_ratio": 1.2,
                "turnover_proxy_count": 100,
                "auroc": 0.49,
                "brier_score": 0.31,
            },
        }

    def test_builds_review_required_decision_from_incomplete_evidence(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            result = build_promotion_review_result(
                settlement_run=self._settlement_run(),
                settlement_run_ref="storage://settlement/fixture",
                benchmark_contract_ref="trading-evaluation/replays/promotion_replay_candidate_policy.json",
                output_dir=Path(raw_tmp) / "review",
            )

            self.assertEqual(result.review["contract_type"], "promotion_evaluation_review")
            self.assertEqual(result.review["recommendation"], "insufficient_evidence")
            self.assertEqual(result.review["hard_guardrail_status"], "failed")
            self.assertIn("AUROC", result.review["material_regressions"][0])
            self.assertEqual(result.eligibility_decision["contract_type"], "promotion_eligibility_decision")
            self.assertEqual(result.eligibility_decision["decision_status"], "review_required")
            self.assertTrue(result.review_path.exists())
            self.assertTrue(result.eligibility_decision_path.exists())

    def test_cli_writes_review_artifacts(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            settlement_path = tmp / "settlement.json"
            settlement_path.write_text(json.dumps(self._settlement_run()) + "\n", encoding="utf-8")
            output_dir = tmp / "out"
            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/build_promotion_evaluation_review.py",
                    "--settlement-run-json",
                    str(settlement_path),
                    "--settlement-run-ref",
                    "storage://settlement/fixture",
                    "--benchmark-contract-ref",
                    "trading-evaluation/replays/promotion_replay_candidate_policy.json",
                    "--output-dir",
                    str(output_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(completed.stdout)
            self.assertEqual(payload["contract_type"], "promotion_evaluation_review_result")
            self.assertEqual(payload["recommendation"], "insufficient_evidence")
            self.assertTrue((output_dir / "promotion_evaluation_review.json").exists())
            self.assertTrue((output_dir / "promotion_eligibility_decision.json").exists())


if __name__ == "__main__":
    unittest.main()
