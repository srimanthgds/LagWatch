"""API RP 581 Risk-Based Inspection (RBI) Engine.

Calculates Probability of Failure (PoF) Categories (1 to 5), evaluates
Consequence of Failure (CoF) Categories (A to E), maps to a 5x5 Risk Matrix,
and determines recommended ASME/API inspection intervals.
"""

from typing import Tuple, Dict

def determine_pof_category(
    remaining_life_yr: float,
    wet_fraction: float,
    current_wall_mm: float,
    t_min_mm: float
) -> int:
    """Evaluates Probability of Failure (PoF) category from 1 (Lowest) to 5 (Highest).

    Criteria:
        Category 5: Remaining life < 2.0 yr OR (wall - t_min <= 0.5 mm).
        Category 4: Remaining life < 5.0 yr OR (remaining life < 8.0 yr AND wet_fraction > 0.30).
        Category 3: Remaining life < 10.0 yr OR (remaining life < 15.0 yr AND wet_fraction > 0.20).
        Category 2: Remaining life < 20.0 yr OR wet_fraction > 0.10.
        Category 1: Healthy piping with long remaining life and dry insulation.

    Returns:
        int: PoF category from 1 to 5.
    """
    margin = current_wall_mm - t_min_mm
    
    if remaining_life_yr < 2.0 or margin <= 0.5:
        return 5
    elif remaining_life_yr < 5.0 or (remaining_life_yr < 8.0 and wet_fraction > 0.30):
        return 4
    elif remaining_life_yr < 10.0 or (remaining_life_yr < 15.0 and wet_fraction > 0.20):
        return 3
    elif remaining_life_yr < 20.0 or wet_fraction > 0.10:
        return 2
    else:
        return 1

# Standard API RP 581 5x5 Risk Matrix
# CoF: 'A', 'B', 'C', 'D', 'E'
# PoF: 1, 2, 3, 4, 5
RISK_MATRIX_MAPPING: Dict[Tuple[int, str], str] = {
    # PoF 5
    (5, 'A'): "Medium-High",
    (5, 'B'): "Medium-High",
    (5, 'C'): "High",
    (5, 'D'): "High",
    (5, 'E'): "High",
    # PoF 4
    (4, 'A'): "Medium",
    (4, 'B'): "Medium",
    (4, 'C'): "Medium-High",
    (4, 'D'): "High",
    (4, 'E'): "High",
    # PoF 3
    (3, 'A'): "Low",
    (3, 'B'): "Medium",
    (3, 'C'): "Medium",
    (3, 'D'): "Medium-High",
    (3, 'E'): "High",
    # PoF 2
    (2, 'A'): "Low",
    (2, 'B'): "Low",
    (2, 'C'): "Medium",
    (2, 'D'): "Medium",
    (2, 'E'): "Medium-High",
    # PoF 1
    (1, 'A'): "Low",
    (1, 'B'): "Low",
    (1, 'C'): "Low",
    (1, 'D'): "Low",
    (1, 'E'): "Medium",
}

INSPECTION_INTERVALS: Dict[str, str] = {
    "High": "6-12 months",
    "Medium-High": "2 years",
    "Medium": "3 years",
    "Low": "5 years",
}

def evaluate_risk(
    pof_category: int,
    cof_category: str
) -> Tuple[str, str]:
    """Calculates risk ranking and recommended inspection interval.

    Args:
        pof_category: 1 to 5.
        cof_category: 'A', 'B', 'C', 'D', 'E'.

    Returns:
        Tuple[str, str]: (Risk Ranking [Low, Medium, Medium-High, High], Recommended Interval).
    """
    cof = cof_category.upper().strip()
    if cof not in ['A', 'B', 'C', 'D', 'E']:
        cof = 'C'
    pof = max(1, min(5, pof_category))
    
    ranking = RISK_MATRIX_MAPPING.get((pof, cof), "Medium")
    interval = INSPECTION_INTERVALS.get(ranking, "3 years")
    return ranking, interval
