from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trading_evaluation.settlement import build_fold_settlement_run, validate_fold_settlement_run


class SettlementTests(unittest.TestCase):
    def _rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for index in range(30):
            positive = index % 3 != 0
            rows.append(
                {
                    "decision_id": f"d{index}",
                    "realized_return": 0.03 if positive else -0.01,
                    "baseline_return": 0.005,
                    "cost": 0.001,
                    "outcome_label": 1 if positive else 0,
                    "prediction_score": 0.8 if positive else 0.2,
                    "action": "trade" if positive else "skip",
                    "feature_momentum": index / 30,
                    "feature_volatility": (30 - index) / 30,
                }
            )
        return rows

    def test_builds_settlement_with_auroc_and_structure_metrics(self):
        payload = build_fold_settlement_run(
            fold_id="fold_2016-01_2016-06",
            candidate_model_ref="model://candidate/a",
            benchmark_contract_ref="benchmark://promotion",
            replay_result_ref="storage://replay/result",
            baseline_ref="baseline://incumbent",
            decision_rows=self._rows(),
        )

        self.assertEqual(payload["contract_type"], "fold_settlement_run")
        self.assertEqual(payload["decision_status"], "passed")
        self.assertGreater(payload["metrics"]["auroc"], 0.9)
        self.assertTrue(payload["metrics"]["pca_available"])
        self.assertTrue(payload["metrics"]["pcoa_available"])
        self.assertEqual(validate_fold_settlement_run(payload).validation_status, "passed")
        self.assertFalse(payload["model_activation_performed"])

    def test_small_or_weak_evidence_requires_review(self):
        payload = build_fold_settlement_run(
            fold_id="fold_2016-01_2016-06",
            candidate_model_ref="model://candidate/a",
            benchmark_contract_ref="benchmark://promotion",
            replay_result_ref="storage://replay/result",
            decision_rows=self._rows()[:3],
        )

        self.assertEqual(payload["decision_status"], "review_required")
        self.assertIn("decision_row_count_below_minimum", payload["gate_failures"])

    def test_cli_writes_settlement(self):
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            rows_path = tmp / "rows.json"
            out_path = tmp / "settlement.json"
            rows_path.write_text(json.dumps({"decisions": self._rows()}), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/build_fold_settlement_run.py",
                    "--decision-rows",
                    str(rows_path),
                    "--fold-id",
                    "fold_2016-01_2016-06",
                    "--candidate-model-ref",
                    "model://candidate/a",
                    "--benchmark-contract-ref",
                    "benchmark://promotion",
                    "--replay-result-ref",
                    "storage://replay/result",
                    "--output-path",
                    str(out_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={"PYTHONPATH": "src"},
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn('"contract_type": "fold_settlement_run"', result.stdout)
            self.assertTrue(out_path.exists())


if __name__ == "__main__":
    unittest.main()
