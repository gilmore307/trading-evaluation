"""Replay helpers that call the execution runtime component builders.

`trading-evaluation` owns replay orchestration and judgment. It does not own
trading decisions, so this module imports `trading-execution` at call time and
uses the same component builders live trading will use.
"""

from __future__ import annotations

from typing import Any, Mapping

REPLAY_RUNTIME_DRY_RUN_CONTRACT = "evaluation_replay_runtime_dry_run"
EXECUTION_REPLAY_ROUTE_REF = "trading-execution://execution_runtime_component_graph/replay"


def build_replay_runtime_dry_run(
    *,
    account_sleeve_id: str,
    target_ref: str,
    trade_risk_cap: Mapping[str, Any],
    market_universe: Any = None,
    account_sleeve_state: Mapping[str, Any] | None = None,
    account_sleeve_risk_budget: Mapping[str, Any] | None = None,
    position_state: Any = None,
    target_context_rows: Any = None,
    target_context_state: Mapping[str, Any] | None = None,
    event_failure_risk_vector: Mapping[str, Any] | None = None,
    alpha_confidence_vector: Mapping[str, Any] | None = None,
    dynamic_risk_policy_state: Mapping[str, Any] | None = None,
    underlying_action_plan: Mapping[str, Any] | None = None,
    option_expression_plan: Mapping[str, Any] | None = None,
    execution_policy_snapshot: Mapping[str, Any] | None = None,
    replay_fill_policy: Mapping[str, Any] | None = None,
    market_snapshot: Mapping[str, Any] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Run one side-effect-free Replay decision pass through execution runtime."""

    runtime = _execution_runtime_api()
    graph = runtime["build_runtime_component_graph"](mode="replay")
    allocation = runtime["build_target_allocation_snapshot"](
        account_sleeve_id=account_sleeve_id,
        market_universe=market_universe,
        account_sleeve_state=account_sleeve_state,
        account_sleeve_risk_budget=account_sleeve_risk_budget,
        position_state=position_state,
        target_context_rows=target_context_rows,
        dynamic_risk_policy_state=dynamic_risk_policy_state,
        generated_at_utc=generated_at_utc,
    )
    entry = runtime["build_entry_decision"](
        target_allocation_snapshot=allocation,
        target_ref=target_ref,
        account_sleeve_state=account_sleeve_state,
        account_sleeve_risk_budget=account_sleeve_risk_budget,
        position_state=position_state,
        target_context_state=target_context_state,
        event_failure_risk_vector=event_failure_risk_vector,
        alpha_confidence_vector=alpha_confidence_vector,
        dynamic_risk_policy_state=dynamic_risk_policy_state,
        underlying_action_plan=underlying_action_plan,
        option_expression_plan=option_expression_plan,
        generated_at_utc=generated_at_utc,
    )
    order_intent = runtime["build_execution_order_intent"](
        decision_record=entry,
        trade_risk_cap=trade_risk_cap,
        execution_policy_snapshot=execution_policy_snapshot,
        generated_at_utc=generated_at_utc,
    )
    simulated_fill = runtime["build_simulated_fill_event"](
        execution_order_intent=order_intent,
        replay_fill_policy=replay_fill_policy,
        market_snapshot=market_snapshot,
        generated_at_utc=generated_at_utc,
    )
    validations = [
        runtime["validate_target_allocation_snapshot"](allocation),
        runtime["validate_entry_decision"](entry),
        runtime["validate_execution_order_intent"](order_intent),
        runtime["validate_simulated_fill_event"](simulated_fill),
    ]
    return {
        "contract_type": REPLAY_RUNTIME_DRY_RUN_CONTRACT,
        "replay_route_ref": EXECUTION_REPLAY_ROUTE_REF,
        "component_graph_mode": graph["mode"],
        "component_graph_policy": graph["component_graph_policy"],
        "account_sleeve_id": account_sleeve_id,
        "target_ref": target_ref,
        "decision_records": {
            "target_allocation_snapshot": allocation,
            "entry_decision": entry,
            "execution_order_intent": order_intent,
            "simulated_fill_event": simulated_fill,
        },
        "validation_status": "passed"
        if all(row["validation_status"] == "passed" for row in validations)
        else "failed",
        "validations": validations,
        "side_effects": {
            "provider_calls_performed": 0,
            "broker_calls_performed": 0,
            "broker_mutation_performed": False,
            "account_mutation_performed": False,
            "model_training_performed": False,
            "active_model_config_written": False,
        },
    }


def _execution_runtime_api() -> dict[str, Any]:
    try:
        from trading_execution.runtime import (  # type: ignore[import-not-found]
            build_entry_decision,
            build_execution_order_intent,
            build_runtime_component_graph,
            build_simulated_fill_event,
            build_target_allocation_snapshot,
            validate_entry_decision,
            validate_execution_order_intent,
            validate_simulated_fill_event,
            validate_target_allocation_snapshot,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "trading-execution must be importable to run Replay through the execution runtime; "
            "install trading-execution or include /root/projects/trading-execution/src on PYTHONPATH"
        ) from exc
    return {
        "build_runtime_component_graph": build_runtime_component_graph,
        "build_target_allocation_snapshot": build_target_allocation_snapshot,
        "build_entry_decision": build_entry_decision,
        "build_execution_order_intent": build_execution_order_intent,
        "build_simulated_fill_event": build_simulated_fill_event,
        "validate_target_allocation_snapshot": validate_target_allocation_snapshot,
        "validate_entry_decision": validate_entry_decision,
        "validate_execution_order_intent": validate_execution_order_intent,
        "validate_simulated_fill_event": validate_simulated_fill_event,
    }
