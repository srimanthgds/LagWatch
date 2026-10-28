import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.entities import Segment, Alarm, WorkOrder, MoistureNode
from app.domain.alarm_fsm import evaluate_alarm_state
from app.domain.remaining_life import calculate_remaining_life, evaluate_health_state

client = TestClient(app)

def test_tracer_leak_scenario_state_machine_transitions():
    """Validates full end-to-end transition path:
    State 0 (Normal) -> State 1 (Advisory) -> State 2 (Verify) -> State 3 (Plan Repair) -> State 4 (Escalate)
    """
    db = SessionLocal()
    try:
        # Create or pick a clean test segment
        test_seg = db.query(Segment).filter(Segment.alarm_state == 0).first()
        assert test_seg is not None
        seg_id = test_seg.id
        nom_wall = test_seg.nominal_wall_mm
        t_min = test_seg.t_min_mm

        # 1. State 0 (Normal)
        assert test_seg.alarm_state == 0

        # 2. Moisture / Tracer Steam leak begins:
        # Ingestion of 2 wet readings (>10%) triggers State 1 (Advisory)
        state_1, reason_1 = evaluate_alarm_state(
            current_state=0,
            consecutive_wet_readings=2,
            consecutive_dry_readings=0,
            jacket_delta_T_C=8.0,  # Hot steam jacket delta-T
            wall_loss_pct_nominal=5.0,
            remaining_life_yr=14.0,
            current_wall_mm=nom_wall - 0.3,
            t_min_mm=t_min
        )
        assert state_1 == 1
        assert "ADVISORY" in reason_1

        # 3. Corrosion accelerates, wall loss exceeds 25% of nominal or remaining life < 5 yr:
        # Triggers State 2 (Verify)
        state_2, reason_2 = evaluate_alarm_state(
            current_state=1,
            consecutive_wet_readings=4,
            consecutive_dry_readings=0,
            jacket_delta_T_C=10.0,
            wall_loss_pct_nominal=28.0,  # > 25%
            remaining_life_yr=4.2,       # < 5 yr
            current_wall_mm=nom_wall * 0.72,
            t_min_mm=t_min
        )
        assert state_2 == 2
        assert "VERIFY" in reason_2

        # 4. Severe thinning continues, remaining life drops under 2.0 yr:
        # Triggers State 3 (Plan Repair)
        state_3, reason_3 = evaluate_alarm_state(
            current_state=2,
            consecutive_wet_readings=6,
            consecutive_dry_readings=0,
            jacket_delta_T_C=12.0,
            wall_loss_pct_nominal=40.0,
            remaining_life_yr=1.4,  # < 2.0 yr threshold!
            current_wall_mm=t_min + 1.2,
            t_min_mm=t_min
        )
        assert state_3 == 3
        assert "PLAN REPAIR" in reason_3

        # 5. Imminent breach: wall within 0.5 mm of t_min:
        # Triggers State 4 (Escalate)
        state_4, reason_4 = evaluate_alarm_state(
            current_state=3,
            consecutive_wet_readings=8,
            consecutive_dry_readings=0,
            jacket_delta_T_C=14.0,
            wall_loss_pct_nominal=55.0,
            remaining_life_yr=0.3,
            current_wall_mm=t_min + 0.35,  # within 0.5 mm!
            t_min_mm=t_min
        )
        assert state_4 == 4
        assert "CRITICAL" in reason_4

        # Now test the HTTP Scenario Injection Endpoint for Tracer Leak
        res = client.post("/api/v1/scenarios/inject", json={
            "scenario_type": "tracer_leak",
            "target_segment_id": seg_id,
            "severity": 1.2
        })
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["scenario"] == "tracer_leak"
        assert data["new_alarm_state"] in [2, 3, 4]
        if data["new_alarm_state"] >= 3:
            assert data["auto_work_order_id"] is not None

            # Verify the work order exists in database
            wo = db.query(WorkOrder).filter(WorkOrder.id == data["auto_work_order_id"]).first()
            assert wo is not None
            assert wo.status == "DRAFT"
            assert "Emergency Steam Tracer" in wo.title

    finally:
        db.close()
