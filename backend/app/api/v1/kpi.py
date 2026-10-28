from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.entities import Segment, MoistureNode, Alarm
from app.schemas.schemas import KPISummary
from app.core.config import settings

router = APIRouter(prefix="/kpis", tags=["KPI Dashboard"])

@router.get("", response_model=KPISummary)
def get_kpi_summary(db: Session = Depends(get_db)):
    total_segments = db.query(Segment).count()
    total_nodes = db.query(MoistureNode).count()
    
    # Wet segments: rolling_wet_fraction > 0.10 or alarm_state >= 1
    wet_count = db.query(Segment).filter(Segment.rolling_wet_fraction > 0.10).count()
    wet_pct = round((wet_count / max(1, total_segments)) * 100.0, 1)
    
    # Health breakdown
    health_rows = db.query(Segment.health_state, func.count(Segment.id)).group_by(Segment.health_state).all()
    health_map = {"Healthy": 0, "Watch": 0, "Priority": 0, "Critical": 0, "Imminent": 0}
    for h, cnt in health_rows:
        if h in health_map:
            health_map[h] = cnt
            
    # Alarm breakdown
    alarm_rows = db.query(Segment.alarm_state, func.count(Segment.id)).group_by(Segment.alarm_state).all()
    alarm_map = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for st, cnt in alarm_rows:
        if st in alarm_map:
            alarm_map[st] = cnt
            
    active_alarms = db.query(Alarm).filter(Alarm.status == "ACTIVE").count()
    high_risk_count = db.query(Segment).filter(Segment.risk_ranking == "High").count()
    
    # Projected avoided loss = baseline annual loss * benefit capture (e.g., $26.8M * 0.65 = $17.42M)
    avoided_cost = round(settings.BASELINE_ANNUAL_LOSS_USD * settings.DEFAULT_BENEFIT_CAPTURE_PCT, 2)
    
    return KPISummary(
        total_segments=total_segments,
        total_nodes=total_nodes,
        wet_segments_count=wet_count,
        wet_segments_pct=wet_pct,
        health_breakdown=health_map,
        alarm_breakdown=alarm_map,
        active_alarms_count=active_alarms,
        high_risk_segments_count=high_risk_count,
        projected_avoided_cost_usd=avoided_cost
    )
