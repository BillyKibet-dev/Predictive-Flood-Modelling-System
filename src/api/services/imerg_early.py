"""NASA GPM IMERG Early daily satellite rainfall for the Nairobi monitoring pins.

Live replacement for CHIRPS as the *observed antecedent rainfall* input. One small
OPeNDAP CSV subset per UTC day covers every Nairobi pin. Files are found through NASA's
CMR catalogue (no credentials sent) and subset through Earthdata Cloud OPeNDAP, strictly
one request at a time (the older gpm1.gesdisc host blocked this address after concurrent
connections on 2026-11-14 and took ~20 s per request; the cloud service takes ~1.5 s). Collected days are stored
immutably (raw response + parsed record, SHA-256 checked on read) and never refetched.
Reads never touch the network. Missing or incomplete days stay missing: nothing is
zero-filled.

Product: GPM_3IMERGDE V07 ("Early", ~4 h half-hourly latency; the daily file appears
a few hours after the UTC day ends). ``precipitation`` is a daily mean rate in mm/day,
i.e. the UTC-day total in mm; ``precipitation_cnt`` is the number of valid half-hours
(48 = complete day).
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import logging
import math
import netrc
import os
from pathlib import Path
import re
import time
from urllib.parse import quote

import requests

logger = logging.getLogger("nairobifloodwatch.imerg_early")

CONTRACT = "imerg-early-daily-v1"
PRODUCT = "GPM_3IMERGDE"
OPENDAP_ROOT = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_L3/GPM_3IMERGDE.07"   # legacy DAP2 host
CLOUD_COLLECTION = "C2723754850-GES_DISC"
CLOUD_OPENDAP = f"https://opendap.earthdata.nasa.gov/collections/{CLOUD_COLLECTION}/granules/"
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
REQUEST_PAUSE_S = 1.0
EARTHDATA_HOST = "urs.earthdata.nasa.gov"
ANTECEDENT_DAYS = 5
RESOLUTION = 0.1
# Native 0.1-degree index box covering Nairobi County with a margin (lat -1.6..-1.0, lon 36.5..37.3).
LAT_INDEX = (884, 889)
LON_INDEX = (2165, 2172)
FILL_VALUE = -9999.9
HALF_HOURS = 48
FILENAME = re.compile(r"3B-DAY-E\.MS\.MRG\.3IMERG\.(\d{8})-S000000-E235959\.(V07[A-Z])\.nc4")
DEFAULT_STORE = Path(__file__).resolve().parents[3] / "data/hotspots/imerg_early"


class ImergError(RuntimeError):
    pass


def store_path() -> Path:
    from src.api.config import settings
    configured = getattr(settings, "IMERG_EARLY_STORE", None)
    if not configured:
        return DEFAULT_STORE
    path = Path(configured).expanduser()
    return path if path.is_absolute() else Path(__file__).resolve().parents[3] / path


# ---------------------------------------------------------------- grid
def cell_index(latitude: float, longitude: float) -> tuple[int, int]:
    """Native IMERG 0.1-degree cell (south-west origin, centre registration)."""
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        raise ValueError("finite coordinates required")
    i = math.floor((latitude + 90.0) / RESOLUTION + 1e-9)
    j = math.floor((longitude + 180.0) / RESOLUTION + 1e-9)
    if not (LAT_INDEX[0] <= i <= LAT_INDEX[1] and LON_INDEX[0] <= j <= LON_INDEX[1]):
        raise ValueError("point outside the collected Nairobi IMERG box")
    return i, j


def cell_id(i: int, j: int) -> str:
    return f"lat{i}_lon{j}"


def cell_centre(i: int, j: int) -> tuple[float, float]:
    return round(-90.0 + RESOLUTION * i + RESOLUTION / 2, 4), round(-180.0 + RESOLUTION * j + RESOLUTION / 2, 4)


# ------------------------------------------------------------- parsing
def subset_query() -> str:
    box = f"[0:0][{LON_INDEX[0]}:{LON_INDEX[1]}][{LAT_INDEX[0]}:{LAT_INDEX[1]}]"
    return f"precipitation{box},precipitation_cnt{box}"


def parse_ascii(text: str) -> dict[str, dict]:
    """OPeNDAP DAP2 ASCII subset -> {cell_id: {precipitation_mm, sample_count, ...}}."""
    values: dict[str, dict[float, list[float]]] = {"precipitation": {}, "precipitation_cnt": {}}
    lats: dict[str, list[float]] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        head = parts[0]
        for var in values:
            if head == f"{var}.lat":
                lats[var] = [float(v) for v in parts[1:]]
            match = re.fullmatch(rf"{var}\.{var}\[{var}\.time=\d+\]\[{var}\.lon=(-?[\d.]+)\]", head)
            if match:
                values[var][round(float(match.group(1)), 4)] = [float(v) for v in parts[1:]]
    expected_lats = [cell_centre(i, LON_INDEX[0])[0] for i in range(LAT_INDEX[0], LAT_INDEX[1] + 1)]
    expected_lons = [cell_centre(LAT_INDEX[0], j)[1] for j in range(LON_INDEX[0], LON_INDEX[1] + 1)]
    for var in values:
        if [round(v, 4) for v in lats.get(var, [])] != expected_lats:
            raise ImergError(f"unexpected {var} latitude axis")
        if sorted(values[var]) != expected_lons or any(len(r) != len(expected_lats) for r in values[var].values()):
            raise ImergError(f"unexpected {var} longitude axis or row length")
    return _cells(values)


def _expected_axes():
    lats = [cell_centre(i, LON_INDEX[0])[0] for i in range(LAT_INDEX[0], LAT_INDEX[1] + 1)]
    lons = [cell_centre(LAT_INDEX[0], j)[1] for j in range(LON_INDEX[0], LON_INDEX[1] + 1)]
    return lats, lons


def dap4_query() -> str:
    box = f"[0][{LON_INDEX[0]}:{LON_INDEX[1]}][{LAT_INDEX[0]}:{LAT_INDEX[1]}]"
    return (f"/lat[{LAT_INDEX[0]}:{LAT_INDEX[1]}];/lon[{LON_INDEX[0]}:{LON_INDEX[1]}];"
            f"/precipitation{box};/precipitation_cnt{box}")


def parse_dap4_csv(text: str) -> dict[str, dict]:
    """Earthdata Cloud OPeNDAP DAP4 CSV subset -> {cell_id: {...}} (same shape as parse_ascii)."""
    axes: dict[str, list[float]] = {}
    rows: dict[str, dict[int, list[float]]] = {"precipitation": {}, "precipitation_cnt": {}}
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if parts[0] in ("/lat", "/lon"):
            axes[parts[0][1:]] = [round(float(v), 4) for v in parts[1:]]
            continue
        match = re.fullmatch(r"/(precipitation|precipitation_cnt)\[0\]\[(\d+)\]", parts[0])
        if match:
            rows[match.group(1)][int(match.group(2))] = [float(v) for v in parts[1:]]
    lats, lons = _expected_axes()
    if axes.get("lat") != lats or axes.get("lon") != lons:
        raise ImergError("unexpected DAP4 latitude/longitude axes")
    values = {}
    for var, by_index in rows.items():
        if sorted(by_index) != list(range(len(lons))) or any(len(r) != len(lats) for r in by_index.values()):
            raise ImergError(f"unexpected {var} shape")
        values[var] = {lons[k]: row for k, row in by_index.items()}
    return _cells(values)


def _cells(values) -> dict[str, dict]:
    cells = {}
    for j in range(LON_INDEX[0], LON_INDEX[1] + 1):
        lon = cell_centre(LAT_INDEX[0], j)[1]
        for k, i in enumerate(range(LAT_INDEX[0], LAT_INDEX[1] + 1)):
            amount, count = values["precipitation"][lon][k], values["precipitation_cnt"][lon][k]
            valid = math.isfinite(amount) and amount >= 0 and abs(amount - FILL_VALUE) > 1e-3
            cells[cell_id(i, j)] = dict(
                latitude=cell_centre(i, j)[0], longitude=lon,
                precipitation_mm=round(amount, 4) if valid else None,
                sample_count=int(count) if math.isfinite(count) else 0,
                complete=valid and int(count) == HALF_HOURS)
    return cells


# ---------------------------------------------------------- transport
class EarthdataSession(requests.Session):
    """Keep Earthdata credentials only for the Earthdata login host (NASA-recommended pattern)."""

    def rebuild_auth(self, prepared_request, response):
        headers = prepared_request.headers
        if "Authorization" in headers:
            original = requests.utils.urlparse(response.request.url).hostname
            redirect = requests.utils.urlparse(prepared_request.url).hostname
            if original != redirect and EARTHDATA_HOST not in (original, redirect):
                del headers["Authorization"]


def earthdata_credentials() -> tuple[str, str]:
    from src.api.config import settings
    user, password = getattr(settings, "EARTHDATA_USERNAME", None), getattr(settings, "EARTHDATA_PASSWORD", None)
    if user and password:
        return user, password
    home = Path(os.path.expanduser("~"))
    for name in (".netrc", "_netrc"):
        path = home / name
        if path.exists():
            found = netrc.netrc(str(path)).authenticators(EARTHDATA_HOST)
            if found:
                return found[0], found[2]
    raise ImergError("Earthdata credentials not configured (EARTHDATA_USERNAME/PASSWORD or ~/.netrc)")


def new_session() -> requests.Session:
    session = EarthdataSession()
    session.auth = earthdata_credentials()
    session.headers["User-Agent"] = "nairobi-floodwatch"
    return session


def cmr_month(year: int, month: int, http=requests) -> dict[date, tuple[str, str]]:
    """Granules published for one month, from NASA's public CMR catalogue (no credentials sent)."""
    first = date(year, month, 1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    response = http.get(CMR_GRANULES, params=dict(short_name=PRODUCT, version="07", page_size=100,
                                                  temporal=f"{first}T00:00:00Z,{last}T23:59:59Z"),
                        headers={"User-Agent": "nairobi-floodwatch"}, timeout=60)
    if response.status_code != 200:
        raise ImergError(f"CMR HTTP {response.status_code}")
    titles = " ".join(entry["title"] for entry in response.json()["feed"]["entry"])
    found: dict[date, list[tuple[str, str]]] = {}
    for name, stamp, version in {(m.group(0), m.group(1), m.group(2)) for m in FILENAME.finditer(titles)}:
        found.setdefault(datetime.strptime(stamp, "%Y%m%d").date(), []).append((version, name))
    # If NASA ever lists two minor versions for one day, use the newest one and record it.
    return {day: max(options) for day, options in found.items()}


# -------------------------------------------------------------- store
def _write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ImergError(f"immutable record conflict: {path.name}")
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def record_path(root: Path, day: date) -> Path:
    return root / "days" / f"{day.isoformat()}.json"


def read_day(day: date, root: Path | None = None) -> dict | None:
    """Verified stored record for one UTC day, or None if never collected."""
    root = root or store_path()
    path = record_path(root, day)
    if not path.exists():
        return None
    record = json.loads(path.read_bytes())
    raw = (root / "raw" / f"{record['raw_sha256']}.txt").read_bytes()
    if hashlib.sha256(raw).hexdigest() != record["raw_sha256"] or record["contract_version"] != CONTRACT:
        raise ImergError(f"stored IMERG record for {day} failed verification")
    parser = parse_dap4_csv if record.get("format") == "dap4-csv" else parse_ascii
    if parser(raw.decode("utf-8")) != record["cells"]:
        raise ImergError(f"stored IMERG cells for {day} do not match raw response")
    return record


def collect_days(days, *, root: Path | None = None, session=None, catalog=None, clock=None,
                 pause: float = REQUEST_PAUSE_S) -> dict:
    """Fetch any of ``days`` (UTC dates) not yet stored, strictly sequentially.

    Bounded: one CMR query per month + one cloud OPeNDAP subset per day.
    """
    catalog = catalog or cmr_month
    root = root or store_path()
    clock = clock or (lambda: datetime.now(timezone.utc))
    summary = {"stored": [], "already_stored": [], "not_yet_published": [], "failed": {}}
    todo = [d for d in sorted(set(days)) if not record_path(root, d).exists()]
    summary["already_stored"] = [d.isoformat() for d in sorted(set(days)) if d not in todo]
    if not todo:
        return summary
    own = session is None
    session = session or new_session()
    listings: dict[tuple[int, int], dict] = {}
    try:
        for day in todo:
            try:
                key = (day.year, day.month)
                if key not in listings:
                    listings[key] = catalog(*key)
                if day not in listings[key]:
                    summary["not_yet_published"].append(day.isoformat())
                    continue
                version, filename = listings[key][day]
                granule = quote(f"{PRODUCT}.07:{filename}", safe="")
                url = f"{CLOUD_OPENDAP}{granule}.dap.csv?dap4.ce={dap4_query()}"
                requested_at = clock()
                response = session.get(url, timeout=90)
                time.sleep(pause)
                if response.status_code != 200:
                    raise ImergError(f"subset HTTP {response.status_code}")
                raw = response.content
                cells = parse_dap4_csv(raw.decode("utf-8"))
                digest = hashlib.sha256(raw).hexdigest()
                _write_once(root / "raw" / f"{digest}.txt", raw)
                record = dict(contract_version=CONTRACT, product=PRODUCT, version=version, granule=filename,
                              format="dap4-csv", access="earthdata-cloud-opendap",
                              utc_day=day.isoformat(), units="mm per UTC day",
                              requested_at_utc=requested_at.isoformat(), received_at_utc=clock().isoformat(),
                              raw_sha256=digest, lat_index=list(LAT_INDEX), lon_index=list(LON_INDEX), cells=cells)
                _write_once(record_path(root, day), json.dumps(record, indent=1, sort_keys=True).encode())
                summary["stored"].append(day.isoformat())
            except (ImergError, requests.RequestException, ValueError, UnicodeDecodeError) as exc:
                summary["failed"][day.isoformat()] = str(exc)[:200]
    finally:
        if own:
            session.close()
    return summary


def antecedent_days(issue_date: date) -> list[date]:
    """UTC days I-5 .. I-1 for a Nairobi issue date I (they end at 00:00 UTC = 03:00 EAT on I)."""
    return [issue_date - timedelta(days=k) for k in range(ANTECEDENT_DAYS, 0, -1)]


def collect_for_issue(issue_date: date, **kwargs) -> dict:
    return collect_days(antecedent_days(issue_date), **kwargs)


@dataclass
class Antecedent:
    status: str                 # AVAILABLE | UNAVAILABLE
    total_mm: float | None
    cell: str | None
    days: list[dict]
    reason: str | None = None

    def as_dict(self) -> dict:
        return dict(status=self.status, total_mm=self.total_mm, cell=self.cell, days=self.days, reason=self.reason,
                    product=PRODUCT, window="5 complete UTC days ending 00:00 UTC (03:00 EAT) on the issue day")


def antecedent(latitude: float, longitude: float, issue_date: date, *, root: Path | None = None) -> Antecedent:
    """Observed 5-day IMERG Early total at the pin's native cell. Never partial, never zero-filled."""
    try:
        i, j = cell_index(latitude, longitude)
    except ValueError:
        return Antecedent("UNAVAILABLE", None, None, [], "POINT_OUTSIDE_IMERG_BOX")
    cid = cell_id(i, j)
    rows, missing = [], []
    for day in antecedent_days(issue_date):
        try:
            record = read_day(day, root)
        except (ImergError, OSError, ValueError, KeyError) as exc:
            logger.warning("IMERG record unreadable for %s: %s", day, exc)
            record = None
        cell = (record or {}).get("cells", {}).get(cid)
        if not cell or not cell["complete"]:
            missing.append(day.isoformat())
            continue
        rows.append(dict(utc_day=day.isoformat(), precipitation_mm=cell["precipitation_mm"], version=record["version"]))
    if missing:
        return Antecedent("UNAVAILABLE", None, cid, rows, "IMERG_DAYS_MISSING:" + ",".join(missing))
    return Antecedent("AVAILABLE", round(math.fsum(r["precipitation_mm"] for r in rows), 4), cid, rows)


def collect_for_issue_safely(issue_date: date) -> dict:
    """Best-effort hook for the forecast collection paths: never raises, never blocks the forecast."""
    from src.api.config import settings
    if not getattr(settings, "IMERG_EARLY_ENABLED", True):
        return {"status": "DISABLED"}
    try:
        result = collect_for_issue(issue_date)
        result["status"] = "FAILED" if result["failed"] else "OK"
        return result
    except (ImergError, requests.RequestException, OSError, ValueError) as exc:
        logger.warning("IMERG Early collection failed: %s", exc)
        return {"status": "FAILED", "error": str(exc)[:200]}
