# Restored training data and daily proxy replay

25 October 2026. Follow-up evidence for issue #19 and the
[model input audit](model-input-audit.md). These results inspect the supplied
files and replay the daily proxy task. They do not establish street-level flood
accuracy or a future warning lead time.

## Files inspected

| File | Rows | First timestamp | Last timestamp |
| --- | ---: | --- | --- |
| `CHIRPS_Nairobi_2016_2026.csv` | 3,653 | 2016-01-01 | 2025-12-31 |
| `nairobi_weather_2016_2026.csv` | 87,696 | 2016-01-01 00:00 | 2026-01-01 23:00 |

Both files have ordered, unique, complete timestamp sequences and finite
required numeric values. All weather days contain 24 hours. No values are
imputed. The runner rejects gaps, duplicates, inconsistent CHIRPS date/index
keys, partial days and invalid measurements before evaluation. Raw CSVs remain
unchanged and ignored by Git. SHA-256 hashes, value ranges and all diagnostics
are recorded in [dataset-evaluation.json](dataset-evaluation.json).

The common daily period is **2016–2025**, comprising 3,653 days. The weather-only
day 2026-01-01 is excluded explicitly. The chronological partitions reproduce
the notebook's row counts: 2,557 training rows through 2022, 365 validation rows
in 2023, and 731 test rows in **2024–2025**. Class counts also match its saved
output: Low 2,682; Moderate 630; High 254; Extreme 87. Reconstructed training
feature min/max values match the frozen scaler.

## Spatial and temporal provenance

The user supplied [candidate export scripts](../data/provenance/candidate-export-scripts.md)
and said they **may** be the originals. Their requested date windows and columns
agree with the CSVs. This is supporting evidence, not verified export history.
The structured [candidate manifest](../data/provenance/training_sources.candidate.json)
is fingerprinted in each report.

Both weather and CHIRPS candidates sample a **single point near central
Nairobi**. They do not aggregate over Nairobi County or supply independent
records for the eight monitoring locations or 17 sub-counties. The export's
mean reducer is applied at a point. A reduction scale cannot turn that point
sample into local drainage measurements or observations everywhere on the map.

CHIRPS uses default UTC image-date formatting; the weather script requests
Africa/Nairobi time. The replay preserves the original calendar-date join and
flags that rainfall accumulation windows have **not** been reconciled. It does
not silently shift a daily rainfall total between timezones. The weather script
discarded returned units, grid coordinates, elevation and model metadata, so
the candidate defaults should not be confused with preserved response metadata.

The IMERG code is a separate export, absent from both the supplied inputs and
current model. Its deprecated V06 source ends in June 2024 and contains
half-hourly rates, despite the requested upper date in 2026. It is not merged
into this replay; see the linked candidate-script notes and provider references.

## What reproduced, and what did not

The daily feature construction, temporal partitions, class distribution and
scaler bounds can be checked against the actual source files. Saved notebook
**metrics were not reproduced exactly**.

| Test metric | Saved notebook | Frozen snapshot under application libraries | Diagnostic recipe refit with matching library versions |
| --- | ---: | ---: | ---: |
| Weighted recall | 0.7962 | 0.7921 | 0.7934 |
| Weighted F1 | 0.7746 | 0.7686 | 0.7727 |
| Weighted AUC-ROC | 0.8769 | 0.8745 | 0.8773 |

The application environment uses XGBoost 2.0.3 and scikit-learn 1.4.2. Loading
the frozen artefacts emits a legacy XGBoost serialization warning and a scaler
warning identifying scikit-learn 1.6.1. The serialized booster contains version
markers for XGBoost 3.4.1. These observations do not constitute a complete
original training-environment record.

An isolated directory containing **XGBoost 3.4.1 and scikit-learn 1.6.1** was
also tested, without changing the application dependencies. In that environment
the frozen snapshot fails to load with `XGBoostError: input stream corrupted`.
Therefore matching two library versions alone does not recover this snapshot.
XGBoost distinguishes stable native model files from pickle memory snapshots;
see its [model persistence guidance](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html).
The cause of the load failure and remaining score differences is not established.

The final table column is a **new, in-memory diagnostic fit**, using the
notebook's documented parameters, random seed, training-only scaler and class
weights. It is not an evaluation of the frozen snapshot, not a replacement
deployment model, and not a claimed accuracy improvement. Its full settings,
results and the frozen-load failure are in
[dataset-evaluation-matching-libraries.json](dataset-evaluation-matching-libraries.json).
Parallel execution and the otherwise unrecorded original environment also limit
exact replication claims.

Per-class recall and confusion matrices are retained, rather than relying only
on weighted scores. Under the application-library replay, High recall is
0.25 (20 of 80 High-labelled days), and Extreme recall is approximately 0.4516
(14 of 31 Extreme-labelled days). These are **proxy-label** outcomes. They do
not count detected or missed observed floods at T-Mall or elsewhere.

The runner includes a training-majority-class baseline. It also explains that
the direct threshold rule agrees perfectly with the labels **by construction**;
that agreement provides no independent evidence of forecasting skill.

## Reproduce the checks

With the original CSVs and trusted `.joblib` artefacts restored locally, run in
the application's existing environment:

```text
python -m src.scripts.evaluate_proxy_model --output docs/dataset-evaluation.json
python -m pytest tests/test_proxy_evaluation.py -v
```

For the separate library-version diagnostic, create an isolated environment.
PowerShell example:

```powershell
py -3.12 -m venv .venv-evaluation
.venv-evaluation/Scripts/python.exe -m pip install -r requirements-evaluation.txt
.venv-evaluation/Scripts/python.exe -m src.scripts.evaluate_proxy_model --reference-fit --output docs/dataset-evaluation-matching-libraries.json
```

The reference fit is opt-in, fits only training rows, and never exports a model.
Reports include source/artefact/notebook fingerprints, environment versions,
date ranges, baselines and explicit notebook comparisons. A frozen-load failure
still writes data and diagnostic results, then returns exit code **1**. This
is intentional: a successful reference fit must not conceal an unavailable
frozen model. No API or database is started, no network requests are made, and
no predictions or alerts are saved. The original CSVs/model files are not
included in a fresh clone; fixture tests need neither.

## Implications for the next change

- Recover or regenerate a portable model export in a controlled, documented
  environment and verify it against recorded predictions before promotion.
  Continue treating snapshot compatibility as unresolved.
- Define the actual prediction target and lead time, and reconcile daily
  accumulation windows and available-at-issue-time features before retraining.
- Use geolocated, timestamped and verified flood/non-flood observations plus
  local terrain/drainage evidence for a small pilot. More administrative
  polygons or point lookups cannot supply that missing evidence.

The restored data strengthens the audit trail. It does not resolve the
daily-training/hourly-serving mismatch or establish local flood probabilities.
