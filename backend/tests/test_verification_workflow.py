import io
import secrets as _secrets
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app, _report_timestamps, _login_timestamps
from app import db as _db

client = TestClient(app)

# Unique suffix per test session so re-runs on the same persistent DB don't collide
_RUN_SUFFIX = _secrets.token_hex(4)
RESIDENT_USER = f"resident_rani_{_RUN_SUFFIX}"
ADMIN_USER = f"admin_kumar_{_RUN_SUFFIX}"
RESIDENT_PASS = "securepassword123"
ADMIN_PASS = "adminpassword123"


@pytest.fixture(autouse=True)
def reset_rate_limit_and_env():
    _report_timestamps.clear()
    _login_timestamps.clear()
    yield
    _report_timestamps.clear()
    _login_timestamps.clear()


def test_auth_register_login_and_roles():
    # 1. Register Resident
    res_reg = client.post(
        "/api/v1/auth/register",
        json={"username": RESIDENT_USER, "password": RESIDENT_PASS, "role": "resident", "display_name": "Rani Resident"},
    )
    assert res_reg.status_code == 200, res_reg.text
    res_data = res_reg.json()
    assert "token" in res_data
    assert res_data["user"]["role"] == "resident"

    # 2. Duplicate username rejected
    dup_reg = client.post(
        "/api/v1/auth/register",
        json={"username": RESIDENT_USER, "password": "password456", "role": "resident"},
    )
    assert dup_reg.status_code == 409

    # 3. Register Admin
    admin_reg = client.post(
        "/api/v1/auth/register",
        json={"username": ADMIN_USER, "password": ADMIN_PASS, "role": "admin", "display_name": "Kumar Officer"},
    )
    assert admin_reg.status_code == 200
    admin_data = admin_reg.json()
    assert admin_data["user"]["role"] == "admin"

    # 4. Login with wrong password
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"username": RESIDENT_USER, "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 5. Login with right password
    login_res = client.post(
        "/api/v1/auth/login",
        json={"username": RESIDENT_USER, "password": RESIDENT_PASS},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]

    # 6. Verify profile via token
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["user"]["username"] == RESIDENT_USER


def test_geography_cascade():
    # States
    st_res = client.get("/api/v1/geography/states")
    assert st_res.status_code == 200
    states = st_res.json()["items"]
    assert any(s["code"] == "TS" for s in states)

    # Districts
    dist_res = client.get("/api/v1/geography/districts?state_code=TS")
    assert dist_res.status_code == 200
    districts = dist_res.json()["items"]
    assert len(districts) >= 1

    # Mandals
    mandal_res = client.get(f"/api/v1/geography/mandals?district_code={districts[0]['code']}")
    assert mandal_res.status_code == 200

    # Villages
    v_res = client.get(f"/api/v1/geography/villages?mandal_code={mandal_res.json()['items'][0]['code']}")
    assert v_res.status_code == 200
    assert len(v_res.json()["items"]) >= 1


def test_village_location_verification():
    # Login resident
    login = client.post("/api/v1/auth/login", json={"username": RESIDENT_USER, "password": RESIDENT_PASS})
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch a village
    villages = client.get("/api/v1/villages?limit=1").json()["items"]
    target_v = villages[0]
    v_id = target_v["id"]
    lat = target_v["latitude"]
    lon = target_v["longitude"]

    # 1. Location verification (accepts any user coordinates)
    match_req = client.post(
        "/api/v1/village-memberships/verify-location",
        json={"village_id": v_id, "latitude": lat + 0.005, "longitude": lon + 0.005, "accuracy_meters": 15.0},
        headers=headers,
    )
    assert match_req.status_code == 200
    match_data = match_req.json()
    assert match_data["matched"] is True
    assert match_data["result"]["status"] in ("accepted", "centroid_match", "boundary_match")

    # 2. Check active membership
    active_v = client.get("/api/v1/me/village", headers=headers)
    assert active_v.status_code == 200
    assert active_v.json()["village"]["village_id"] == v_id

    # 3. Location from any distance is accepted and grants access
    far_req = client.post(
        "/api/v1/village-memberships/verify-location",
        json={"village_id": v_id, "latitude": 51.5074, "longitude": -0.1278, "accuracy_meters": 10.0},
        headers=headers,
    )
    assert far_req.status_code == 200
    assert far_req.json()["matched"] is True
    assert far_req.json()["result"]["status"] in ("accepted", "centroid_match", "boundary_match")


def test_admin_development_import_workflow():
    # 1. Resident cannot access admin import
    res_login = client.post("/api/v1/auth/login", json={"username": RESIDENT_USER, "password": RESIDENT_PASS})
    res_headers = {"Authorization": f"Bearer {res_login.json()['token']}"}
    forbidden = client.get("/api/v1/admin/imports", headers=res_headers)
    assert forbidden.status_code == 403

    # 2. Admin can access
    adm_login = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    adm_headers = {"Authorization": f"Bearer {adm_login.json()['token']}"}

    # Template
    template = client.get("/api/v1/admin/imports/template.csv")
    assert template.status_code == 200
    assert "asset_or_project_name" in template.text

    # Validation
    v_id = client.get("/api/v1/villages?limit=1").json()["items"][0]["id"]
    csv_data = f"""record_id,state_name,district_name,mandal_name,village_id,village_name,dimension,asset_or_project_name,description,reported_status,start_date,reported_completion_date,last_observed_date,source_name,source_url,source_reference_id,estimated_cost,latitude,longitude,notes
REC-TEST-01,Telangana,Karimnagar,Thimmapur,{v_id},Demo Village,roads,Bridge Construction,Submersible causeway repair,reportedly_completed,2024-01-01,2024-09-01,2024-09-10,R&B Dept,https://rb.gov.in/,RB-102,5000000,18.44,79.12,Test import record
REC-TEST-02,Telangana,Karimnagar,Thimmapur,{v_id},Demo Village,electricity,Solar High-Mast Lighting,100W LED solar pole installation,operational,2024-02-01,2024-05-01,2024-05-10,Discom,https://discom.gov.in/,DIS-55,200000,18.44,79.12,Test import lighting
"""
    files = {"file": ("test_import.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    val_res = client.post("/api/v1/admin/imports/validate", files=files, headers=adm_headers)
    assert val_res.status_code == 200, val_res.text
    val_data = val_res.json()
    assert val_data["accepted_count"] == 2
    assert val_data["rejected_count"] == 0

    # Confirmation
    confirm_res = client.post(
        "/api/v1/admin/imports/confirm",
        json={
            "batch_id": val_data["batch_id"],
            "filename": "test_import.csv",
            "file_hash": val_data["file_hash"],
            "records": val_data["preview_records"],
            "errors": [],
            "notes": "Verified test batch",
        },
        headers=adm_headers,
    )
    assert confirm_res.status_code == 200

    # Verify record in village records
    v_records = client.get(f"/api/v1/admin/villages/{v_id}/development-records", headers=adm_headers)
    assert v_records.status_code == 200
    assert any(r["id"] == "REC-TEST-01" for r in v_records.json()["items"])


def test_admin_import_tsv_and_status_normalization():
    """Validates that:
    1. TSV files are accepted (tab-delimited)
    2. 'Completed & Finalled' maps to 'reportedly_completed'
    3. Unknown village IDs are auto-registered (not rejected)
    4. Missing lat/lon is allowed
    """
    adm_login = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    adm_headers = {"Authorization": f"Bearer {adm_login.json()['token']}"}

    tsv_data = (
        "record_id\tstate_name\tdistrict_name\tmandal_name\tvillage_id\tvillage_name\tdimension\t"
        "asset_or_project_name\tdescription\treported_status\tstart_date\treported_completion_date\t"
        "last_observed_date\tsource_name\tsource_url\tsource_reference_id\testimated_cost\tlatitude\tlongitude\tnotes\n"
        f"REC-AUTO-001\tTelangana\tMahabubabad\tGudur\tTEL-NEW-AUTO-VIL-{_RUN_SUFFIX}\tAuto Village\troads\t"
        "Test Road\tTest description.\tCompleted & Finalled\t\t\t\t"
        "District Dept\thttps://example.gov.in/\tTST-001\t5000000\t\t\tAuto test\n"
        f"REC-AUTO-002\tTelangana\tMahabubabad\tGudur\tTEL-NEW-AUTO-VIL-{_RUN_SUFFIX}\tAuto Village\telectricity\t"
        "Solar Lights\tSolar lighting.\toperational\t\t\t\t"
        "District Dept\thttps://example.gov.in/\tTST-002\t200000\t\t\tAuto test"
    )

    files = {"file": ("user_data.tsv", io.BytesIO(tsv_data.encode("utf-8")), "text/tab-separated-values")}
    val_res = client.post("/api/v1/admin/imports/validate", files=files, headers=adm_headers)
    assert val_res.status_code == 200, val_res.text
    val_data = val_res.json()
    assert val_data["accepted_count"] == 2, f"Expected 2 accepted, got {val_data['accepted_count']}. Errors: {val_data.get('rejected_errors')}"
    assert val_data["rejected_count"] == 0

    # Verify status was normalized correctly
    rec = next((r for r in val_data["preview_records"] if r["id"] == "REC-AUTO-001"), None)
    assert rec is not None, "REC-AUTO-001 not in preview"
    assert rec["reported_status"] == "reportedly_completed", f"Status should be 'reportedly_completed', got: {rec['reported_status']}"

    # Confirm import
    confirm_res = client.post(
        "/api/v1/admin/imports/confirm",
        json={
            "batch_id": val_data["batch_id"],
            "filename": "user_data.tsv",
            "file_hash": val_data["file_hash"],
            "records": val_data["preview_records"],
            "errors": [],
            "notes": "TSV auto-test",
        },
        headers=adm_headers,
    )
    assert confirm_res.status_code == 200
    # Check village was auto-registered
    vil = client.get(f"/api/v1/villages/TEL-NEW-AUTO-VIL-{_RUN_SUFFIX}").json()
    assert vil.get("id") == f"TEL-NEW-AUTO-VIL-{_RUN_SUFFIX}", "Village was not auto-registered"
    # Records should be visible
    v_recs = client.get(f"/api/v1/admin/villages/TEL-NEW-AUTO-VIL-{_RUN_SUFFIX}/development-records", headers=adm_headers)
    assert v_recs.status_code == 200
    assert any(r["id"] == "REC-AUTO-001" for r in v_recs.json()["items"])


def test_resident_submission_with_image_and_protected_attachment():
    # Resident login
    res_login = client.post("/api/v1/auth/login", json={"username": RESIDENT_USER, "password": RESIDENT_PASS})
    res_headers = {"Authorization": f"Bearer {res_login.json()['token']}"}

    # Admin login
    adm_login = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    adm_headers = {"Authorization": f"Bearer {adm_login.json()['token']}"}

    # Second resident login (babu — unique per run too)
    babu_user = f"resident_babu_{_RUN_SUFFIX}"
    client.post("/api/v1/auth/register", json={"username": babu_user, "password": "babupassword123", "role": "resident"})
    babu_login = client.post("/api/v1/auth/login", json={"username": babu_user, "password": "babupassword123"})
    babu_headers = {"Authorization": f"Bearer {babu_login.json()['token']}"}

    # Fetch resident development records
    dev_records = client.get("/api/v1/me/development-records", headers=res_headers).json()["items"]
    assert len(dev_records) >= 1
    target_rec = dev_records[0]
    rec_id = target_rec["id"]

    # Minimal valid JPEG file: SOI (\xff\xd8), APP0 marker, EOI (\xff\xd9)
    valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"

    form_data = {
        "observed_status": "exists_but_damaged_or_not_functional",
        "notes": "Guard rails broken and surface potholed after heavy monsoon rain.",
        "capture_latitude": "18.438",
        "capture_longitude": "79.128",
        "capture_accuracy": "8.5",
        "client_capture_time": "2026-10-09T23:30:00Z",
        "user_ai_verdict_notes": "Resident concurs that visible damage is present.",
    }
    files = {"file": ("camera_photo.jpg", valid_jpeg, "image/jpeg")}

    # Submit evidence
    sub_res = client.post(
        f"/api/v1/development-records/{rec_id}/submissions",
        data=form_data,
        files=files,
        headers=res_headers,
    )
    assert sub_res.status_code == 200, sub_res.text
    sub_data = sub_res.json()["submission"]
    assert sub_data["observed_status"] == "exists_but_damaged_or_not_functional"
    assert sub_data["attachment"] is not None
    storage_key = sub_data["attachment"]["storage_key"]
    sub_id = sub_data["id"]

    # AI analysis is present (complete or unconfigured fallback)
    assert sub_data["ai_analysis"] is not None
    assert "summary" in sub_data["ai_analysis"]

    # Access Control on protected attachment
    # 1. Babu (other resident) is denied
    assert client.get(f"/api/v1/attachments/{storage_key}", headers=babu_headers).status_code == 403

    # 2. Submitting resident is granted
    assert client.get(f"/api/v1/attachments/{storage_key}", headers=res_headers).status_code == 200

    # 3. Admin is granted
    assert client.get(f"/api/v1/attachments/{storage_key}", headers=adm_headers).status_code == 200

    # Resident lists submissions
    my_subs = client.get("/api/v1/me/submissions", headers=res_headers).json()["items"]
    assert any(s["id"] == sub_id for s in my_subs)

    # Resident updates follow-up note
    upd_note = client.post(
        f"/api/v1/submissions/{sub_id}/user-review",
        json={"user_notes": "Resident verified again in daylight: culvert is blocked."},
        headers=res_headers,
    )
    assert upd_note.status_code == 200


def test_admin_review_and_indicator_promotion():
    adm_login = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    adm_headers = {"Authorization": f"Bearer {adm_login.json()['token']}"}

    # List submissions in review queue
    subs = client.get("/api/v1/admin/submissions", headers=adm_headers).json()["items"]
    assert len(subs) >= 1
    target_sub = subs[0]
    sub_id = target_sub["id"]
    village_id = target_sub["village_id"]

    # Admin reviews submission
    review_res = client.post(
        f"/api/v1/admin/submissions/{sub_id}/review",
        json={"review_status": "verified", "review_note": "Confirmed by panchayat secretary on site inspection."},
        headers=adm_headers,
    )
    assert review_res.status_code == 200
    assert review_res.json()["submission"]["review_status"] == "verified"

    # Admin promotes to trusted indicator
    promote_res = client.post(
        f"/api/v1/admin/submissions/{sub_id}/promote-indicator",
        json={
            "dimension": "roads",
            "indicator_name": "Field-Verified Seasonal Road Accessibility",
            "promoted_value": 35.0,
            "reason": "Direct evidence of monsoon culvert failure reducing passability score.",
        },
        headers=adm_headers,
    )
    assert promote_res.status_code == 200
    promoted_data = promote_res.json()["promoted_indicator"]
    assert promoted_data["promoted_value"] == 35.0

    # Verification summary for village
    sum_res = client.get(f"/api/v1/admin/villages/{village_id}/verification-summary", headers=adm_headers)
    assert sum_res.status_code == 200
    summary = sum_res.json()["summary"]
    assert summary["verified_submissions_count"] >= 1
    assert summary["response_coverage_percent"] > 0

    # Audit events logged
    audit_res = client.get("/api/v1/admin/audit-events", headers=adm_headers)
    assert audit_res.status_code == 200
    events = audit_res.json()["items"]
    assert any(e["action"] == "promote_indicator" for e in events)

