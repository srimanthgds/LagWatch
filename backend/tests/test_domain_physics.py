import pytest
from datetime import datetime, timedelta
from app.domain.corrosion import (
    temp_factor_fT, calculate_model_cr, calculate_measured_cr_from_pec, blend_corrosion_rates
)
from app.domain.remaining_life import calculate_remaining_life, evaluate_health_state
from app.domain.alarm_fsm import evaluate_alarm_state
from app.domain.risk_engine import determine_pof_category, evaluate_risk
from app.domain.calibration import compute_ut_pec_statistics, update_model_parameters_from_calibration
from app.domain.signal_filter import apply_5point_median_filter

def test_thermal_factor_fT():
    # Below -4C: ~0
    assert temp_factor_fT(-10.0) == 0.0
    # -4 to 50C: 0.6
    assert temp_factor_fT(25.0) == 0.6
    assert temp_factor_fT(-4.0) == 0.6
    # 50 to 125C: 1.0
    assert temp_factor_fT(60.0) == 1.0
    assert temp_factor_fT(124.9) == 1.0
    # 125 to 175C: 1.2
    assert temp_factor_fT(140.0) == 1.2
    assert temp_factor_fT(175.0) == 1.2
    # Above 175C: 0.3
    assert temp_factor_fT(200.0) == 0.3

def test_corrosion_model_calculation():
    # CR0 = 0.35, T = 130C (f(T)=1.2), W(t) = 0.5, C_Cl = 1.0
    # CR_eff = 0.35 * 1.2 * 0.5 * 1.0 = 0.21 mm/yr
    cr = calculate_model_cr(cr0_mm_yr=0.35, operating_temp_C=130.0, wet_fraction=0.5, chloride_factor=1.0)
    assert cr == 0.21

    # Completely dry: W(t) = 0.0 => CR_eff = 0.0
    cr_dry = calculate_model_cr(cr0_mm_yr=0.35, operating_temp_C=100.0, wet_fraction=0.0)
    assert cr_dry == 0.0

def test_pec_measured_rate_and_blending():
    now = datetime(2026, 1, 1)
    past = now - timedelta(days=365)
    history = [(past, 10.0), (now, 9.2)]  # 0.8 mm loss over 1 yr
    measured = calculate_measured_cr_from_pec(history)
    assert measured is not None
    assert pytest.approx(measured, 0.01) == 0.8

    # Blend 0.8 mm/yr measured with 0.2 mm/yr model (blend weight 0.65)
    # 0.65 * 0.8 + 0.35 * 0.2 = 0.52 + 0.07 = 0.59 mm/yr
    blended = blend_corrosion_rates(0.20, measured, blend_weight=0.65)
    assert pytest.approx(blended, 0.01) == 0.59

def test_remaining_life_and_health_states():
    # current = 8.0, t_min = 4.0, CR = 0.4 => t_rem = (8.0 - 4.0)/0.4 = 10.0 yr
    rem = calculate_remaining_life(current_wall_mm=8.0, t_min_mm=4.0, effective_cr_mm_yr=0.4)
    assert rem == 10.0
    assert evaluate_health_state(8.0, 4.0, rem) == "Watch"

    # Healthy: > 10 yr
    assert evaluate_health_state(9.0, 4.0, 12.0) == "Healthy"
    # Priority: 2 - 5 yr
    assert evaluate_health_state(5.5, 4.0, 3.5) == "Priority"
    # Critical: < 2 yr
    assert evaluate_health_state(4.8, 4.0, 1.6) == "Critical"
    # Imminent: within 0.5 mm of t_min (e.g. 4.4 mm with t_min 4.0 mm)
    assert evaluate_health_state(4.3, 4.0, 3.0) == "Imminent"

def test_alarm_fsm_and_hysteresis():
    # Normal state 0 -> 1 wet reading (remain 0)
    state, _ = evaluate_alarm_state(
        current_state=0,
        consecutive_wet_readings=1,
        consecutive_dry_readings=0,
        jacket_delta_T_C=2.0,
        wall_loss_pct_nominal=5.0,
        remaining_life_yr=15.0,
        current_wall_mm=8.0,
        t_min_mm=4.0
    )
    assert state == 0

    # 2 consecutive wet readings -> Advisory (State 1)
    state, reason = evaluate_alarm_state(
        current_state=0,
        consecutive_wet_readings=2,
        consecutive_dry_readings=0,
        jacket_delta_T_C=2.0,
        wall_loss_pct_nominal=5.0,
        remaining_life_yr=15.0,
        current_wall_mm=8.0,
        t_min_mm=4.0
    )
    assert state == 1
    assert "Active moisture ingress" in reason

    # Delta T > 6C triggers State 1 Advisory even if wet count < 2
    state_dt, _ = evaluate_alarm_state(
        current_state=0,
        consecutive_wet_readings=0,
        consecutive_dry_readings=2,
        jacket_delta_T_C=7.5,
        wall_loss_pct_nominal=5.0,
        remaining_life_yr=15.0,
        current_wall_mm=8.0,
        t_min_mm=4.0
    )
    assert state_dt == 1

    # In State 1: 2 dry readings over 4 days does NOT clear advisory (hysteresis hold)
    state_hold, reason_hold = evaluate_alarm_state(
        current_state=1,
        consecutive_wet_readings=0,
        consecutive_dry_readings=2,
        jacket_delta_T_C=1.0,
        wall_loss_pct_nominal=5.0,
        remaining_life_yr=15.0,
        current_wall_mm=8.0,
        t_min_mm=4.0,
        dry_duration_days=4.0
    )
    assert state_hold == 1
    assert "Hysteresis hold" in reason_hold

    # In State 1: 3 consecutive dry readings over 7.5 days CLEARS to State 0
    state_clear, reason_clear = evaluate_alarm_state(
        current_state=1,
        consecutive_wet_readings=0,
        consecutive_dry_readings=3,
        jacket_delta_T_C=1.0,
        wall_loss_pct_nominal=5.0,
        remaining_life_yr=15.0,
        current_wall_mm=8.0,
        t_min_mm=4.0,
        dry_duration_days=7.5
    )
    assert state_clear == 0
    assert "CLEARED" in reason_clear

    # State 2 (Verify): wall loss > 25% or rem life < 5 yr
    state_v, _ = evaluate_alarm_state(
        current_state=1,
        consecutive_wet_readings=2,
        consecutive_dry_readings=0,
        jacket_delta_T_C=2.0,
        wall_loss_pct_nominal=28.0,
        remaining_life_yr=4.2,
        current_wall_mm=6.5,
        t_min_mm=4.0
    )
    assert state_v == 2

    # State 3 (Plan Repair): rem life < 2 yr
    state_pr, _ = evaluate_alarm_state(
        current_state=2,
        consecutive_wet_readings=2,
        consecutive_dry_readings=0,
        jacket_delta_T_C=2.0,
        wall_loss_pct_nominal=35.0,
        remaining_life_yr=1.5,
        current_wall_mm=4.8,
        t_min_mm=4.0
    )
    assert state_pr == 3

    # State 4 (Escalate): wall within 0.5 mm of t_min
    state_esc, _ = evaluate_alarm_state(
        current_state=3,
        consecutive_wet_readings=2,
        consecutive_dry_readings=0,
        jacket_delta_T_C=2.0,
        wall_loss_pct_nominal=45.0,
        remaining_life_yr=0.8,
        current_wall_mm=4.3,
        t_min_mm=4.0
    )
    assert state_esc == 4

def test_risk_engine_api_581():
    # High risk: CoF = E, PoF = 5
    pof = determine_pof_category(remaining_life_yr=1.2, wet_fraction=0.8, current_wall_mm=4.8, t_min_mm=4.0)
    assert pof == 5
    ranking, interval = evaluate_risk(pof, "E")
    assert ranking == "High"
    assert interval == "6-12 months"

    # Low risk: CoF = A, PoF = 1
    pof_low = determine_pof_category(remaining_life_yr=25.0, wet_fraction=0.02, current_wall_mm=10.0, t_min_mm=4.0)
    assert pof_low == 1
    ranking_low, interval_low = evaluate_risk(pof_low, "A")
    assert ranking_low == "Low"
    assert interval_low == "5 years"

def test_calibration_and_scatter():
    # PEC vs UT pairs
    # delta: (7.2 - 7.0) = +0.2, (6.5 - 6.3) = +0.2, (8.1 - 7.9) = +0.2
    pairs = [(7.2, 7.0), (6.5, 6.3), (8.1, 7.9)]
    stats = compute_ut_pec_statistics(pairs)
    assert pytest.approx(stats["bias_mm"], 0.01) == 0.20
    assert pytest.approx(stats["scatter_mm"], 0.01) == 0.0

    # Model parameter update: positive bias means actual wall is thinner than PEC,
    # so corrosion was higher -> CR0 should increase
    new_cr0, new_c_cl = update_model_parameters_from_calibration(
        current_cr0=0.35, current_c_cl=1.0, bias_mm=0.20, average_service_years=3.0
    )
    assert new_cr0 > 0.35
    assert new_c_cl >= 1.0

def test_5point_median_filter_and_deadband():
    history = [12.0, 12.5, 12.1, 12.3]
    # Current raw value has a micro-spike to 13.5 (difference vs prev 12.3 is 1.2%, < 3% deadband)
    filtered = apply_5point_median_filter(history, current_raw_value=13.5, previous_filtered_value=12.3, deadband_pct=3.0)
    assert filtered == 12.3  # Retained due to deadband

    # Large real jump to 30.0% (median of [12.0, 12.5, 12.1, 12.3, 30.0] is 12.3)
    filtered_spike = apply_5point_median_filter(history, current_raw_value=30.0, previous_filtered_value=12.3)
    assert filtered_spike == 12.3  # Noise spike rejected by median

    # Consistent high readings
    wet_history = [28.0, 29.0, 31.0, 30.0]
    filtered_wet = apply_5point_median_filter(wet_history, current_raw_value=32.0, previous_filtered_value=12.3)
    assert filtered_wet == 30.0  # Real wetting confirmed (> 3% delta)
