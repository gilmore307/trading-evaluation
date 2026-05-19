# Decisions

## D001 - Evaluation Is An Independent Referee

Date: 2026-05-19
Status: Accepted

`trading-evaluation` owns benchmark judgment, fold settlement, and promotion eligibility. It does not train models, schedule workflow, store durable artifacts, activate production configs, execute broker actions, or mutate accounts.

## D002 - Primary Benchmark Is One Frozen Target Window

Date: 2026-05-19
Status: Accepted

The primary benchmark uses one fixed target and one fixed time window so fold settlement remains horizontally comparable across model generations.

The benchmark window must be long enough to reduce accident, structurally complex enough to cover diverse market states, and excluded from training. The target must not be a training-used target.

## D003 - Promotion Eligibility Is Not Activation

Date: 2026-05-19
Status: Accepted

`trading-evaluation` may produce promotion eligibility decisions from settlement evidence. It must not activate models. Activation remains a separate controlled gate outside this repository.

