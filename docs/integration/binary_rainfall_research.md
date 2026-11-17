# Binary rainfall research model

`models/nextday-rainfall-binary-v1/model.json` is the supplied native XGBoost
3.1.3 artifact. Its SHA-256 is fixed in the server adapter:
`4c9f9b3b7f5185a1cd42c01441144becedbd4d916734393115b9c18726d03811`.

The model accepts these ten features, in order: total forecast rainfall, maximum
3-hour and 6-hour rainfall, rainy-hour count, mean temperature, mean humidity,
maximum wind, mean shallow soil moisture, and target-month sine/cosine. It
returns an uncalibrated binary score for the experimental label **ERA5-estimated
next-day rainfall at or above 5 mm**.

It does not predict observed flooding, street flooding, drain performance,
inundation extent/depth, or a flood probability. It is available only to signed-in
staff at `GET /api/research/binary-rainfall/current`, runs on demand against the
latest verified point-weather receipt, and is neither persisted nor connected to
alerts. Missing, stale, incomplete, or failed source data return `UNAVAILABLE`.

The model executes in the isolated `.venv-model-v1` interpreter because the
artifact was serialized with XGBoost 3.1.3. Loading it through the application
runtime's different XGBoost version is prohibited. The service verifies the
artifact SHA-256 and native feature/objective/version before every execution.

The historical evaluation used eight zone associations and an ERA5 proxy target;
the newer monitoring-area pins were not part of that evaluation. Each output is
therefore labelled `NOT_VALIDATED_FOR_NEW_MONITORING_AREAS`. Areas that share a
provider grid can legitimately produce identical feature values and scores.

The weather receipt is request-time evidence. Its timestamps do not prove that a
historical forecast was originally available at the 06:00 EAT research cutoff.
