# Stage 2 live rainfall-risk model (guarded XGBoost)

The public monitoring outlook (`GET /monitoring-areas/outlook`, contract
`monitoring-rainfall-outlook-v3`) classifies each located area for **tomorrow** with a
small XGBoost model wherever its inputs are complete. Otherwise it uses the Stage 1 rule
([rainfall_risk_rule.md](rainfall_risk_rule.md)). The rule class is always reported
alongside (`rule_class`) as the explanation, and `model_status` says why the model did or
did not run (`APPLIED`, `INPUTS_INCOMPLETE`, `MODEL_UNAVAILABLE`, `MODEL_INPUT_REJECTED`,
`NO_FORECAST`).

## What it predicts

The v1 label, unchanged. **Extreme** if CHIRPS rain on the target day is ≥ 40 mm or the
7-day CHIRPS total ending that day is ≥ 150 mm; **High** 20 mm or 80 mm; **Moderate**
5 mm or 25 mm; otherwise **Low**. These are rainfall-proxy risk conditions, not observed
floods or flood probabilities. CHIRPS is used only as the label, never as an input.

## Inputs (19, all available at issue time)

`src/modeling/stage2/features.py`, one function for training and live use:

- **Tomorrow (ECMWF IFS forecast):** total rain; maximum 1, 3 and 6 h rain; rainy hours;
  mean humidity, temperature and soil moisture; maximum wind.
- **Rest of today (forecast):** rain total.
- **Observed (NASA IMERG Early, UTC days *I*−5 … *I*−1):** yesterday, 3-day and 5-day
  totals.
- **Combined:** the 7-day total and the Stage 1 rule levels.
- **Calendar:** target month (sine/cosine).

No terrain or zone identity. On v1 data they added nothing beyond a zone label
(macro F1 0.640 with, 0.642 without), because each zone has one fixed value.

## Training data

| | |
|---|---|
| Forecasts | 924 archived ECMWF IFS 00 UTC single runs (Open-Meteo), 20 Mar 2024 – 29 Sep 2026, 8 zones (`src/scripts/fetch_stage2_forecasts.py`) |
| Observations | IMERG Early daily, 15 Mar 2024 – 28 Sep 2026 (`src/scripts/collect_imerg_early.py`; V07B, and V07C since late 2025) |
| Labels | CHIRPS 2016 – 30 Sep 2026: the v1 file plus a verified 2026 extension (`notebooks/export_chirps_extension_colab.py`, `src/scripts/prepare_chirps_labels.py`) |
| Rows | 7,384 zone-days (Low 5,268 · Moderate 1,137 · High 667 · Extreme 312, on 56 distinct Extreme dates); 8 rows skipped for a missing forecast hour |

Model: XGBoost `multi:softprob`, 300 trees, depth 3, learning rate 0.05, balanced class
weights, fixed in advance with no tuning. Trained with XGBoost 2.0.3, the same version as
the application, so it runs in the API process.

## Evaluation (`python -m src.modeling.stage2.train`, report `data/stage2/evaluation.json`)

The protocol was written in the code before any result. Primary metric: zone-day
High-or-above CSI, leave-one-season-out (10 seasonal blocks), checked with a date-cluster
bootstrap. Adopt only if the gain is positive, its 95% interval excludes zero, and Extreme
recall drops by no more than 0.05.

| Held-out seasons | High+ CSI | High+ detected | High+ false alarms | Extreme detected | Extreme false alarms | Low→Extreme |
|---|---|---|---|---|---|---|
| Old tomorrow-only rule | 0.060 | 6% | 54% | 0% | — | 0 |
| Stage 1 rule | 0.394 | 45% | 24% | 30% | 32% | 0 |
| XGBoost (pre-registered) | 0.524 | 70% | 33% | 32% | 57% | 24 |
| **XGBoost + guard (live)** | **0.524** | 70% | 33% | 29% | 41% | **0** |

- **Pre-registered decision: adopt.** The CSI gain is +0.130 (95% +0.077 … +0.186), and
  Extreme recall did not drop.
- **Forward-only check** (training only on earlier seasons): XGBoost CSI 0.472 vs rule 0.388.
- XGBoost was better in 7 of the 9 seasons with events. It scored worse in June–September
  2025 (0 vs 0.18; few events).
- **1 May 2024 (UNOSAT flood day):** both the rule and the model gave Extreme for all 8 zones.

**Guard (post-hoc, decided after seeing the results; reported separately):** the model may
show Extreme only if the Stage 1 rule reaches at least High; otherwise Extreme becomes
High. It keeps the whole High-or-above gain and removes every Low→Extreme false alarm.

**Why it helps:** the rule under-calls High (367 of 667 High zone-days rated Moderate),
because IMERG Early usually reads lower than CHIRPS. The model learns that offset.

## Runtime safety

`src/modeling/stage2/runtime.py` refuses the package, and the rule stays live, if the
model hash, feature contract, class order or XGBoost version differ from
`models/stage2-rainfall-risk/manifest.json`, or if the manifest does not record an
adopted evaluation. Live features are rebuilt from the verified weather receipt with the
same feature function. A test checks they equal the training features for the same
forecast. The rebuilt rule level must also match the Stage 1 context. The frontend
re-derives the rule class, checks the scores and the guard, and rejects any mismatch.

Settings: `STAGE2_MODEL_ENABLED` (default true) and `STAGE2_MODEL_DIR` (default
`models/stage2-rainfall-risk`, 1.4 MB, deployed with the repository).

## Retraining (monthly, as CHIRPS publishes)

```powershell
# 1. Colab: run notebooks/export_chirps_extension_colab.py, download the CSV into data/stage2/
.venv\Scripts\python.exe -m src.scripts.prepare_chirps_labels
# 2. Extend forecasts and observations to the new last label day (already-stored days are skipped)
.venv\Scripts\python.exe -m src.scripts.fetch_stage2_forecasts --start 2024-03-20 --end <last-day-minus-1>
.venv\Scripts\python.exe -m src.scripts.collect_imerg_early --start 2024-03-15 --end <last-day-minus-2>
# 3. Re-run the pre-declared evaluation and retrain
.venv\Scripts\python.exe -m src.modeling.stage2.train
```

The export script must start its overlap on 1 December 2025. For later extensions,
change `EXPORT_START` in the script and the expected file-name prefix in
`prepare_chirps_labels`. The newest merged label file is used automatically.

If the new evaluation does not pass, the package is written to
`models/stage2-rainfall-risk-rejected/` and the live package is untouched. A passing
retrain replaces it; restart the API to load it.

## Limitations

- Training used 00 UTC runs of the issue day. In the morning, the live system may use the
  previous day's 12 UTC run (12 h longer lead). In the evening the issue-day forecast is
  incomplete, so the rule applies.
- 56 distinct Extreme dates: Extreme-class behaviour is still unstable (preliminary runs
  ranged from 6% to 32% recall) and should improve with monthly retraining.
- The 8 labelled zones share a few forecast and satellite grid cells. Applying the model
  to the 36 monitoring pins assumes the same rainfall-to-label relationship nearby.
- No terrain, drainage or observed flooding: the output is a rainfall-risk category, not a
  flood forecast.
