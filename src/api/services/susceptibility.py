"""Local flood susceptibility per monitored place (prepared offline by prepare_susceptibility).

A fixed-weight ranking of the monitored places from terrain, rivers, the 2024 satellite water
map, built-up cover and recorded flooding. It does not change with the weather; the rainfall
outlook says how much rain, this says where water collects first.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data/monitoring_susceptibility.json"
SHA256 = "85fda8f837d7630adad0c4e173c0dbb4178d056f7c1b71dc412e587923e9bd86"
LEVELS = ("Lower", "Medium", "Higher")


class SusceptibilityUnavailable(Exception):
    pass


@lru_cache(maxsize=1)
def load() -> dict:
    try:
        raw = PATH.read_bytes()
    except OSError as exc:
        raise SusceptibilityUnavailable("Susceptibility file is missing") from exc
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise SusceptibilityUnavailable("Susceptibility file failed its integrity check")
    document = json.loads(raw)
    if document.get("contract_version") != "monitoring-susceptibility-v1" or any(
            r["level"] not in LEVELS or not 0 <= r["score"] <= r["max_score"] for r in document["rows"]):
        raise SusceptibilityUnavailable("Susceptibility file is not in the expected form")
    return document


def by_area() -> dict:
    return {r["area_id"]: r for r in load()["rows"]}
