# Model input and spatial capability audit

Recorded 25 October 2026. First implementation step under issue #19; the issue
remains open for local data collection, retraining and validation.

After this initial artefact inspection, the user restored both training CSVs
and supplied candidate source scripts. See the
[dataset replay report](dataset-evaluation.md) for source fingerprints, actual
coverage, observed metrics, and the separate snapshot compatibility failure.
The baseline below remains the record of the initial inspection.

## Current capability

The packaged v2 classifier produces a **shared Nairobi weather-based risk
indication**. Its labels describe rainfall/soil-moisture threshold classes.
Street flooding, drainage blockage, flood depth and a future warning lead time
have not been validated. A model score is an uncalibrated class score, not an
established probability of flooding at a coordinate.

The eight monitoring records and 17 sub-county polygons are a presentation and
reporting structure. The pipeline supplies one shared weather feature row; it
now runs inference once and copies that result to the existing zone records.
Sub-county colours summarise available records. Administrative boundaries do
not create additional model resolution. A lookup near T-Mall can identify its
administrative area; this model cannot establish that road junction's risk.

## Reproduce the inspection

With the normal Python dependencies and trusted artefacts in `models/`:

```text
python -m src.scripts.audit_model
python -m src.scripts.audit_model --output docs/model-audit-baseline.json
```

The command hashes artefacts and the notebook, checks feature order/model/scaler
dimensions and classes, records dependency versions/load warnings, and extracts
saved notebook evidence. It executes no notebook cells, makes no weather
requests, and connects to no database. `--model-dir` and `--notebook` select
alternative local inputs. Exit code 0 means the inspection completed and the
structural artefact contract matched; `audit_status: review_required` explicitly
does not certify forecasting accuracy. Missing/incompatible artefacts return 1.

The committed [baseline](model-audit-baseline.json) identifies the inspected
local files. Model `.joblib` files and the original CSVs are ignored by Git and
are **not included in a fresh clone**. These hashes identify today's inspected
files; there is no training-time manifest proving that the saved notebook
outputs were produced by those exact files.

## Final input contract

`models/feature_cols_final.joblib` and the model/scaler all agree on nine inputs,
in the following order. Latitude, longitude, sub-county, slope, NDVI, impervious
surfaces and drainage are absent from the final feature list.

| Feature | Notebook computation | Live computation after this change |
| --- | --- | --- |
| `delta_water_level` | Consecutive daily runoff-index difference from CHIRPS rainfall and daily mean soil moisture | Today-so-far versus yesterday's runoff index, using current and previous-day mean soil moisture |
| `temperature_2m` | Daily mean | Latest hourly value; Celsius requested |
| `relative_humidity_2m` | Daily mean | Latest hourly value; percent |
| `wind_speed_10m` | Daily mean; original CSV unit metadata is unavailable | Latest hourly value; km/h requested explicitly |
| `is_long_rains` | Month in March–May | Derived from Nairobi weather timestamp |
| `is_short_rains` | Month in October–December | Derived from Nairobi weather timestamp |
| `day_of_year` | Date's day number | Nairobi weather date's day number |
| `month` | Date's month | Nairobi weather date's month |
| `soil_moisture_0_to_7cm` | Daily mean | Latest hourly value; m³/m³ |

Missing/non-finite required inputs are rejected. The feature order, dimensions,
class order, physical ranges and seasonal flags are checked. No temperature,
rainfall, soil-moisture or calendar defaults are inserted to manufacture a row.
Training min/max values are recorded in the baseline for inspection; live values
are not silently clipped to those ranges.

The runoff index reproduces the notebook formula with fixed slope `3.63` and
impervious parameter `0.72`. These constants are not local terrain measurements.
The index is not measured water depth. The old runtime also fixed soil moisture
at `0.5` inside this formula; it now uses the supplied current/previous-day
moisture. Daily-versus-hourly differences remain, as shown above.

## Labels and evaluation evidence

The notebook assigns **same-day** labels in descending order:

| Class | Rule |
| --- | --- |
| Extreme | Daily rainfall ≥ 40 mm OR seven-day rainfall ≥ 150 mm |
| High | Daily rainfall ≥ 20 mm OR seven-day rainfall ≥ 80 mm |
| Moderate | Daily rainfall ≥ 5 mm OR seven-day rainfall ≥ 25 mm OR soil moisture > 0.70 |
| Low | Remaining rows |

These are notebook rules. Their stated attribution to KMD criteria has not been
independently verified by this audit. They are not observed flood/non-flood
outcomes at specific locations. Removing rainfall column names does not remove
rainfall information: `delta_water_level` is calculated from the same rainfall
source used to construct labels. Agreement with these labels cannot establish
independent flood-event forecasting skill.

Saved notebook output records 3,653 merged daily rows from **2016-01-01 through
2025-12-31**: 2,557 training rows through 2022, 365 validation rows in 2023, and
731 test rows covering 2024–2025. Some headings/report dictionaries say
2024–2026 or end in December 2026; the saved date range does not support that.

| Metric | Previous API fallback | Saved notebook test output |
| --- | --- | --- |
| Weighted recall | 0.7880 | 0.7962 |
| Weighted F1 | 0.7790 | 0.7746 |
| Weighted AUC-ROC | 0.8732 | 0.8769 |

Neither column was recomputed during this audit. The API fallback has been
removed rather than replacing it with unverified notebook numbers. Missing or
malformed `models/model_report_final.json` produces HTTP 503. The existing admin
chart is labelled as demo metrics; its API integration remains a separate task.

Further evidence limitations:

- Missing values are interpolated and filled using full-data medians **before**
  the chronological split. This can contaminate evaluation. The scaler itself
  is fitted on training rows only; those are separate operations.
- `TimeSeriesSplit` is imported, but the committed training cells do not execute
  the five-fold cross-validation claimed by report text. Training uses fixed
  parameters and class weights. SMOTE is not used by these cells.
- Duplicate report/export cells contain different hard-coded claims and
  variable names. Saved outputs can be stale; the notebook must be rerun in a
  controlled environment with the original inputs before publishing metrics.
- The scaler was serialized with scikit-learn **1.6.1**, while requirements and
  the inspected environment use **1.4.2**. XGBoost also warns about legacy
  serialization. Structural compatibility checks do not resolve version
  compatibility; a matching environment and reviewed re-export are still needed.

## Runtime corrections and remaining mismatch

The live request now gets yesterday and today from the same forecast endpoint
using `past_days=1`. It validates units, ordered unique hours, current-hour data,
all required rainfall hours and all 24 previous-day soil-moisture values. Future
hours are excluded. Missing precipitation is not replaced with zero, and an
unavailable previous day is not treated as a dry day. Calculations use Nairobi
time and the weather timestamp, independently of the server timezone.

This avoids relying on a potentially delayed reanalysis archive for yesterday.
Open-Meteo documents both the recent-history option and reanalysis delays in its
[Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api).
Explicit units and forecast variables follow its
[forecast API specification](https://github.com/open-meteo/open-meteo/blob/main/openapi/forecast.yml).

**These corrections do not establish training/serving parity.** Training uses
complete daily means and daily CHIRPS rainfall, while serving still uses hourly
weather and partial-day Open-Meteo rainfall. This must be resolved together with
an explicit target/lead time and a new evaluation; simply substituting inputs
does not justify a new accuracy claim. Preprocessing should be fitted inside
training splits, following the
[scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).

Missing model files now disable prediction instead of returning mock Moderate.
Input/inference failures write no new predictions or alerts, leaving previous
data to become stale visibly. The dashboard returns Unknown/null when no
prediction exists, without inventing a last-updated time. `/dashboard`, `/health`
and pipeline summaries declare shared spatial scope, current-condition timing,
proxy labels and uncalibrated scores. Public map/citizen/officer views explain
that scope and label confidence values as **Model score**. Citizen guidance
describes weather indications; the model alone no longer issues an evacuation
instruction or describes Low as proof that conditions are normal.

Existing prediction history is retained. Old rows do not record enough input
provenance to retrospectively identify placeholder/imputed runs. These checks
protect future writes; they do not validate previously saved predictions. New
rows use serving version **`v2_final_inputs_v1`** to distinguish this input
pipeline from older `v2_final` rows; the model weights are unchanged. `/health`
reports the same serving version.

## Follow-up order under issue #19

1. Retrieve `CHIRPS_Nairobi_2016_2026.csv` and
   `nairobi_weather_2016_2026.csv` from the user's Google Drive `Project Dataset`
   folder. Record source metadata, checksums, actual dates, units and gaps;
   filenames alone are not evidence of coverage. Preserve an untouched copy.
2. Define the next target and lead time. Align available-at-issue-time features,
   split before fitting preprocessing, compare against a simple threshold
   baseline, and reproduce results with a matching artefact environment.
3. Add geolocated, timestamped incident reports and a verified hotspot register.
   Keep historical susceptibility, reported incidents and model indications
   distinct. Absence of a report is not proof of no flooding.
4. Pilot a small area such as the T-Mall surroundings, with verified drainage,
   terrain/flow paths, land cover, rainfall and observed outcomes. Additional
   coordinates or smaller polygons alone cannot supply missing local evidence.
5. Evaluate on withheld storms and locations, measure missed floods/false
   alarms/lead time, and calibrate probabilities against the defined outcome.
   Benchmarking, final export, the model card and deployment follow that work.

No new location-specific accuracy or improved model performance is claimed by
this first PR.
