# Selected v1 model and data contract

This contract registers `nairobi_xgboost_nextday_proxy_v1`, task `next_day_proxy_risk`. Its four classes, in numeric/score order, are **Low, Moderate, High, Extreme**. There is no approved mapping of Extreme to Very High. The selected artifact is native JSON SHA-256 `b185eced1e8887b0fdbcb539567ea4f7d485583848c81c81eacc2979d8c728bb`. `src/modeling/v1/package_manifest.json` is the version-controlled integrity anchor for the package, research source files and stored evaluation. Joblib and later notebook candidates are not used by this runtime.

The model estimates a **next-day rule-defined environmental proxy category**, not recorded flood occurrence, depth, inundation or a calibrated chance of flooding. A high class score expresses model preference among proxy labels; it is not a guarantee of accuracy. No synthetic water-level feature, guessed terrain, imputed weather, or previous nine-feature scaler is used.

## Temporal semantics

| Field | Definition |
| --- | --- |
| `zone_id` | One exact lower-case monitoring area ID: cbd, dagoretti, embakasi, kasarani, kibera, mathare, ruaraka, westlands. It associates data with the research monitoring area, not an independently validated neighbourhood gauge. |
| `input_date` | D, the complete predictor calendar date. Weather uses Africa/Nairobi 00:00–23:00 hourly stamps. |
| `forecast_target_date` | D+1, regardless of actual execution date. |
| `forecast_horizon` | Literal `next_calendar_day`; not a configurable 0–6h forecast. |
| `issued_at` | Explicitly timezone-aware, falling on D+1 in Africa/Nairobi. Cannot precede the D+1 00:00 full-day cutoff. In historical replay this is a simulated research issue time; source publication then is not established. |
| `executed_at` | Actual time the application executes the research run; never substituted for the historical issue/target dates. |
| `data_as_of` | The feature builder's observed input coverage boundary, separate from release time. It does not establish real-time availability. See source metadata for exact inclusive hourly coverage/cutoff. |
| Source observed/released/imported times | Observation window/date keys are retained. Original release times are null/unknown because originals did not record them. `imported_at` is actual local import time, not a fabricated observation/release time. |

CHIRPS image-date accumulation windows have not been reconciled with Nairobi-local days. Historical replay preserves the original training alignment and exposes that limitation. Retrospective ERA5-Seamless and delayed CHIRPS cannot be silently replaced by current forecast fields or partial-day rain. Late data cannot be relabelled as having been available at simulated issue time.

## Exact feature schema

There are exactly 20 finite numeric inputs in this order. Missing, extra, reordered, boolean, numeric-string, NaN and infinite values are rejected; the canonical builder emits this precise order. No model-input defaults or scaling are applied. Parenthetical code references are to zero-based cells of the recovered research notebook, identified by hash in the audit.

| # | Feature | Unit and exact definition |
| ---: | --- | --- |
| 1 | `chirps_daily_rain_mm` | mm; same-zone CHIRPS D (NB7). |
| 2 | `chirps_prev_1d_mm` | mm; same-zone D−1, `shift(1)` (NB9). |
| 3 | `chirps_prev_3d_sum_mm` | mm; D−3…D−1 inclusive; `shift(1).rolling(3,min_periods=3).sum()` (NB9). |
| 4 | `chirps_prev_7d_sum_mm` | mm; D−7…D−1 inclusive, seven complete preceding dates, excludes D (NB9). |
| 5 | `meteo_daily_rain_mm` | mm; sum of all 24 local hourly precipitation depths on D (NB6). |
| 6 | `rainfall_3h_eod_mm` | mm; final three hourly depths, 21:00–23:00 stamps on D (NB6 plus independently verified raw source slice). |
| 7 | `rainfall_6h_eod_mm` | mm; final six, 18:00–23:00. |
| 8 | `rainfall_12h_eod_mm` | mm; final twelve, 12:00–23:00. |
| 9 | `rainfall_24h_eod_mm` | mm; final 24, 00:00–23:00, equal to full-day weather rain within numeric tolerance. |
| 10 | `temperature_mean_c` | °C; arithmetic mean of 24 hourly values (NB6). |
| 11 | `humidity_mean_pct` | %; daily hourly mean, range0–100. |
| 12 | `wind_speed_mean_kmh` | km/h; daily hourly mean, nonnegative. |
| 13 | `soil_moisture_mean_m3m3` | m³/m³, layer0–7cm; daily mean, range0–1. |
| 14 | `soil_moisture_eod_m3m3` | m³/m³; same layer at final23:00 stamp, not daily mean. |
| 15 | `slope_degrees` | degrees0–90; provenance-bearing persisted terrain record for this zone. |
| 16 | `ndvi` | Unitless−1…1; supplied 2023 static summary, not a daily measured feature. |
| 17 | `impervious_fraction` | Fraction0–1; supplied built-up land-cover fraction, 2021 static approximation. |
| 18 | `vegetation_fraction` | Fraction0–1; supplied vegetation land-cover fraction, 2021 static approximation. |
| 19 | `season_sin` | `sin(2*pi*dayofyear(D)/365.25)`; no subtraction of1 (NB9). |
| 20 | `season_cos` | `cos(2*pi*dayofyear(D)/365.25)`; input-day calendar (NB9). |

Rainfall windows must be nonnegative/nested, 24h total must match daily weather rain, and season components must form a common unit angle. A real observed zero is accepted; a missing rain value is never converted to zero. The raw-hourly builder requires exactly 24 unique, ordered local timestamps and original units; partial days, off-hour timestamps and missing values are rejected.

Historical source replay independently reconstructs CHIRPS history and seasonal terms from the hash-verified source, reads validated full-day weather aggregates, and uses versioned database terrain values matching the selected source. The CBD2024 raw hourly slice independently verifies all ten daily weather features; source retrieval/extraction for every original hourly/raster record has not been re-executed. Underlying terrain reduction scripts/source metadata remain incompletely recovered, so the source CSV hash and declared years are preserved as provenance rather than inventing raster dates/resolution or an extraction method.

Targets are used only for historical evaluation: Extreme if next-day CHIRPS>=40 or seven-day rain ending next day>=150; otherwise High>=20/>=80; otherwise Moderate>=5/>=25; otherwise Low. No soil-moisture rule is in these v1 labels. Target-day CHIRPS and constructed target labels never enter runtime features. Training/refit target dates end2023; held-out target dates cover2024–2025 (5,848 zone-days).

## Native inference and compatibility

The application `.venv` retains its existing XGBoost2.0.3/sklearn1.4.2 pins and legacy artifacts. An isolated `.venv-model-v1` contains XGBoost3.1.3, NumPy1.26.4 and SciPy1.17.1. The worker uses the integrity-checked native model buffer with `Booster`; it imports no API settings, database, network client, joblib or sklearn. This avoids unpickling the selected wrapper and does not require the training Python3.13.5 environment for native inference.

The current application's older native library matched all classes but failed frozen-score tolerance (max error6.50e−6). The pinned isolated worker matches all5,848 classes with maximum absolute score error2.98e−8, within `rtol=atol=1e−6`. That measured comparison is the compatibility evidence; merely loading JSON is not sufficient.

Inputs are ordered explicitly. Outputs must have batch shape(n,4), finite numbers in[0,1] and each vector sum to1 within1e−6. No clipping, padding, class renaming or calibration is applied. Missing/corrupt/wrong-hash/wrong-schema/wrong-runtime models fail closed; isolated worker exceptions/timeouts are sanitized. The API can still serve legacy/public metadata and unavailable v1 states when v1 inference cannot execute.

## Output and failure semantics

| Field/status | Meaning |
| --- | --- |
| `model_task_type` | `next_day_proxy_risk`. Legacy rows retain their original current-condition contract on old endpoints. |
| `model_class_score` | Score of the highest-scoring proxy class; null if unavailable. |
| `proxy_class_scores` | Raw ordered Low/Moderate/High/Extreme scores; null if unavailable. |
| `flood_probability` | Always null. |
| `flood_probability_reason` | `NOT_CALIBRATED_TO_OBSERVED_FLOODS`. |
| `SUCCESS` | Research inputs/model validated and inference executed; no claim of operational forecast reliability. |
| `PARTIAL` | Some requested zones succeeded while others are explicitly unavailable. Each zone retains its own status. |
| `INSUFFICIENT_DATA` | Required source/terrain/history/full-day coverage, original availability or live parity missing; Unknown/no score. |
| `STALE_DATA` | Available inputs do not cover the required timely period; Unknown/no score. Historical replay is explicitly labelled historical, not masqueraded as live freshness. |
| `MODEL_UNAVAILABLE` / `FAILED` | Pinned artifact/runtime absent/incompatible or execution failed. No manufactured score or fallback class. |
| `freshness` | Successful replay uses `HISTORICAL_REPLAY`; live/stale/unavailable values remain visibly distinct. |
| `limitation_flags` | Proxy-only, uncalibrated, no inundation/water level, coarse/shared grids, approximate areas, static NDVI/land cover, unknown release time, unverified CHIRPS/EAT alignment and disabled emergency delivery. |

The public v1 dashboard defaults to live/unavailable state; replay requires explicit `mode=historical_replay` and an input date. A missing stored replay stays Unknown. The React application initially preserves its legacy view and provides explicit v1 live/replay selection; it never substitutes another view/date's last successful response. Administrative boundary fills are highest monitored proxy class summaries, not observed floods or predicted depth. Coincident model inputs are expected to produce identical scores and are not hidden.

## Additive API, persistence and access

`GET /api/v1/model` exposes pinned artifact status and actual stored proxy evaluation. `GET /api/v1/dashboard` provides explicit mode/date/status per configured zone. `GET /api/v1/predictions` exposes research history with filters; detailed routes/OpenAPI are generated from typed schemas. Admin-only `POST /api/v1/predictions/run` accepts validated research context/zone IDs/idempotency key, never user filesystem paths, training or deployment requests. Anonymous/unauthorized users cannot trigger it.

Companion tables retain versioned terrain provenance, execution/run identity, input/target/issue/actual execution times, source metadata, limitation flags, feature/artifact hashes and complete class scores. Repeated identical requests resolve to the existing immutable run; key reuse with different context is a409 conflict. Database constraints and PostgreSQL concurrency tests provide cross-worker safety. Zone results and their run commit atomically. Failed/blocked outcomes are explicit audit records; successful partial writes must not escape a rolled-back transaction.

No v1 run writes legacy `flood_predictions` or `alert_notifications`. Real emergency delivery is disabled. API startup does not create v1 tables or schedule v1 inference. Schema changes require an explicit transactional migration; rollback operates only on new tables, with nonempty history protected. See the runbook for exact commands and operational gaps.
