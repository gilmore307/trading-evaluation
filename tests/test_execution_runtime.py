import sys
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path("/root/projects/trading-execution/src")))

from trading_evaluation import build_replay_runtime_dry_run


class EvaluationExecutionRuntimeTests(unittest.TestCase):
    def test_replay_dry_run_calls_execution_runtime_builders(self) -> None:
        result = build_replay_runtime_dry_run(
            account_sleeve_id="crypto_spot_account",
            target_ref="SOL",
            alpha_confidence_vector={"alpha_confidence_score": 0.90},
            underlying_action_plan={"entry_direction": "long", "model_ref": "model_07_underlying_action/unit"},
            trade_risk_cap={
                "max_loss_usd": 25.0,
                "max_loss_pct": 0.02,
                "time_stop_at": "2026-01-05T20:00:00Z",
                "cap_enforcement_mode": "broker_native_stop",
                "cap_failure_action": "reject_order",
                "model_invalidation_price": 120.0,
                "hard_stop_price": 119.0,
                "planned_quantity": 1.5,
                "planned_limit_price": 130.0,
            },
            market_snapshot={"reference_price": 129.0},
            replay_fill_policy={"slippage_bps": 10, "fee_bps": 5},
            generated_at_utc="2026-01-01T00:00:00Z",
        )

        self.assertEqual(result["contract_type"], "evaluation_replay_runtime_dry_run")
        self.assertEqual(result["component_graph_mode"], "replay")
        self.assertEqual(result["validation_status"], "passed")
        records = result["decision_records"]
        self.assertEqual(records["target_allocation_snapshot"]["contract_type"], "target_allocation_snapshot")
        self.assertEqual(records["entry_decision"]["contract_type"], "entry_decision")
        self.assertEqual(records["execution_order_intent"]["contract_type"], "execution_order_intent")
        self.assertEqual(records["execution_gate_result"]["contract_type"], "execution_gate_result")
        self.assertEqual(records["simulated_fill_event"]["contract_type"], "simulated_fill_event")
        self.assertEqual(records["execution_gate_result"]["execution_gate_status"], "rejected_execution_gate")
        self.assertEqual(records["simulated_fill_event"]["fill_status"], "simulated_rejected")
        self.assertFalse(result["side_effects"]["broker_mutation_performed"])
        self.assertFalse(result["side_effects"]["account_mutation_performed"])

    def test_replay_dry_run_cli_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "dry_run.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/evaluation/run_replay_runtime_dry_run.py",
                    "--account-sleeve-id",
                    "crypto_spot_account",
                    "--target-ref",
                    "ETH",
                    "--output-path",
                    str(output_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={"PYTHONPATH": "src"},
                check=True,
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["contract_type"], "evaluation_replay_runtime_dry_run")
            self.assertEqual(payload["target_ref"], "ETH")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["validation_status"], "passed")


if __name__ == "__main__":
    unittest.main()
