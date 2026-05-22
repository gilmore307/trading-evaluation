"""Promotion evaluation review artifact assembly.

This module turns deterministic settlement evidence into the advisory review
and promotion eligibility decision consumed by model-group promotion tasks. It
does not activate models, write active config pointers, call providers, call
brokers, or mutate accounts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from .promotion import build_promotion_eligibility_decision

PROMOTION_EVALUATION_REVIEW_CONTRACT = "promotion_evaluation_review"


@dataclass(frozen=True)
class PromotionEvaluationReviewResult:
    """Paths and payloads emitted by a promotion evaluation review run."""

    review_path: Path
    eligibility_decision_path: Path
    review: dict[str, Any]
    eligibility_decision: dict[str, Any]


def build_promotion_evaluation_review(
    *,
    settlement_run: Mapping[str, Any],
    settlement_run_ref: str,
    benchmark_contract_ref: str,
    candidate_label: str = "model_a",
    comparison_label: str = "model_b",
    comparison_result_ref: str | None = None,
    candidate_config_ref: str | None = None,
    first_run_evidence_ref: str | None = None,
    first_model_bootstrap: bool = False,
    review_ref: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the advisory promotion-evaluation-review payload."""

    created_at = created_at_utc or _now_utc()
    fold_id = str(settlement_run.get("fold_id") or "")
    metrics = settlement_run.get("metrics") if isinstance(settlement_run.get("metrics"), Mapping) else {}
    gate_failures = [str(item) for item in settlement_run.get("gate_failures") or []]
    blocking_issues: list[str] = []
    required_followups: list[str] = []

    if first_model_bootstrap:
        required_followups.append("use this bootstrap baseline as the anonymous incumbent comparison for later candidates")
    if not comparison_result_ref and not first_model_bootstrap:
        blocking_issues.append("missing anonymous comparison model result on the same benchmark contract")
        required_followups.append("provide blinded model_a/model_b comparison evidence on the frozen replay contract")
    if not candidate_config_ref and not first_model_bootstrap:
        blocking_issues.append("missing candidate config evidence for shadow-readiness judgment")
        required_followups.append("attach candidate config and rollback refs before shadow-readiness review")
    if not first_run_evidence_ref and not first_model_bootstrap:
        blocking_issues.append("missing first-run or benchmark query-count evidence")
        required_followups.append("attach first-run/query-count evidence for this candidate lineage")
    if gate_failures and not first_model_bootstrap:
        blocking_issues.append("settlement gate failures: " + ", ".join(gate_failures))

    recommendation = "insufficient_evidence" if blocking_issues else "eligible_for_shadow"
    hard_guardrail_status = "passed" if first_model_bootstrap else ("failed" if gate_failures else "passed")
    comparison_status = "not_applicable" if first_model_bootstrap else ("insufficient_evidence" if not comparison_result_ref else "mixed")
    shadow_status = "ready" if first_model_bootstrap else ("insufficient_evidence" if not candidate_config_ref else "ready")
    uncertainty_status = "acceptable" if first_model_bootstrap else ("insufficient_evidence" if not comparison_result_ref else "acceptable")
    integrity_status = "passed" if benchmark_contract_ref and settlement_run_ref else "insufficient_evidence"

    material_regressions = []
    if "auroc_below_minimum" in gate_failures:
        material_regressions.append(f"AUROC {metrics.get('auroc')} is below the accepted settlement minimum")
    if metrics.get("max_drawdown") is not None:
        material_regressions.append(f"max drawdown observed at {metrics.get('max_drawdown')}")

    material_improvements = []
    if _number(metrics.get("excess_return_total")) > 0:
        material_improvements.append(f"positive excess return total {metrics.get('excess_return_total')}")
    if _number(metrics.get("decision_row_count")) >= 20:
        material_improvements.append(f"settlement row count {metrics.get('decision_row_count')} is above minimum")

    return {
        "contract_type": PROMOTION_EVALUATION_REVIEW_CONTRACT,
        "review_type": "promotion_evaluation_review",
        "review_ref": review_ref or f"promotion-review://{fold_id or 'unknown'}",
        "candidate_label": candidate_label,
        "fold_id": fold_id,
        "benchmark_contract_ref": benchmark_contract_ref,
        "comparison_label": comparison_label,
        "recommendation": recommendation,
        "confidence": "medium" if first_model_bootstrap or gate_failures else "low",
        "identity_blinding_status": "not_applicable" if first_model_bootstrap else ("insufficient_evidence" if not comparison_result_ref else "passed"),
        "integrity_status": integrity_status,
        "hard_guardrail_status": hard_guardrail_status,
        "comparison_status": comparison_status,
        "uncertainty_status": uncertainty_status,
        "shadow_readiness_status": shadow_status,
        "settlement_run_ref": settlement_run_ref,
        "first_model_bootstrap": first_model_bootstrap,
        "bootstrap_baseline_ref": settlement_run_ref if first_model_bootstrap else "",
        "candidate_model_ref": str(settlement_run.get("candidate_model_ref") or ""),
        "replay_contract_ref": str(settlement_run.get("replay_contract_ref") or ""),
        "metric_refs": list(settlement_run.get("metric_refs") or []),
        "gate_failures": gate_failures,
        "metrics_summary": {
            "decision_row_count": metrics.get("decision_row_count"),
            "net_return_total": metrics.get("net_return_total"),
            "baseline_return_total": metrics.get("baseline_return_total"),
            "excess_return_total": metrics.get("excess_return_total"),
            "max_drawdown": metrics.get("max_drawdown"),
            "hit_rate": metrics.get("hit_rate"),
            "payoff_ratio": metrics.get("payoff_ratio"),
            "turnover_proxy_count": metrics.get("turnover_proxy_count"),
            "auroc": metrics.get("auroc"),
            "brier_score": metrics.get("brier_score"),
        },
        "material_improvements": material_improvements,
        "material_regressions": material_regressions,
        "blocking_issues": blocking_issues,
        "required_followups": required_followups,
        "rationale": _rationale(
            metrics=metrics,
            gate_failures=gate_failures,
            blocking_issues=blocking_issues,
            first_model_bootstrap=first_model_bootstrap,
        ),
        "created_at_utc": created_at,
        "model_activation_performed": False,
        "active_model_config_written": False,
        "broker_execution_performed": False,
        "account_mutation_performed": False,
    }


def build_promotion_review_result(
    *,
    settlement_run: Mapping[str, Any],
    settlement_run_ref: str,
    benchmark_contract_ref: str,
    output_dir: Path,
    candidate_label: str = "model_a",
    comparison_label: str = "model_b",
    comparison_result_ref: str | None = None,
    candidate_config_ref: str | None = None,
    first_run_evidence_ref: str | None = None,
    first_model_bootstrap: bool = False,
    created_at_utc: str | None = None,
) -> PromotionEvaluationReviewResult:
    """Write advisory review and eligibility decision artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = output_dir / "promotion_evaluation_review.json"
    eligibility_path = output_dir / "promotion_eligibility_decision.json"
    review = build_promotion_evaluation_review(
        settlement_run=settlement_run,
        settlement_run_ref=settlement_run_ref,
        benchmark_contract_ref=benchmark_contract_ref,
        candidate_label=candidate_label,
        comparison_label=comparison_label,
        comparison_result_ref=comparison_result_ref,
        candidate_config_ref=candidate_config_ref,
        first_run_evidence_ref=first_run_evidence_ref,
        first_model_bootstrap=first_model_bootstrap,
        review_ref=str(review_path),
        created_at_utc=created_at_utc,
    )
    decision_status = "eligible" if review["recommendation"] == "eligible_for_shadow" else "review_required"
    fold_stack_evidence_ref = str(settlement_run.get("fold_stack_evidence_ref") or "")
    fold_stack_status = str(settlement_run.get("fold_stack_status") or "")
    if first_model_bootstrap:
        fold_stack_evidence_ref = fold_stack_evidence_ref or settlement_run_ref
        fold_stack_status = fold_stack_status or "complete_layer_01_10"
    eligibility = build_promotion_eligibility_decision(
        fold_id=str(settlement_run.get("fold_id") or ""),
        candidate_model_ref=str(settlement_run.get("candidate_model_ref") or ""),
        replay_contract_ref=str(settlement_run.get("replay_contract_ref") or benchmark_contract_ref),
        settlement_run_ref=settlement_run_ref,
        decision_status=decision_status,
        decision_reason=str(review["rationale"]),
        metric_refs=settlement_run.get("metric_refs") or [],
        guardrail_refs=[str(review_path)],
        replay_validation_ref=str(settlement_run.get("replay_result_ref") or ""),
        replay_freeze_status="frozen",
        fold_stack_evidence_ref=fold_stack_evidence_ref,
        fold_stack_status=fold_stack_status,
        guardrail_status="passed" if review["hard_guardrail_status"] == "passed" else "failed",
        incumbent_comparison_ref=comparison_result_ref or (settlement_run_ref if first_model_bootstrap else ""),
        incumbent_comparison_status="passed" if comparison_result_ref or first_model_bootstrap else "",
        agent_review_ref=str(review_path),
        agent_review_recommendation=str(review["recommendation"]),
        created_at_utc=str(review["created_at_utc"]),
    )
    review_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    eligibility_path.write_text(json.dumps(eligibility, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return PromotionEvaluationReviewResult(
        review_path=review_path,
        eligibility_decision_path=eligibility_path,
        review=review,
        eligibility_decision=eligibility,
    )


def _rationale(
    *,
    metrics: Mapping[str, Any],
    gate_failures: list[str],
    blocking_issues: list[str],
    first_model_bootstrap: bool,
) -> str:
    parts = [
        f"settlement rows={metrics.get('decision_row_count')}",
        f"AUROC={metrics.get('auroc')}",
        f"excess_return_total={metrics.get('excess_return_total')}",
        f"max_drawdown={metrics.get('max_drawdown')}",
    ]
    if first_model_bootstrap:
        parts.append("first_model_bootstrap=true")
    if gate_failures:
        parts.append("gate_failures=" + ",".join(gate_failures))
    if blocking_issues:
        parts.append("blocking_issues=" + str(len(blocking_issues)))
    return "; ".join(parts)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "PROMOTION_EVALUATION_REVIEW_CONTRACT",
    "PromotionEvaluationReviewResult",
    "build_promotion_evaluation_review",
    "build_promotion_review_result",
]
