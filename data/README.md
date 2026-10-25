# Boundary data

`boundaries/nairobi_county.geojson` contains one **Nairobi County** polygon,
extracted from the provider-simplified Kenya ADM1 layer in geoBoundaries gbOpen.
Coordinates are unchanged from that extract (172 positions); the application
adds a stable `nairobi-county` ID and provenance properties.

- Provider: [geoBoundaries](https://www.geoboundaries.org/), layer `KEN-ADM1-32016919`.
- Original sources: RCMRD GeoPortal and Africa GeoPortal.
- Boundary year represented: **2020**; this is a dated administrative reference,
  not a statement that boundaries were surveyed in 2026.
- Original layer licence: **Public Domain**, as recorded in the provider metadata.
- [Pinned download](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/KEN/ADM1/geoBoundaries-KEN-ADM1_simplified.geojson)
  at upstream commit `9469f09`.
- [Provider metadata](https://www.geoboundaries.org/api/gbID/KEN-ADM1-32016919/).

`boundaries/nairobi_county.source.json` records retrieval date, source feature
properties, processing, and SHA-256 hashes for both the upstream file and the
committed extract. To reproduce the extract, select the single upstream feature
with `shapeISO == "KE-30"` and `shapeName == "Nairobi"`, preserve its geometry,
and apply the properties in the committed GeoJSON. Attribute geoBoundaries and
the original sources when displaying this data.

The file uses RFC 7946 longitude/latitude coordinates (WGS84 / EPSG:4326). The
import normalizes Polygon to MultiPolygon and ring orientation in PostGIS; it
does not simplify the boundary further or repair invalid topology silently.

## Nairobi sub-counties

`boundaries/nairobi_subcounties.geojson` contains 17 features from the
provider-simplified Kenya ADM2 layer, `KEN-ADM2-3690345`.

- Original sources: **IEBC and OCHA ROSEA**, distributed by geoBoundaries gbOpen.
- Boundary year: **2020**. Source names and coordinates are preserved, including
  the labels **Kilimani** and **Dagoretti**; these are dated source labels.
- Licence: [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/).
  Attribute IEBC, OCHA ROSEA, and geoBoundaries when displaying the data.
- [Pinned download](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/KEN/ADM2/geoBoundaries-KEN-ADM2_simplified.geojson)
  at upstream commit `9469f09`.
- [Provider metadata](https://www.geoboundaries.org/api/gbID/KEN-ADM2-3690345/).

The companion `.source.json` records upstream/extract SHA-256 hashes, the county
extract hash, and all selected source properties. To reproduce the selection,
use PostGIS `ST_Covers(county_geometry, ST_PointOnSurface(adm2_geometry))` against
the committed Nairobi County outline. Preserve the selected geometry and names,
and add the stable IDs/provenance properties in the committed extract. No
additional simplification, clipping, or coordinate movement is applied.

The application's eight monitoring points remain separate from these
administrative areas. The boundary API assigns point IDs using `ST_Covers` on
their coordinates, not neighbourhood labels. Consequently the existing CBD
point falls in the source's Kilimani polygon and the Kibera point in Langata.
The map identifies both the source boundary and contributing point names.
Unmonitored polygons show Unknown; a coloured polygon represents the highest
available monitored risk in that area, not a predicted flood footprint.
