"""Piping Remaining Life & Health Classification Engine.

Implements remaining service life calculations and health classification states
conforming to API 570 (Piping Inspection Code) and refinery asset risk criteria.
"""

from typing import Tuple

def calculate_remaining_life(
    current_wall_mm: float,
    t_min_mm: float,
    effective_cr_mm_yr: float
) -> float:
    """Calculates remaining life until minimum structural thickness is breached.

    Formula:
        t_rem = (t_meas - t_min) / CR_eff

    Units:
        current_wall_mm: Measured or projected metal wall thickness (mm).
        t_min_mm: Minimum required design structural wall thickness per ASME B31.3 (mm).
        effective_cr_mm_yr: Effective corrosion thinning rate (mm/yr).

    Returns:
        float: Remaining service life in years [0.0, 50.0].
    """
    margin_mm = max(0.0, current_wall_mm - t_min_mm)
    
    if margin_mm <= 0.0:
        return 0.0
    
    if effective_cr_mm_yr <= 0.001:
        # Passive state: cap at theoretical plant design horizon
        return 50.0
        
    rem_life = margin_mm / effective_cr_mm_yr
    return round(min(50.0, max(0.0, rem_life)), 2)

def evaluate_health_state(
    current_wall_mm: float,
    t_min_mm: float,
    remaining_life_yr: float,
    imminent_margin_mm: float = 0.5
) -> str:
    """Evaluates pipe integrity health tier.

    Health States:
        - Imminent: Wall thickness within 0.5 mm of minimum allowable limit (t_meas - t_min <= 0.5 mm).
        - Critical: Remaining life under 2 years (immediate engineering action required).
        - Priority: Remaining life 2 to 5 years (turnaround repair planning horizon).
        - Watch: Remaining life 5 to 10 years (increased inspection frequency).
        - Healthy: Remaining life over 10 years (normal routine surveillance).

    Returns:
        str: Health state classification.
    """
    margin_mm = current_wall_mm - t_min_mm
    
    if margin_mm <= imminent_margin_mm:
        return "Imminent"
    elif remaining_life_yr < 2.0:
        return "Critical"
    elif 2.0 <= remaining_life_yr < 5.0:
        return "Priority"
    elif 5.0 <= remaining_life_yr <= 10.0:
        return "Watch"
    else:
        return "Healthy"
