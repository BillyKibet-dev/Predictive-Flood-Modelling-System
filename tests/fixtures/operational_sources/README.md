# Public IFS shadow-collector fixtures

These are two **real, unmodified HTTP response bodies** collected by the manual
NairobiFloodWatch shadow collector on 8 November 2026, shortly after 00:21
Africa/Nairobi (7 November 21:21 UTC). No model inference occurred.

`index.json` points to the content-addressed readiness documents. Each document
references its immutable request/provenance capture and original raw body. The
same relative layout works with `LocalEvidenceStore`; tests require neither the
locally ignored audit files nor PostgreSQL, credentials or network access.

- `available_12utc`: explicitly selected `ecmwf_ifs`, 7 November 12:00 UTC run,
  HTTP 200, eight existing public monitoring coordinates. The following-day
  target for the candidate 8 November 06:00 EAT issue is 9 November, physically
  00:00 through 10 November 00:00 EAT. All required target windows are complete.
  Initial precipitation is genuinely null at 7 November 15:00 EAT; it is outside
  that target and remains null. Source quality is PARTIAL, target QC PASSED.
- `unavailable_18utc`: explicit 7 November 18:00 UTC run, HTTP 400 because that
  run was not available at receipt. Error bytes and timestamps are retained.
  No fallback or retry occurred within either collection.

Exact timestamps, requested/returned grids, elevations, variables, units,
physical intervals and hashes live in the capture/readiness documents. These
are numerical weather forecasts, not ground-station measurements or flood-risk
predictions. The request is the model/run identity basis; no independent run
identifier or original publication timestamp was returned. HTTP Date is retained
only as an HTTP header. One successful receipt is not a reliability study.

Weather data by [Open-Meteo.com](https://open-meteo.com/), upstream ECMWF IFS.
API data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/);
[provider licence and attribution](https://open-meteo.com/en/licence).
Original response bytes are unchanged. NairobiFloodWatch added the request,
storage and diagnostic metadata. The providers do not endorse these diagnostics.
This collection used bounded non-commercial academic access under the
[service terms](https://open-meteo.com/en/terms).

Only public weather data and the eight public study coordinates are included.
There are no API keys, cookies, database URLs, personal accounts or citizen
reports. Controlled changes made by rejection tests exist only in memory or
temporary test directories and are not presented as actual provider captures.
