"""One bounded, explicit-run IFS request; local shadow evidence only.

No model, legacy weather service, application database or scheduler imports.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import requests

from src.api.services.operational_source_contract import (
    ATTRIBUTION, CONTRACT_VERSION, ENDPOINT, CollectionPolicy, aware_utc, iso_utc,
    request_params, validate_zones,
)
from src.api.services.operational_source_storage import LocalEvidenceStore
from src.api.services.operational_source_validation import validate_source

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ALLOWED_HEADERS = {"date", "last-modified", "etag", "content-type", "content-length", "cache-control", "age", "retry-after"}


def utcnow():
    return datetime.now(timezone.utc)


class OperationalSourceCollector:
    def __init__(self, store: LocalEvidenceStore, *, session_factory=requests.Session, clock=utcnow):
        self.store = store
        self.session_factory = session_factory
        self.clock = clock

    def collect(self, zones, policy: CollectionPolicy, *, zone_catalogue_source):
        zones = validate_zones(zones)
        start = aware_utc(self.clock())
        if policy.run_initialization > start:
            raise ValueError("Cannot collect a run that has not initialized yet")
        capture = {"contract_version": CONTRACT_VERSION, "policy": policy.as_dict(),
                   "requested_zones": [zone.as_dict() for zone in zones],
                   "zone_catalogue_source": zone_catalogue_source,
                   "request": {"method": "GET", "endpoint": ENDPOINT, "params": request_params(zones, policy)},
                   "request_started_at_utc": iso_utc(start), "response_received_at_utc": None,
                   "http_status": None, "response_headers": {}, "body_complete": False,
                   "source_publication_utc": None, "publication_evidence_basis": None,
                   "attribution": ATTRIBUTION, "automatic_retries": 0,
                   "request_budget": 1, "max_response_bytes": MAX_RESPONSE_BYTES,
                   "connect_read_timeout_seconds": [10, 30], "transport_error": None}
        raw, pieces = None, []
        response = None
        tick = time.monotonic()
        with self.session_factory() as session:
            # requests defaults to zero retries; make that policy explicit.
            session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
            try:
                response = session.get(ENDPOINT, params=capture["request"]["params"],
                                       timeout=(10, 30), allow_redirects=False, stream=True,
                                       headers={"User-Agent": "NairobiFloodWatch-academic-shadow-collector/1.0"})
                capture["http_status"] = response.status_code
                capture["response_headers"] = {key: value for key, value in response.headers.items() if key.lower() in ALLOWED_HEADERS}
                size = 0
                for piece in response.iter_content(chunk_size=16384):
                    size += len(piece)
                    if size > MAX_RESPONSE_BYTES:
                        capture["transport_error"] = "RESPONSE_SIZE_LIMIT_EXCEEDED"
                        break
                    pieces.append(piece)
                else:
                    capture["body_complete"] = True
                raw = b"".join(pieces)
            except requests.RequestException as exc:
                # Deliberately do not persist exception text, proxy URLs or credentials.
                capture["transport_error"] = type(exc).__name__
                raw = b"".join(pieces) if pieces else None
            finally:
                capture["response_received_at_utc"] = iso_utc(self.clock())
                if response is not None:
                    response.close()
        capture["elapsed_seconds"] = round(time.monotonic() - tick, 6)
        raw_ref = self.store.put("raw", raw) if raw is not None else None
        capture["raw"] = raw_ref
        capture["raw_persisted_at_utc"] = iso_utc(self.clock()) if raw_ref else None
        capture_ref = self.store.put_json("captures", capture)
        # This clock reading follows durable publication of raw and capture files.
        storage_complete = iso_utc(self.clock())
        report = validate_source(capture, raw, policy, storage_complete)
        report.update(capture=capture_ref, raw=raw_ref, attribution=ATTRIBUTION)
        report_ref = self.store.put_json("readiness", report)
        return {"report": report, "reference": report_ref, "replayed": False}

    def replay(self, readiness_path):
        """Recompute saved QC without a request, database query or changed receipt time."""
        path = Path(readiness_path).resolve()
        if not path.is_relative_to(self.store.root):
            raise ValueError("Replay document must be inside the selected store")
        reference = {"path": path.relative_to(self.store.root).as_posix(),
                     "sha256": path.stem, "bytes": path.stat().st_size}
        saved = self.store.read_json(reference, "readiness")
        capture = self.store.read_json(saved["capture"], "captures")
        if saved["raw"] != capture["raw"]:
            raise ValueError("Capture and readiness raw references disagree")
        raw = self.store.read(capture["raw"], "raw") if capture["raw"] else None
        policy = CollectionPolicy.from_dict(capture["policy"])
        recomputed = validate_source(capture, raw, policy, saved["storage_completed_at_utc"])
        recomputed.update(capture=saved["capture"], raw=saved["raw"], attribution=capture["attribution"])
        return {"report": recomputed, "reference": reference, "replayed": True,
                "identical_to_saved_report": recomputed == saved}
