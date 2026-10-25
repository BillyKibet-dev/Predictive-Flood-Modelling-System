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

This county outline is separate from the application's eight monitoring-zone
points. Neighbourhood labels such as CBD and Kibera are not county boundaries;
no zone polygons or zone-to-admin-area assignments are inferred from this file.
