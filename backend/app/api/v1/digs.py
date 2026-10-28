from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import VerificationDig, Segment, ModelVersion, AuditLog, User
from app.schemas.schemas import VerificationDigResponse, VerificationDigCreate
from app.domain.calibration import compute_ut_pec_statistics, update_model_parameters_from_calibration
from app.api.deps import require_roles

router = APIRouter(prefix="/digs", tags=["Verification Digs & UT Calibration"])

@router.get("", response_model=List[VerificationDigResponse])
def list_digs(
    segment_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    query = db.query(VerificationDig).join(Segment, VerificationDig.segment_id == Segment.id)
    if segment_id:
        query = query.filter(VerificationDig.segment_id == segment_id)
    if status_filter:
        query = query.filter(VerificationDig.status == status_filter)
        
    digs = query.order_by(VerificationDig.dig_date.desc()).limit(limit).all()
    for d in digs:
        if d.segment:
            d.line_tag = d.segment.line_tag
    return digs

@router.post("", response_model=VerificationDigResponse)
def create_verification_dig(
    dig_in: VerificationDigCreate,
    current_user: User = Depends(require_roles(["admin", "integrity_engineer"])),
    db: Session = Depends(get_db)
):
    segment = db.query(Segment).filter(Segment.id == dig_in.segment_id).first()
    if not segment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target segment not found")
        
    delta = round(dig_in.pec_predicted_wall_mm - dig_in.ut_measured_wall_mm, 3)
    now = datetime.now(timezone.utc)
    
    dig = VerificationDig(
        segment_id=segment.id,
        location_chainage_m=dig_in.location_chainage_m,
        dig_date=now,
        insulation_condition=dig_in.insulation_condition,
        corrosion_severity=dig_in.corrosion_severity,
        ut_measured_wall_mm=dig_in.ut_measured_wall_mm,
        pec_predicted_wall_mm=dig_in.pec_predicted_wall_mm,
        delta_mm=delta,
        photo_url=dig_in.photo_url or "/assets/digs/dig_1.jpg",
        inspector_notes=dig_in.inspector_notes,
        status="INSPECTED"
    )
    db.add(dig)
    db.flush()

    # Trigger Calibration update for this circuit family
    all_circuit_digs = db.query(VerificationDig).join(Segment).filter(
        Segment.circuit_family == segment.circuit_family
    ).all()
    pairs = [(d.pec_predicted_wall_mm, d.ut_measured_wall_mm) for d in all_circuit_digs]
    pairs.append((dig.pec_predicted_wall_mm, dig.ut_measured_wall_mm))

    stats = compute_ut_pec_statistics(pairs)

    latest_version = db.query(ModelVersion).filter(
        ModelVersion.circuit_family == segment.circuit_family
    ).order_by(ModelVersion.created_at.desc()).first()

    base_cr0 = latest_version.cr0_mm_yr if latest_version else 0.35
    base_c_cl = latest_version.chloride_factor if latest_version else 1.0

    new_cr0, new_c_cl = update_model_parameters_from_calibration(
        current_cr0=base_cr0,
        current_c_cl=base_c_cl,
        bias_mm=stats["bias_mm"],
        average_service_years=3.0
    )

    ver_count = db.query(ModelVersion).filter(ModelVersion.circuit_family == segment.circuit_family).count()
    new_version_tag = f"v{ver_count // 10 + 1}.{(ver_count % 10) + 1}.0-Calibrated"

    mv = ModelVersion(
        circuit_family=segment.circuit_family,
        version_tag=new_version_tag,
        cr0_mm_yr=new_cr0,
        chloride_factor=new_c_cl,
        bias_mm=stats["bias_mm"],
        scatter_mm=stats["scatter_mm"],
        r2_score=stats["r2_score"],
        calibration_points_count=len(pairs),
        updated_by=current_user.email,
        created_at=now,
        notes=f"Auto-calibrated following verification dig #{dig.id} on line {segment.line_tag}. Bias: {stats['bias_mm']}mm, Scatter: {stats['scatter_mm']}mm."
    )
    db.add(mv)

    # Log audit
    audit = AuditLog(
        user_email=current_user.email,
        action="VERIFICATION_DIG_CALIBRATION",
        entity_type="VERIFICATION_DIG",
        entity_id=str(dig.id),
        previous_value=f"Model {latest_version.version_tag if latest_version else 'None'} (CR0={base_cr0})",
        new_value=f"Model {new_version_tag} (CR0={new_cr0}, C_Cl={new_c_cl}, Bias={stats['bias_mm']}mm)",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    db.refresh(dig)
    
    dig.line_tag = segment.line_tag
    return dig
