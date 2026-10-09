from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app, _report_timestamps

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Clear the in-memory rate-limit store before every test to prevent cross-test pollution."""
    _report_timestamps.clear()
    yield
    _report_timestamps.clear()


# ---------------------------------------------------------------------------
# Existing tests (unchanged)
# ---------------------------------------------------------------------------
def test_health_and_summary():
    assert client.get('/health').status_code == 200
    summary = client.get('/api/v1/summary')
    assert summary.status_code == 200
    body = summary.json()
    assert body['total_villages'] >= 1
    assert 'DEMO DATA' in body['data_notice']


def test_village_list_detail_and_geojson():
    result = client.get('/api/v1/villages?limit=3')
    assert result.status_code == 200
    body = result.json()
    assert len(body['items']) == 3
    village_id = body['items'][0]['id']
    detail = client.get(f'/api/v1/villages/{village_id}')
    assert detail.status_code == 200
    assert detail.json()['id'] == village_id
    geo = client.get('/api/v1/map').json()
    assert geo['type'] == 'FeatureCollection'
    assert len(geo['features']) >= 1


def test_scenario_api_validates_and_does_not_mutate_baseline():
    village = client.get('/api/v1/villages?limit=1').json()['items'][0]
    baseline = village['score']['overall']
    response = client.post('/api/v1/scenarios', json={
        'village_id': village['id'], 'overrides': {'roads': 90},
        'assumptions': 'Illustrative scenario only'
    })
    assert response.status_code == 200
    assert response.json()['baseline']['score'] == baseline
    invalid = client.post('/api/v1/scenarios', json={
        'village_id': village['id'], 'overrides': {'roads': 101}
    })
    assert invalid.status_code == 422
    after = client.get(f"/api/v1/villages/{village['id']}").json()['score']['overall']
    assert after == baseline


def test_csv_export_and_methodology():
    response = client.get('/api/v1/export.csv')
    assert response.status_code == 200
    assert response.text.startswith('village_id,village_name,district')
    # New columns present
    assert 'export_scope' in response.text
    assert 'methodology_version' in response.text
    method = client.get('/api/v1/methodology')
    assert method.status_code == 200
    assert abs(sum(method.json()['weights'].values()) - 1.0) < 1e-9


def test_public_report_listing_hides_description_and_status_requires_reference():
    village = client.get('/api/v1/villages?limit=1').json()['items'][0]
    created = client.post('/api/v1/field-reports', json={
        'village_id': village['id'],
        'dimension': 'roads',
        'description': 'Seasonal access is difficult after rainfall.',
    })
    assert created.status_code == 200
    body = created.json()
    assert body['verification_status'] == 'unverified'
    assert body['reference_code']
    assert 'description' not in body

    listing = client.get(f"/api/v1/field-reports?village_id={village['id']}")
    assert listing.status_code == 200
    assert all('description' not in item for item in listing.json()['items'])

    status = client.get(f"/api/v1/field-reports/status/{body['reference_code']}")
    assert status.status_code == 200
    assert status.json()['report']['verification_status'] == 'unverified'
    assert status.json()['report']['history'][0]['status'] == 'unverified'
    assert client.get('/api/v1/field-reports/status/not-a-real-reference').status_code == 404


# ---------------------------------------------------------------------------
# New: rate limiting
# ---------------------------------------------------------------------------
def test_rate_limiting_blocks_excessive_submissions():
    # After RATE_LIMIT_REPORTS submissions from the same IP, the next should be 429.
    from app.config import RATE_LIMIT_REPORTS
    village = client.get('/api/v1/villages?limit=1').json()['items'][0]
    payload = {'village_id': village['id'], 'dimension': 'roads', 'description': 'Test report for rate limit check.'}
    for _ in range(RATE_LIMIT_REPORTS):
        r = client.post('/api/v1/field-reports', json=payload)
        assert r.status_code == 200, f"Unexpected status {r.status_code}: {r.text}"
    # One more should be blocked
    r = client.post('/api/v1/field-reports', json=payload)
    assert r.status_code == 429


# ---------------------------------------------------------------------------
# New: reviewer auth — 501 when REVIEWER_TOKEN not set
# ---------------------------------------------------------------------------
def test_reviewer_endpoints_require_token():
    # When REVIEWER_TOKEN env var is empty, moderation endpoints return 501.
    village = client.get('/api/v1/villages?limit=1').json()['items'][0]
    created = client.post('/api/v1/field-reports', json={
        'village_id': village['id'], 'dimension': 'digital',
        'description': 'Connectivity is intermittent during peak hours.',
    })
    ref = created.json()['reference_code']

    # Moderate without token — 501 (not configured)
    r = client.post(f'/api/v1/reviewer/reports/{ref}/moderate', json={'action': 'approve', 'note': ''})
    assert r.status_code == 501

    # Reviewer list without token — 501
    r = client.get('/api/v1/reviewer/reports')
    assert r.status_code == 501


# ---------------------------------------------------------------------------
# New: reviewer auth — 401 with wrong token
# ---------------------------------------------------------------------------
def test_reviewer_endpoints_reject_wrong_token():
    import os
    import importlib
    import app.config as cfg
    import app.main as m

    original = cfg.REVIEWER_TOKEN
    try:
        cfg.REVIEWER_TOKEN = "correct-token"
        village = client.get('/api/v1/villages?limit=1').json()['items'][0]
        created = client.post('/api/v1/field-reports', json={
            'village_id': village['id'], 'dimension': 'electricity',
            'description': 'Frequent outages lasting several hours.',
        })
        ref = created.json()['reference_code']

        # Wrong token → 401
        r = client.post(
            f'/api/v1/reviewer/reports/{ref}/moderate',
            json={'action': 'approve', 'note': 'Looks valid'},
            headers={'Authorization': 'Bearer wrong-token'},
        )
        assert r.status_code == 401
    finally:
        cfg.REVIEWER_TOKEN = original


# ---------------------------------------------------------------------------
# New: reviewer moderation happy path
# ---------------------------------------------------------------------------
def test_reviewer_moderation_changes_status_and_records_history():
    import app.config as cfg
    original = cfg.REVIEWER_TOKEN
    try:
        cfg.REVIEWER_TOKEN = "test-reviewer-secret"
        village = client.get('/api/v1/villages?limit=1').json()['items'][0]
        created = client.post('/api/v1/field-reports', json={
            'village_id': village['id'], 'dimension': 'essential_services',
            'description': 'Health centre closed on weekends and lacks equipment.',
        })
        ref = created.json()['reference_code']

        r = client.post(
            f'/api/v1/reviewer/reports/{ref}/moderate',
            json={'action': 'approve', 'note': 'Confirmed by local admin survey.'},
            headers={'Authorization': 'Bearer test-reviewer-secret'},
        )
        assert r.status_code == 200
        data = r.json()['report']
        assert data['verification_status'] == 'verified'
        assert len(data['history']) == 2  # initial 'unverified' + 'verified'
        assert data['history'][-1]['status'] == 'verified'

        # Public status lookup should reflect the new status
        status = client.get(f'/api/v1/field-reports/status/{ref}')
        assert status.json()['report']['verification_status'] == 'verified'
    finally:
        cfg.REVIEWER_TOKEN = original


# ---------------------------------------------------------------------------
# New: CSV preview/confirm two-step import
# ---------------------------------------------------------------------------
def test_csv_preview_and_confirm_workflow():
    header = "id,name,district,latitude,longitude,population,digital_score,electricity_score,road_score,public_digital_score,essential_services_score"
    row1   = "test-v1,Test Village 1,Test District,12.34,56.78,1000,80,80,80,80,80"
    row2   = "test-v2,Test Village 2,Test District,12.35,56.79,1500,60,60,60,60,60"
    csv_content = "\n".join([header, row1, row2])

    # 1. Preview
    files = {'file': ('test.csv', csv_content.encode('utf-8'), 'text/csv')}
    preview_res = client.post('/api/v1/imports/csv/preview', files=files)
    assert preview_res.status_code == 200
    preview_data = preview_res.json()
    
    assert preview_data['accepted_count'] == 2
    assert len(preview_data['rejected']) == 0
    token = preview_data['preview_token']
    
    # 2. Confirm
    confirm_res = client.post(f'/api/v1/imports/csv/confirm?preview_token={token}')
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data['accepted'] == 2
    
    # 3. Check history
    history_res = client.get('/api/v1/imports/history')
    assert history_res.status_code == 200
    history_items = history_res.json()['items']
    assert any(item['token'] == token for item in history_items)
