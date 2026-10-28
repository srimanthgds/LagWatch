from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import Segment, User, AuditLog
from app.schemas.schemas import SegmentResponse, SegmentDetailResponse
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/segments", tags=["Piping Segments"])

@router.get("", response_model=List[SegmentResponse])
def list_segments(
    area: Optional[str] = Query(None, description="Filter by process unit"),
    health_state: Optional[str] = Query(None, description="Healthy, Watch, Priority, Critical, Imminent"),
    alarm_state: Optional[int] = Query(None, description="0 to 4"),
    risk_ranking: Optional[str] = Query(None, description="Low, Medium, Medium-High, High"),
    search: Optional[str] = Query(None, description="Search line tag or material"),
    limit: int = Query(350, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    query = db.query(Segment)
    if area:
        query = query.filter(Segment.area == area)
    if health_state:
        query = query.filter(Segment.health_state == health_state)
    if alarm_state is not None:
        query = query.filter(Segment.alarm_state == alarm_state)
    if risk_ranking:
        query = query.filter(Segment.risk_ranking == risk_ranking)
    if search:
        query = query.filter(Segment.line_tag.ilike(f"%{search}%") | Segment.material.ilike(f"%{search}%"))
    
    return query.order_by(Segment.id).offset(offset).limit(limit).all()

@router.get("/{segment_id}", response_model=SegmentDetailResponse)
def get_segment_detail(segment_id: int, db: Session = Depends(get_db)):
    segment = db.query(Segment).filter(Segment.id == segment_id).first()
    if not segment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
    
    # Attach line_tag and area to nested alarms, work orders, and digs
    for a in segment.alarms:
        a.line_tag = segment.line_tag
        a.area = segment.area
    for w in segment.work_orders:
        w.line_tag = segment.line_tag
        w.area = segment.area
    for d in segment.digs:
        d.line_tag = segment.line_tag

    return segment
