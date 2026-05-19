# Promotion Eligibility

Promotion eligibility is the evaluation-owned decision that a candidate has enough settlement evidence to proceed to evaluation-owned activation.

## Rules

- Eligibility must be based on frozen benchmark evidence.
- Eligibility must compare against accepted baselines and prior promoted candidates.
- Any reviewer-agent pass must use the fixed workspace skill `skills/openclaw/promotion-evaluation-review`.
- Reviewer-agent output is advisory evidence; deterministic evaluation code owns the final eligibility and activation records.
- Guardrails may block eligibility when the primary benchmark score is strong but risk, calibration, turnover, or overfit indicators fail.
- Eligibility is the required predecessor for `model_activation_record` and has no execution side effects.

## Reviewer Recommendation States

- `failed`: benchmark integrity or hard guardrails failed.
- `deferred`: evidence is valid but the candidate is not materially better than the incumbent.
- `eligible_for_shadow`: benchmark evidence is promising but still needs forward shadow evidence.
- `eligible_for_activation`: benchmark integrity, risk guardrails, incumbent comparison, uncertainty checks, and rollback/config evidence all pass.
