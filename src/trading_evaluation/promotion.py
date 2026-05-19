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


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _list(values: Iterable[str] | None) -> list[str]:
    return [str(value) for value in values or []]


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
    benchmark_contract_ref: str,
    settlement_run_ref: str,
    decision_status: Literal["eligible", "rejected", "review_required", "revoked", "superseded"],
    decision_reason: str,
    metric_refs: Iterable[str] | None = None,
    guardrail_refs: Iterable[str] | None = None,
    decision_id: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build an evaluation-owned promotion eligibility decision."""

    metric_ref_list = _list(metric_refs)
    guardrail_ref_list = _list(guardrail_refs)
    payload = {
        "contract_type": PROMOTION_ELIGIBILITY_DECISION_CONTRACT,
        "promotion_eligibility_decision_id": decision_id
        or _stable_id("promelig", fold_id, candidate_model_ref, benchmark_contract_ref, settlement_run_ref, decision_status),
        "fold_id": fold_id,
        "candidate_model_ref": candidate_model_ref,
        "benchmark_contract_ref": benchmark_contract_ref,
        "settlement_run_ref": settlement_run_ref,
        "decision_status": decision_status,
        "decision_reason": decision_reason,
        "metric_refs": metric_ref_list,
        "guardrail_refs": guardrail_ref_list,
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
        "benchmark_contract_ref",
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
    return ActivationValidation(
        contract_type="promotion_eligibility_decision_validation",
        validation_status="passed" if not errors else "failed",
        errors=tuple(errors),
    )


def build_promotion_readiness_record(
    *,
    promotion_eligibility_decision: Mapping[str, Any],
    candidate_model_ref: str,
    candidate_config_ref: str,
    rollback_ref: str,
    execution_shadow_scope: str = "paper_or_live_shadow",
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
    record = {
        "contract_type": PROMOTION_READINESS_RECORD_CONTRACT,
        "promotion_readiness_record_id": readiness_record_id
        or _stable_id("promready", decision_ref, candidate_model_ref, candidate_config_ref, rollback_ref),
        "promotion_eligibility_decision_ref": decision_ref,
        "candidate_model_ref": candidate_model_ref,
        "candidate_config_ref": candidate_config_ref,
        "rollback_ref": rollback_ref,
        "execution_shadow_scope": execution_shadow_scope,
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
        "created_at_utc",
    )
    for field in required:
        if payload.get(field) in (None, ""):
            errors.append(f"{field} is required")
    if payload.get("contract_type") != PROMOTION_READINESS_RECORD_CONTRACT:
        errors.append(f"contract_type must be {PROMOTION_READINESS_RECORD_CONTRACT}")
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
