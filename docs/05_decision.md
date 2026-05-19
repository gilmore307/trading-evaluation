# Decisions

## D001 - Evaluation Is An Independent Referee

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns benchmark judgment, fold settlement, promotion eligibility, and model activation records. It does not train models, schedule workflow, store durable artifacts, execute broker actions, or mutate accounts.

## D002 - Primary Benchmark Is One Frozen Target Window

Date: 2026-05-19
Status: Accepted

The primary benchmark uses one fixed target and one fixed time window so fold settlement remains horizontally comparable across model generations.

The benchmark window must be long enough to reduce accident, structurally complex enough to cover diverse market states, and excluded from training. The target must not be a training-used target.

## D003 - Model Activation Belongs In Evaluation

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns model activation because manager should remain a scheduler. Activation is a controlled config-release record from an eligible evaluation decision; it is not broker execution, order construction, or account mutation.
