# Stage 1 live rainfall-risk rule (observed + forecast)

The public monitoring outlook (`GET /monitoring-areas/outlook`, contract
`monitoring-rainfall-outlook-v2`) scores each located monitored area for **tomorrow**
(the next complete Nairobi day) with the **v1 model's own label rule**, using inputs
that exist at request time.

## Why

v1 was trained on CHIRPS, published days to weeks late, so it can never run live. Its
label, however, is

| Class | Tomorrow's rain | or 7-day total ending tomorrow |
|---|---|---|
| Extreme | ≥ 40 mm | ≥ 150 mm |
| High | ≥ 20 mm | ≥ 80 mm |
| Moderate | ≥ 5 mm | ≥ 25 mm |
| Low | otherwise | |

On the 2016–2025 data, 90% of v1 labels (and 64% of High-or-above days) are already
determined by the six days of rain that have fallen before the forecast is issued. The
previous public rule used only tomorrow's forecast and ignored that accumulation.

## Inputs and timing (issue day *I*, target *I*+1)

| Component | Source | Window |
|---|---|---|
| Tomorrow | ECMWF IFS single run via Open-Meteo (existing point collection) | 24 h of *I*+1, EAT |
| Rest of today | Same run | 21 h from 00:00 UTC (03:00 EAT) on *I* to 00:00 EAT on *I*+1 |
| Observed antecedent | NASA GPM IMERG Early daily (`GPM_3IMERGDE` V07), native 0.1° cell of the pin | UTC days *I*−5 … *I*−1 |

The 7-day total is therefore 165 h (whole UTC days leave 3 h uncovered at the start,
making it very slightly conservative). The 36 located pins fall in six IMERG cells.

**Lower bound.** Rain cannot be negative. If observed days are not yet published, or the
selected run starts after 00:00 UTC on *I* (for example, the 12 UTC run used in the
evening leaves 12 hours uncovered), the sum of the available parts is a minimum.
The class is scored on that minimum. It can understate but never overstate. The output
sets `accumulation_complete=false`, method `observed_plus_forecast_rule_lower_bound`
and lists `fallback_reasons`. Missing rain is never reported as an observed zero.

## Operation

IMERG is collected automatically whenever forecast weather is collected: the admin
**Collect latest weather** button, `run_point_collection`, and the CLI below. Files are found
through NASA's public CMR catalogue (no credentials sent) and subset through **Earthdata
Cloud OPeNDAP** (`opendap.earthdata.nasa.gov`, DAP4 CSV, about 1.5 s per day), strictly one
request at a time with a 1 s pause. Days already stored are never refetched. Collection
failures never block the forecast collection.

Do not parallelise these requests. On 14 November 2026 six concurrent connections to the
older `gpm1.gesdisc.eosdis.nasa.gov` OPeNDAP host got this address blocked there. That
host was also slow (~20 s per request). Days stored from it keep their original DAP2 ASCII
response and still verify on read.

```powershell
.venv\Scripts\python.exe -m src.scripts.collect_imerg_early                 # days needed now
.venv\Scripts\python.exe -m src.scripts.collect_imerg_early --show 2026-11-14 # per-pin antecedent
.venv\Scripts\python.exe -m src.scripts.collect_imerg_early --start 2024-03-20 --end 2026-11-13  # backfill
```

Storage: `data/hotspots/imerg_early/` (or `IMERG_EARLY_STORE`). Each day has a raw
OPeNDAP response (`raw/<sha256>.txt`) and a parsed record (`days/YYYY-MM-DD.json`).
Records are re-verified against the raw bytes on every read.

**Credentials.** The server needs a NASA Earthdata account. Set `EARTHDATA_USERNAME` and
`EARTHDATA_PASSWORD` in the private environment file, or provide `~/.netrc` with
`machine urs.earthdata.nasa.gov`. `IMERG_EARLY_ENABLED=false` disables collection;
the outlook then reports lower bounds.

**Versions.** NASA switched recent files from V07B to V07C. The file name is read from the
directory listing, and the version is recorded per day. Watch for this shift in Stage 2
training.

## Limitations

- Rainfall-proxy conditions, not observed floods, calibrated probabilities, drainage or
  inundation. Terrain and land cover do not adjust the class.
- IMERG Early is a satellite estimate, not gauge-calibrated (it runs wetter or drier than
  CHIRPS on individual days). On 1 May 2024 both captured the event: CHIRPS 21–37 mm,
  IMERG Early 39–53 mm.
- Six IMERG cells and a few IFS grid points cover all pins, so nearby pins share values.
- No ML is involved. Stage 2 will train a model on the same live inputs and must beat this
  rule in season-blocked validation before replacing it.

Code: `src/api/services/imerg_early.py`, `src/api/services/rainfall_risk_rule.py`,
`src/api/services/point_outlook.py`, `dashboard/src/services/monitoringOutlook.js`.
Tests: `tests/test_rainfall_risk_rule.py`, `dashboard/tests/monitoringOutlook.test.js`.
