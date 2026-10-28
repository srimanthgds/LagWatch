import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "OPERATIONAL"

def test_login_and_auth():
    # Correct login
    res = client.post("/api/v1/auth/login", json={
        "email": "engineer@insulguard.com",
        "password": "engineerpassword123"
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["role"] == "integrity_engineer"

    # Invalid login
    bad_res = client.post("/api/v1/auth/login", json={
        "email": "engineer@insulguard.com",
        "password": "wrongpassword"
    })
    assert bad_res.status_code == 401

def test_list_and_filter_segments():
    # List all
    res = client.get("/api/v1/segments?limit=20")
    assert res.status_code == 200
    segments = res.json()
    assert len(segments) > 0
    seg = segments[0]
    assert "line_tag" in seg
    assert "nominal_wall_mm" in seg
    assert "health_state" in seg

    # Filter by area
    area_res = client.get("/api/v1/segments?area=Fluid Catalytic Cracking (FCC)&limit=10")
    assert area_res.status_code == 200
    fcc_segs = area_res.json()
    for s in fcc_segs:
        assert s["area"] == "Fluid Catalytic Cracking (FCC)"

def test_segment_detail():
    res = client.get("/api/v1/segments/1")
    assert res.status_code == 200
    detail = res.json()
    assert detail["id"] == 1
    assert "nodes" in detail
    assert len(detail["nodes"]) == 8  # 8 moisture nodes per line
    assert "pec_readings" in detail
    assert "dts_readings" in detail

def test_alarms_and_two_step_acknowledge():
    # Login as engineer
    login_res = client.post("/api/v1/auth/login", json={
        "email": "engineer@insulguard.com",
        "password": "engineerpassword123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Get active alarm
    alarms_res = client.get("/api/v1/alarms?status_filter=ACTIVE")
    assert alarms_res.status_code == 200
    alarms = alarms_res.json()
    if alarms:
        alarm_id = alarms[0]["id"]
        # Attempt ack without two-step confirm checkbox -> should fail
        fail_ack = client.post(f"/api/v1/alarms/{alarm_id}/acknowledge", json={
            "ack_notes": "Checking with field crew",
            "confirmed_by_operator": False
        }, headers=headers)
        assert fail_ack.status_code == 400

        # Two-step confirm -> succeeds
        ack_res = client.post(f"/api/v1/alarms/{alarm_id}/acknowledge", json={
            "ack_notes": "Ultrasonic thickness crew deployed to low point elbow",
            "confirmed_by_operator": True
        }, headers=headers)
        assert ack_res.status_code == 200
        assert ack_res.json()["status"] == "ACKNOWLEDGED"

def test_kpi_summary():
    res = client.get("/api/v1/kpis")
    assert res.status_code == 200
    kpis = res.json()
    assert kpis["total_segments"] >= 250
    assert kpis["total_nodes"] >= 2000
    assert "health_breakdown" in kpis
    assert kpis["projected_avoided_cost_usd"] > 10_000_000

def test_financial_calculations():
    res = client.post("/api/v1/financials/calculate", json={
        "baseline_annual_loss_usd": 26800000.0,
        "capex_usd": 12513000.0,
        "opex_usd_yr": 1850000.0,
        "discount_rate": 0.08,
        "loss_reduction_pct": 0.65
    })
    assert res.status_code == 200
    data = res.json()
    assert data["base_case_payback_years"] < 2.0  # Fast payback on severe CUI losses
    assert data["base_case_5yr_npv_usd"] > 30_000_000.0
    assert len(data["scenarios"]) == 4

def test_opcua_browse_and_read():
    res = client.get("/api/v1/opcua/browse?limit=5")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert len(data["nodes"]) > 0

    first_node_browse_name = data["nodes"][0]["browseName"]
    read_res = client.get(f"/api/v1/opcua/read/{first_node_browse_name}")
    assert read_res.status_code == 200
    assert "value" in read_res.json()
