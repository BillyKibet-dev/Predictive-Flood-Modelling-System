# Candidate source scripts supplied by the user

Received 25 October 2026. The user said these **may** be the original scripts.
They are preserved as evidence, without executing new export jobs or treating
them as verified export history. Structured settings are recorded in
[training_sources.candidate.json](training_sources.candidate.json).

## CHIRPS

```javascript
var chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY')
  .filterDate('2016-01-01', '2026-01-01')
  .filterBounds(ee.Geometry.Point(36.817, -1.286));

var nairobiPoint = ee.Geometry.Point(36.817, -1.286);

var timeSeries = chirps.map(function(image) {
  var value = image.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: nairobiPoint,
    scale: 5000
  });
  return ee.Feature(null, value)
    .set('date', image.date().format('YYYY-MM-dd'));
});

Export.table.toDrive({
  collection: ee.FeatureCollection(timeSeries),
  description: 'CHIRPS_Nairobi_2016_2026',
  fileFormat: 'CSV'
});
```

## Open-Meteo

```python
import requests
import pandas as pd

url = "https://archive-api.open-meteo.com/v1/archive"
params = {
    "latitude": -1.286389,
    "longitude": 36.817223,
    "start_date": "2016-01-01",
    "end_date": "2026-01-01",
    "hourly": [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "wind_speed_10m",
        "soil_moisture_0_to_7cm"
    ],
    "timezone": "Africa/Nairobi"
}

response = requests.get(url, params=params)
data = response.json()

df = pd.DataFrame(data["hourly"])
df.to_csv("nairobi_weather_2016_2026.csv", index=False)
print(df.head())
print(f"Total records: {len(df)}")
```

## IMERG (separate reference; not an input to the current model)

```javascript
var imerg = ee.ImageCollection('NASA/GPM_L3/IMERG_V06')
  .filterDate('2023-01-01', '2026-01-01')
  .filterBounds(ee.Geometry.Point(36.817, -1.286))
  .select('precipitationCal');

var nairobiPoint = ee.Geometry.Point(36.817, -1.286);

var timeSeries = imerg.map(function(image) {
  var value = image.reduceRegion({
    reducer: ee.Reducer.mean(),
    geometry: nairobiPoint,
    scale: 11132
  });
  return ee.Feature(null, value)
    .set('date', image.date().format('YYYY-MM-dd HH:mm'));
});

Export.table.toDrive({
  collection: ee.FeatureCollection(timeSeries),
  description: 'IMERG_Nairobi_2023_2026',
  fileFormat: 'CSV'
});
```

The candidate scripts sample a central Nairobi **point**, rather than a county
or sub-county polygon. CHIRPS's date filter excludes its upper bound, while the
weather request includes 1 January 2026. These settings agree with the observed
CSV endpoints. The CHIRPS export formats image dates without a timezone argument;
[Earth Engine defaults that formatting to UTC](https://developers.google.com/earth-engine/apidocs/ee-date-format).
The original notebook joins those date keys to Nairobi local calendar days.
Actual rainfall accumulation windows still need reconciliation before defining
a local forecast target.

The [CHIRPS catalogue](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY)
describes daily precipitation at approximately 0.05° grid spacing. A 5,000 m
reduction scale does not establish 5,000 m independent observations at every
location. The [IMERG V06 catalogue](https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V06)
is deprecated, supplies half-hourly rates in mm/hour, and ends in June 2024.
Its filename/date filter cannot establish 2025 coverage. No IMERG values are
merged into this evaluation.
