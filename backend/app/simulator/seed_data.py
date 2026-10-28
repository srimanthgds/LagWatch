"""Seed Data Generator for InsulGuard 4.0.

Synthesizes:
- 300 realistic refinery piping segments across 6 operating units
- 2,400 wireless moisture & temperature nodes (3/6/9 o'clock)
- 3 years of synthetic inspection and telemetry history
- ~12% active wet segments (~36 lines)
- ~40 high-degradation CUI lines (0.4 - 1.3 mm/yr wall loss in 50-175C sweet spot)
- Initial Alarms, Work Orders, Verification Digs with UT calibration pairs, Model Versions, Users, and Audit Logs.
"""

import random
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine, Base
from app.core.security import get_password_hash
from app.models.entities import (
    User, Segment, MoistureNode, DTSReading, PECReading,
    Alarm, WorkOrder, VerificationDig, ModelVersion, AuditLog
)
from app.domain.corrosion import calculate_model_cr, blend_corrosion_rates
from app.domain.remaining_life import calculate_remaining_life, evaluate_health_state
from app.domain.alarm_fsm import evaluate_alarm_state
from app.domain.risk_engine import determine_pof_category, evaluate_risk
from app.domain.calibration import compute_ut_pec_statistics

AREAS = [
    "Crude/Vacuum Overhead",
    "Fluid Catalytic Cracking (FCC)",
    "Naphtha Hydrotreater",
    "Catalytic Reformer",
    "Utilities Steam/Condensate",
    "Sulfur Recovery Unit (SRU)"
]

MATERIALS = ["Carbon Steel A106-B", "Carbon Steel A53", "Low Alloy 1.25Cr-0.5Mo", "Austenitic 304L SS"]
INSULATIONS = ["Calcium Silicate", "Mineral Wool", "Cellular Glass", "Aerogel Blanket"]
SERVICES = ["hot", "cold", "cyclic", "steam-traced"]
CONSEQUENCES = ["A", "B", "C", "D", "E"]

CIRCUIT_FAMILIES = {
    "Crude/Vacuum Overhead": "ATM-CS-100",
    "Fluid Catalytic Cracking (FCC)": "FCC-CS-200",
    "Naphtha Hydrotreater": "HT-ALLOY-300",
    "Catalytic Reformer": "REF-CS-400",
    "Utilities Steam/Condensate": "STM-CS-500",
    "Sulfur Recovery Unit (SRU)": "SRU-CS-600"
}

def seed_database(db: Session, force: bool = False):
    """Populates database with realistic 300-segment refinery asset hierarchy."""
    Base.metadata.create_all(bind=engine)
    
    if not force:
        try:
            existing_count = db.query(Segment).count()
            if existing_count >= 250:
                print(f"[Seed] Database already populated with {existing_count} segments. Skipping.")
                return
        except Exception:
            pass

    print("[Seed] Resetting database tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # 1. Seed Users
    print("[Seed] Seeding Default Users...")
    users = [
        User(
            email="admin@insulguard.com",
            full_name="Plant Integrity Director (Admin)",
            hashed_password=get_password_hash("adminpassword123"),
            role="admin",
            is_active=True
        ),
        User(
            email="engineer@insulguard.com",
            full_name="Chief CUI Corrosion Engineer",
            hashed_password=get_password_hash("engineerpassword123"),
            role="integrity_engineer",
            is_active=True
        ),
        User(
            email="viewer@insulguard.com",
            full_name="Operations Board Operator",
            hashed_password=get_password_hash("viewerpassword123"),
            role="viewer",
            is_active=True
        )
    ]
    db.add_all(users)
    db.commit()

    # 2. Seed Initial Model Versions
    print("[Seed] Seeding Baseline Model Versions...")
    model_versions = []
    for area, family in CIRCUIT_FAMILIES.items():
        mv = ModelVersion(
            circuit_family=family,
            version_tag="v1.0.0-Baseline",
            cr0_mm_yr=0.35,
            chloride_factor=1.15 if "Crude" in area or "Sulfur" in area else 1.0,
            bias_mm=0.12,
            scatter_mm=0.08,
            r2_score=0.94,
            calibration_points_count=18,
            notes=f"Initial commissioning physics baseline for {family} ({area})"
        )
        model_versions.append(mv)
    db.add_all(model_versions)
    db.commit()

    # 3. Seed Segments (300 total, 50 per area)
    print("[Seed] Generating 300 Piping Segments and 2,400 Sensors...")
    random.seed(42)  # Deterministic seed for reproducible testing
    now = datetime.now(timezone.utc)

    # We want ~12% wet segments => ~36 segments
    # We want ~40 degrading segments (some severely degraded with wall loss 0.4 - 1.3 mm/yr)
    degradation_indices = set(random.sample(range(300), 40))
    wet_indices = set(random.sample(range(300), 36))
    # Ensure significant overlap: degrading lines are predominantly wet
    wet_indices.update(list(degradation_indices)[:30])

    segments = []
    all_nodes = []
    all_pec_readings = []
    all_dts_readings = []
    all_alarms = []
    all_work_orders = []
    all_digs = []

    # Pipe size schedule choices
    SCHEDULES = [
        (4, 6.02, 3.2, 1.5),    # 4in: nom 6.02mm, t_min 3.2mm, CA 1.5mm
        (6, 7.11, 3.8, 2.0),    # 6in: nom 7.11mm, t_min 3.8mm, CA 2.0mm
        (8, 8.18, 4.2, 2.5),    # 8in: nom 8.18mm, t_min 4.2mm, CA 2.5mm
        (10, 9.27, 4.8, 2.5),   # 10in: nom 9.27mm, t_min 4.8mm, CA 2.5mm
        (12, 10.31, 5.2, 3.0),  # 12in: nom 10.31mm, t_min 5.2mm, CA 3.0mm
        (16, 12.70, 6.4, 3.5),  # 16in: nom 12.70mm, t_min 6.4mm, CA 3.5mm
        (20, 15.09, 7.5, 4.0)   # 20in: nom 15.09mm, t_min 7.5mm, CA 4.0mm
    ]

    for i in range(300):
        area = AREAS[i % len(AREAS)]
        family = CIRCUIT_FAMILIES[area]
        is_degrading = (i in degradation_indices)
        is_wet = (i in wet_indices) or is_degrading

        size_in, nom_wall, t_min, ca = random.choice(SCHEDULES)
        line_num = 1000 + i
        line_tag = f"{size_in}in-P-{line_num}-A1A"
        material = "Carbon Steel A106-B" if random.random() < 0.85 else random.choice(MATERIALS)
        insulation = random.choice(INSULATIONS)

        # Service and temperature
        if is_degrading:
            # Concentrated in the CUI sweet spot (50 - 175C)
            operating_temp = random.uniform(65.0, 160.0)
            service = "steam-traced" if random.random() < 0.5 else "hot"
        else:
            temp_profile = random.choice(["cold", "moderate", "hot_high", "cyclic"])
            if temp_profile == "cold":
                operating_temp = random.uniform(-15.0, 20.0)
                service = "cold"
            elif temp_profile == "moderate":
                operating_temp = random.uniform(25.0, 50.0)
                service = "hot"
            elif temp_profile == "hot_high":
                operating_temp = random.uniform(180.0, 290.0)
                service = "hot"
            else:
                operating_temp = random.uniform(40.0, 140.0)
                service = "cyclic"

        # Consequence category
        if is_degrading:
            consequence = random.choice(["C", "D", "E"])
        else:
            consequence = random.choice(CONSEQUENCES)

        chainage_m = round(random.uniform(60.0, 280.0), 1)
        rack_level = f"Tier-{random.randint(1, 4)}"
        rack_bay = (i % 25) + 1
        lat = 29.7604 + (random.uniform(-0.005, 0.005))
        lon = -95.3698 + (random.uniform(-0.005, 0.005))

        # Wet fraction calculation
        if is_degrading:
            rolling_wet_fraction = random.uniform(0.45, 0.95)
        elif is_wet:
            rolling_wet_fraction = random.uniform(0.15, 0.40)
        else:
            rolling_wet_fraction = random.uniform(0.0, 0.05)

        # Physics corrosion rate
        c_cl = 1.25 if "Crude" in area or "Sulfur" in area else 1.0
        model_cr = calculate_model_cr(
            cr0_mm_yr=0.35,
            operating_temp_C=operating_temp,
            wet_fraction=rolling_wet_fraction,
            chloride_factor=c_cl
        )

        if is_degrading:
            # Plant realistic wall loss rate of 0.4 to 1.3 mm/yr
            effective_cr = round(random.uniform(0.40, 1.30), 4)
        else:
            effective_cr = max(0.02, model_cr)

        # Simulated 3 years of degradation
        total_loss_3yr = effective_cr * 3.0
        current_wall = max(t_min + 0.1, nom_wall - total_loss_3yr)

        # For a few severely degrading segments, bring within 0.5 mm of t_min or under 2 yr
        if is_degrading and i % 5 == 0:
            current_wall = round(t_min + random.uniform(0.15, 0.48), 2)  # Imminent!
        elif is_degrading and i % 3 == 0:
            current_wall = round(t_min + random.uniform(0.60, 1.20), 2)  # Critical (<2 yr)

        rem_life = calculate_remaining_life(current_wall, t_min, effective_cr)
        health = evaluate_health_state(current_wall, t_min, rem_life)

        # Alarm state evaluation
        wall_loss_pct = round(((nom_wall - current_wall) / nom_wall) * 100.0, 1)
        consec_wet = random.randint(3, 8) if is_wet else 0
        consec_dry = 0 if is_wet else random.randint(4, 12)
        jacket_dt = random.uniform(6.5, 11.0) if is_wet else random.uniform(0.5, 3.5)

        alarm_st, alarm_reason = evaluate_alarm_state(
            current_state=0,
            consecutive_wet_readings=consec_wet,
            consecutive_dry_readings=consec_dry,
            jacket_delta_T_C=jacket_dt,
            wall_loss_pct_nominal=wall_loss_pct,
            remaining_life_yr=rem_life,
            current_wall_mm=current_wall,
            t_min_mm=t_min
        )

        # Risk evaluation
        pof = determine_pof_category(rem_life, rolling_wet_fraction, current_wall, t_min)
        risk_rank, insp_interval = evaluate_risk(pof, consequence)

        # Next inspection date based on interval
        if insp_interval == "6-12 months":
            next_insp = (now + timedelta(days=random.randint(60, 240))).strftime("%Y-%m-%d")
        elif insp_interval == "2 years":
            next_insp = (now + timedelta(days=random.randint(400, 700))).strftime("%Y-%m-%d")
        elif insp_interval == "3 years":
            next_insp = (now + timedelta(days=random.randint(800, 1050))).strftime("%Y-%m-%d")
        else:
            next_insp = (now + timedelta(days=random.randint(1400, 1750))).strftime("%Y-%m-%d")

        seg = Segment(
            id=i + 1,
            line_tag=line_tag,
            area=area,
            material=material,
            nominal_wall_mm=nom_wall,
            t_min_mm=t_min,
            corrosion_allowance_mm=ca,
            operating_temp_C=round(operating_temp, 1),
            insulation_type=insulation,
            service=service,
            consequence_category=consequence,
            chainage_m=chainage_m,
            rack_level=rack_level,
            rack_bay=rack_bay,
            lat=lat,
            lon=lon,
            circuit_family=family,
            current_wall_mm=round(current_wall, 2),
            remaining_life_yr=rem_life,
            health_state=health,
            alarm_state=alarm_st,
            rolling_wet_fraction=round(rolling_wet_fraction, 3),
            effective_cr_mm_yr=effective_cr,
            pof_category=pof,
            risk_ranking=risk_rank,
            next_inspection_date=next_insp
        )
        segments.append(seg)

        # 4. Generate 8 Moisture Nodes per segment (2,400 total)
        for n in range(8):
            clock = [6, 3, 9, 6, 6, 3, 9, 6][n]  # 6 o'clock is gravity water accumulation point
            chainage_pos = round((chainage_m / 9.0) * (n + 1), 1)
            node_id = f"MN-{line_num}-{n+1:02d}"

            if is_wet and (clock == 6 or random.random() < 0.6):
                moist_val = round(random.uniform(22.0, 88.0), 1)
                consec_w = random.randint(3, 10)
                consec_d = 0
            else:
                moist_val = round(random.uniform(0.5, 4.5), 1)
                consec_w = 0
                consec_d = random.randint(5, 20)

            node_obj = MoistureNode(
                id=node_id,
                segment_id=seg.id,
                clock_position=clock,
                chainage_position_m=chainage_pos,
                moisture_pct=moist_val,
                raw_moisture_pct=moist_val,
                jacket_temp_C=round(max(15.0, operating_temp * 0.35 + random.uniform(-2, 3)), 1),
                battery_pct=round(random.uniform(78.0, 99.5), 1),
                last_seen=now - timedelta(minutes=random.randint(1, 45)),
                consecutive_wet_count=consec_w,
                consecutive_dry_count=consec_d
            )
            all_nodes.append(node_obj)

        # 5. Generate 3 years of PEC readings (3 inspection campaigns)
        for year_offset in [3, 2, 1, 0]:
            pec_time = now - timedelta(days=year_offset * 365 + random.randint(0, 30))
            loss_at_time = effective_cr * (3.0 - year_offset)
            pec_wall = round(max(t_min - 0.1, nom_wall - loss_at_time + random.uniform(-0.15, 0.15)), 2)
            pec_reading = PECReading(
                segment_id=seg.id,
                position_m=round(chainage_m * 0.45, 1),
                measured_wall_mm=pec_wall,
                timestamp=pec_time,
                method="PEC",
                inspector="Robotic Crawler PEC-04"
            )
            all_pec_readings.append(pec_reading)

        # 6. Generate DTS Temperature profile points along line
        for step in range(10):
            dts_pos = round((chainage_m / 10.0) * step, 1)
            # Cold spots or heat loss along insulation defect
            if is_wet and 3 <= step <= 6:
                dts_temp = operating_temp - random.uniform(8.0, 18.0)
            else:
                dts_temp = operating_temp + random.uniform(-1.5, 1.5)
            dts_reading = DTSReading(
                segment_id=seg.id,
                position_m=dts_pos,
                temp_C=round(dts_temp, 1),
                timestamp=now - timedelta(minutes=random.randint(5, 60))
            )
            all_dts_readings.append(dts_reading)

        # 7. Generate Alarms if alarm_state > 0
        if alarm_st > 0:
            severity = "CRITICAL" if alarm_st == 4 else ("HIGH" if alarm_st == 3 else ("MEDIUM" if alarm_st == 2 else "LOW"))
            alarm_obj = Alarm(
                segment_id=seg.id,
                node_id=f"MN-{line_num}-01",
                state=alarm_st,
                trigger_reason=alarm_reason or f"Integrity threshold state {alarm_st} exceeded",
                severity=severity,
                status="ACTIVE" if random.random() < 0.7 else "ACKNOWLEDGED",
                created_at=now - timedelta(days=random.randint(1, 14)),
                acknowledged_at=now - timedelta(days=random.randint(0, 2)) if random.random() >= 0.7 else None,
                acknowledged_by="engineer@insulguard.com" if random.random() >= 0.7 else None,
                ack_notes="Field crew scheduled for targeted UT verification" if random.random() >= 0.7 else None
            )
            all_alarms.append(alarm_obj)

        # 8. Auto-create Work Order for Critical / Imminent / Priority lines
        if alarm_st >= 3 or health in ["Critical", "Imminent"]:
            wo_id = f"WO-2026-{1000 + len(all_work_orders)}"
            wo = WorkOrder(
                id=wo_id,
                segment_id=seg.id,
                title=f"Emergency CUI Strip & Clamp: {line_tag}",
                description=f"Automated priority repair draft. Remaining life {rem_life} yr. Wall thickness {current_wall} mm approaching t_min {t_min} mm.",
                status="IN_PROGRESS" if alarm_st == 4 else "DRAFT",
                priority="P1" if alarm_st == 4 else "P2",
                created_at=now - timedelta(days=random.randint(1, 10)),
                due_date=now + timedelta(days=14 if alarm_st == 4 else 45),
                assigned_to="Turnaround Mechanical Crew #3",
                estimated_cost_usd=round(random.uniform(35000, 75000), 2)
            )
            all_work_orders.append(wo)

        # 9. Verification Digs with UT calibration pairs (for ~35 segments)
        if (is_degrading or i % 8 == 0) and len(all_digs) < 35:
            pec_pred = current_wall
            # UT is ground truth: shows slightly worse or better thinning
            ut_meas = round(pec_pred - random.uniform(-0.25, 0.35), 2)
            delta = round(pec_pred - ut_meas, 3)
            dig = VerificationDig(
                segment_id=seg.id,
                location_chainage_m=round(chainage_m * 0.45, 1),
                dig_date=now - timedelta(days=random.randint(10, 180)),
                insulation_condition="Wet Degraded / Saturated" if is_wet else "Intact with Surface Scale",
                corrosion_severity="Severe Pitting & Delamination" if is_degrading else "Light Atmospheric Pitting",
                ut_measured_wall_mm=ut_meas,
                pec_predicted_wall_mm=pec_pred,
                delta_mm=delta,
                photo_url=f"/assets/digs/dig_{len(all_digs)%4 + 1}.jpg",
                inspector_notes=f"UT verified at 6 o'clock elbow low point. Pitting depth confirms active CUI electrolyte cell. PEC correlation delta: {delta} mm.",
                status="INSPECTED"
            )
            all_digs.append(dig)

    print(f"[Seed] Saving {len(segments)} segments to database...")
    db.add_all(segments)
    db.commit()

    print(f"[Seed] Saving {len(all_nodes)} moisture nodes...")
    db.add_all(all_nodes)
    db.commit()

    print(f"[Seed] Saving {len(all_pec_readings)} PEC readings...")
    db.add_all(all_pec_readings)
    db.commit()

    print(f"[Seed] Saving {len(all_dts_readings)} DTS readings...")
    db.add_all(all_dts_readings)
    db.commit()

    print(f"[Seed] Saving {len(all_alarms)} alarms, {len(all_work_orders)} work orders, {len(all_digs)} verification digs...")
    db.add_all(all_alarms)
    db.add_all(all_work_orders)
    db.add_all(all_digs)
    db.commit()

    # Initial Audit Log
    audit = AuditLog(
        user_email="admin@insulguard.com",
        action="SYSTEM_INITIALIZE",
        entity_type="SYSTEM",
        entity_id="ALL",
        previous_value=None,
        new_value=f"Populated 300 segments, 2400 nodes, 35 digs, and {len(all_alarms)} alarms.",
        timestamp=now
    )
    db.add(audit)
    db.commit()
    print("[Seed] Seed generation completed successfully!")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed_database(db, force=True)
    finally:
        db.close()
