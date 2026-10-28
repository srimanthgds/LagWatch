from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import ModelVersion, VerificationDig, Segment, User, AuditLog
from app.schemas.schemas import ModelVersionResponse
from app.domain.calibration import compute_ut_pec_statistics, update_model_parameters_from_calibration
from app.api.deps import require_roles

router = APIRouter(prefix="/calibration", tags=["Model Calibration"])

@router.get("/versions", response_model=List[ModelVersionResponse])
def list_model_versions(
    circuit_family: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(ModelVersion)
    if circuit_family:
        query = query.filter(ModelVersion.circuit_family == circuit_family)
    return query.order_by(ModelVersion.created_at.desc()).limit(limit).all()

@router.get("/scatter")
def get_scatter_data(
    circuit_family: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    query = db.query(VerificationDig).join(Segment)
    if circuit_family:
        query = query.filter(Segment.circuit_family == circuit_family)
        
    digs = query.all()
    results = []
    for d in digs:
        results.append({
            "id": d.id,
            "segment_id": d.segment_id,
            "line_tag": d.segment.line_tag if d.segment else f"Segment #{d.segment_id}",
            "area": d.segment.area if d.segment else "General",
            "circuit_family": d.segment.circuit_family if d.segment else "Default",
            "pec_predicted_wall_mm": round(d.pec_predicted_wall_mm, 2),
            "ut_measured_wall_mm": round(d.ut_measured_wall_mm, 2),
            "delta_mm": round(d.delta_mm, 3),
            "dig_date": d.dig_date.strftime("%Y-%m-%d"),
            "corrosion_severity": d.corrosion_severity
        })
    return results

@router.get("/stats")
def get_calibration_stats(
    circuit_family: Optional[str] = Query(None),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    query = db.query(VerificationDig).join(Segment)
    if circuit_family:
        query = query.filter(Segment.circuit_family == circuit_family)
    digs = query.all()
    
    pairs = [(d.pec_predicted_wall_mm, d.ut_measured_wall_mm) for d in digs]
    stats = compute_ut_pec_statistics(pairs)
    
    latest_models = {}
    families = [f[0] for f in db.query(Segment.circuit_family).distinct().all()]
    for f in families:
        mv = db.query(ModelVersion).filter(ModelVersion.circuit_family == f).order_by(ModelVersion.created_at.desc()).first()
        if mv:
            latest_models[f] = {
                "version_tag": mv.version_tag,
                "cr0_mm_yr": mv.cr0_mm_yr,
                "chloride_factor": mv.chloride_factor,
                "bias_mm": mv.bias_mm,
                "scatter_mm": mv.scatter_mm,
                "r2_score": mv.r2_score
            }
            
    return {
        "stats": stats,
        "latest_family_models": latest_models
    }

@router.post("/recalculate/{circuit_family}", response_model=ModelVersionResponse)
def recalculate_model_version(
    circuit_family: str,
    current_user: User = Depends(require_roles(["admin", "integrity_engineer"])),
    db: Session = Depends(get_db)
):
    digs = db.query(VerificationDig).join(Segment).filter(Segment.circuit_family == circuit_family).all()
    if not digs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No verification dig pairs found for {circuit_family}")
        
    pairs = [(d.pec_predicted_wall_mm, d.ut_measured_wall_mm) for d in digs]
    stats = compute_ut_pec_statistics(pairs)
    
    latest = db.query(ModelVersion).filter(ModelVersion.circuit_family == circuit_family).order_by(ModelVersion.created_at.desc()).first()
    curr_cr0 = latest.cr0_mm_yr if latest else 0.35
    curr_c_cl = latest.chloride_factor if latest else 1.0
    
    new_cr0, new_c_cl = update_model_parameters_from_calibration(
        current_cr0=curr_cr0,
        current_c_cl=curr_c_cl,
        bias_mm=stats["bias_mm"]
    )
    
    count = db.query(ModelVersion).filter(ModelVersion.circuit_family == circuit_family).count()
    ver_tag = f"v{count // 10 + 1}.{(count % 10) + 1}.0-Recalibrated"
    now = datetime.now(timezone.utc)
    
    mv = ModelVersion(
        circuit_family=circuit_family,
        version_tag=ver_tag,
        cr0_mm_yr=new_cr0,
        chloride_factor=new_c_cl,
        bias_mm=stats["bias_mm"],
        scatter_mm=stats["scatter_mm"],
        r2_score=stats["r2_score"],
        calibration_points_count=len(pairs),
        updated_by=current_user.email,
        created_at=now,
        notes=f"Manual batch recalibration on {len(pairs)} UT-vs-PEC inspection pairs."
    )
    db.add(mv)
    
    audit = AuditLog(
        user_email=current_user.email,
        action="MODEL_RECALIBRATE",
        entity_type="MODEL_VERSION",
        entity_id=ver_tag,
        previous_value=f"CR0={curr_cr0}, C_Cl={curr_c_cl}",
        new_value=f"CR0={new_cr0}, C_Cl={new_c_cl}, Bias={stats['bias_mm']}",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    db.refresh(mv)
    return mv
