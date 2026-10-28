from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime, ForeignKey, Text, Index
)
from sqlalchemy.orm import relationship
from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(120), unique=True, index=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="viewer", nullable=False)  # viewer, integrity_engineer, admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

class Segment(Base):
    __tablename__ = "segments"
    
    id = Column(Integer, primary_key=True, index=True)
    line_tag = Column(String(80), unique=True, index=True, nullable=False)
    area = Column(String(80), index=True, nullable=False)
    material = Column(String(50), nullable=False)
    nominal_wall_mm = Column(Float, nullable=False)
    t_min_mm = Column(Float, nullable=False)
    corrosion_allowance_mm = Column(Float, nullable=False)
    operating_temp_C = Column(Float, nullable=False)
    insulation_type = Column(String(50), nullable=False)
    service = Column(String(50), nullable=False)  # hot, cold, cyclic, steam-traced
    consequence_category = Column(String(5), nullable=False)  # A, B, C, D, E
    chainage_m = Column(Float, default=100.0)
    rack_level = Column(String(50), default="Tier-1")
    rack_bay = Column(Integer, default=1)
    lat = Column(Float, default=29.7604)
    lon = Column(Float, default=-95.3698)
    circuit_family = Column(String(50), index=True, default="ATM-CS-100")
    
    # Dynamic computed fields
    current_wall_mm = Column(Float, nullable=False)
    remaining_life_yr = Column(Float, default=15.0)
    health_state = Column(String(20), default="Healthy")  # Healthy, Watch, Priority, Critical, Imminent
    alarm_state = Column(Integer, default=0)  # 0 to 4
    rolling_wet_fraction = Column(Float, default=0.0)
    effective_cr_mm_yr = Column(Float, default=0.05)
    pof_category = Column(Integer, default=1)  # 1 to 5
    risk_ranking = Column(String(20), default="Low")  # Low, Medium, Medium-High, High
    next_inspection_date = Column(String(30), default="2029-01-01")
    
    # Relationships
    nodes = relationship("MoistureNode", back_populates="segment", cascade="all, delete-orphan")
    dts_readings = relationship("DTSReading", back_populates="segment", cascade="all, delete-orphan")
    pec_readings = relationship("PECReading", back_populates="segment", cascade="all, delete-orphan")
    alarms = relationship("Alarm", back_populates="segment", cascade="all, delete-orphan")
    work_orders = relationship("WorkOrder", back_populates="segment", cascade="all, delete-orphan")
    digs = relationship("VerificationDig", back_populates="segment", cascade="all, delete-orphan")

class MoistureNode(Base):
    __tablename__ = "moisture_nodes"
    
    id = Column(String(60), primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    clock_position = Column(Integer, nullable=False)  # 3, 6, 9
    chainage_position_m = Column(Float, default=10.0)
    moisture_pct = Column(Float, default=0.0)
    jacket_temp_C = Column(Float, default=25.0)
    battery_pct = Column(Float, default=95.0)
    last_seen = Column(DateTime, default=utc_now)
    raw_moisture_pct = Column(Float, default=0.0)
    consecutive_wet_count = Column(Integer, default=0)
    consecutive_dry_count = Column(Integer, default=10)
    
    segment = relationship("Segment", back_populates="nodes")
    alarms = relationship("Alarm", back_populates="node")

class DTSReading(Base):
    __tablename__ = "dts_readings"
    
    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    position_m = Column(Float, nullable=False)
    temp_C = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=utc_now, index=True)
    
    segment = relationship("Segment", back_populates="dts_readings")

class PECReading(Base):
    __tablename__ = "pec_readings"
    
    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    position_m = Column(Float, nullable=False)
    measured_wall_mm = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=utc_now, index=True)
    method = Column(String(20), default="PEC")  # PEC, UT
    inspector = Column(String(80), default="Robotic Crawler PEC-04")
    
    segment = relationship("Segment", back_populates="pec_readings")

class Alarm(Base):
    __tablename__ = "alarms"
    
    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id = Column(String(60), ForeignKey("moisture_nodes.id", ondelete="SET NULL"), nullable=True)
    state = Column(Integer, nullable=False)  # 1 (Advisory), 2 (Verify), 3 (Plan Repair), 4 (Escalate)
    trigger_reason = Column(String(255), nullable=False)
    severity = Column(String(20), default="MEDIUM")  # LOW, MEDIUM, HIGH, CRITICAL
    status = Column(String(20), default="ACTIVE", index=True)  # ACTIVE, ACKNOWLEDGED, CLEARED
    created_at = Column(DateTime, default=utc_now, index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(120), nullable=True)
    ack_notes = Column(Text, nullable=True)
    cleared_at = Column(DateTime, nullable=True)
    
    segment = relationship("Segment", back_populates="alarms")
    node = relationship("MoistureNode", back_populates="alarms")

class WorkOrder(Base):
    __tablename__ = "work_orders"
    
    id = Column(String(60), primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(30), default="DRAFT", index=True)  # DRAFT, APPROVED, IN_PROGRESS, COMPLETED, CANCELLED
    priority = Column(String(10), default="P2")  # P1 (Immediate), P2 (High), P3 (Medium), P4 (Low)
    created_at = Column(DateTime, default=utc_now)
    due_date = Column(DateTime, nullable=True)
    assigned_to = Column(String(120), nullable=True)
    estimated_cost_usd = Column(Float, default=45000.0)
    
    segment = relationship("Segment", back_populates="work_orders")

class VerificationDig(Base):
    __tablename__ = "verification_digs"
    
    id = Column(Integer, primary_key=True, index=True)
    segment_id = Column(Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    location_chainage_m = Column(Float, nullable=False)
    dig_date = Column(DateTime, default=utc_now)
    insulation_condition = Column(String(100), default="Wet Degraded")
    corrosion_severity = Column(String(100), default="General Wall Loss")
    ut_measured_wall_mm = Column(Float, nullable=False)
    pec_predicted_wall_mm = Column(Float, nullable=False)
    delta_mm = Column(Float, nullable=False)
    photo_url = Column(String(255), default="/assets/dig_inspection.jpg")
    inspector_notes = Column(Text, nullable=True)
    status = Column(String(30), default="INSPECTED")  # SCHEDULED, EXCAVATED, INSPECTED, CLOSED
    
    segment = relationship("Segment", back_populates="digs")

class ModelVersion(Base):
    __tablename__ = "model_versions"
    
    id = Column(Integer, primary_key=True, index=True)
    circuit_family = Column(String(50), index=True, nullable=False)
    version_tag = Column(String(30), nullable=False)
    cr0_mm_yr = Column(Float, nullable=False)
    chloride_factor = Column(Float, nullable=False)
    bias_mm = Column(Float, default=0.0)
    scatter_mm = Column(Float, default=0.0)
    r2_score = Column(Float, default=0.95)
    calibration_points_count = Column(Integer, default=0)
    updated_by = Column(String(120), default="System Auto-Calibration")
    created_at = Column(DateTime, default=utc_now)
    notes = Column(Text, nullable=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(120), nullable=False)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    previous_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utc_now)
    client_ip = Column(String(50), default="127.0.0.1")
