from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import AuditLog, User
from app.schemas.schemas import AuditLogResponse
from app.core.config import settings
from app.api.deps import require_roles

router = APIRouter(prefix="/admin", tags=["Admin & Audit Trail"])

@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()

@router.get("/thresholds")
def get_system_thresholds():
    return {
        "moisture_threshold_pct": settings.MOISTURE_THRESHOLD_PCT,
        "delta_t_threshold_C": settings.DELTA_T_THRESHOLD_C,
        "wall_loss_verify_threshold_pct": settings.WALL_LOSS_VERIFY_THRESHOLD_PCT,
        "remaining_life_plan_repair_yr": settings.REMAINING_LIFE_PLAN_REPAIR_YR,
        "imminent_margin_mm": settings.IMMINENT_MARGIN_MM,
        "default_cr0_mm_yr": settings.DEFAULT_CR0_MM_YR,
        "baseline_annual_loss_usd": settings.BASELINE_ANNUAL_LOSS_USD,
        "default_capex_usd": settings.DEFAULT_CAPEX_USD,
        "default_opex_usd_yr": settings.DEFAULT_OPEX_USD_YR,
    }

@router.post("/thresholds")
def update_system_thresholds(
    new_thresholds: Dict[str, Any],
    current_user: User = Depends(require_roles(["admin"])),
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    updated_items = []
    for k, v in new_thresholds.items():
        if hasattr(settings, k.upper()):
            old_val = getattr(settings, k.upper())
            setattr(settings, k.upper(), v)
            updated_items.append(f"{k}: {old_val} -> {v}")
            
    audit = AuditLog(
        user_email=current_user.email,
        action="UPDATE_THRESHOLDS",
        entity_type="SYSTEM_CONFIG",
        entity_id="GLOBAL_THRESHOLDS",
        previous_value="Default Configuration",
        new_value="; ".join(updated_items),
        timestamp=now
    )
    db.add(audit)
    db.commit()
    
    return {
        "status": "success",
        "message": f"Updated thresholds: {', '.join(updated_items)}",
        "current": get_system_thresholds()
    }
