# Model Activation

Model activation is evaluation-owned.

`trading-evaluation` may publish `model_activation_record` and `active_model_config` after a candidate has passed frozen benchmark settlement and promotion eligibility checks. This keeps the manager as a scheduler instead of a model-quality judge.

## Required Inputs

- accepted `promotion_eligibility_decision` with `decision_status = eligible`;
- accepted benchmark contract reference;
- fold settlement run and metric references;
- activated model/config refs;
- active model config destination ref;
- rollback ref;
- activation scope.

Agent review can support activation readiness only through the fixed `promotion-evaluation-review` skill and only as advisory evidence. It cannot directly switch active config pointers.

## Forbidden Side Effects

Activation records must not place orders, call brokers, mutate accounts, call providers, or perform storage lifecycle mutation.

Execution and realtime services consume the active config after it exists; they do not decide activation.
