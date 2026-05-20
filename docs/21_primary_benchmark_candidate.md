# Fixed Target/Window Diagnostic Candidate

Status: diagnostic/stress candidate, not a promotion benchmark.

The current candidate contract is benchmarks/primary_benchmark_candidate_20260519.json.
It is retained as a fixed target/window diagnostic and stress panel candidate. It should not be promoted as the full primary benchmark for target-selection models because it preselects final target identities instead of replaying a fixed candidate-universe policy.

## Composition

| Sleeve | Components | Weight |
|---|---:|---:|
| Single-name optionable equities | 29 | 0.88 |
| ETF and macro regime anchors | 4 | 0.09 |
| Crypto spot | 2 | 0.03 |
| Controlled stress components | 2 | 0.05 |

Stress weight is counted inside the single-name and crypto sleeves. ETF components are deliberately minor context anchors, not the primary benchmark surface, because the live system is expected to focus on stock and stock-option decisions.

## Time Allocation

| Bucket | Window | Weight | Components |
|---|---|---:|---|
| 2020/2021 | 2020-02-18 to 2021-12-31 | 0.25 | SPY, TSLA, MRNA, GME, MP, CCJ, DIS, RCL, BTC-USDT |
| 2022 | 2021-09-01 to 2022-12-30 | 0.25 | XLE, TLT, META, FSLR, OXY, ENPH, TGT, NFLX, BTC-USDT |
| 2023/2024 | 2023-01-03 to 2024-06-28 | 0.25 | XLF, NVDA, VRT, SMCI, LLY, COIN, AAOI, AMD, COST |
| 2025/2026 | 2025-01-02 to 2026-04-30 | 0.25 | WDC, MU, CEG, LITE, WMT, CMG, RBLX, HD |

Each time bucket is fixed at 25% so the benchmark is not dominated by the 2023-2024 AI/data-center tape or by older COVID/rate-shock episodes.

## Sector Allocation

| Sector bucket | Weight | Components |
|---|---:|---|
| Consumer and retail | 0.22 | TSLA, GME, RCL, TGT, COST, WMT, CMG, HD |
| Entertainment, media, gaming, and travel | 0.17 | GME, DIS, RCL, META, NFLX, RBLX |
| AI compute, semiconductors, storage, and optical networking | 0.25 | NVDA, SMCI, AAOI, AMD, WDC, MU, LITE |
| Energy, nuclear, clean energy, power, and rare earth materials | 0.21 | MP, CCJ, XLE, FSLR, OXY, ENPH, CEG |
| Healthcare and biotech | 0.06 | MRNA, LLY |
| Financials and crypto | 0.07 | BTC-USDT, BTC-USDT, XLF, COIN |
| Broad-market and rate/macro anchors | 0.05 | SPY, TLT |
| Data-center infrastructure | 0.10 | VRT, SMCI, CEG |

Sector buckets overlap when one target legitimately belongs to more than one exposure group, such as data-center power and nuclear power.

## Event Allocation

| Event bucket | Weight | Components |
|---|---:|---|
| earnings crossing | 0.66 | TSLA, DIS, RCL, META, OXY, ENPH, TGT, NFLX, NVDA, VRT, SMCI, LLY, COIN, AMD, COST, WDC, MU, LITE, WMT, CMG, RBLX, HD |
| policy macro shock | 0.42 | SPY, MRNA, MP, CCJ, DIS, RCL, XLE, TLT, META, FSLR, OXY, TGT, XLF, CEG, HD |
| liquidity squeeze stress | 0.18 | SPY, GME, RCL, BTC-USDT, XLF, SMCI, AAOI |
| product cycle repricing | 0.63 | TSLA, MRNA, DIS, FSLR, ENPH, NFLX, NVDA, VRT, SMCI, LLY, AAOI, AMD, COST, WDC, MU, CEG, LITE, WMT, CMG, RBLX |
| crypto cycle | 0.05 | BTC-USDT, BTC-USDT, COIN |

Event buckets may overlap because a component can cross earnings while also representing a product-cycle, policy, liquidity, or crypto-cycle event.

## Components

| Component | Target | Window | Weight | Role | Sectors | Event tags | Purpose |
|---|---|---|---:|---|---|---|---|
| bmk_20260519_01_spy_covid_shock | SPY | 2020-02-18 to 2020-06-30 | 0.02 | primary | broad_market | policy_macro_event, liquidity_shock | broad-market COVID crash and rebound anchor |
| bmk_20260519_02_tsla_split_sp500_momentum | TSLA | 2020-08-31 to 2021-01-29 | 0.04 | primary | consumer_discretionary | earnings_crossing, product_cycle_repricing | large-cap retail momentum and option activity |
| bmk_20260519_03_mrna_vaccine_leader | MRNA | 2020-05-01 to 2021-08-31 | 0.03 | primary | biotech_healthcare, healthcare | medical_trial_or_approval, policy_macro_event | vaccine-era biotech leadership |
| bmk_20260519_04_gme_meme_option_stress | GME | 2021-01-04 to 2021-03-31 | 0.03 | primary | consumer_discretionary, gaming_social | squeeze_event, liquidity_shock | meme-stock option/liquidity stress |
| bmk_20260519_05_mp_rare_earth | MP | 2020-11-18 to 2021-06-30 | 0.03 | primary | materials_rare_earth | commodity_supply_shock, policy_macro_event | rare-earth leader |
| bmk_20260519_06_ccj_nuclear_uranium | CCJ | 2021-08-02 to 2021-11-30 | 0.03 | primary | nuclear_power, energy | commodity_supply_shock, policy_macro_event | nuclear/uranium leader |
| bmk_20260519_07_dis_reopening_streaming | DIS | 2020-03-16 to 2021-03-31 | 0.03 | primary | entertainment_media, travel_leisure | earnings_crossing, product_cycle_repricing, policy_macro_event | entertainment reopening and streaming repricing |
| bmk_20260519_08_rcl_reopening_travel | RCL | 2020-04-01 to 2021-06-30 | 0.03 | primary | travel_leisure, consumer_discretionary | earnings_crossing, policy_macro_event, liquidity_shock | travel/leisure reopening shock and rebound |
| bmk_20260519_09_btc_crypto_bull | BTC-USDT | 2021-01-01 to 2021-04-30 | 0.01 | primary | crypto | crypto_cycle_event | crypto bull cycle |
| bmk_20260519_10_xle_energy_inflation | XLE | 2021-09-01 to 2022-06-30 | 0.02 | primary | energy | rate_inflation_shock, commodity_supply_shock | energy inflation leadership anchor |
| bmk_20260519_11_tlt_duration_crash | TLT | 2022-01-03 to 2023-10-31 | 0.03 | primary | broad_market | rate_inflation_shock, policy_macro_event | duration/rate shock anchor |
| bmk_20260519_12_meta_rate_hike_drawdown | META | 2022-02-03 to 2022-11-30 | 0.03 | primary | entertainment_media, gaming_social | earnings_crossing, earnings_gap, rate_inflation_shock | mega-cap platform rate-hike drawdown |
| bmk_20260519_13_fslr_clean_energy_rotation | FSLR | 2022-07-01 to 2023-02-28 | 0.03 | primary | clean_energy | policy_macro_event, sector_rotation | clean-energy policy rotation |
| bmk_20260519_14_oxy_energy_leader | OXY | 2021-12-01 to 2022-06-30 | 0.03 | primary | energy | earnings_crossing, commodity_supply_shock, rate_inflation_shock | 2022 energy inflation single-name leader |
| bmk_20260519_15_enph_clean_energy_volatility | ENPH | 2022-07-01 to 2022-12-30 | 0.03 | primary | clean_energy | earnings_crossing, sector_rotation | 2022 clean-energy high-volatility single name |
| bmk_20260519_16_tgt_inventory_shock | TGT | 2022-05-18 to 2022-11-30 | 0.03 | primary | consumer_staples, retail | earnings_crossing, earnings_gap, rate_inflation_shock | consumer retail inventory and margin shock |
| bmk_20260519_17_nflx_subscriber_shock | NFLX | 2022-01-20 to 2022-07-29 | 0.03 | primary | entertainment_media | earnings_crossing, earnings_gap, product_cycle_repricing | streaming subscriber shock and earnings gap |
| bmk_20260519_18_btc_crypto_winter_stress | BTC-USDT | 2022-05-01 to 2022-11-30 | 0.02 | stress_edge_case | crypto | crypto_cycle_event, liquidity_shock, data_availability_stress | crypto winter with missing quote/order-book context |
| bmk_20260519_19_xlf_bank_stress | XLF | 2023-03-01 to 2023-05-31 | 0.02 | primary | financials | banking_stress, liquidity_shock | regional-bank stress anchor |
| bmk_20260519_20_nvda_ai_repricing | NVDA | 2023-05-24 to 2023-08-31 | 0.03 | primary | semiconductors, ai_compute | earnings_crossing, earnings_gap, ai_capex_repricing | AI semiconductor repricing |
| bmk_20260519_21_vrt_data_center_power | VRT | 2023-04-26 to 2023-10-31 | 0.03 | primary | data_center_infrastructure | earnings_crossing, ai_capex_repricing, product_cycle_repricing | data-center power infrastructure |
| bmk_20260519_22_smci_ai_server_mania | SMCI | 2024-01-02 to 2024-03-29 | 0.03 | primary | ai_compute, data_center_infrastructure | earnings_crossing, ai_capex_repricing, liquidity_shock | AI server hot thematic move |
| bmk_20260519_23_lly_glp1_leader | LLY | 2023-08-01 to 2024-06-28 | 0.03 | primary | healthcare | earnings_crossing, medical_trial_or_approval | GLP-1 healthcare leader |
| bmk_20260519_24_coin_crypto_equity_proxy | COIN | 2023-01-03 to 2023-12-29 | 0.02 | primary | crypto, financials | earnings_crossing, crypto_cycle_event | crypto equity proxy |
| bmk_20260519_25_aaoi_optical_module_stress | AAOI | 2023-07-01 to 2023-09-29 | 0.03 | stress_edge_case | optical_networking | data_availability_stress, liquidity_shock, ai_capex_repricing | optical-module hot stock with missing Layer 2 context |
| bmk_20260519_26_amd_ai_semiconductor_followthrough | AMD | 2023-10-02 to 2024-03-29 | 0.03 | primary | semiconductors, ai_compute | earnings_crossing, ai_capex_repricing | AI semiconductor follow-through |
| bmk_20260519_27_cost_consumer_defensive | COST | 2023-05-01 to 2024-03-31 | 0.03 | primary | consumer_staples, retail | earnings_crossing, product_cycle_repricing | consumer defensive retail leadership |
| bmk_20260519_28_wdc_storage_cycle | WDC | 2025-04-01 to 2026-04-30 | 0.05 | primary | storage_memory | earnings_crossing, product_cycle_repricing | 2025-2026 storage/hard-drive cycle |
| bmk_20260519_29_mu_ai_memory_cycle | MU | 2025-06-02 to 2026-04-30 | 0.04 | primary | storage_memory, semiconductors | earnings_crossing, product_cycle_repricing | 2025-2026 AI memory cycle |
| bmk_20260519_30_ceg_nuclear_power_repricing | CEG | 2025-01-02 to 2025-12-31 | 0.04 | primary | nuclear_power, data_center_infrastructure | policy_macro_event, ai_capex_repricing | 2025 nuclear and data-center power repricing |
| bmk_20260519_31_lite_optical_module_reacceleration | LITE | 2025-08-01 to 2026-04-30 | 0.04 | primary | optical_networking | earnings_crossing, ai_capex_repricing | 2025-2026 optical-module reacceleration |
| bmk_20260519_32_wmt_consumer_staples_recent | WMT | 2025-02-20 to 2026-04-30 | 0.02 | primary | consumer_staples, retail | earnings_crossing, product_cycle_repricing | 2025-2026 consumer staples retail leadership |
| bmk_20260519_33_cmg_restaurant_consumer | CMG | 2025-02-01 to 2026-04-30 | 0.02 | primary | restaurants, consumer_discretionary | earnings_crossing, product_cycle_repricing | restaurant consumer cycle |
| bmk_20260519_34_rblx_gaming_social_recent | RBLX | 2025-02-06 to 2026-04-30 | 0.02 | primary | gaming_social, entertainment_media | earnings_crossing, product_cycle_repricing | gaming/social entertainment cycle |
| bmk_20260519_35_hd_housing_consumer | HD | 2025-02-25 to 2026-04-30 | 0.02 | primary | consumer_discretionary, retail | earnings_crossing, rate_inflation_shock | housing-sensitive consumer retail |

## Review Notes

- Every target/window in this candidate has a matching training-exclusion window.
- The panel avoids using many ETFs; ETF components are 9% of weight and serve as background anchors only.
- Single-name optionable equities are 88% of weight.
- Time allocation is balanced across four review buckets: 2020/2021, 2022, 2023/2024, and 2025/2026.
- Consumer, entertainment/media, travel/leisure, retail, restaurants, healthcare, financials, energy, clean energy, nuclear/power, rare earth, AI compute, storage, optical networking, data-center infrastructure, and crypto are all explicitly covered.
- Earnings-crossing and event-driven windows are explicit benchmark requirements, not incidental side effects of long windows.
- Recent 2025/2026 windows are included as sealed completed benchmark windows for storage, memory, optical-module, nuclear/data-center-power, consumer, entertainment/gaming, and current hot-theme behavior.
- Same-background overlap is intentionally restrained by using shorter single-name episode windows instead of long full-cycle overlapping ranges.
- Single-name components require reviewed target-context refs before freeze.
- The crypto route assumes OKX trade-derived liquidity bars; standalone raw crypto trades are transient, and quote/order-book context is the explicit stress gap.
- Layer 8 option-expression evaluation should compare option expression against an underlying-only expression baseline. If options are unsuitable, the model may recommend the underlying-expression route rather than forcing an option contract.
- This candidate should not be used for training, tuning, prompt iteration, model selection, or promotion. It can support diagnostic/stress replay after review; promotion requires a benchmark that freezes the candidate-universe policy and lets the model select/rank targets inside each historical replay batch.
