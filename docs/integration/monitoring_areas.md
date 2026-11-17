# Monitored areas

The main map is the primary monitoring interface. **Monitored areas** opens a
compact zone filter and location search; selecting a record focuses its mapped
reference and opens details on the map. There is no separate Hotspots tab.
Existing `/hotspots?site=NFW-S037` links redirect to `/?area=NFW-S037`.

## Coordinate import and parent zones

The user-supplied `NairobiFloodWatch_Hotspot_Coordinate_Lookup_v0_2.zip` contains
40 records: 28 place/landmark references and 12 unresolved locations. Original
ZIP SHA-256: `d87bbc2c82e8fc35c563ea57c01012bcbaf8919d1466f056d20a23f487f23de8`.
The original bytes, CSV and import receipt are preserved locally.

Two previously reviewed OSM references are retained, including the Kenyatta/Moi
junction unresolved in the new attachment. T-Mall uses a local observer's
specified point: **1°18′39.4″S 36°49′01.8″E**, converted to WGS84
**−1.310944444, 36.817166667** (latitude, longitude). It falls within the stored
Langata polygon. `USER_REPORTED_LOCATION` records personal observations of
recurring flooding; event dates, measured depth and surveyed accuracy are unknown.
The previous roundabout coordinates and attributes remain in `location_history`.
The declarative input is `src/api/data/monitoring_area_location_updates.json`.
Uhuru Highway uses the user-selected coordinate **1°17′39.5″S 36°49′17.0″E**,
or **−1.294305556, 36.821388889** (latitude, longitude). The stored polygon
assigns it to **Kibra**, which needs review against current official boundaries.
It remains distinct from the historical Uhuru/Kenyatta-junction evidence. A new
pin is not interpreted as a new confirmed incident. Both previous locations and
their attributes remain in `location_history`.
The result was **29 mapped area records, 27 physical map pins and 11 unresolved
records**. Two pairs share neighbourhood references; these use one pin with
multiple selectable records, without jitter or fabricated coordinates.

### Location review, 15 November 2026 (current inventory)

The user located 7 of the 11 unresolved records and supplied their coordinates.
They are recorded in the same `monitoring_area_location_updates.json` file
(`USER_REPORTED_LOCATION`, `field_verified: false`, no event date or depth):

| Record | Display name | Supplied (DMS) | WGS84 lat, lon | Parent zone |
|---|---|---|---|---|
| NFW-S008 | Mukuru Kwa Reuben Feed the Children zone | 1°18'57.2"S 36°52'09.0"E | −1.315889, 36.869167 | Embakasi South |
| NFW-S010 | Mukuru Kwa Reuben Cosovo area | 1°18'36.7"S 36°52'58.4"E | −1.310194, 36.882889 | Embakasi South |
| NFW-S013 | Mukuru Kayaba area | 1°18'47.9"S 36°50'57.1"E | −1.313306, 36.849194 | Starehe |
| NFW-S016 | Infinity, Kasarani | 1°13'26.9"S 36°54'48.4"E | −1.224139, 36.913444 | Kasarani |
| NFW-S019 | Mwengenye, Njiru | 1°15'11.3"S 36°55'02.8"E | −1.253139, 36.917444 | Kasarani |
| NFW-S021 | Gatwekera Sokomoko | 1°18'54.4"S 36°46'56.9"E | −1.315111, 36.782472 | Langata |
| NFW-S032 | Gumba Bridge | 1°15'43.0"S 36°51'37.4"E | −1.261944, 36.860389 | Mathare |

The four records the user could not locate were **removed** from the served
inventory: NFW-S009 (Mukuru Kwa Reuben Kariobangi Zone), NFW-S017 (Gachieko, Ruai),
NFW-S029 (Utalii 4A) and NFW-S036 (Kitisuru households along Kibagare Dam). They are
listed under `removals` in the updates file and `removed_records` in the catalogue;
the original v0.2 package and base catalogue still contain them. Only unlocated
records can be removed this way.

**Current inventory: 36 records, all mapped, at 34 physical pins** (Dandora Area 3
and Gatwekera Riverside / Kwa Mwangi still share pins), in 12 parent zones. Terrain
was recomputed for the new points (35/36; Gituamba, Ruai is still outside the cached
elevation tile), and NDVI and land cover cover all 36 points. The public outlook,
point weather collection and Stage 2 model apply to all 36. Catalogue SHA-256:
`e01c2e7cb744dd64db0c55829650fd3416b6f134203e1335ebe4ca23d719d7c9`; enrichment SHA-256:
`591f66727d4065a34284727e35af725f22560be5af0e0521f925b1b109711524`. Older
counts later in this runbook describe the inventory at the time they were written.

### Sub-county boundaries and the public map, 15 November 2026

**Boundaries.** The packaged county and 17 sub-county (constituency) outlines now come
from OpenStreetMap, the same source as the basemap, so they line up with it. The
previous geoBoundaries 2020 layers had three problems:

- They sat 250–800 m north of the basemap. Kibra overlapped OSM's Kibra by only 64%.
- The county line came from a different dataset than the sub-counties, so the two
  disagreed by up to 3 km.
- Kibera's Gatwekera and Soweto West villages fell in Langata, Uhuru Highway in Kibra,
  and the outlines used old names ("Kilimani" for Dagoretti North, "Dagoretti" for
  Dagoretti South).

`python -m src.scripts.prepare_osm_boundaries data/boundaries/source/osm_nominatim_lookup_2026-11-15.geojson`
rebuilds both files from the saved Nominatim response (`--fetch` requests it again). It
refuses to write unless:

- every outline is valid;
- the 17 sub-counties have no overlaps or gaps;
- together they equal the OSM county outline.

Shared borders are simplified together, at most 3.3 m, so neighbours keep identical
edges. The county outline is the union of the sub-counties. After a change, run
`python -m src.scripts.load_boundaries`, which now also removes renamed or retired
outlines from PostGIS. OSM boundaries are community-mapped, not an official survey.

Ten monitored records changed parent zone, all corrections:

- Uhuru Highway moved to Starehe.
- Kawangware moved to Dagoretti North.
- The Gatwekera and Soweto West records moved to Kibra.
- Mathare 4A, Mathare North and Kasabuni moved to Ruaraka. Mathare North is a Ruaraka
  ward.

Points are classified individually from their own forecast grid cell and satellite
rainfall cell. The sub-county is used only for grouping and filtering. The Stage 2
model has no zone input.

**Public map.** Pins are coloured by tomorrow's rainfall-risk category (Low green,
Moderate yellow, High orange, Extreme red). They are grey when no fresh outlook exists,
and the outlook expires after 6 hours. A shared pin shows its highest category.

The legend gives the target day, counts per category, the update time and the warning
that these are rainfall categories, not flood warnings.

Selecting an area first shows a short summary: the category, one plain sentence about
the rain, cautious advice, official-warning guidance for High and Extreme, and a report
link. Rainfall components, model details, terrain, vegetation, land cover and history
are under **More details**, which is open by default for signed-in staff. Evidence
SHA-256 hashes are shown to staff only.

Current hashes: catalogue
`f0dcd9bddfb8957d4271285259599aee6952b35fb48df9c05d2e94d63c9fc016`, enrichment
`f7859dcdedf4301b5e8696dcd65dc338d52d127481975bff30ba4a9d262228b2`.

Every mapped record has `parent_zone_id`, `parent_zone_name` and
`parent_assignment: REFERENCE_POINT_SPATIAL_JOIN`. These come from point coverage
by the repository's 2020 administrative polygons. T-Mall is under **Langata**;
Gikomba's supplied reference is under **Kamukunji**, independent of the original
CBD inventory grouping. Twelve parent polygons contain the current references.
These are assignments against the stored boundary version, not independently
verified current administrative boundaries. Unlocated records retain tentative
groups (`review-*`) with `INVENTORY_GROUP_PENDING_LOCATION`.

`inventory_group` and the complete `coordinate_lookup` row preserve original
grouping, source URLs, review notes and coordinate status. The existing `zone_id`
is retained solely for legacy compatibility; new geographic classification uses
`parent_zone_id`. No model-zone seed, database row, feature contract or saved
prediction is changed. Geographic parent assignment does not create model output
for a new zone.

Neighbourhood, related-school and reservoir coordinates are displayed using the
actual matched feature name. For example, **South C suburb** is the map label;
the historical electrical-substation record remains in the source context.
The point does not locate that substation. Dashed pins indicate approximate
place references. No record claims a field-verified flood point, current flood
state, calibrated probability, inundation extent or depth.

## Geographic context and evidence

The original source inventory, historical press reports, warnings and provenance
are preserved. Original `src/api/data/hotspots.json` and its read-only API remain
available for rollback compatibility; the UI reads the new catalog exclusively.
All existing raw public-source requests retain actual receipt times and hashes.

- Elevation/slope are computed from the locally captured Copernicus GLO-30
  S02/E036 surface tile at each supported coordinate. **28 records** have terrain
  context; Gituamba lies in the adjacent E037 tile and remains unavailable.
  No additional download was needed. Horn slope uses a native 3×3 window with
  WGS84 metre spacing. Buildings and vegetation affect this ~30 m DSM.
- Four genuine Sentinel-2 NDVI samples are now available: two unchanged original
  references plus new B04/B08/SCL requests at the updated T-Mall and Uhuru points.
  Both updated samples have SCL 5 and use the verified 12 August 2026 scene,
  quantification 10000 and band offsets −1000. Their NDVI values are 0.08518 and
  0.12607 respectively. Earlier samples remain only in location history.
  New references have no invented or copied NDVI. The dated scene,
  actual reflectance offsets, SCL checks and raw hashes remain in their profiles.
- A bounded official OSM extract was retrieved around the new Uhuru coordinate.
  Its mapped-waterway context and T-Mall's context were calculated at their exact
  updated pins. Across the catalog only two records have mapped-waterway context;
  one reviewed extract contains no mapped waterway, and the rest are unavailable.
  Missing OSM mapping does not establish absence of actual roadside drains.
  New locations
  have no invented drainage capacity, blockage or measured condition.
- Full source attribution and original coordinate precision limitations are
  preserved in `src/api/data/monitoring_areas.json`.

## Historical nearby-water references

Each area profile now includes a collapsed **Historical nearby-water reference ·
1 May 2024** section. The supplied v0.3 GIS package and local original UNOSAT
3834 archive were independently checked; native source hashes also match the
existing historical archive used by the application. This is one scene, not a
new independent validation event. Raw historical geometry and the existing map
layer remain unchanged; no buffers are presented as flood extents.

Distances, clear analysis coverage and water area are recomputed from authentic
native shapefiles at the **current** map coordinates. Source-package statistics
are not transferred across moved pins. Five references have mapped water within
250 m and four at 250–500 m; fifteen current references are outside scene
coverage, one is in cloud, four have no mapped water in the 500 m search window,
and eleven are unlocated. T-Mall's new pin remains outside the scene; distance
and water area there are null, not evidence of flood absence.

`nearby_water_reference` preserves coordinates, acquisition time, source URL,
native archive/package hashes, search radius, method and limitations. A 500 m
window is an exploratory reference search, not a site boundary. Overlapping
windows and patches cannot be summed as independent floods or area estimates.
`confirmed_flood_free`, `actual_incident_point` and `verified_flood_boundary`
remain null; `operational_use_allowed` is false. No training target, risk class,
forecast, alert or public hazard polygon is generated from this evidence.

## API, deployment and reproduction

`GET /monitoring-areas` returns all area records, parent-zone summaries and source
metadata. Optional filters: `parent_zone_id=nairobi-subcounty-langata` and
`located=true|false`. `returned_count` describes the filtered records; summaries
describe the complete inventory. Unknown parent zones return 422; missing or
corrupt evidence returns 503 without substitute locations. There are no writes.

Deploy `src/api/data/monitoring_areas.json` with the API. Its SHA-256 is pinned in
`monitoring_area_service.py`. Restart the backend for the new route; rebuild or
reload the dashboard. No migration, seed operation, GIS runtime dependency or
network access is needed to serve the compiled catalog.

For offline reproduction, restore the ignored `data/hotspots/` backup, including
original ZIPs, `original/hotspot_inventory_v1.json`, public-source captures and
the isolated optional GIS dependencies. The original base catalog hash is checked
before import. Receipts distinguish user-supplied imports from network retrieval.
The native satellite archive is also preserved in the local content-addressed
evidence store. Use that file or the unchanged original download as the archive
argument below. `pyshp` is available in the bundled optional
`data/hotspots/gis_dependencies` preparation environment; the API needs no GIS
libraries. The preparation process selects its matching rasterio PROJ database,
without changing persistent environment configuration.

```powershell
.venv/Scripts/python.exe -m src.scripts.prepare_monitoring_areas data/hotspots/original/NairobiFloodWatch_Hotspot_Coordinate_Lookup_v0_2.zip --nearby-water-package C:/Users/ryank/Downloads/NairobiFloodWatch_Hotspot_GIS_Verification_v0_3.zip --unosat-archive C:/Users/ryank/Downloads/_static_unosat_filesystem_3834_FL20240426KEN_SHP.zip
.venv/Scripts/python.exe -m pytest tests/test_monitoring_areas.py tests/test_hotspots.py -q
```

The same inputs and saved import receipt reproduce the same catalog bytes. A
reviewed data revision requires updating the hash pin. Original archives and the
base catalog are never overwritten. This import performs no collection,
inference, model training or database changes.

## Verification

- Full backend suite: 533 passed, 81 skipped by optional integration/environment
  gates; one existing model-refit test explicitly excluded. No model training ran.
- Area/inventory backend checks: 42 passed, covering source identity, correct
  latitude/longitude order, native polygon joins, T-Mall/Langata, shared points,
  unresolved records, supported attributes, corrupt inputs and read-only APIs.
- Frontend unit suite: 97 passed. Production build passes; the existing large
  bundle warning remains.
- Headless Chrome: 29 workflow checks cover both user-supplied coordinates,
  recomputed context and new-coordinate NDVI, as well as removal of the tab,
  neutral area pins, parent-zone filtering, keyboard access, shared-reference
  selection, mobile details, API failure/retry and old-link redirection, alongside
  existing reporting, authentication, research and administrative workflows.
  Browser mutations use controlled fixtures, not production writes.
- The running local API was refreshed through its existing reload watcher and
  `/monitoring-areas` returned HTTP 200 with both new coordinates and new NDVI
  values. No scheduler or inference was activated by that refresh.
- Historical UNOSAT browser regression: 12 checks passed with real stored
  satellite evidence and basemap tiles.

Next refinement: check the supplied neighbourhood references against local
knowledge/field pins and review boundary assignments before defining precise
subareas or using them for location-specific model classification.

## Point-model readiness and next implementation workstream

The experimental v3 short-horizon nowcast (3/6/24 h runoff-proxy classes for the
original eight zones) was retired on 14 November 2026. A fixed-run comparison over
23 April–6 May 2024 showed limited transfer to genuinely available forecast runs, so
its code, routes, table and scheduler setting were removed. The trained package and
evaluation data are preserved outside the repository under
`../.local-archives/nowcast-v3-retired-20261114/` as historical research evidence.
No current monitored-area output depends on it.

The following bounded workstream was implemented on 12 November 2026; its
remaining scientific requirements are unchanged. It produces one consistent, source-linked
point-feature table and a collection-only weather join for a small set of
confirmed monitored locations. Current coverage is 29 mapped records, 28 terrain
profiles and four dated NDVI samples; measured drain capacity/condition is absent.
Record raster support/resolution, scene date, quality, native weather grid and
shared-grid associations. Populate missing attributes only from verified inputs.

Pair dated, located flood/non-flood observations with eligible historical weather
before proposing a point-level trained classifier. Neither a new feature table
nor one UNOSAT scene supplies that evaluation dataset. Changing feature spatial
support or adding drainage requires a separately versioned training/inference
contract and chronological evaluation against the existing forecast-rule
baseline. Existing models, labels and schedulers must remain unchanged until
that work is approved and its evidence supports activation.

## Point feature table and collection-only weather connection

`src/api/services/monitoring_point_features.py` defines the separate
`monitored-point-context-v1` data contract. This is a geographic context table,
not the frozen v1/v2/v3 model interface. `GET /monitoring-areas/features` exposes
40 consistent records with coordinate order, actual parent assignment, units,
explicit missing fields and the existing source profiles (hashes, receipt times,
scene dates, resolution, extraction methods and quality). There are 29 located
records, 28 terrain profiles, four quality-accepted dated NDVI values and two
mapped-waterway profiles. These are available-data counts, not complete model
readiness. Unlocated and unsupported attributes remain null. All records carry
`model_ready=false`.

Land-cover fractions, measured drain capacity, condition and blockage are
unavailable. Distance to a mapped river/culvert remains a contextual distance;
it is not a measured drainage-capacity feature. DEM surface slopes and the
August 2026 Sentinel pixels must not be represented as the old model's original
terrain/2023 vegetation summaries or as historically available predictors.

`src/scripts/collect_monitoring_point_weather.py` issues one explicit-run request
for four directly selected points: Kenyatta/Moi junction, updated Uhuru Highway,
Mathare North Primary School and updated T-Mall. It reuses the immutable local
evidence store and the existing pure source-quality checks while leaving the
eight-zone collector and PostgreSQL schema unchanged. The client allows one
request, no redirects or automatic retries, 10/30-second connect/read timeouts
and a 2 MiB retained-body cap. Identical requests reuse the saved receipt,
including failed attempts; no implicit replacement or retry occurs.

Successful reads recheck raw/capture/receipt hashes, catalogue identity, exact
requested coordinates, request/run identity, response order/location IDs,
returned grid bounds, units, finite values, timeline coverage and actual receipt
ordering. Malformed sources are withheld, and individual failed point windows
remain unavailable. The physical next-day Nairobi rainfall window uses the
24 preceding-hour amounts labelled 01:00 through the following 00:00. An amount
at the first day's 00:00 belongs to the preceding hour and is excluded. No
missing-to-zero conversion, hourly-rate conversion or forecast substitution into
the historical v1 feature builder occurs.

Native returned grid coordinates and separately detected identical series are
preserved for each association. Returned provider elevation stays separate from
the Copernicus terrain elevation. There is no join through an old model-zone ID.

The authenticated staff-only read endpoint is:

```text
GET /monitoring-areas/features/weather?receipt_sha256=<64-character receipt hash>
```

It requires an explicit immutable receipt; it never selects an old record as a
current forecast. The response carries target dates, current/upcoming/archived
period status, source times, null publication metadata, cutoff eligibility and
source QC. It accepts no filesystem paths and performs no provider request,
database write, model invocation or alert. The weather output is available for
integration through this API and the local export; no new dashboard panel or
automatic polling has been added.

### Genuine pilot evidence

One request succeeded on **12 November 2026**, with 14,118 original response
bytes. The explicitly requested IFS run was 12 November at 00:00 UTC (03:00 EAT).
The response's first valid time aligned with that run. This is request/time-axis
evidence, not independent producer model-cycle/publication attestation.

- Actual request: `2026-11-12T09:45:32.275026+00:00`.
- Actual complete receipt: `2026-11-12T09:45:33.747612+00:00` (12:45 EAT).
- Target: 13 November 00:00 through 14 November 00:00 EAT; UTC interval
  `2026-11-12T21:00Z` through `2026-11-13T21:00Z`, end exclusive.
- All four points passed target-window QC, with 24 precipitation intervals and
  24 weather timestamps each. No local weather sensor measurement is implied.
- CBD/Uhuru/T-Mall share returned grid `[-1.3005272, 36.824646]` (lat, lon).
  Mathare uses `[-1.2302285, 36.866615]`. Four point associations are two grid
  locations, not four independent forecast locations.
- Receipt/storage occurred **after** the 06:00 EAT issue cutoff. The output is
  `NOT_ELIGIBLE_AT_ISSUE`; no historical availability was backdated.
- Original publication time is unknown/null. Continuous delivery and reliable
  arrival before cutoff have not been demonstrated.

Evidence stays local and Git-ignored under `data/hotspots/point_weather/`:

| Object | SHA-256 |
| --- | --- |
| Original response | `1b745198916cd869e20127ac8ece3cefaeffd58bc5ba71c127e366ef98c8be72` |
| Immutable receipt | `ca5924f330bc3e505efa7c5e2263160ecbcb45a71172f984c6f1c6cc19d130b2` |
| Joined context export | `c8fdf9d51015b38d021dd1cba8348f2b5552effa26e29917f466295772f018c2` |

The joined export's path is `persistence/sha256/c8/<hash>.json`. Replaying later
preserves original receipt and source bytes; period status can change with the
current clock, resulting in a new derived export hash.

Offline export/replay (no network):

```powershell
.venv/Scripts/python.exe -m src.scripts.collect_monitoring_point_weather
.venv/Scripts/python.exe -m src.scripts.collect_monitoring_point_weather --receipt data/hotspots/point_weather/readiness/sha256/ca/ca5924f330bc3e505efa7c5e2263160ecbcb45a71172f984c6f1c6cc19d130b2.json
```

The bounded network mode requires `--collect --issue-date YYYY-MM-DD --run
<timezone-aware-initialization>`. Do not automate it or change the declared issue
time just to make late samples appear eligible. The service API only reads;
collection is an explicit local CLI action.

Provider semantics: [Open-Meteo Single Runs](https://open-meteo.com/en/docs/single-runs-api)
and [ECMWF variable documentation](https://open-meteo.com/en/docs/ecmwf-api).
The provider forecast represents coarse numerical weather context, not local
street-drainage resolution.

### Can the original 20-feature v1 model be used?

Yes, for its verified historical replay and as a frozen research comparator. A
read-only package/runtime check on 12 November confirmed `AVAILABLE`, 20 features,
the original four classes and artifact SHA-256
`b185eced1e8887b0fdbcb539567ea4f7d485583848c81c81eacc2979d8c728bb`.
Its live status remains `INSUFFICIENT_DATA`.

Its exact inputs comprise four CHIRPS rainfall/history terms, ten complete-day
historical weather aggregates, four static terrain/land-cover descriptors and
two seasonal terms. Drainage is not one of these 20 features. In v1, completed
input day D predicts proxy class for D+1 and is issued on D+1; this new weather
collection instead describes issue I's next complete day I+1. They are separate
temporal contracts.

Running 20 numbers through a classifier is technically possible, but meaningful
new-point/live use requires reproducing the exact source, units, periods,
preprocessing and spatial support, then evaluating transfer to those points.
Current gaps include CHIRPS release/day alignment, issue-time availability of
the retrospective weather inputs, unavailable point land-cover fractions and
different terrain/NDVI extraction support. Forecast IFS fields cannot silently
replace ERA5-Seamless historical fields; the newer Sentinel point NDVI cannot
silently replace a 2023 summary. Existing runtime IDs/source records also cover
the original eight research areas, not these 40 records.

V1's outputs remain rainfall-defined environmental proxy classes, not calibrated
probabilities of an observed street flood. Its frozen historical accuracy does
not validate the new locations. Preserve it; any altered source/point model needs
a separately versioned experiment and time-separated evaluation against a simple
forecast-rule baseline. Nothing in this workstream retrains or activates a model.

### Verification of this increment

Automated checks cover incomplete/invalid weather, nulls without zero-fill,
source identity/coordinate tampering, after-cutoff/future receipts, shared grids,
physical-day interval selection, immutable raw bytes, request caching, one-request
bounds, transfer-size failure, sanitized network failures, staff-only API access,
invalid path attempts and missing-evidence failures. The pre-existing v1 feature
and runtime regression checks also pass. The existing localhost API was offline
at the time of the network smoke check; endpoint behavior was verified in the
FastAPI test client, not claimed as a running-server demonstration.

The completed backend regression run passed **562 tests**, with 81 optional or
environment-gated skips and one explicitly deselected model-refit test:

```powershell
.venv/Scripts/python.exe -m pytest tests -q --deselect=tests/test_proxy_evaluation.py::test_reference_refit_is_explicit_train_only_and_never_exports
```

The focused point/area/v1 feature/runtime run passed 220 tests. `git diff --check`
passed. Existing legacy serialization/deprecation warnings remain; no legacy
artifacts or dependency pins were changed. Frontend sources were unchanged in
this increment, so the previous browser/build evidence is not claimed as rerun.

No database migration/write, model training, inference, scheduled collection,
alert activation, dashboard change, commit or push was performed.

## Follow-up: satellite gaps, forecast proxy and close-button repair

The subsequent user request authorized filling input gaps, investigating the
notebook and attempting a separate retraining experiment. The earlier increment's
no-training statement above describes that increment only.

### Available geographic context

The source-linked enrichment now supplies **29/29 mapped records with NDVI and
2021 land-cover fractions**. Two coincident reference pairs still represent
shared physical locations. All 11 unresolved records remain unlocated; no new
coordinates were invented. The original inventory and its coordinate histories
remain unchanged. `monitoring_point_enrichment.json` is an additive runtime
dataset, integrity-pinned by `monitoring_point_enrichment.py`, tied to the original
catalogue SHA and each exact coordinate. The base catalog remains available for
offline reproduction, while the area API and feature table attach the validated
enrichment.

NDVI reuses the existing 12 August 2026 Sentinel scene and verified BOA offsets;
each added point passed SCL 4/5/6 and its actual coordinate check. The WorldCover
subsets use genuine 2021 v200 categorical pixels in a declared 500 m square
context box, nearest sampling, complete valid coverage and recorded class counts.
Built-up fraction is class 50 / valid pixels. Vegetation fraction sums classes
10,20,30,40,90,95,100 / valid pixels. The original histogram, source request/body,
receipt/hash, catalogue evidence and method are retained. These are descriptive
spatial summaries, not surveyed flood catchments. See [ESA WorldCover data and
licence documentation](https://esa-worldcover.org/en/data-access).

Measured `impervious_fraction` remains null; `built_up_fraction` is exposed
separately. The old training table approximated imperviousness with land cover,
but these new box summaries do not reproduce its undocumented original spatial
reduction. Drainage capacity, condition and blockage remain null. Neither can be
recovered reliably from NDVI or a categorical satellite image.

Terrain coverage remains **28/29**. One explicitly bounded attempt to obtain the
adjacent E037 Copernicus tile timed out. The failure was recorded, no automatic
retry followed, and existing successful evidence was retained. That point's
terrain remains unavailable. The optional extra tile request requires an explicit
`--terrain-tile` flag; normal satellite enrichment does not retry it.

Offline rebuild:

```powershell
.venv/Scripts/python.exe -m src.scripts.enrich_monitoring_points
```

`--fetch` is the explicit bounded network mode. It reuses cached responses and
requests at most 27 distinct coordinate subsets for each satellite variable
group, plus one WorldCover discovery response. It stops on authentication/rate
failure; no general historical acquisition or scheduler is involved. The
enrichment SHA is
`1067727ff24916c658f83b212acbb7e3ecc9e9d6430e824a23c79a7d124eecc8` at the time
(now `591f66727d4065a34284727e35af725f22560be5af0e0521f925b1b109711524` after the
15 November location review).

### Useful live-source proxy without misrepresenting v1

Staff can inspect **Forecast rainfall proxy** within the map's selected-area
profile. `GET /monitoring-areas/features/weather/current` requires the existing
active staff authentication and selects only the latest recorded point collection.
A latest failed attempt is not hidden by falling back to an older success.
There is a bounded 64-receipt index scan; larger collections require an indexed
storage implementation before expansion. Reads perform no collection, database
write, model invocation or alert. Browser requests are cancelled when changing or
closing the selected area; anonymous map viewers make no protected weather call.

`forecast_proxy_context.py` adds a **request-time weather rule** to verified
receipts. It uses the daily component of the pre-existing provisional proxy:
Low <5 mm, Moderate 5–<20, High 20–<40, Extreme >=40. It sums exactly the 24 genuine
preceding-hour forecast amounts covering the next complete Nairobi day. No
seven-day component, soil-moisture rule, terrain adjustment or drainage multiplier
is added. `model_version` and `flood_probability` are null. It is explicitly
labelled as a forecast rule, not the selected XGBoost model.

This is a **separate request-time context policy**, not a retrospective change
to the 06:00 EAT study. Original cutoff failures remain in the receipt. The rule
requires source receipt/storage before the actual request-time issue, receipt age
at most six hours, run age at most 24 hours, complete quality-accepted target
coverage, and tomorrow's full day still in the future. These freshness guards are
provisional. Expired/incomplete sources return unavailable, and the displayed
category expires locally at the earliest freshness/target deadline without
silently retaining an old category. No unattended collection was enabled.

Using the genuine existing 12 November receipt, a read-time check returned
12.6 mm for CBD/Uhuru/T-Mall and 11.2 mm for Mathare for 13 November, each a
Moderate **forecast-rule context**. Three associations share one provider grid.
These numerical forecasts are not rainfall measurements or confirmed flood
conditions. The other mapped points have no collected point-weather sample yet.
The locally preserved current-context export SHA is
`d9a70ae8d126ad922dbe2115508ffbe5c138df098280d865e7283c10b4aca95e`;
its request-time issue and expiry must not be treated as immutable model history.

### Notebook review and bounded retraining result

The selected notebook is `data/model_v1/NairobiFloodWatch.ipynb`, hash
`d0def899812c01a88c13084937a4e8f86340172d468d3888279f33b2431abe5b`.
Cells 14–16 define next-day CHIRPS daily/seven-day proxy labels, the 20 ordered
inputs and chronological partitions; cells 17–18 compare XGBoost configurations.
The older `notebooks/FloodHub.ipynb` also contains different later experiments,
including simulated-water-level discussion; it is not the selected 20-feature
artifact's authoritative recipe. Neither notebook was executed or modified.

The complete R3 rainfall-severity handoff was recovered locally rather than
relying on its earlier partial progress report: 365 dates / 2,920 retrospective
forecast–ERA5 proxy pairs. `evaluate_forecast_proxy_candidate.py` uses that existing
cohort and unchanged chronological train/validation/test/purged partitions and
daily-only label contract. It does not replace v1's CHIRPS seven-day target or
silently change the frozen ten-feature forecast contract. Its native XGBoost
3.1.3 diagnostic uses one fixed shallow configuration, 100 rounds, seed 42,
balanced weights for genuinely observed training classes, no oversampling,
tuning, early stopping or model selection. Results/model bytes are kept local
under ignored `data/hotspots/forecast_proxy_candidate/`; no candidate is registered
with application inference.

*Removed 17 November 2026:* this retired v2 candidate evaluation (script, R3 export and
local results) was deleted from the project;
the live outlook uses the Stage 2 model instead.

| Held-out row-based metric | New XGBoost diagnostic | Fixed forecast rule |
| --- | ---: | ---: |
| Accuracy | 0.8019 | 0.8683 |
| Macro F1 across supported Low/Moderate classes | 0.5442 | 0.6303 |
| Moderate recall | 0.4800 | 0.6400 |
| High/Extreme recall | Undefined: no held-out examples | Undefined: no held-out examples |

Training has eight High rows on only two dates and zero Extreme rows. Validation
and test have no High or Extreme targets. Repeated zone/reference-grid pairs
are dependent; row counts are not independent weather events. Original historical
as-issued availability is unverified and these are experimental ERA5 rainfall
labels, not observed floods. The new candidate loses to the baseline and is
**research only, rejected for live model activation**. The forecast rule is not
thereby validated for severe events either. No classes or dates were moved to
hide this result.

The final diagnostic report SHA is
`b439491a68aaca500be9a4caae43006eb42932355e17720d124d58f98f213304`.
It includes input hashes, code/configuration identity, support, confusion matrices,
undefined metrics, native model hash and blockers. Reproduce/reuse it with:

```powershell
.venv-model-v1/Scripts/python.exe -m src.scripts.evaluate_forecast_proxy_candidate
```

The selected v1 artifact still loads with its original SHA and historical replay;
its operational status remains insufficient data. A validated learned live
replacement still needs useful class/date support, homogeneous forecast/reference
sources, issue-time evidence and evaluation at the new point supports. Current
satellite context alone cannot establish those requirements.

### Map dismissal and regression evidence

Both details-panel and native popup close buttons now dismiss the selection.
Details close clears area/hotspot/inspect parameters while retaining any parent
zone filter. The native popup guard consumes the close click before Leaflet
removes its DOM target, preventing the underlying polygon from handling the same
click. Pointer/touch starts do not trigger map interactions; the click remains
available for touch/keyboard activation. The selected marker closes when cleared.
Disabling Leaflet's animated zoom also prevents a pending zoom callback from
accessing a destroyed map during navigation.

Headless Chrome verified real pointer clicks with native subcounty polygons
underneath, popup disappearance after its fade, no replacement popup/reselection,
staff proxy/land-cover display and existing reporting/authentication/admin flows.
Controlled workflow evidence: `floodhub-staff-ui-FlBuqE` in the local temporary
directory. Those browser values are test fixtures, distinct from the genuine
source read-time check above.

The original v1 model/contracts, v2 interface, migration 005, saved histories and
all existing source originals remain unchanged. No database migration/write,
automatic inference/collection, public alerts, commit, push or deployment occurred.

Final follow-up checks: **583 backend tests passed**, 81 optional/environment-gated
skips, one explicitly excluded reference-refit test; **100 frontend tests passed**;
production build and `git diff --check` passed. Headless Chrome passed 31 workflow
checks, including real pointer dismissal and staff forecast context. The existing
legacy dependency/deprecation warnings and frontend bundle-size warning remain.

## Consolidated monitoring workflow — 13 November 2026

The main workflow is now source collection → immutable evidence → validation →
monitored-location rainfall outlook → staff review of nearby community reports.
Experimental v1/v3 results remain in the research workspace. No model, label,
training dataset, migration or production database record was changed in this
increment.

### One complete, recoverable collection

The collector supports all 29 located records in one explicitly bounded request
(40-record hard bound, 2 MiB retained-body cap, no redirects or automatic retries).
Eleven unresolved records remain unavailable. Coincident locations and shared
weather grids are retained without invented spatial distinctions.

`point_collection_workflow.py` adds an OS lock, fsynced job journal, immutable
request index and atomically replaced current-receipt pointer. Repeating a completed
context revalidates and reuses its original bytes and timestamps. A crash after
capture can recover the existing receipt; a request with uncertain completion
stops instead of automatically fetching again. Failed attempts remain recorded.
An explicit new attempt label permits a deliberate refresh/retry. Old cached
requests cannot replace a newer current pointer. The normal reader no longer
scans the entire growing receipt history; the old bounded scan remains solely
for compatibility with pre-pointer local collections.

Commands from the repository root:

```powershell
# Read-only plan; no provider request.
.venv/Scripts/python.exe -m src.scripts.collect_monitoring_point_weather --plan --current --all
# One manual collection; repeating the same context resumes/reuses it.
.venv/Scripts/python.exe -m src.scripts.collect_monitoring_point_weather --collect --current --all
# A deliberate new attempt, preserving the first receipt. Choose a unique label.
.venv/Scripts/python.exe -m src.scripts.collect_monitoring_point_weather --collect --current --all --attempt-label refresh-02
# Offline integrity audit and isolated source-copy restore check.
.venv/Scripts/python.exe -m src.scripts.verify_point_weather_store --round-trip
```

`--current` selects an explicit 00/12 UTC run at least six hours before the actual
request. This guard is provisional publication-latency policy, not producer
publication evidence. It does not modify the existing 06:00 EAT research policy;
late receipts retain their original cutoff failure. Request-time rainfall
context still requires the existing six-hour receipt / 24-hour run freshness
guards and the next complete Nairobi calendar day.

One genuine request on 13 November returned **HTTP 200**, **102,830 response-body
bytes**, **29/29 complete target-day point associations** and **seven distinct
returned provider grid points**. There are 27 physical inventory coordinates.

| Evidence | Actual value |
| --- | --- |
| Explicit run | 13 November 2026, 00:00 UTC / 03:00 EAT |
| Request start | `2026-11-13T10:32:01.510979+00:00` |
| Complete receipt | `2026-11-13T10:32:03.105980+00:00` / 13:32 EAT |
| Target | 14 November 00:00 through 15 November 00:00 EAT, end exclusive |
| UTC target interval | `2026-11-13T21:00Z` through `2026-11-14T21:00Z` |
| Current freshness deadline | 13 November 19:32 EAT; no guaranteed replacement arrival |
| Original publication | Unknown/null |
| Source SHA-256 | `3c7a8dbd13786c0ffa1113985196579889330e13f0bca49cb102be7cb2a94e9d` |
| Receipt SHA-256 | `e77b146082f0d950538e0b2a2fdcd4071edc391d7ce1713ca600c58d3a61ef52` |

The current source was received after 06:00 EAT, so original-issue eligibility
remains `NOT_ELIGIBLE_AT_ISSUE`. The request-time outlook is explicitly separate.
Returned source units, whole-hour ordering, complete physical-day intervals,
coordinate association and finite/ranged values are checked. Point-specific grid
distance now also fails beyond a conservative 20 km engineering guard; it does
not imply street-level resolution. Equivalent valid ISO whole-hour formatting
is normalized before lookup.

### One understandable application view

`GET /monitoring-areas/outlook` is a sanitized public read endpoint. It exposes
per-area availability, rainfall amount/category, target/source dates, expiry and
shared-grid associations; it returns no raw file paths, hourly source payloads
or citizen reports. Source corruption/failure yields unavailable values rather
than a fallback category. It never acquires weather or writes predictions.

The map puts the rainfall outlook first in a selected location's panel. The
compact map status shows coverage and a read-only refresh. The weather page now
defaults to the same 29-location outlook with geographic parent filtering. Its
original eight-zone hourly/snapshot page remains behind an explicit archive
button, so old snapshots cannot masquerade as the current monitored-location
service. Administrative status shows the same fresh-coverage count.

Browser validation checks identity, physical target day, method, source timing,
expiry and category arithmetic. Open pages clear amounts/categories when they
expire without silently retaining the former result. Refresh makes a stored-data
read, not a provider request. The category remains a provisional daily rainfall
rule: no learned-model output, flood probability or terrain/drainage adjustment
is claimed. Pins and administrative polygons remain neutral.

Authenticated staff can read
`GET /monitoring-areas/{area_id}/reports` for coordinate-matched reports within
500 m during the last 30 days. It queries existing report records, uses actual
submitted coordinates and returns at most ten recent matches from a bounded
candidate query. No migration or automatic assignment of reports to a new area
is made. Unlocated areas and reports without coordinates are explicit gaps.
The ordinary review inbox remains authoritative; proximity is not confirmation
of flooding at the selected point. This endpoint and the panel are staff-only.

### Collection automation remains unactivated

`run_point_collection.py` defaults to plan-only. Execution requires an explicit
flag and successful Linux NTP verification. It collects sources only. Proposed
four-hourly systemd examples are in `deploy/examples/monitoring-point-weather.*`;
neither unit was installed, enabled or started. `Persistent=false` avoids an
automatic catch-up after missed runs. The four-hour cadence is a proposed
freshness operating window, not a measured delivery guarantee. The current API
correctly continues to report manual collection and no next arrival time.

Before any separately approved activation: mount `data/hotspots/point_weather`
on durable storage shared by API and collector; verify service user permissions,
Linux paths, NTP and the systemd calendar; check the applicable provider quota;
exercise an actual failure/restart; and wire actual schedule status before
claiming automatic operation. Do not enable legacy or v3 inference as part of
weather collection. Provider interface/terms were checked against
[Single Runs documentation](https://open-meteo.com/en/docs/single-runs-api) and
[Open-Meteo terms](https://open-meteo.com/en/terms).

### Paired backup and restore

Preserve the application PostgreSQL dump **together with** the complete configured
`OPERATIONAL_SOURCE_STORE` and `data/hotspots/point_weather`, including CAS objects,
request indexes, job journals and the current pointer. Include the versioned
catalogue/enrichment and separately maintained frozen-model/GIS source bundles.
A database dump alone cannot restore evidence verification. Never place private
configuration, credentials or backups in Git.

For a clean checkpoint, keep collection paused/locked, take a PostgreSQL custom
format dump with `pg_dump`, copy both source stores, and record hashes for the dump
and every file. In an isolated restore, use `pg_restore`, restore the matching
source stores to their configured paths, audit point receipts, and run
`OperationalSnapshotService.check_snapshot` for all restored Phase 2 snapshots.
Check row counts/hashes, application login/report review, unavailable states and
duplicate collection recovery before considering deployment. A new host also
needs the existing migrations and tested platform-specific native runtimes.

An actual `pg_dump`/`pg_restore` round trip of a generated **disposable test schema**
and its matching Phase 2 CAS succeeded. The restored snapshot verified; an empty
source store correctly failed verification. The application schema was excluded.
The real local point store also passed an isolated copy/restore check: 15 audited
objects, two receipts, identical inventory SHA
`092f1fab6114031d5819855d03e0faa6d0441bf12b5168ecffbbe9286222ff82`.
This is restore evidence for these tested graphs, not a production disaster-
recovery drill or proof of off-site backup retention.

### Verification of the consolidated workflow

- Full backend suite: **597 passed**, 82 optional/environment-gated skips and one
  explicitly excluded reference-refit test. The gated PostgreSQL cases were also
  run separately as listed below; the full default run does not claim its skips
  as passing checks.
- Native PostgreSQL suite: **74 passed**, including source persistence, stored
  weather reads, report review/admin concurrency and actual paired restore.
- Frontend units: **104 passed**. Production build passed, retaining the existing
  bundle-size warning. No dependency pins changed.
- Chrome: **34 workflow checks passed**, using the genuine CAS-derived public
  outlook; report/account writes remained controlled fixtures. Evidence is in
  local temporary `floodhub-staff-ui-N0gCOc`.
- Original eight-zone archive browser suite: **13 checks passed**.
- Genuine FastAPI read check returned 29/29 available mapped records from the
  preserved source graph. No model run was invoked.
- `git diff --check` passed. Existing legacy serialization/deprecation and bundle
  warnings remain; no dependency or frozen-model changes were made.

The source pipeline and application integration are ready for local review.
Sustained collection reliability, operational learned-model validity and a
production deployment remain unestablished. No scheduler, public alert, commit,
push or deployment was activated.

## Manual administration and deployment completion — 14 November 2026

The admin **System status** screen now has **Collect latest weather**. It calls
the existing collector for all located monitoring areas, not a model. Public map
and weather refreshes continue to read saved evidence only. Officers and anonymous
users cannot trigger acquisition.

- `GET /monitoring-areas/collection`: administrator-only, sanitized manual-attempt
  status. It does not create source directories or issue network requests.
- `POST /monitoring-areas/collection`, body `{"request_id":"<UUID>"}`:
  administrator-only explicit acquisition. No client source paths, dates, model
  choices or run overrides are accepted. The server selects its current explicit
  run and records the authenticated requesting user ID in the private journal.
- The UUID fixes the original policy, catalogue, area IDs and attempt label.
  Repeating it verifies/reuses completion or recovers durable source evidence.
  A crash with uncertain provider completion is refused rather than reissued.
  Different new admin requests are limited to one per 15 minutes; this is not a
  scheduled collection promise. Cross-process control/collector locks protect
  concurrent requests. CLI use remains an explicit operator action.
- Completion reports target-day record coverage, not live freshness or flood
  prediction success. The separate public outlook still applies actual age/day
  guards. Latest partial/failed collections are preserved without falling back
  to an older apparently successful source. UI timeouts do not cause a retry;
  **Resume same attempt** retains the original UUID.
- `control/requests/` and `control/latest.json` are part of the point-store backup.
  The checkpoint lock order is `control/manual.lock` then
  `jobs/collection.lock`, shared by the isolated source restore check. Incomplete
  attempts refuse a verified backup checkpoint; preserve them for recovery.

`MONITORING_POINT_SOURCE_STORE` is shared by API, collection CLI, optional runner
and audit/restore CLI. Unset preserves the original local path; relative overrides
resolve from the repository, not process cwd. Production templates use an absolute
durable mount. The API and point collection service examples now use the same
identity, paths and private environment. Their writable directories must exist
with the service user's permissions. Neither unit was installed or activated.

The deployment environment now explicitly disables experimental v3 scheduling.
The reverse-proxy example also blocks manual v3 execution. The initial database
setup command now requires `--admin-email`, prompts privately for the first
password (or accepts private `FLOODWATCH_BOOTSTRAP_PASSWORD`), creates no default
officer and runs no prediction pipeline. Existing account passwords/roles and
original reporting-zone records are never overwritten. The README replaces
superseded demo/default-live-model setup instructions with the current workflow.

The independently reviewed 13 November binary rainfall model remains outside the
application. No model weights, frozen v1/v2 contracts, migration 005, research
labels, previous source receipts or historical predictions were modified.

### Optional collection-only automation

Yes, collection can be automated on the approved Linux host. The repository ships
an inactive four-hourly timer at **02:00, 06:00, 10:00, 14:00, 18:00 and 22:00
UTC** (05:00, 09:00, 13:00, 17:00, 21:00 and 01:00 EAT). It invokes only
`run_point_collection --execute --automated --require-synced-clock`; it never
executes model inference or alert delivery. `Persistent=false` deliberately avoids
making up a missed source request after a server restart.

The service refuses unless all of the following are true: the private environment
sets `MONITORING_POINT_COLLECTION_AUTOMATED=true`; its declared interval remains
the reviewed four hours; and Linux `timedatectl` reports NTP synchronization. A
configured timer is not evidence that a request completed. The API preserves actual
receipt/source times, and the public outlook still removes expired evidence.

After a staging collection, source-store restore, service-failure/restart and clock
check have been reviewed, an operator can install the examples under the system
paths and deliberately enable them:

```text
sudo install -m 0644 deploy/examples/monitoring-point-weather.service /etc/systemd/system/
sudo install -m 0644 deploy/examples/monitoring-point-weather.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now monitoring-point-weather.timer
systemctl list-timers monitoring-point-weather.timer
```

Set the private environment flag only immediately before that final step. Do not
enable the timer while the API/collector point-store mount, service permissions,
NTP or provider constraints remain unverified. Stopping it is explicit:

```text
sudo systemctl disable --now monitoring-point-weather.timer
```

### Verification for this completion

- Full backend regression: **614 passed, 84 optional/environment-gated skips,
  one explicitly excluded reference-refit test**. No model was fitted.
- PostgreSQL-enabled targeted suite: **91 passed**, including native-user
  authorization for the new collection route, preservation of existing bootstrap
  accounts/zones and the existing real paired PostgreSQL/CAS dump/restore check.
  These use disposable schemas, not application-account/report mutations.
- Frontend: **108 unit tests passed** and production build passed. The existing
  dependency/deprecation warnings and 885 kB bundle-size warning remain.
- Headless Chrome: **36 checks passed** with today's genuine CAS-derived public
  outlook and controlled account/report/collection mutations. Evidence remains in
  local temporary `floodhub-staff-ui-JobcA6`. A separate controlled run also passed.
- One actual source request on 14 November 2026 returned HTTP 200 and **103,419
  bytes**, with 29 complete target-day associations on seven returned provider
  grid points. Request `2026-11-14T06:35:51.625043Z`; receipt
  `2026-11-14T06:35:52.663752Z` (09:35 EAT). Run: 14 November 00:00 UTC.
  Target: **15 November 00:00 through 16 November 00:00 EAT**, end exclusive.
  Source SHA-256:
  `d7e2f6ca611c77ba4c9b0e1444ac733bccff84062d8ad402a9dfbdf826b9fcc3`.
  Receipt SHA-256:
  `46e097455fed924d3629b355866fc8a4fb10f7df9b2313cf8f3b07a47e408f88`.
  Its request-time outlook expires by 14 November **15:35 EAT** without another
  eligible collection. It was received after 06:00, so original-issue eligibility
  remains false; it is not backdated to the research cutoff.
- In-process public API and the running local API both returned **29/29 available**
  located records. Anonymous access to the new admin collection route returned
  401. Unresolved records retain unavailable/null rainfall, with no substitute pins.
- Actual point-source isolated copy/restore: **21 objects, three receipts**, same
  inventory hash `d860984bfcd8f91281d0fe40124e2a35e783e772e2836db3dbde0b535e402e9e`.
  Original v1 model, v1 contract and migration 005 still match their recorded hashes.
- `git diff --check` passed. No migration was applied to the application database,
  no model inference/alert/scheduler was activated, and no commit/push/deployment
  occurred. Only one genuine weather acquisition was made for this verification.

Remaining work is operational acceptance on the intended Linux host (private
configuration, durable stores, HTTPS, NTP, actual service failure/restart and
separately approved timer activation), refinement of the eleven unresolved
locations and unavailable measured drainage inputs. A future learned model still
requires its own runtime/source integration and prospective scientific evaluation.
