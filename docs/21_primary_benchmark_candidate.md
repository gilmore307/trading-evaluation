# Primary Benchmark Candidate

Status: candidate, not frozen.

The current candidate contract is benchmarks/primary_benchmark_candidate_20260519.json.
It is intended for review before promotion to the frozen primary benchmark.

## Composition

| Sleeve | Components | Weight |
|---|---:|---:|
| ETF and macro regime backbone | 10 | 0.62 |
| Hot thematic single names | 5 | 0.26 |
| Crypto spot | 2 | 0.12 |
| Controlled stress components | 2 | 0.10 |

Stress weight is counted inside the thematic and crypto sleeves. It remains
below the 15% benchmark cap.

## Components

| Component | Target | Window | Weight | Role | Purpose |
|---|---|---|---:|---|---|
| bmk_20260519_01_spy_covid_shock | SPY | 2020-02-18 to 2020-06-30 | 0.08 | primary | COVID crash and rebound |
| bmk_20260519_02_qqq_rate_hike_drawdown | QQQ | 2022-01-03 to 2022-12-30 | 0.08 | primary | rate-hike technology drawdown |
| bmk_20260519_03_iwm_reopening_rotation | IWM | 2020-11-02 to 2021-06-30 | 0.06 | primary | reopening and small-cap rotation |
| bmk_20260519_04_xle_energy_inflation | XLE | 2020-11-02 to 2022-06-30 | 0.07 | primary | energy inflation leadership |
| bmk_20260519_05_xlf_bank_stress | XLF | 2023-03-01 to 2023-05-31 | 0.04 | primary | regional-bank stress window |
| bmk_20260519_06_xbi_biotech_unwind | XBI | 2021-02-16 to 2022-06-30 | 0.06 | primary | speculative biotech unwind |
| bmk_20260519_07_smh_ai_semiconductor_cycle | SMH | 2023-01-03 to 2024-06-28 | 0.07 | primary | AI semiconductor leadership |
| bmk_20260519_08_tlt_duration_crash | TLT | 2022-01-03 to 2023-10-31 | 0.06 | primary | duration/rate shock |
| bmk_20260519_09_uso_oil_dislocation | USO | 2020-03-02 to 2020-05-29 | 0.05 | primary | oil dislocation |
| bmk_20260519_10_xme_materials_reflation | XME | 2020-04-01 to 2021-05-31 | 0.05 | primary | materials reflation |
| bmk_20260519_11_nvda_ai_leader | NVDA | 2023-01-03 to 2024-06-28 | 0.07 | primary | AI/data-center leader |
| bmk_20260519_12_mp_rare_earth | MP | 2020-11-18 to 2021-11-30 | 0.04 | primary | rare-earth leader |
| bmk_20260519_13_ccj_nuclear_uranium | CCJ | 2020-11-02 to 2021-11-30 | 0.04 | primary | nuclear/uranium leader |
| bmk_20260519_14_vrt_data_center | VRT | 2023-01-03 to 2024-06-28 | 0.06 | primary | data-center power infrastructure |
| bmk_20260519_15_aaoi_optical_module_stress | AAOI | 2023-05-01 to 2024-03-29 | 0.05 | stress_edge_case | optical-module hot stock with missing Layer 2 context |
| bmk_20260519_16_btc_crypto_bull | BTC-USDT | 2021-01-01 to 2021-12-31 | 0.07 | primary | crypto bull cycle |
| bmk_20260519_17_btc_crypto_winter_stress | BTC-USDT | 2022-01-01 to 2022-12-31 | 0.05 | stress_edge_case | crypto winter with missing quote/order-book context |

## Review Notes

- Every target/window in this candidate has a matching training-exclusion window.
- ETF backbone symbols have local Alpaca monthly bar coverage in the current storage tree.
- Single-name components require reviewed target-context refs before freeze.
- The crypto route assumes OKX trade-derived liquidity bars; standalone raw crypto trades are transient, and quote/order-book context is the explicit stress gap.
- This candidate should not be used for training, tuning, prompt iteration, or model selection until it is frozen and sealed as evaluation-only data.

