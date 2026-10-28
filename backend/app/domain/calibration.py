"""Verification Dig UT-vs-PEC Calibration Engine.

Computes empirical bias and scatter (variance/standard deviation) between
non-destructive Pulsed Eddy Current (PEC) screening readings and direct
destructive/insulation-stripped Ultrasonic Thickness (UT) calibration pairs.
Updates circuit-family baseline corrosion rates (CR0) and chloride factors (C_Cl).
"""

from typing import List, Tuple, Dict, Any
import numpy as np

def compute_ut_pec_statistics(
    pairs: List[Tuple[float, float]]  # List of (pec_reading_mm, ut_reading_mm)
) -> Dict[str, float]:
    """Calculates bias, scatter (standard deviation), and R^2 correlation.

    Definitions:
        Delta_i = PEC_i - UT_i
        Bias = Mean(Delta)
        Scatter = StdDev(Delta)
        R^2 = Pearson correlation squared

    Args:
        pairs: List of (PEC_wall_mm, UT_wall_mm) measurement pairs.

    Returns:
        Dict[str, float]: {
            'bias_mm': float,
            'scatter_mm': float,
            'r2_score': float,
            'points_count': int
        }
    """
    if len(pairs) == 0:
        return {
            "bias_mm": 0.0,
            "scatter_mm": 0.0,
            "r2_score": 1.0,
            "points_count": 0
        }
    
    pec_vals = np.array([p[0] for p in pairs], dtype=float)
    ut_vals = np.array([p[1] for p in pairs], dtype=float)
    
    deltas = pec_vals - ut_vals
    bias = float(np.mean(deltas))
    scatter = float(np.std(deltas)) if len(deltas) > 1 else 0.0
    
    # Calculate R^2 correlation coefficient
    if len(pairs) >= 2:
        correlation_matrix = np.corrcoef(pec_vals, ut_vals)
        corr_coef = correlation_matrix[0, 1]
        r2 = float(corr_coef ** 2) if not np.isnan(corr_coef) else 0.95
    else:
        r2 = 0.95
        
    return {
        "bias_mm": round(bias, 4),
        "scatter_mm": round(scatter, 4),
        "r2_score": round(max(0.0, min(1.0, r2)), 4),
        "points_count": len(pairs)
    }

def update_model_parameters_from_calibration(
    current_cr0: float,
    current_c_cl: float,
    bias_mm: float,
    average_service_years: float = 3.0,
    learning_rate: float = 0.15
) -> Tuple[float, float]:
    """Updates circuit family CR0 and chloride factor using Bayesian/gradient calibration.

    If PEC consistently over-predicted wall (bias > 0), the actual wall is thinner
    (more corrosion occurred than predicted), so CR0 or chloride factor must increase.
    Conversely, if bias < 0 (actual wall is thicker than PEC indicated), model CR0 slightly decreases.

    Args:
        current_cr0: Current baseline corrosion rate (mm/yr).
        current_c_cl: Current chloride environment multiplier.
        bias_mm: PEC minus UT mean delta (mm).
        average_service_years: Time horizon over which deviation developed.
        learning_rate: Damping factor to prevent parameter oscillation.

    Returns:
        Tuple[float, float]: (Updated CR0 in mm/yr, Updated Chloride factor).
    """
    # Annualized bias error
    annual_bias_mm_yr = bias_mm / max(1.0, average_service_years)
    
    # Adjustment ratio
    adjustment = 1.0 + (annual_bias_mm_yr * learning_rate)
    # Bound adjustment between 0.70x and 1.40x to guarantee stability
    bounded_adj = max(0.70, min(1.40, adjustment))
    
    new_cr0 = round(max(0.10, min(1.50, current_cr0 * bounded_adj)), 4)
    new_c_cl = round(max(0.80, min(2.50, current_c_cl * (1.0 + (bounded_adj - 1.0) * 0.5))), 3)
    
    return new_cr0, new_c_cl
