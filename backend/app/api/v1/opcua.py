from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.entities import Segment

router = APIRouter(prefix="/opcua", tags=["OPC UA Industrial Export Mirror"])

@router.get("/browse")
def browse_opcua_tags(
    area: str = Query(None, description="Filter by refinery area"),
    limit: int = Query(50, ge=1, le=300),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Provides an OPC UA Address Space JSON browse tree.

    Format matches industrial automation servers:
    ns=2;s=Refinery.Area.<area>.Line.<tag>.<Metric>
    """
    query = db.query(Segment)
    if area:
        query = query.filter(Segment.area == area)
    segments = query.limit(limit).all()

    nodes: List[Dict[str, Any]] = []
    for s in segments:
        clean_tag = s.line_tag.replace(" ", "_")
        prefix = f"ns=2;s=Plant.CUI.{s.area.replace(' ', '_')}.Line.{clean_tag}"
        nodes.append({
            "nodeId": f"{prefix}.RemainingLife",
            "browseName": f"Line.{clean_tag}.RemainingLife",
            "displayName": f"{s.line_tag} Remaining Life",
            "dataType": "Float",
            "value": s.remaining_life_yr,
            "engineeringUnits": "years",
            "status": "Good"
        })
        nodes.append({
            "nodeId": f"{prefix}.CurrentWall",
            "browseName": f"Line.{clean_tag}.CurrentWall",
            "displayName": f"{s.line_tag} Current Wall Thickness",
            "dataType": "Float",
            "value": s.current_wall_mm,
            "engineeringUnits": "mm",
            "status": "Good"
        })
        nodes.append({
            "nodeId": f"{prefix}.MoisturePct",
            "browseName": f"Line.{clean_tag}.MoisturePct",
            "displayName": f"{s.line_tag} Rolling Wet Fraction",
            "dataType": "Float",
            "value": round(s.rolling_wet_fraction * 100.0, 1),
            "engineeringUnits": "%",
            "status": "Good"
        })
        nodes.append({
            "nodeId": f"{prefix}.AlarmState",
            "browseName": f"Line.{clean_tag}.AlarmState",
            "displayName": f"{s.line_tag} Alarm State (0-4)",
            "dataType": "Int32",
            "value": s.alarm_state,
            "engineeringUnits": "state",
            "status": "Good" if s.alarm_state == 0 else "ActiveAlarm"
        })
        nodes.append({
            "nodeId": f"{prefix}.HealthState",
            "browseName": f"Line.{clean_tag}.HealthState",
            "displayName": f"{s.line_tag} Health Classification",
            "dataType": "String",
            "value": s.health_state,
            "engineeringUnits": "tier",
            "status": "Good"
        })

    return {
        "serverUri": "urn:insulguard:opcua:refinery-stream",
        "timestamp": "2026-10-28T10:35:42Z",
        "totalNodeCount": len(nodes),
        "nodes": nodes
    }

@router.get("/read/{tag_path:path}")
def read_opcua_variable(tag_path: str, db: Session = Depends(get_db)):
    """Directly reads single OPC UA point, e.g. Line.12in-P-1043-A1A.RemainingLife"""
    parts = tag_path.split(".")
    if len(parts) < 3 or parts[0] != "Line":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tag format. Expected format: Line.<tag>.<Metric> (e.g. Line.12in-P-1043-A1A.RemainingLife)"
        )
    tag = parts[1]
    metric = parts[2]
    
    seg = db.query(Segment).filter(Segment.line_tag == tag).first()
    if not seg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Line tag {tag} not found")
        
    value = None
    units = ""
    if metric == "RemainingLife":
        value = seg.remaining_life_yr
        units = "years"
    elif metric == "CurrentWall":
        value = seg.current_wall_mm
        units = "mm"
    elif metric == "MoisturePct":
        value = round(seg.rolling_wet_fraction * 100.0, 1)
        units = "%"
    elif metric == "AlarmState":
        value = seg.alarm_state
        units = "state"
    elif metric == "HealthState":
        value = seg.health_state
        units = "tier"
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown metric {metric}")
        
    return {
        "tag": tag_path,
        "value": value,
        "engineeringUnits": units,
        "quality": "Good",
        "sourceTimestamp": "2026-10-28T10:35:42Z"
    }
