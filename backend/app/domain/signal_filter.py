"""Moisture Signal Filtering Module.

Implements a 5-point median filter with a 3% deadband to eliminate RF telemetry
noise and environmental transients while preserving true wetting transitions.
"""

from typing import List, Optional
import numpy as np

def apply_5point_median_filter(
    history: List[float],
    current_raw_value: float,
    previous_filtered_value: Optional[float] = None,
    deadband_pct: float = 3.0
) -> float:
    """Computes filtered moisture reading using a 5-point rolling window and deadband.

    Args:
        history: Recent raw moisture readings (up to last 4 values, in percent 0-100).
        current_raw_value: Current raw sensor reading (moisture percentage 0-100%).
        previous_filtered_value: Prior output from the filter to evaluate deadband.
        deadband_pct: Minimum delta required to update filter output (default 3.0%).

    Returns:
        float: Filtered moisture reading in percentage [0.0, 100.0].
    """
    window = list(history[-4:]) + [current_raw_value]
    median_val = float(np.median(window))
    
    if previous_filtered_value is None:
        return round(median_val, 2)
    
    # Deadband check: suppress micro-fluctuations smaller than deadband
    if abs(median_val - previous_filtered_value) < deadband_pct:
        return round(previous_filtered_value, 2)
    
    return round(median_val, 2)
