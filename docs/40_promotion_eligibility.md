# Promotion Eligibility

Promotion eligibility is the evaluation-owned decision that a candidate has enough settlement evidence to proceed to execution-owned shadow review.

## Rules

- Eligibility must be based on frozen benchmark evidence.
- Eligibility must be based on a complete fold-stack run: Layer 1 through Layer 10 model evaluation for the same fold must be complete before promotion review starts.
- Eligibility applies to one pinned Layer 1-10 version bundle. The bundle is accepted or rejected as a whole; layer-local results support diagnostics only.
- Eligibility must compare against accepted baselines and prior promoted candidates.
- Any reviewer-agent pass must use the fixed workspace skill `skills/openclaw/promotion-evaluation-review`.
- Reviewer-agent output is advisory evidence; deterministic evaluation code owns the final eligibility and readiness records.
- Guardrails may block eligibility when the primary benchmark score is strong but risk, calibration, turnover, or overfit indicators fail.
- Eligibility is the required predecessor for `promotion_readiness_record` and has no execution side effects.

## Reviewer Recommendation States

- `failed`: benchmark integrity or hard guardrails failed.
- `deferred`: evidence is valid but the candidate is not materially better than the incumbent.
- `eligible_for_shadow`: benchmark evidence is promising but still needs forward shadow evidence.
- `eligible_for_shadow`: benchmark integrity, risk guardrails, incumbent comparison, uncertainty checks, and rollback/config evidence all pass well enough for execution shadow review.
