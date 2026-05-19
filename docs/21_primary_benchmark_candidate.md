# Primary Benchmark Candidate

Status: candidate, not frozen.

The current candidate contract is benchmarks/primary_benchmark_candidate_20260519.json.
It is intended for review before promotion to the frozen primary benchmark.

## Composition

| Sleeve | Components | Weight |
|---|---:|---:|
| Single-name optionable equities | 18 | 0.73 |
| ETF and macro regime anchors | 4 | 0.17 |
| Crypto spot | 2 | 0.10 |
| Controlled stress components | 2 | 0.10 |

Stress weight is counted inside the single-name and crypto sleeves. It remains
below the 15% benchmark cap. ETF components are deliberately minor context
anchors, not the primary benchmark surface, because the live system is expected
to focus on stock and stock-option decisions.

## Components

| Component | Target | Window | Weight | Role | Purpose |
|---|---|---|---:|---|---|
| bmk_20260519_01_spy_covid_shock | SPY | 2020-02-18 to 2020-06-30 | 0.05 | primary | broad-market COVID crash and rebound anchor |
| bmk_20260519_02_xle_energy_inflation | XLE | 2021-09-01 to 2022-06-30 | 0.04 | primary | energy inflation leadership anchor |
| bmk_20260519_03_tlt_duration_crash | TLT | 2022-01-03 to 2023-10-31 | 0.04 | primary | duration/rate shock anchor |
| bmk_20260519_04_xlf_bank_stress | XLF | 2023-03-01 to 2023-05-31 | 0.04 | primary | regional-bank stress anchor |
| bmk_20260519_05_tsla_split_sp500_momentum | TSLA | 2020-08-31 to 2021-01-29 | 0.06 | primary | large-cap retail momentum and option activity |
| bmk_20260519_06_mrna_vaccine_leader | MRNA | 2020-05-01 to 2021-08-31 | 0.03 | primary | vaccine-era biotech leadership |
| bmk_20260519_07_gme_meme_option_stress | GME | 2021-01-04 to 2021-03-31 | 0.03 | primary | meme-stock option/liquidity stress |
| bmk_20260519_08_mp_rare_earth | MP | 2020-11-18 to 2021-06-30 | 0.03 | primary | rare-earth leader |
| bmk_20260519_09_ccj_nuclear_uranium | CCJ | 2021-08-02 to 2021-11-30 | 0.03 | primary | nuclear/uranium leader |
| bmk_20260519_10_meta_rate_hike_drawdown | META | 2022-02-03 to 2022-11-30 | 0.03 | primary | mega-cap platform rate-hike drawdown |
| bmk_20260519_11_fslr_clean_energy_rotation | FSLR | 2022-07-01 to 2023-02-28 | 0.03 | primary | clean-energy policy rotation |
| bmk_20260519_12_nvda_ai_repricing | NVDA | 2023-05-24 to 2023-08-31 | 0.07 | primary | AI semiconductor repricing |
| bmk_20260519_13_vrt_data_center_power | VRT | 2023-04-26 to 2023-10-31 | 0.06 | primary | data-center power infrastructure |
| bmk_20260519_14_smci_ai_server_mania | SMCI | 2024-01-02 to 2024-03-29 | 0.06 | primary | AI server hot thematic move |
| bmk_20260519_15_lly_glp1_leader | LLY | 2023-08-01 to 2024-06-28 | 0.04 | primary | GLP-1 healthcare leader |
| bmk_20260519_16_coin_crypto_equity_proxy | COIN | 2023-01-03 to 2023-12-29 | 0.04 | primary | crypto equity proxy |
| bmk_20260519_17_aaoi_optical_module_stress | AAOI | 2023-07-01 to 2023-09-29 | 0.05 | stress_edge_case | optical-module hot stock with missing Layer 2 context |
| bmk_20260519_18_amd_ai_semiconductor_followthrough | AMD | 2023-10-02 to 2024-03-29 | 0.04 | primary | AI semiconductor follow-through |
| bmk_20260519_21_wdc_storage_cycle | WDC | 2025-04-01 to 2026-04-30 | 0.04 | primary | 2025-2026 storage/hard-drive cycle |
| bmk_20260519_22_mu_ai_memory_cycle | MU | 2025-06-02 to 2026-04-30 | 0.03 | primary | 2025-2026 AI memory cycle |
| bmk_20260519_23_ceg_nuclear_power_repricing | CEG | 2025-01-02 to 2025-12-31 | 0.03 | primary | 2025 nuclear and data-center power repricing |
| bmk_20260519_24_lite_optical_module_reacceleration | LITE | 2025-08-01 to 2026-04-30 | 0.03 | primary | 2025-2026 optical-module reacceleration |
| bmk_20260519_19_btc_crypto_bull | BTC-USDT | 2021-01-01 to 2021-04-30 | 0.05 | primary | crypto bull cycle |
| bmk_20260519_20_btc_crypto_winter_stress | BTC-USDT | 2022-05-01 to 2022-11-30 | 0.05 | stress_edge_case | crypto winter with missing quote/order-book context |

## Review Notes

- Every target/window in this candidate has a matching training-exclusion window.
- The panel avoids using many ETFs; ETF components are 17% of weight and serve as background anchors only.
- Single-name optionable equities are 73% of weight.
- Recent 2025/2026 windows are included as sealed completed benchmark windows for storage, memory, optical-module, nuclear/data-center-power, and current hot-theme behavior.
- Same-background overlap is intentionally restrained by using shorter single-name episode windows instead of long full-cycle overlapping ranges.
- Single-name components require reviewed target-context refs before freeze.
- The crypto route assumes OKX trade-derived liquidity bars; standalone raw crypto trades are transient, and quote/order-book context is the explicit stress gap.
- Layer 8 option-expression evaluation should compare option expression against an underlying-only expression baseline. If options are unsuitable, the model may recommend the underlying-expression route rather than forcing an option contract.
- This candidate should not be used for training, tuning, prompt iteration, or model selection until it is frozen and sealed as evaluation-only data.
