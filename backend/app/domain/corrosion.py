"""Corrosion Physics Engine for Corrosion Under Insulation (CUI).

Calculates effective corrosion rates based on operating thermal zones,
wetness exposure duration, and localized chloride concentration factors,
blending theoretical degradation models with non-destructive Pulsed Eddy Current (PEC)
and Ultrasonic Testing (UT) field inspections.
"""

from typing import List, Tuple, Optional
from datetime import datetime

def temp_factor_fT(temp_celsius: float) -> float:
    """Calculates thermal acceleration factor f(T) according to CUI risk profiles.

    Physical rationale:
    - Below -4 C: Moisture freezes; liquid electrolyte absent; CR ~ 0.0.
    - -4 to 50 C: Atmospheric/ambient moisture pooling; moderate kinetics; factor = 0.6.
    - 50 to 125 C: Primary condensation / evaporation cycle zone; high moisture mobility; factor = 1.0.
    - 125 to 175 C: Severe CUI sweet spot; water boiling/evaporating concentrates corrosive salts (chlorides/sulfates); factor = 1.2.
    - Above 175 C: Water flashing; pipe surface stays mostly dry unless thermal cyclic or shutdown; factor = 0.3.

    Args:
        temp_celsius: Continuous metal operating temperature in degrees Celsius (C).

    Returns:
        float: Dimensionless thermal multiplier f(T).
    """
    if temp_celsius < -4.0:
        return 0.0
    elif -4.0 <= temp_celsius < 50.0:
        return 0.6
    elif 50.0 <= temp_celsius < 125.0:
        return 1.0
    elif 125.0 <= temp_celsius <= 175.0:
        return 1.2
    else:
        return 0.3

def calculate_model_cr(
    cr0_mm_yr: float,
    operating_temp_C: float,
    wet_fraction: float,
    chloride_factor: float = 1.0
) -> float:
    """Calculates theoretical effective CUI corrosion rate.

    Formula:
        CR_eff = CR0 * f(T) * W(t) * C_Cl

    Units:
        CR0: Base corrosion rate for bare carbon steel in aerated aqueous electrolyte (mm/yr).
        operating_temp_C: Pipe surface metal temperature in degrees Celsius (C).
        wet_fraction: Dimensionless rolling fraction of time insulation is wet (W(t) in [0.0, 1.0]).
        chloride_factor: Environmental marine/refinery salt multiplier (dimensionless, >= 1.0).

    Returns:
        float: Effective corrosion rate in millimeters per year (mm/yr).
    """
    f_t = temp_factor_fT(operating_temp_C)
    w_t = max(0.0, min(1.0, wet_fraction))
    cr_eff = cr0_mm_yr * f_t * w_t * chloride_factor
    return round(max(0.0, cr_eff), 4)

def calculate_measured_cr_from_pec(
    pec_history: List[Tuple[datetime, float]]
) -> Optional[float]:
    """Calculates empirical wall thinning rate from sequential PEC/UT inspection points.

    Args:
        pec_history: List of (timestamp, measured_wall_mm) pairs ordered chronologically.

    Returns:
        Optional[float]: Annualized thinning rate in mm/yr, or None if insufficient history.
    """
    if len(pec_history) < 2:
        return None
    
    t_start, wall_start = pec_history[0]
    t_end, wall_end = pec_history[-1]
    
    delta_days = (t_end - t_start).total_seconds() / 86400.0
    if delta_days < 30.0:  # Minimum 1 month span to avoid short-term noise
        return None
        
    delta_years = delta_days / 365.25
    wall_loss = wall_start - wall_end
    
    # Negative loss implies measurement noise/swelling; bound at 0.0
    measured_rate = max(0.0, wall_loss / delta_years)
    return round(measured_rate, 4)

def blend_corrosion_rates(
    model_cr_mm_yr: float,
    measured_cr_mm_yr: Optional[float],
    blend_weight: float = 0.65
) -> float:
    """Blends theoretical model corrosion rate with empirical PEC trendline.

    Args:
        model_cr_mm_yr: Calculated physical rate (mm/yr).
        measured_cr_mm_yr: Empirically observed thinning rate (mm/yr), or None.
        blend_weight: Weight given to empirical measurements when present (0.0 to 1.0).

    Returns:
        float: Blended effective corrosion rate in mm/yr.
    """
    if measured_cr_mm_yr is None:
        return round(model_cr_mm_yr, 4)
    
    blended = (blend_weight * measured_cr_mm_yr) + ((1.0 - blend_weight) * model_cr_mm_yr)
    return round(max(0.005, blended), 4)
