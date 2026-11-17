# Historical UNOSAT layer: restoration and operation

The fixed research dataset `unosat-20240501-nairobi-kiambu` uses official
UNITAR-UNOSAT water, analysis-footprint and cloud-obstruction geometry from
1 May 2024, separate from modelled proxy risk. It supplies no depth,
flood-free labels, calibrated probability or model validation score.

## Restore verified data

Source: [UNOSAT product 3833](https://unosat.org/products/3833), whose
[linked event SHP archive](https://unosat.org/static/unosat_filesystem/3833/FL20240426KEN_SHP.zip)
is broader than the associated PDF map sheet. The archive revision's original
publication time is unknown. Acquisition time is 08:06 UTC / 11:06 EAT on
1 May; it is not flood onset. The interpretation is preliminary, confidence
to be evaluated, and not field validated.

Native and derived geographic files are intentionally excluded from Git.
The reviewed metadata and original-member/display hashes are committed as
code-reviewable anchors in `src/api/data/unosat_20240501.json`.
Keep data local for attributed educational/non-commercial research under
[UNITAR terms](https://unitar.org/legal); no unrestricted redistribution or
commercial licence is asserted. Satellite imagery is not included.

Either restore byte-identical reviewed `flood.geojson`, `coverage.geojson`
and `cloud.geojson` files into `data/historical_unosat/20240501`, or obtain
the official archive and explicitly prepare its pinned members. An updated
archive/member must fail verification rather than silently replacing history.

Optional preparation dependencies belong in a separate environment or isolated
directory; do not upgrade the model runtime:

```powershell
.venv/Scripts/python.exe -m pip install --target data/hotspots/gis_dependencies -r requirements-unosat-preparation.txt
.venv/Scripts/python.exe -m src.scripts.prepare_unosat_evidence --archive <downloaded-archive.zip> --output data/historical_unosat/20240501 --reader-path local_audits/unosat/dependencies --manifest-output <new-review-manifest.json>
```

The preparer verifies exact required member names, hashes and lengths; decodes
native WGS84 2D geometry; repairs topology; computes area in UTM37S; and makes
1-metre topology-preserving display simplifications. Full-resolution repaired
source is used for comparison, not the simplified display. Preparation is an
explicit offline operation using read-only PostGIS queries; no migration or
model/alert action runs. It can take several minutes for the million-vertex
source. It refuses differing existing output files and never automatically
overwrites the trusted metadata manifest.

Review separately generated metadata if geography or spatial-library versions
differ. Current preparation evidence used PostGIS 3.6.2, GEOS 3.14.1dev,
PROJ 8.2.1, pyshp 3.1.7 and Shapely 2.2.0. Do not edit hashes just to pass
runtime checks. Archive native bytes, processing versions and derived output
together under the recorded permissions.

## API and map use

Active officer/admin JWT required:

- `GET /api/v1/geospatial/historical-floods/unosat-20240501-nairobi-kiambu`
- `GET .../flood`, `GET .../coverage`, `GET .../cloud`

The fixed responses revalidate source-file hashes, polygon validity and the
reviewed current point/administrative-geometry fingerprint. Missing data,
corruption or changed geography yields safe 503; no placeholder is generated.
Anonymous/inactive sessions receive 401, unapproved roles 403. Public boundary
and risk routes retain their existing rules. No POST/import endpoint exists.

On Map, open **Map layers & legend**, then enable **Historical UNOSAT ·
1 May 2024**. Cyan is historical source water; purple dashed outline is the
analysed footprint; grey is mapped cloud. Outside/obscured areas are unknown.
No detection at a covered point does not prove no flooding. Original study
rectangles, current monitoring points and administrative context are distinct;
the original rectangle definitions were not supplied. Small source slivers in
cloud/outside analysis remain explicitly unassessable. No extra mask is invented.

Existing risk layers and saved replay remain independent. The weather-outlook
page, source snapshots, v1 model, collection scheduling and alerts are untouched.
There is no automatic acquisition. Normal map basemap availability depends on
the existing tile provider; its arrival does not establish source-data validity.

## Verification and rollback

Run `tests/test_historical_floods.py` with `RUN_POSTGIS_TESTS=1` for isolated
native tests, the existing API/model suites, and `npm.cmd test` /
`npm.cmd run build` inside `dashboard`. Native tests use disposable schemas.
Synthetic fixtures must never replace the restored historical bundle.

Removing the historical router registration and new map hook/controls/panes
rolls back the application increment. No database downgrade or source-history
deletion is required. Keep original evidence for review. Publishing, broader
data distribution and deployment require separate authorization.
