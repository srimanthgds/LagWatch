from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.entities import Segment
from app.schemas.schemas import SegmentResponse

router = APIRouter(prefix="/risk", tags=["Risk Engine & Inspection Planner"])

@router.get("/matrix")
def get_risk_matrix(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Returns counts of segments distributed across the 5x5 API RP 581 Matrix."""
    matrix: Dict[str, Dict[int, int]] = {
        'A': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        'B': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        'C': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        'D': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        'E': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
    }
    
    rows = db.query(
        Segment.consequence_category,
        Segment.pof_category,
        func.count(Segment.id)
    ).group_by(Segment.consequence_category, Segment.pof_category).all()
    
    for cof, pof, cnt in rows:
        cof_upper = cof.upper()
        if cof_upper in matrix and pof in matrix[cof_upper]:
            matrix[cof_upper][pof] = cnt
            
    summary = {
        "High": db.query(Segment).filter(Segment.risk_ranking == "High").count(),
        "Medium-High": db.query(Segment).filter(Segment.risk_ranking == "Medium-High").count(),
        "Medium": db.query(Segment).filter(Segment.risk_ranking == "Medium").count(),
        "Low": db.query(Segment).filter(Segment.risk_ranking == "Low").count(),
    }
    
    return {
        "matrix": matrix,
        "summary": summary
    }

@router.get("/inspection-planner", response_model=List[SegmentResponse])
def get_inspection_planner_ranked(
    area: Optional[str] = Query(None),
    risk_ranking: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=300),
    db: Session = Depends(get_db)
):
    """Returns segments prioritized by Risk and Next Inspection Date."""
    query = db.query(Segment)
    if area:
        query = query.filter(Segment.area == area)
    if risk_ranking:
        query = query.filter(Segment.risk_ranking == risk_ranking)
        
    # Priority sorting: High risk first, then lowest remaining life
    return query.order_by(
        Segment.pof_category.desc(),
        Segment.remaining_life_yr.asc()
    ).limit(limit).all()
