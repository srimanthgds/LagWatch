from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import Alarm, Segment, User, AuditLog
from app.schemas.schemas import AlarmResponse, AlarmAckRequest
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/alarms", tags=["Alarm Console"])

@router.get("", response_model=List[AlarmResponse])
def list_alarms(
    status_filter: Optional[str] = Query(None, description="ACTIVE, ACKNOWLEDGED, CLEARED"),
    state_filter: Optional[int] = Query(None, description="1 to 4"),
    area: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(Alarm).join(Segment, Alarm.segment_id == Segment.id)
    if status_filter:
        query = query.filter(Alarm.status == status_filter)
    if state_filter is not None:
        query = query.filter(Alarm.state == state_filter)
    if area:
        query = query.filter(Segment.area == area)
        
    alarms = query.order_by(Alarm.state.desc(), Alarm.created_at.desc()).limit(limit).all()
    for a in alarms:
        if a.segment:
            a.line_tag = a.segment.line_tag
            a.area = a.segment.area
    return alarms

@router.post("/{alarm_id}/acknowledge", response_model=AlarmResponse)
def acknowledge_alarm(
    alarm_id: int,
    ack_data: AlarmAckRequest,
    current_user: User = Depends(require_roles(["admin", "integrity_engineer", "viewer"])),
    db: Session = Depends(get_db)
):
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found")
        
    if not ack_data.confirmed_by_operator:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-step operator confirmation is required")
        
    now = datetime.now(timezone.utc)
    prev_status = alarm.status
    alarm.status = "ACKNOWLEDGED"
    alarm.acknowledged_at = now
    alarm.acknowledged_by = current_user.email
    alarm.ack_notes = ack_data.ack_notes
    
    # Audit log
    audit = AuditLog(
        user_email=current_user.email,
        action="ALARM_ACKNOWLEDGE",
        entity_type="ALARM",
        entity_id=str(alarm.id),
        previous_value=prev_status,
        new_value=f"ACKNOWLEDGED: {ack_data.ack_notes}",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    db.refresh(alarm)
    
    if alarm.segment:
        alarm.line_tag = alarm.segment.line_tag
        alarm.area = alarm.segment.area
    return alarm

@router.post("/{alarm_id}/clear", response_model=AlarmResponse)
def clear_alarm(
    alarm_id: int,
    current_user: User = Depends(require_roles(["admin", "integrity_engineer"])),
    db: Session = Depends(get_db)
):
    alarm = db.query(Alarm).filter(Alarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alarm not found")
        
    now = datetime.now(timezone.utc)
    prev_status = alarm.status
    alarm.status = "CLEARED"
    alarm.cleared_at = now
    
    # Also adjust segment alarm_state if no active alarms remain
    seg = alarm.segment
    if seg:
        active_remaining = db.query(Alarm).filter(
            Alarm.segment_id == seg.id,
            Alarm.id != alarm.id,
            Alarm.status == "ACTIVE"
        ).order_by(Alarm.state.desc()).first()
        seg.alarm_state = active_remaining.state if active_remaining else 0
        
    audit = AuditLog(
        user_email=current_user.email,
        action="ALARM_CLEAR",
        entity_type="ALARM",
        entity_id=str(alarm.id),
        previous_value=prev_status,
        new_value="CLEARED",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    db.refresh(alarm)
    
    if alarm.segment:
        alarm.line_tag = alarm.segment.line_tag
        alarm.area = alarm.segment.area
    return alarm
