# XGBoost v1 integration audit and implementation plan

Audit started 6 November 2026, before runtime changes, at `47e0d94` on a new `feat/model-v1-integration` branch. The existing untracked Chapter 5 evidence and supplied `codex-handoff/` are retained. This document is updated with final verification after implementation; the baseline below records what was actually inspected first.

## Scope and gate

Read `codex-handoff/README_START_HERE.md`, then the entire `01_Codex_Model_Integration.md`. Prompt 2 is not being undertaken. Read all 29 pages of `reference/Webmasters_Specification.pdf` (SHA-256 recorded in supplied `SHA256SUMS.txt`), particularly pp.4–10 (§§3.1–3.14), 20–24 (§§7–11), 26–29 (§§13–15). Requirements for provenance, missing/zero distinction, model versions, horizon, insufficient-data handling and risk/inundation separation apply. Water-level ingestion, hydraulic inundation, new role systems, external notifications and the broader company roadmap are outside this integration.

The selected native artifact is **XGBoost v1**, not later notebook experimental candidates or Random Forest. It forecasts next-calendar-day **rule-defined environmental proxy classes**. It does not estimate observed flood occurrence, depth, inundation or calibrated flood probability. Operational promotion and emergency delivery remain disabled at the replay gate.

## Before implementation

| Area | Actual baseline | Integration decision |
| --- | --- | --- |
| Backend | FastAPI `src/api/main.py`; SQLAlchemy config/session; application `.venv` Python3.12.1, XGBoost2.0.3, sklearn1.4.2, NumPy1.26.4, pandas2.2.1 | Preserve application dependencies; isolate v1 native runtime if frozen-score tolerance requires it. |
| Legacy model | Nine inputs, MinMaxScaler/joblib, shared runoff-index weather row; `ml_service.py`, `model_contract.py`, `pipeline.py` | Preserve artifact bytes, paths, old reads and old rows for rollback; do not feed legacy features to v1. Guard corrupt legacy loading. |
| Existing DB/API | Five ORM tables + explicitly migrated PostGIS boundary table; `/dashboard`, `/predictions`, reports, boundaries, auth/admin | Add companion run/result/terrain tables and `/api/v1` reads/privileged replay. Never put a hindcast into the legacy prediction table. |
| Scheduling | Main lifespan creates tables and one hourly scheduler per API process | Make side effects explicit/opt-in, retain manual legacy worker, DB-enforce v1 idempotency. No scheduled v1 live inference without parity. |
| Frontend | Shared legacy polling/context; Leaflet county/17 sub-counties/eight points; many management panels mock | Preserve legacy view and polling; explicit v1 live/replay view; replace misleading v1 model/health presentations with real read metadata. |
| Tests | Isolated SQLite and disposable native PostGIS fixtures; `test_api.py` still mutates configured DB | Isolate smoke auth/report tests before full-suite execution; add real-artifact parity, v1 API/concurrency and UI contract tests. |
| Deployment | No verified deployment/CI or production telemetry | Local research integration only; no cloud provisioning or deployment. |

## Input integrity and recovered research evidence

All 16 supplied SHA256SUMS entries match, including model/native JSON and untouched alternative joblib. The joblib is not deserialized. Native JSON declares 20 ordered float features, four classes, `multi:softprob`, producer version `[3,1,3]` and 496 rounds. Fingerprints:

| File | SHA-256 |
| --- | --- |
| native model JSON (5,487,493 bytes) | `b185eced1e8887b0fdbcb539567ea4f7d485583848c81c81eacc2979d8c728bb` |
| feature_columns.json | `521f691dd7b0a97fbbcb604ca97beaaffc94988ae58e75ba4e30f92cfb96c179` |
| class_names.json | `04c5d0f21df96a18bad6d0496c55312ef5854e70d096dd6448cf5c2c330a7721` |
| experiment_manifest.json | `5c5434c82db2d86f26c6aea042c356969fb409ff6142627298e2d92079fe799e` |
| supplied frozen score reference CSV | `16ce072199936925168130ec705d9f1c7594b0faa451ae715335f61f036beeac` |
| recovered integrated 29,224-row source CSV | `9bf5c7b014e75b9dbfc551f391413f81a1d5b0c30d9cea834d4112927c00a665` (exact experiment-manifest match) |
| recovered frozen 5,848-row test-feature CSV | `c6d65812903dc68abdd51c0af5ef1494bc13ee6bc54ed231597d95817b3ec58e` |
| recovered current research notebook | `d0def899812c01a88c13084937a4e8f86340172d468d3888279f33b2431abe5b` |

Needed source files were retrieved read-only from the connected Project Dataset/Colab Notebooks folders. No original 114MB hourly archive or large GIS archive was required. The local integration packaging command will verify these hashes and keep data/artifacts ignored, separate from the legacy bundle. Notebook evidence uses zero-based JSON cell indices (the recovered notebook cells have no IDs). Only Part1/selected-v1 cells 0–26 are used; later experimental cells are not selected.

Compatibility probe in the actual application XGBoost2.0.3 loads the JSON and matches all 5,848 classes, but its maximum absolute score difference is **6.499645996083103e-06**, failing `rtol=atol=1e-6` against the selected frozen reference. A syntactically successful load is therefore insufficient. Plan: pin XGBoost3.1.3 in a separate native-inference environment, keep the application environment intact, and verify all frozen scores through that actual runtime before inference persistence/UI integration. Do not rewrite base scores or trees to accommodate the older library.

## Feature parity matrix

Keys: input calendar date **D**, lower-case exact zone ID; Open-Meteo daily boundaries **00:00–23:00 Africa/Nairobi**, full 24 hourly rows; cutoff is D+1 00:00 EAT. CHIRPS dates retain their original product keys; their actual accumulation boundary versus EAT and release timestamps are unverified. `NB[n]` refers to recovered notebook zero-based cell n. All missing/NaN/inf/duplicate/incomplete source values fail closed, never zero-filled. Static terrain requires a persisted, provenance-bearing zone record.

| # / exact feature | Definition from research code | Unit / source / window | Live availability / latency | Reproduction / missing policy |
| --- | --- | --- | --- | --- |
| 1 chirps_daily_rain_mm | Same-zone CHIRPS at D; NB[7] rename | mm/day; zone-associated export | Full D/release time not available from current live adapter | Compare corrected zone CHIRPS and hash-verified integrated source; missing -> INSUFFICIENT_DATA |
| 2 chirps_prev_1d_mm | `groupby(zone).shift(1)`; NB[9] | mm on D−1, excludes D | CHIRPS publication delay applies | Recompute from same-zone preceding dates, never target day |
| 3 chirps_prev_3d_sum_mm | shift(1), rolling(3,min_periods=3); NB[9] | mm, D−3…D−1 | All three preceding days required | Reject a calendar gap or short history |
| 4 chirps_prev_7d_sum_mm | shift(1), rolling(7,min_periods=7); NB[9] | mm, D−7…D−1 | All seven preceding days required | Recompute, compare frozen row; no min_periods=1 shortcut |
| 5 meteo_daily_rain_mm | Hourly precipitation sum; NB[6] | mm, all 24 Nairobi-local hours at D | ERA5-Seamless retrospective, not current forecast equivalent | Historical aggregate replay; raw hourly slice verification where obtained |
| 6 rainfall_3h_eod_mm | Last hourly rolling3h value at23:00; NB[6] | mm, hours21–23 on D | End-of-day only; no partial day | Match frozen EOD field; independently check last3 hourly depths in source slice |
| 7 rainfall_6h_eod_mm | Last rolling6h at23:00; NB[6] | mm, hours18–23 | Same retrospective/EOD blocker | Check all required hourly values, not interpolated daily CHIRPS |
| 8 rainfall_12h_eod_mm | Last rolling12h at23:00; NB[6] | mm, hours12–23 | Same | Match historical/frozen aggregate, reject missing coverage |
| 9 rainfall_24h_eod_mm | Last rolling24h at23:00; NB[6] asserts equals local-day total | mm, hours00–23 | Same | Explicit equality check to meteo_daily_rain_mm; no guessed rain |
| 10 temperature_mean_c | Arithmetic daily hourly mean; NB[6] | °C, 24 observations | ERA5-Seamless release not recorded; live forecast differs | Preserve verified original returned units; full day required |
| 11 humidity_mean_pct | Arithmetic daily hourly mean; NB[6] | %, 24 observations | Same | Physical range0–100, finite, no default |
| 12 wind_speed_mean_kmh | Arithmetic daily hourly mean; NB[6] | km/h, 24 observations | Same | Explicit original unit provenance; nonnegative |
| 13 soil_moisture_mean_m3m3 | Arithmetic daily hourly mean; NB[6] | m³/m³, layer0–7cm | Same | Range0–1; no invented moisture |
| 14 soil_moisture_eod_m3m3 | Last sorted daily soil value; NB[6] | m³/m³ at23:00 | Same EOD constraint | Require that hour; do not substitute daily mean |
| 15 slope_degrees | Per-zone terrain join; NB[7] | degrees; static source summary | Zone terrain required; provenance incomplete until source metadata imported | Store immutable version/hash and actual values; no fixed terrain guess |
| 16 ndvi | Per-zone terrain join; NB[7] | unitless−1…1; 2023 static summary | Not a daily 2016–2025 measurement | Flag STATIC_NDVI_2023, including retrospective application to earlier dates |
| 17 impervious_fraction | Per-zone built-up land-cover fraction; NB[7] | fraction0–1; 2021 land cover | Static approximation | Preserve original definition/source year, no substitution with legacy0.72 |
| 18 vegetation_fraction | Per-zone vegetation land-cover fraction; NB[7] | fraction0–1; 2021 land cover | Static approximation | Persist provenance; absent terrain -> INSUFFICIENT_DATA |
| 19 season_sin | sin(2π*D.dayofyear/365.25); NB[9] | unitless; input date (no−1) | Available; depends on verified local input date | Leap/boundary tests; reject target-day calendar substitution |
| 20 season_cos | cos(2π*D.dayofyear/365.25); NB[9] | unitless; input date | Available | Same exact formula; frozen parity |

Daily/frozen feature rows agree to floating CSV precision (max ~5.7e-14); recomputed CHIRPS lags ~8.6e-14 and season ~1.2e-16. The first seven input dates per zone cannot supply complete history. Frozen test input dates are 2023-12-31…2025-12-30, targets 2024-01-01…2025-12-31, 731 per zone. Source data are zone-associated approximate monitoring rectangles, not administrative sub-county means or gauges.

Weather provenance identifies ERA5-Seamless, actual units °C/%/mm/kmh/m³m³, 80 zone-year responses and **three** returned grid coordinate pairs shared across eight zones. Coincident/coarse inputs and overlapping areas must be disclosed, even when terrain makes feature vectors distinct. Original per-source released-at timestamps are absent. The original creation code for hourly rolling columns is not in this notebook; verify EOD sums directly from a small raw yearly source slice, and retain the remaining raw-source replication limitation.

Official provider references checked 6 November: [CHIRPS2 FAQ](https://wiki.chc.ucsb.edu/CHIRPS2_FAQ) describes preliminary/final publication lag; [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) lists approximately five-day ERA5/ERA5-Land delay. Neither supplies a verified original per-row release time. Do not substitute CHIRPS3 or forecast weather for the selected retrospective products silently. See [XGBoost model IO guidance](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html) for native models versus Python snapshots; actual frozen-score comparison decides this package's compatibility.

## Time and status plan

- `input_date=D`, `forecast_target_date=D+1`, `forecast_horizon=next_calendar_day`; these are calendar dates, not a six-hour forecast.
- `issued_at` must be timezone aware and on the target local calendar day at/after cutoff. For replay it is explicitly a **simulated research issue time**, not evidence that retrospective data had been published then.
- `executed_at` is actual execution time; `data_as_of`/source observed-through describe input coverage, not publication availability. Missing original released-at stays null with an explicit flag; actual import/retrieval time is a separate provenance field.
- Live mode remains `INSUFFICIENT_DATA`/`STALE_DATA`, with null risk/scores and explicit blocker codes until source availability/parity is demonstrated. Historical replay status/freshness is separate from current monitoring.
- Scores are `proxy_class_scores`/`model_class_score`; `flood_probability=null`, reason `NOT_CALIBRATED_TO_OBSERVED_FLOODS`. Keep raw Extreme class.

## Reviewable implementation units

1. Record this baseline and package/source hash manifest before runtime edits.
2. Install ignored local native artifact + isolated pinned runtime; implement strict contract/worker and historical feature construction with real frozen-row parity tests. No classifier fitting or artifact mutation.
3. Add explicit transactional/reversible migrations, provenance-bearing terrain versions, immutable/idempotent replay runs and per-zone results; secure admin trigger; typed public v1 reads/history/model metadata. Preserve old API/table contracts. No external alert delivery.
4. Add explicit frontend legacy/v1 live/replay display and real evaluation/health data, status/freshness/target-date caveats; preserve boundary overlays and report routes.
5. Run full isolated backend/frontend/build, native PostgreSQL concurrency/rollback and real-artifact parity; manually replay 2024-04-30 ->2024-05-01 in an isolated schema. Document exact results, rollback and acceptance blockers. Stop before Prompt2 or any operational promotion.

## Final state

Implementation and verification results will be recorded here and in `model_v1_validation.md` after the above units complete. No operational readiness is implied by this audit/plan.
