from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# User & Auth
class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    full_name: str
    email: str

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool

# Moisture Node
class MoistureNodeResponse(BaseModel):
    id: str
    segment_id: int
    clock_position: int
    chainage_position_m: float
    moisture_pct: float
    jacket_temp_C: float
    battery_pct: float
    last_seen: datetime
    consecutive_wet_count: int
    consecutive_dry_count: int

    class Config:
        from_attributes = True

# Readings
class DTSReadingResponse(BaseModel):
    id: int
    segment_id: int
    position_m: float
    temp_C: float
    timestamp: datetime

    class Config:
        from_attributes = True

class PECReadingResponse(BaseModel):
    id: int
    segment_id: int
    position_m: float
    measured_wall_mm: float
    timestamp: datetime
    method: str
    inspector: str

    class Config:
        from_attributes = True

# Alarms
class AlarmResponse(BaseModel):
    id: int
    segment_id: int
    node_id: Optional[str]
    state: int
    trigger_reason: str
    severity: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    ack_notes: Optional[str] = None
    cleared_at: Optional[datetime] = None
    line_tag: Optional[str] = None
    area: Optional[str] = None

    class Config:
        from_attributes = True

class AlarmAckRequest(BaseModel):
    ack_notes: str = Field(..., min_length=3, description="Operator justification or action plan")
    confirmed_by_operator: bool = Field(..., description="Two-step confirmation checkbox")

# Work Orders
class WorkOrderResponse(BaseModel):
    id: str
    segment_id: int
    line_tag: Optional[str] = None
    area: Optional[str] = None
    title: str
    description: Optional[str]
    status: str
    priority: str
    created_at: datetime
    due_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    estimated_cost_usd: float

    class Config:
        from_attributes = True

class WorkOrderCreate(BaseModel):
    segment_id: int
    title: str
    description: Optional[str] = None
    priority: str = "P2"
    assigned_to: Optional[str] = None
    estimated_cost_usd: float = 45000.0

# Verification Digs
class VerificationDigResponse(BaseModel):
    id: int
    segment_id: int
    line_tag: Optional[str] = None
    location_chainage_m: float
    dig_date: datetime
    insulation_condition: str
    corrosion_severity: str
    ut_measured_wall_mm: float
    pec_predicted_wall_mm: float
    delta_mm: float
    photo_url: str
    inspector_notes: Optional[str]
    status: str

    class Config:
        from_attributes = True

class VerificationDigCreate(BaseModel):
    segment_id: int
    location_chainage_m: float
    insulation_condition: str = "Wet Degraded"
    corrosion_severity: str = "General Wall Loss"
    ut_measured_wall_mm: float
    pec_predicted_wall_mm: float
    photo_url: str = "/assets/digs/dig_1.jpg"
    inspector_notes: Optional[str] = None

# Model Versions
class ModelVersionResponse(BaseModel):
    id: int
    circuit_family: str
    version_tag: str
    cr0_mm_yr: float
    chloride_factor: float
    bias_mm: float
    scatter_mm: float
    r2_score: float
    calibration_points_count: int
    updated_by: str
    created_at: datetime
    notes: Optional[str]

    class Config:
        from_attributes = True

# Segments
class SegmentResponse(BaseModel):
    id: int
    line_tag: str
    area: str
    material: str
    nominal_wall_mm: float
    t_min_mm: float
    corrosion_allowance_mm: float
    operating_temp_C: float
    insulation_type: str
    service: str
    consequence_category: str
    chainage_m: float
    rack_level: str
    rack_bay: int
    lat: float
    lon: float
    circuit_family: str
    current_wall_mm: float
    remaining_life_yr: float
    health_state: str
    alarm_state: int
    rolling_wet_fraction: float
    effective_cr_mm_yr: float
    pof_category: int
    risk_ranking: str
    next_inspection_date: str

    class Config:
        from_attributes = True

class SegmentDetailResponse(SegmentResponse):
    nodes: List[MoistureNodeResponse] = []
    dts_readings: List[DTSReadingResponse] = []
    pec_readings: List[PECReadingResponse] = []
    alarms: List[AlarmResponse] = []
    work_orders: List[WorkOrderResponse] = []
    digs: List[VerificationDigResponse] = []

# Financials
class FinancialParams(BaseModel):
    baseline_annual_loss_usd: float = 26_800_000.0
    capex_usd: float = 12_513_000.0
    opex_usd_yr: float = 1_850_000.0
    discount_rate: float = 0.08
    loss_reduction_pct: float = 0.65  # Base case 65%

class SensitivityScenario(BaseModel):
    scenario_name: str
    loss_reduction_pct: float
    payback_years: float
    npv_5yr_usd: float
    irr_pct: float
    five_year_net_benefit_usd: float

class FinancialResponse(BaseModel):
    inputs: FinancialParams
    base_case_payback_years: float
    base_case_5yr_npv_usd: float
    base_case_roi_pct: float
    scenarios: List[SensitivityScenario]

# KPI Summary
class KPISummary(BaseModel):
    total_segments: int
    total_nodes: int
    wet_segments_count: int
    wet_segments_pct: float
    health_breakdown: Dict[str, int]
    alarm_breakdown: Dict[int, int]
    active_alarms_count: int
    high_risk_segments_count: int
    projected_avoided_cost_usd: float

# Scenarios
class ScenarioTrigger(BaseModel):
    scenario_type: str  # "rain_event", "tracer_leak", "blocked_drain", "pec_sweep_upload"
    target_segment_id: Optional[int] = None
    target_area: Optional[str] = None
    severity: Optional[float] = 1.0

# Audit Log
class AuditLogResponse(BaseModel):
    id: int
    user_email: str
    action: str
    entity_type: str
    entity_id: str
    previous_value: Optional[str]
    new_value: Optional[str]
    timestamp: datetime
    client_ip: Optional[str]

    class Config:
        from_attributes = True
