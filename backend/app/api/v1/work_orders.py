from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import WorkOrder, Segment, User, AuditLog
from app.schemas.schemas import WorkOrderResponse, WorkOrderCreate
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/work-orders", tags=["Work Orders"])

@router.get("", response_model=List[WorkOrderResponse])
def list_work_orders(
    status_filter: Optional[str] = Query(None, description="DRAFT, APPROVED, IN_PROGRESS, COMPLETED"),
    priority: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(WorkOrder).join(Segment, WorkOrder.segment_id == Segment.id)
    if status_filter:
        query = query.filter(WorkOrder.status == status_filter)
    if priority:
        query = query.filter(WorkOrder.priority == priority)
        
    orders = query.order_by(WorkOrder.created_at.desc()).limit(limit).all()
    for o in orders:
        if o.segment:
            o.line_tag = o.segment.line_tag
            o.area = o.segment.area
    return orders

@router.post("", response_model=WorkOrderResponse)
def create_work_order(
    wo_data: WorkOrderCreate,
    current_user: User = Depends(require_roles(["admin", "integrity_engineer"])),
    db: Session = Depends(get_db)
):
    seg = db.query(Segment).filter(Segment.id == wo_data.segment_id).first()
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target segment not found")
        
    count = db.query(WorkOrder).count()
    wo_id = f"WO-2026-{1000 + count + 1}"
    
    wo = WorkOrder(
        id=wo_id,
        segment_id=seg.id,
        title=wo_data.title,
        description=wo_data.description,
        status="DRAFT",
        priority=wo_data.priority,
        created_at=datetime.now(timezone.utc),
        assigned_to=wo_data.assigned_to,
        estimated_cost_usd=wo_data.estimated_cost_usd
    )
    db.add(wo)
    
    audit = AuditLog(
        user_email=current_user.email,
        action="WORK_ORDER_CREATE",
        entity_type="WORK_ORDER",
        entity_id=wo_id,
        previous_value=None,
        new_value=f"Created {wo.title} for {seg.line_tag}",
        timestamp=datetime.now(timezone.utc)
    )
    db.add(audit)
    db.commit()
    db.refresh(wo)
    
    wo.line_tag = seg.line_tag
    wo.area = seg.area
    return wo

@router.patch("/{wo_id}/status", response_model=WorkOrderResponse)
def update_work_order_status(
    wo_id: str,
    new_status: str = Query(..., description="DRAFT, APPROVED, IN_PROGRESS, COMPLETED, CANCELLED"),
    current_user: User = Depends(require_roles(["admin", "integrity_engineer"])),
    db: Session = Depends(get_db)
):
    wo = db.query(WorkOrder).filter(WorkOrder.id == wo_id).first()
    if not wo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work Order not found")
        
    prev = wo.status
    wo.status = new_status
    audit = AuditLog(
        user_email=current_user.email,
        action="WORK_ORDER_STATUS_UPDATE",
        entity_type="WORK_ORDER",
        entity_id=wo_id,
        previous_value=prev,
        new_value=new_status,
        timestamp=datetime.now(timezone.utc)
    )
    db.add(audit)
    db.commit()
    db.refresh(wo)
    if wo.segment:
        wo.line_tag = wo.segment.line_tag
        wo.area = wo.segment.area
    return wo
