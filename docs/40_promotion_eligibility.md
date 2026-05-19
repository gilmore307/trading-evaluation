# Promotion Eligibility

Promotion eligibility is the evaluation-owned decision that a candidate has enough settlement evidence to proceed to evaluation-owned activation.

## Rules

- Eligibility must be based on frozen benchmark evidence.
- Eligibility must compare against accepted baselines and prior promoted candidates.
- Guardrails may block eligibility when the primary benchmark score is strong but risk, calibration, turnover, or overfit indicators fail.
- Eligibility is the required predecessor for `model_activation_record` and has no execution side effects.
