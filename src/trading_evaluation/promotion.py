"""Evaluation-owned promotion eligibility and readiness records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Literal, Mapping

ELIGIBLE_STATUS = "eligible"
PROMOTION_ELIGIBILITY_DECISION_CONTRACT = "promotion_eligibility_decision"
PROMOTION_READINESS_RECORD_CONTRACT = "promotion_readiness_record"
ALLOWED_ELIGIBILITY_STATUSES = {"eligible", "rejected", "review_required", "revoked", "superseded"}
ELIGIBLE_REPLAY_FREEZE_STATUS = "frozen"
ELIGIBLE_FOLD_STACK_STATUS = "complete_m01_m06"
ELIGIBLE_GUARDRAIL_STATUS = "passed"
ELIGIBLE_INCUMBENT_COMPARISON_STATUS = "passed"
ELIGIBLE_AGENT_REVIEW_RECOMMENDATION = "eligible_for_shadow"
MODEL_INPUT_CONTEXT_LAYERS = (
    "model_02_target_state",
    "model_03_event_state",
    "model_04_unified_decision",
    "model_05_option_expression",
    "model_06_residual_event_governance",
)


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _list(values: Iterable[str] | None) -> list[str]:
    return [str(value) for value in values or []]


def _model_input_context_bundle(
    *,
    promotion_readiness_record_id: str,
    promotion_eligibility_decision: Mapping[str, Any],
    candidate_config_ref: str,
    historical_dataset_snapshot_ref: str | None = None,
) -> dict[str, Any]:
    """Build the canonical context-ref bundle handed to realtime/shadow input builders."""

    fold_stack_ref = str(promotion_eligibility_decision.get("fold_stack_evidence_ref") or "").strip()
    replay_contract_ref = str(promotion_eligibility_decision.get("replay_contract_ref") or "").strip()
    dataset_ref = str(historical_dataset_snapshot_ref or "").strip()
    if not dataset_ref:
        dataset_ref = f"{replay_contract_ref}#historical_dataset_snapshot"
    return {
        "contract_type": "model_input_context_bundle",
        "context_bundle_id": _stable_id("modelctx", promotion_readiness_record_id, fold_stack_ref, candidate_config_ref),
        "promotion_readiness_record_ref": promotion_readiness_record_id,
        "historical_dataset_snapshot_ref": dataset_ref,
        "frozen_model_config_ref": candidate_config_ref,
        "upstream_context_refs": {
            layer: f"{fold_stack_ref}#{layer}_context"
            for layer in MODEL_INPUT_CONTEXT_LAYERS
        },
        "context_source_refs": {
            "fold_stack_evidence_ref": fold_stack_ref,
            "replay_contract_ref": replay_contract_ref,
            "replay_validation_ref": str(promotion_eligibility_decision.get("replay_validation_ref") or ""),
            "settlement_run_ref": str(promotion_eligibility_decision.get("settlement_run_ref") or ""),
        },
        "context_status": "ready_for_realtime_shadow_snapshot",
    }


@dataclass(frozen=True)
class ActivationValidation:
    """Validation result for an evaluation promotion artifact."""

    contract_type: str
    validation_status: str
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_type": self.contract_type,
            "validation_status": self.validation_status,
            "errors": list(self.errors),
        }


def build_promotion_eligibility_decision(
    *,
    fold_id: str,
    candidate_model_ref: str,
    replay_contract_ref: str,
    settlement_run_ref: str,
    decision_status: Literal["eligible", "rejected", "review_required", "revoked", "superseded"],
    decision_reason: str,
    metric_refs: Iterable[str] | None = None,
    guardrail_refs: Iterable[str] | None = None,
    replay_validation_ref: str | None = None,
    replay_freeze_status: str | None = None,
    fold_stack_evidence_ref: str | None = None,
    fold_stack_status: str | None = None,
    guardrail_status: str | None = None,
    incumbent_comparison_ref: str | None = None,
    incumbent_comparison_status: str | None = None,
    agent_review_ref: str | None = None,
    agent_review_recommendation: str | None = None,
    first_model_bootstrap: bool = False,
    bootstrap_baseline_ref: str | None = None,
    decision_id: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build an evaluation-owned promotion eligibility decision."""

    metric_ref_list = _list(metric_refs)
    guardrail_ref_list = _list(guardrail_refs)
    payload = {
        "contract_type": PROMOTION_ELIGIBILITY_DECISION_CONTRACT,
        "promotion_eligibility_decision_id": decision_id
        or _stable_id("promelig", fold_id, candidate_model_ref, replay_contract_ref, settlement_run_ref, decision_status),
        "fold_id": fold_id,
        "candidate_model_ref": candidate_model_ref,
        "replay_contract_ref": replay_contract_ref,
        "settlement_run_ref": settlement_run_ref,
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "metric_refs": metric_ref_list,
        "guardrail_refs": guardrail_ref_list,
        "replay_validation_ref": replay_validation_ref or "",
        "replay_freeze_status": replay_freeze_status or "",
        "fold_stack_evidence_ref": fold_stack_evidence_ref or "",
        "fold_stack_status": fold_stack_status or "",
        "guardrail_status": guardrail_status or "",
        "incumbent_comparison_ref": incumbent_comparison_ref or "",
        "incumbent_comparison_status": incumbent_comparison_status or "",
        "agent_review_ref": agent_review_ref or "",
        "agent_review_recommendation": agent_review_recommendation or "",
        "first_model_bootstrap": bool(first_model_bootstrap),
        "bootstrap_baseline_ref": bootstrap_baseline_ref or "",
        "created_at_utc": created_at_utc or _now_utc(),
    }
    validation = validate_promotion_eligibility_decision(payload)
    if validation.validation_status != "passed":
        raise ValueError("; ".join(validation.errors))
    return payload


def validate_promotion_eligibility_decision(payload: Mapping[str, Any]) -> ActivationValidation:
    errors: list[str] = []
    required = (
        "contract_type",
        "promotion_eligibility_decision_id",
        "fold_id",
        "candidate_model_ref",
        "replay_contract_ref",
        "settlement_run_ref",
        "decision_status",
        "decision_reason",
        "created_at_utc",
    )
    for field in required:
        if payload.get(field) in (None, ""):
            errors.append(f"{field} is required")
    if payload.get("contract_type") != PROMOTION_ELIGIBILITY_DECISION_CONTRACT:
        errors.append(f"contract_type must be {PROMOTION_ELIGIBILITY_DECISION_CONTRACT}")
    if payload.get("decision_status") not in ALLOWED_ELIGIBILITY_STATUSES:
        errors.append("decision_status is not accepted")
    for field in ("metric_refs", "guardrail_refs"):
        if field in payload and not isinstance(payload[field], list):
            errors.append(f"{field} must be a list")
    if payload.get("decision_status") == ELIGIBLE_STATUS:
        _validate_eligible_evidence(payload, errors)
    return ActivationValidation(
        contract_type="promotion_eligibility_decision_validation",
        validation_status="passed" if not errors else "failed",
        errors=tuple(errors),
    )


def _validate_eligible_evidence(payload: Mapping[str, Any], errors: list[str]) -> None:
    required_refs = (
        "replay_validation_ref",
        "fold_stack_evidence_ref",
        "incumbent_comparison_ref",
        "agent_review_ref",
    )
    for field in required_refs:
        if payload.get(field) in (None, ""):
            errors.append(f"{field} is required when decision_status is eligible")
    if not payload.get("metric_refs"):
        errors.append("metric_refs is required when decision_status is eligible")
    if not payload.get("guardrail_refs"):
        errors.append("guardrail_refs is required when decision_status is eligible")
    expected_statuses = {
        "replay_freeze_status": ELIGIBLE_REPLAY_FREEZE_STATUS,
        "fold_stack_status": ELIGIBLE_FOLD_STACK_STATUS,
        "guardrail_status": ELIGIBLE_GUARDRAIL_STATUS,
        "incumbent_comparison_status": ELIGIBLE_INCUMBENT_COMPARISON_STATUS,
        "agent_review_recommendation": ELIGIBLE_AGENT_REVIEW_RECOMMENDATION,
    }
    for field, expected in expected_statuses.items():
        if payload.get(field) != expected:
            errors.append(f"{field} must be {expected} when decision_status is eligible")


def build_promotion_readiness_record(
    *,
    promotion_eligibility_decision: Mapping[str, Any],
    candidate_model_ref: str,
    candidate_config_ref: str,
    rollback_ref: str,
    execution_shadow_scope: str = "paper_or_live_shadow",
    historical_dataset_snapshot_ref: str | None = None,
    readiness_record_id: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a record admitting an eligible candidate to execution shadow review."""

    validation = validate_promotion_eligibility_decision(promotion_eligibility_decision)
    if validation.validation_status != "passed":
        raise ValueError("; ".join(validation.errors))
    if promotion_eligibility_decision["decision_status"] != ELIGIBLE_STATUS:
        raise ValueError("promotion readiness requires an eligible promotion_eligibility_decision")
    for field, value in {
        "candidate_model_ref": candidate_model_ref,
        "candidate_config_ref": candidate_config_ref,
        "rollback_ref": rollback_ref,
        "execution_shadow_scope": execution_shadow_scope,
    }.items():
        if not value:
            raise ValueError(f"{field} is required")
    decision_ref = str(promotion_eligibility_decision["promotion_eligibility_decision_id"])
    record_id = readiness_record_id or _stable_id("promready", decision_ref, candidate_model_ref, candidate_config_ref, rollback_ref)
    model_input_context_bundle = _model_input_context_bundle(
        promotion_readiness_record_id=record_id,
        promotion_eligibility_decision=promotion_eligibility_decision,
        candidate_config_ref=candidate_config_ref,
        historical_dataset_snapshot_ref=historical_dataset_snapshot_ref,
    )
    record = {
        "contract_type": PROMOTION_READINESS_RECORD_CONTRACT,
        "promotion_readiness_record_id": record_id,
        "promotion_eligibility_decision_ref": decision_ref,
        "candidate_model_ref": candidate_model_ref,
        "candidate_config_ref": candidate_config_ref,
        "historical_dataset_snapshot_ref": model_input_context_bundle["historical_dataset_snapshot_ref"],
        "frozen_model_config_ref": model_input_context_bundle["frozen_model_config_ref"],
        "model_input_context_bundle": model_input_context_bundle,
        "rollback_ref": rollback_ref,
        "execution_shadow_scope": execution_shadow_scope,
        "replay_contract_ref": promotion_eligibility_decision["replay_contract_ref"],
        "replay_validation_ref": promotion_eligibility_decision["replay_validation_ref"],
        "replay_freeze_status": promotion_eligibility_decision["replay_freeze_status"],
        "settlement_run_ref": promotion_eligibility_decision["settlement_run_ref"],
        "metric_refs": list(promotion_eligibility_decision["metric_refs"]),
        "fold_stack_evidence_ref": promotion_eligibility_decision["fold_stack_evidence_ref"],
        "fold_stack_status": promotion_eligibility_decision["fold_stack_status"],
        "guardrail_refs": list(promotion_eligibility_decision["guardrail_refs"]),
        "guardrail_status": promotion_eligibility_decision["guardrail_status"],
        "incumbent_comparison_ref": promotion_eligibility_decision["incumbent_comparison_ref"],
        "incumbent_comparison_status": promotion_eligibility_decision["incumbent_comparison_status"],
        "agent_review_ref": promotion_eligibility_decision["agent_review_ref"],
        "agent_review_recommendation": promotion_eligibility_decision["agent_review_recommendation"],
        "first_model_bootstrap": bool(promotion_eligibility_decision.get("first_model_bootstrap", False)),
        "bootstrap_baseline_ref": str(promotion_eligibility_decision.get("bootstrap_baseline_ref") or ""),
        "created_at_utc": created_at_utc or _now_utc(),
        "model_activation_performed": False,
        "active_model_config_written": False,
        "broker_execution_performed": False,
        "account_mutation_performed": False,
    }
    readiness_validation = validate_promotion_readiness_record(record)
    if readiness_validation.validation_status != "passed":
        raise ValueError("; ".join(readiness_validation.errors))
    return record


def validate_promotion_readiness_record(payload: Mapping[str, Any]) -> ActivationValidation:
    errors: list[str] = []
    required = (
        "contract_type",
        "promotion_readiness_record_id",
        "promotion_eligibility_decision_ref",
        "candidate_model_ref",
        "candidate_config_ref",
        "rollback_ref",
        "execution_shadow_scope",
        "replay_contract_ref",
        "replay_validation_ref",
        "replay_freeze_status",
        "historical_dataset_snapshot_ref",
        "frozen_model_config_ref",
        "model_input_context_bundle",
        "settlement_run_ref",
        "fold_stack_evidence_ref",
        "fold_stack_status",
        "guardrail_status",
        "incumbent_comparison_ref",
        "incumbent_comparison_status",
        "agent_review_ref",
        "agent_review_recommendation",
        "created_at_utc",
    )
    for field in required:
        if payload.get(field) in (None, ""):
            errors.append(f"{field} is required")
    if payload.get("contract_type") != PROMOTION_READINESS_RECORD_CONTRACT:
        errors.append(f"contract_type must be {PROMOTION_READINESS_RECORD_CONTRACT}")
    for field in ("metric_refs", "guardrail_refs"):
        if not isinstance(payload.get(field), list) or not payload.get(field):
            errors.append(f"{field} must be a non-empty list")
    _validate_model_input_context_bundle(payload, errors)
    _validate_eligible_evidence(payload, errors)
    for field in (
        "model_activation_performed",
        "active_model_config_written",
        "broker_execution_performed",
        "account_mutation_performed",
    ):
        if payload.get(field) is not False:
            errors.append(f"{field} must be false")
    return ActivationValidation(
        contract_type="promotion_readiness_record_validation",
        validation_status="passed" if not errors else "failed",
        errors=tuple(errors),
    )


def _validate_model_input_context_bundle(payload: Mapping[str, Any], errors: list[str]) -> None:
    bundle = payload.get("model_input_context_bundle")
    if not isinstance(bundle, Mapping):
        errors.append("model_input_context_bundle must be an object")
        return
    if bundle.get("contract_type") != "model_input_context_bundle":
        errors.append("model_input_context_bundle.contract_type must be model_input_context_bundle")
    if bundle.get("promotion_readiness_record_ref") != payload.get("promotion_readiness_record_id"):
        errors.append("model_input_context_bundle.promotion_readiness_record_ref must match promotion_readiness_record_id")
    for field in ("context_bundle_id", "historical_dataset_snapshot_ref", "frozen_model_config_ref", "context_status"):
        if not bundle.get(field):
            errors.append(f"model_input_context_bundle.{field} is required")
    if bundle.get("historical_dataset_snapshot_ref") != payload.get("historical_dataset_snapshot_ref"):
        errors.append("model_input_context_bundle.historical_dataset_snapshot_ref must match readiness record")
    if bundle.get("frozen_model_config_ref") != payload.get("frozen_model_config_ref"):
        errors.append("model_input_context_bundle.frozen_model_config_ref must match readiness record")
    upstream_refs = bundle.get("upstream_context_refs")
    if not isinstance(upstream_refs, Mapping):
        errors.append("model_input_context_bundle.upstream_context_refs must be an object")
        return
    for layer in MODEL_INPUT_CONTEXT_LAYERS:
        value = str(upstream_refs.get(layer) or "")
        if not value:
            errors.append(f"model_input_context_bundle.upstream_context_refs.{layer} is required")
        if value.startswith("placeholder://"):
            errors.append(f"model_input_context_bundle.upstream_context_refs.{layer} must not be placeholder")
