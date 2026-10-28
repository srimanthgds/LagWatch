from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import Segment, MoistureNode, PECReading, DTSReading, Alarm, WorkOrder, AuditLog, User
from app.schemas.schemas import ScenarioTrigger
from app.domain.alarm_fsm import evaluate_alarm_state
from app.domain.remaining_life import calculate_remaining_life, evaluate_health_state
from app.domain.corrosion import calculate_model_cr
from app.api.deps import require_roles

router = APIRouter(prefix="/scenarios", tags=["Scenario Injection & Simulator Control"])

@router.post("/inject")
def inject_scenario(
    trigger: ScenarioTrigger,
    current_user: User = Depends(require_roles(["admin", "integrity_engineer", "viewer"])),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    scenario_type = trigger.scenario_type.lower()
    now = datetime.now(timezone.utc)

    # 1. RAIN EVENT
    if scenario_type == "rain_event":
        target_query = db.query(Segment)
        if trigger.target_area:
            target_query = target_query.filter(Segment.area == trigger.target_area)
        segments = target_query.limit(40).all()
        
        affected_nodes_count = 0
        for seg in segments:
            seg.rolling_wet_fraction = min(1.0, seg.rolling_wet_fraction + 0.35)
            nodes = db.query(MoistureNode).filter(MoistureNode.segment_id == seg.id).all()
            for n in nodes:
                n.moisture_pct = min(100.0, max(25.0, n.moisture_pct + 35.0))
                n.consecutive_wet_count += 2
                n.consecutive_dry_count = 0
                n.last_seen = now
                affected_nodes_count += 1
            
            # Re-evaluate alarm
            st, reason = evaluate_alarm_state(
                current_state=seg.alarm_state,
                consecutive_wet_readings=2,
                consecutive_dry_readings=0,
                jacket_delta_T_C=3.0,
                wall_loss_pct_nominal=((seg.nominal_wall_mm - seg.current_wall_mm) / seg.nominal_wall_mm) * 100.0,
                remaining_life_yr=seg.remaining_life_yr,
                current_wall_mm=seg.current_wall_mm,
                t_min_mm=seg.t_min_mm
            )
            if st > seg.alarm_state:
                seg.alarm_state = st
                alarm = Alarm(
                    segment_id=seg.id,
                    state=st,
                    trigger_reason=f"Rain Event Ingress: {reason}",
                    severity="LOW" if st == 1 else "MEDIUM",
                    status="ACTIVE",
                    created_at=now
                )
                db.add(alarm)
                
        db.commit()
        return {
            "status": "success",
            "scenario": "rain_event",
            "message": f"Precipitation storm injected across {len(segments)} segments ({affected_nodes_count} nodes wet)."
        }

    # 2. TRACER LEAK (Demonstrates Advisory -> Verify -> Plan Repair transitions)
    elif scenario_type == "tracer_leak":
        seg = None
        if trigger.target_segment_id:
            seg = db.query(Segment).filter(Segment.id == trigger.target_segment_id).first()
        if not seg:
            # Pick a hot/steam-traced line in Cracking or Hydrotreater
            seg = db.query(Segment).filter(Segment.service.in_(["steam-traced", "hot"])).first()
        
        if not seg:
            seg = db.query(Segment).first()

        # Step 1: Steam tracer bursts -> 85% moisture and +14C jacket delta-T
        nodes = db.query(MoistureNode).filter(MoistureNode.segment_id == seg.id).all()
        for n in nodes:
            n.moisture_pct = 85.0
            n.jacket_temp_C += 14.0
            n.consecutive_wet_count += 3
            n.consecutive_dry_count = 0
            n.last_seen = now
            
        seg.rolling_wet_fraction = 0.90
        # Accelerated corrosion in boiling zone: effective CR surges to 1.15 mm/yr
        seg.effective_cr_mm_yr = 1.15
        
        # Severe thinning occurs
        loss = round(trigger.severity * 1.5, 2)  # mm thinning
        seg.current_wall_mm = max(seg.t_min_mm + 0.3, seg.current_wall_mm - loss)
        seg.remaining_life_yr = calculate_remaining_life(seg.current_wall_mm, seg.t_min_mm, seg.effective_cr_mm_yr)
        seg.health_state = evaluate_health_state(seg.current_wall_mm, seg.t_min_mm, seg.remaining_life_yr)

        wall_loss_pct = round(((seg.nominal_wall_mm - seg.current_wall_mm) / seg.nominal_wall_mm) * 100.0, 1)

        st, reason = evaluate_alarm_state(
            current_state=seg.alarm_state,
            consecutive_wet_readings=4,
            consecutive_dry_readings=0,
            jacket_delta_T_C=14.0,
            wall_loss_pct_nominal=wall_loss_pct,
            remaining_life_yr=seg.remaining_life_yr,
            current_wall_mm=seg.current_wall_mm,
            t_min_mm=seg.t_min_mm
        )
        prev_st = seg.alarm_state
        seg.alarm_state = st

        # Record Alarm
        new_alarm = Alarm(
            segment_id=seg.id,
            state=st,
            trigger_reason=f"Steam Tracer Burst: {reason}",
            severity="CRITICAL" if st >= 3 else "HIGH",
            status="ACTIVE",
            created_at=now
        )
        db.add(new_alarm)

        # Auto-create draft work order if State 3 or 4
        wo_created = None
        if st >= 3:
            wo_id = f"WO-TRACER-{seg.id}-{int(now.timestamp())%10000}"
            wo = WorkOrder(
                id=wo_id,
                segment_id=seg.id,
                title=f"Emergency Steam Tracer Leak Repair: {seg.line_tag}",
                description=f"Auto-generated Plan Repair order. Remaining life breached {seg.remaining_life_yr} yr. High temperature CUI cell active.",
                status="DRAFT",
                priority="P1" if st == 4 else "P2",
                created_at=now,
                due_date=now + timedelta(days=14),
                assigned_to="Turnaround Emergency Mechanical",
                estimated_cost_usd=55000.0
            )
            db.add(wo)
            wo_created = wo_id

        db.commit()
        return {
            "status": "success",
            "scenario": "tracer_leak",
            "segment_id": seg.id,
            "line_tag": seg.line_tag,
            "previous_alarm_state": prev_st,
            "new_alarm_state": st,
            "health_state": seg.health_state,
            "remaining_life_yr": seg.remaining_life_yr,
            "auto_work_order_id": wo_created,
            "message": f"Injected steam tracer breach on {seg.line_tag}. Transitioned to State {st} ({reason})."
        }

    # 3. BLOCKED DRAIN
    elif scenario_type == "blocked_drain":
        seg = None
        if trigger.target_segment_id:
            seg = db.query(Segment).filter(Segment.id == trigger.target_segment_id).first()
        if not seg:
            seg = db.query(Segment).filter(Segment.insulation_type.in_(["Calcium Silicate", "Mineral Wool"])).first()

        # Water pools at 6 o'clock low points
        six_nodes = db.query(MoistureNode).filter(
            MoistureNode.segment_id == seg.id,
            MoistureNode.clock_position == 6
        ).all()
        for n in six_nodes:
            n.moisture_pct = 92.0
            n.consecutive_wet_count += 4
            n.last_seen = now

        seg.rolling_wet_fraction = 0.55
        st, reason = evaluate_alarm_state(
            current_state=seg.alarm_state,
            consecutive_wet_readings=4,
            consecutive_dry_readings=0,
            jacket_delta_T_C=4.5,
            wall_loss_pct_nominal=((seg.nominal_wall_mm - seg.current_wall_mm) / seg.nominal_wall_mm) * 100.0,
            remaining_life_yr=seg.remaining_life_yr,
            current_wall_mm=seg.current_wall_mm,
            t_min_mm=seg.t_min_mm
        )
        seg.alarm_state = max(seg.alarm_state, st)
        alarm = Alarm(
            segment_id=seg.id,
            state=seg.alarm_state,
            trigger_reason=f"Blocked Jacketing Drainage Low Point: {reason}",
            severity="MEDIUM",
            status="ACTIVE",
            created_at=now
        )
        db.add(alarm)
        db.commit()
        return {
            "status": "success",
            "scenario": "blocked_drain",
            "segment_id": seg.id,
            "line_tag": seg.line_tag,
            "message": f"Blocked drain low-point saturation simulated on {seg.line_tag}."
        }

    # 4. PEC SWEEP UPLOAD
    elif scenario_type == "pec_sweep_upload":
        seg = None
        if trigger.target_segment_id:
            seg = db.query(Segment).filter(Segment.id == trigger.target_segment_id).first()
        if not seg:
            seg = db.query(Segment).filter(Segment.alarm_state > 0).first() or db.query(Segment).first()

        measured_wall = round(max(seg.t_min_mm + 0.2, seg.current_wall_mm - 0.45), 2)
        pec_scan = PECReading(
            segment_id=seg.id,
            position_m=round(seg.chainage_m * 0.5, 1),
            measured_wall_mm=measured_wall,
            timestamp=now,
            method="PEC",
            inspector="Robotic Crawler PEC-04 (Automated Sweep)"
        )
        db.add(pec_scan)
        seg.current_wall_mm = measured_wall
        seg.remaining_life_yr = calculate_remaining_life(seg.current_wall_mm, seg.t_min_mm, seg.effective_cr_mm_yr)
        seg.health_state = evaluate_health_state(seg.current_wall_mm, seg.t_min_mm, seg.remaining_life_yr)

        wall_loss_pct = round(((seg.nominal_wall_mm - seg.current_wall_mm) / seg.nominal_wall_mm) * 100.0, 1)
        st, reason = evaluate_alarm_state(
            current_state=seg.alarm_state,
            consecutive_wet_readings=2,
            consecutive_dry_readings=0,
            jacket_delta_T_C=4.0,
            wall_loss_pct_nominal=wall_loss_pct,
            remaining_life_yr=seg.remaining_life_yr,
            current_wall_mm=seg.current_wall_mm,
            t_min_mm=seg.t_min_mm
        )
        seg.alarm_state = max(seg.alarm_state, st)

        db.commit()
        return {
            "status": "success",
            "scenario": "pec_sweep_upload",
            "segment_id": seg.id,
            "line_tag": seg.line_tag,
            "measured_wall_mm": measured_wall,
            "remaining_life_yr": seg.remaining_life_yr,
            "health_state": seg.health_state,
            "message": f"Robotic PEC sweep uploaded for {seg.line_tag}. Wall updated to {measured_wall} mm."
        }

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown scenario_type: {scenario_type}. Supported: rain_event, tracer_leak, blocked_drain, pec_sweep_upload"
        )
