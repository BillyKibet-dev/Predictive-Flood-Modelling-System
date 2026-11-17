"""Report status by reference + private code; photos without metadata; officer advisories."""
from datetime import datetime, timedelta, timezone
import io

import pytest
from PIL import Image

from src.api.config import settings
from src.api.models.db_models import AreaAdvisory, CitizenReport
from src.api.utils.security import create_access_token
from tests.test_api import api, password_hash  # noqa: F401  (fixtures)

KIBRA_PIN = dict(latitude=-1.315111, longitude=36.782472)
LANGATA_PIN = dict(latitude=-1.310944, longitude=36.817167)


def token(role="officer"):
    return {"Authorization": "Bearer " + create_access_token({"sub": f"{role}@example.test"})}


def send(client, **changes):
    body = dict(observed_condition="Street flooding", perceived_severity="Serious", location_description="Fixture landmark",
                area_id="nairobi-subcounty-kibra", **changes)
    response = client.post("/citizen-report", json=body)
    assert response.status_code == 201
    return response.json()


def photo_with_gps(fmt="JPEG", size=(2400, 1800)):
    image = Image.new("RGB", size, (30, 90, 160))
    exif = Image.Exif()
    exif[0x010F] = "FixturePhone"                        # Make
    exif[0x8825] = {1: "S", 2: (1.0, 18.0, 54.0), 3: "E", 4: (36.0, 46.0, 56.0)}   # GPS
    out = io.BytesIO()
    image.save(out, format=fmt, exif=exif.tobytes()) if fmt != "PNG" else image.save(out, format=fmt)
    return out.getvalue()


@pytest.fixture
def photos(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "REPORT_PHOTO_DIR", str(tmp_path / "photos"))
    return tmp_path / "photos"


def test_code_is_shown_once_and_status_needs_reference_and_code(api):
    client, db = api
    saved = send(client)
    code = saved["tracking_code"]
    assert len(code) == 9 and code[4] == "-"
    stored = db.get(CitizenReport, saved["id"])
    assert stored.tracking_hash and code.replace("-", "") not in stored.tracking_hash
    staff_view = client.get("/citizen-reports", headers=token()).json()["items"][0]
    assert staff_view["tracking_code"] is None, "staff lists never show the code"

    status = client.post("/citizen-report/status", json=dict(reference=saved["id"], code=code.lower().replace("-", " ")))
    assert status.status_code == 200 and status.headers["cache-control"] == "no-store"
    body = status.json()
    assert body["status_text"].startswith("Received") and body["sub_county"] == "Kibra"
    assert "review_note" not in body and "description" not in body

    for wrong in (dict(reference=saved["id"], code="AAAA-AAAA"), dict(reference=999, code=code)):
        miss = client.post("/citizen-report/status", json=wrong)
        assert miss.status_code == 404 and "do not match" in miss.json()["detail"]


def test_status_follows_the_officer_decision_in_plain_words(api):
    client, _ = api
    saved = send(client)
    client.patch(f"/citizen-reports/{saved['id']}/review", headers=token(),
                 json=dict(status="ActionNeeded", note="Private staff note", expected_version=0))
    body = client.post("/citizen-report/status", json=dict(reference=saved["id"], code=saved["tracking_code"])).json()
    assert body["review_status"] == "ActionNeeded" and "following it up" in body["status_text"]
    assert "Private staff note" not in str(body)


def test_photo_is_reencoded_without_gps_shrunk_and_staff_only(api, photos):
    client, _ = api
    saved = send(client)
    raw = photo_with_gps()
    assert b"FixturePhone" in raw
    upload = client.post(f"/citizen-report/{saved['id']}/photo", data=dict(code=saved["tracking_code"]),
                         files=dict(photo=("p.jpg", raw, "image/jpeg")))
    assert upload.status_code == 200, upload.text
    assert client.get(f"/citizen-reports/{saved['id']}/photo").status_code == 401
    served = client.get(f"/citizen-reports/{saved['id']}/photo", headers=token())
    assert served.status_code == 200 and served.headers["content-type"] == "image/jpeg"
    data = served.content
    assert b"FixturePhone" not in data and b"Exif" not in data
    with Image.open(io.BytesIO(data)) as image:
        assert max(image.size) == 1600 and not image.getexif()
    assert client.get("/citizen-reports", headers=token()).json()["items"][0]["photo_attached"] is True
    again = client.post(f"/citizen-report/{saved['id']}/photo", data=dict(code=saved["tracking_code"]),
                        files=dict(photo=("p.jpg", raw, "image/jpeg")))
    assert again.status_code == 409


@pytest.mark.parametrize("content,status", [(b"not an image", 422), (b"", 422), (b"x" * (8 * 1024 * 1024 + 10), 422)],
                         ids=["not-image", "empty", "over-8mb"])
def test_bad_uploads_are_refused(api, photos, content, status):
    client, _ = api
    saved = send(client)
    response = client.post(f"/citizen-report/{saved['id']}/photo", data=dict(code=saved["tracking_code"]),
                           files=dict(photo=("p.jpg", content, "image/jpeg")))
    assert response.status_code == status
    assert not any(photos.glob("*.jpg")) if photos.exists() else True


def test_photo_needs_the_code_and_the_two_hour_window(api, photos):
    client, db = api
    saved = send(client)
    wrong = client.post(f"/citizen-report/{saved['id']}/photo", data=dict(code="AAAA-AAAA"),
                        files=dict(photo=("p.png", photo_with_gps("PNG", (50, 50)), "image/png")))
    assert wrong.status_code == 404
    db.get(CitizenReport, saved["id"]).timestamp = datetime.now(timezone.utc) - timedelta(hours=3)
    db.commit()
    late = client.post(f"/citizen-report/{saved['id']}/photo", data=dict(code=saved["tracking_code"]),
                       files=dict(photo=("p.png", photo_with_gps("PNG", (50, 50)), "image/png")))
    assert late.status_code == 409


def test_officer_advisory_lifecycle(api):
    client, db = api
    body = dict(area_id="nairobi-subcounty-langata", place_label="Outering Road underpass", message="Avoid the underpass until water clears.",
                level="Warning", hours=6, **LANGATA_PIN)
    assert client.post("/advisories", json=body).status_code == 401
    created = client.post("/advisories", json=body, headers=token())
    assert created.status_code == 201 and created.json()["state"] == "Active"
    public = client.get("/advisories/active").json()["items"]
    assert len(public) == 1 and public[0]["area_name"] == "Langata" and "issued_by" not in public[0]
    # Pin and sub-county must agree.
    assert client.post("/advisories", json=dict(body, area_id="nairobi-subcounty-kibra"), headers=token()).status_code == 422
    assert client.post("/advisories", json=dict(body, hours=100), headers=token()).status_code == 422
    withdrawn = client.post(f"/advisories/{created.json()['id']}/withdraw", headers=token("admin"))
    assert withdrawn.json()["state"] == "Withdrawn"
    assert client.get("/advisories/active").json()["items"] == []
    row = db.get(AreaAdvisory, created.json()["id"])
    assert row.withdrawn_by is not None and row.created_by != row.withdrawn_by


def test_expired_advisories_leave_the_public_list(api):
    client, db = api
    created = client.post("/advisories", json=dict(area_id="nairobi-subcounty-kibra", message="Drain blocked near the market.", hours=1),
                          headers=token()).json()
    row = db.get(AreaAdvisory, created["id"])
    row.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert client.get("/advisories/active").json()["items"] == []
    assert client.get("/advisories", headers=token()).json()["items"][0]["state"] == "Expired"
