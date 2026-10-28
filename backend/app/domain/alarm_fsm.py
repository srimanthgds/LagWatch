"""Alarm Finite State Machine (0-4) with Industrial Hysteresis.

State Definitions (ISA-101 Aligned):
- State 0 (Normal): Insulation dry, integrity healthy.
- State 1 (Advisory): 2 consecutive readings > 10% moisture, or jacket delta-T > 6C vs neighbouring nodes.
- State 2 (Verify): PEC wall loss > 25% of nominal, or remaining life < 5 yr.
- State 3 (Plan Repair): Remaining life < 2 yr (requires automatic work order draft).
- State 4 (Escalate): Wall thickness within 0.5 mm of t_min (immediate containment protocol).

Hysteresis Rule:
- Advisory (State 1) transitions back to State 0 only after at least 3 consecutive dry readings
  (<= 10.0% moisture) spanning a minimum of 7 days (or 3 consecutive verified dry observations).
- Higher severity alarms (States 2, 3, 4) do not clear until physical inspection/repair resolves the thinning.
"""

from typing import Tuple, Optional

def evaluate_alarm_state(
    current_state: int,
    consecutive_wet_readings: int,
    consecutive_dry_readings: int,
    jacket_delta_T_C: float,
    wall_loss_pct_nominal: float,
    remaining_life_yr: float,
    current_wall_mm: float,
    t_min_mm: float,
    dry_duration_days: float = 7.0,
    imminent_margin_mm: float = 0.5
) -> Tuple[int, Optional[str]]:
    """Evaluates the next alarm state and trigger reason based on sensor and NDT telemetry.

    Args:
        current_state: Active state integer (0, 1, 2, 3, 4).
        consecutive_wet_readings: Count of consecutive moisture readings > 10%.
        consecutive_dry_readings: Count of consecutive moisture readings <= 10%.
        jacket_delta_T_C: Temperature discrepancy vs adjacent rack nodes (C).
        wall_loss_pct_nominal: Percentage wall thinning vs original nominal (e.g., 28.5%).
        remaining_life_yr: Projected remaining service life in years.
        current_wall_mm: Measured or estimated remaining wall thickness (mm).
        t_min_mm: Code minimum required wall thickness (mm).
        dry_duration_days: Span of verified dry conditions.
        imminent_margin_mm: Distance to t_min triggering emergency escalation (mm).

    Returns:
        Tuple[int, Optional[str]]: (New state integer, Trigger/Clear rationale string).
    """
    margin_mm = current_wall_mm - t_min_mm
    
    # Priority 4: Escalate - Critical threshold breach
    if margin_mm <= imminent_margin_mm:
        return 4, f"CRITICAL: Wall margin is {margin_mm:.2f} mm <= {imminent_margin_mm:.2f} mm of t_min. Immediate breach risk."
    
    # Priority 3: Plan Repair - Less than 2 years remaining
    if remaining_life_yr < 2.0:
        return 3, f"PLAN REPAIR: Remaining life {remaining_life_yr:.1f} yr < 2.0 yr threshold. Repair work order required."
    
    # Priority 2: Verify - Significant degradation or moderate remaining life
    if wall_loss_pct_nominal >= 25.0 or remaining_life_yr < 5.0:
        reasons = []
        if wall_loss_pct_nominal >= 25.0:
            reasons.append(f"PEC wall loss {wall_loss_pct_nominal:.1f}% >= 25% nominal")
        if remaining_life_yr < 5.0:
            reasons.append(f"remaining life {remaining_life_yr:.1f} yr < 5.0 yr")
        return 2, f"VERIFY: {' and '.join(reasons)}. Targeted NDT verification required."
    
    # Priority 1: Advisory - Active wetting detected
    is_wet_advisory = (consecutive_wet_readings >= 2) or (jacket_delta_T_C >= 6.0)
    if is_wet_advisory:
        reason_items = []
        if consecutive_wet_readings >= 2:
            reason_items.append(f"{consecutive_wet_readings} consecutive wet readings (>10% moisture)")
        if jacket_delta_T_C >= 6.0:
            reason_items.append(f"jacket delta-T {jacket_delta_T_C:.1f} C >= 6.0 C")
        return 1, f"ADVISORY: Active moisture ingress detected ({', '.join(reason_items)})."
    
    # Hysteresis Clear Condition for Advisory (State 1 -> State 0)
    if current_state == 1:
        if consecutive_dry_readings >= 3 and dry_duration_days >= 7.0:
            return 0, f"CLEARED: Insulation dried out ({consecutive_dry_readings} dry readings over {dry_duration_days:.1f} days)."
        else:
            # Maintain Advisory under hysteresis hold
            return 1, f"ADVISORY: Ingress suspected. Hysteresis hold ({consecutive_dry_readings}/3 dry readings, {dry_duration_days:.1f}/7 days)."
            
    # For States 2, 3, 4: Retain state unless wall thickness / remaining life has been physically repaired
    if current_state in (2, 3, 4):
        return current_state, f"MAINTAINED: Integrity state {current_state} pending physical inspection/repair signoff."
        
    return 0, None
