from typing import List, Dict, Any
from fastapi import APIRouter
from app.schemas.schemas import FinancialParams, FinancialResponse, SensitivityScenario

router = APIRouter(prefix="/financials", tags=["Financial ROI & CUI Loss Ledger"])

def calculate_npv(discount_rate: float, cash_flows: List[float]) -> float:
    npv = 0.0
    for t, cf in enumerate(cash_flows):
        npv += cf / ((1.0 + discount_rate) ** t)
    return npv

def calculate_payback_years(capex: float, annual_net_cash_flow: float) -> float:
    if annual_net_cash_flow <= 0:
        return 99.0
    return round(capex / annual_net_cash_flow, 2)

@router.post("/calculate", response_model=FinancialResponse)
def compute_financials(params: FinancialParams):
    baseline_loss = params.baseline_annual_loss_usd
    capex = params.capex_usd
    opex = params.opex_usd_yr
    dr = params.discount_rate
    base_capture = params.loss_reduction_pct

    # Base Case Cash flows: Year 0: -CapEx, Years 1-5: (Gross Benefit - OpEx)
    base_annual_benefit = baseline_loss * base_capture
    base_annual_net = base_annual_benefit - opex
    base_cfs = [-capex] + [base_annual_net] * 5
    base_npv = calculate_npv(dr, base_cfs)
    base_payback = calculate_payback_years(capex, base_annual_net)
    base_total_net_5yr = (base_annual_net * 5) - capex
    base_roi_pct = round((base_total_net_5yr / max(1.0, capex)) * 100.0, 1)

    # 1. Base Case Scenario
    scenarios = [
        SensitivityScenario(
            scenario_name="Base Case (65% Loss Capture)",
            loss_reduction_pct=round(base_capture * 100.0, 1),
            payback_years=base_payback,
            npv_5yr_usd=round(base_npv, 2),
            irr_pct=round((base_annual_net / capex) * 100.0, 1),
            five_year_net_benefit_usd=round(base_total_net_5yr, 2)
        )
    ]

    # 2. Benefits 40% Lower Scenario (Capture is 60% of base => 39%)
    lower_capture = base_capture * 0.60
    lower_annual_benefit = baseline_loss * lower_capture
    lower_annual_net = lower_annual_benefit - opex
    lower_cfs = [-capex] + [lower_annual_net] * 5
    lower_npv = calculate_npv(dr, lower_cfs)
    lower_payback = calculate_payback_years(capex, lower_annual_net)
    lower_total_net_5yr = (lower_annual_net * 5) - capex

    scenarios.append(
        SensitivityScenario(
            scenario_name="Conservative Case (Benefits 40% Lower)",
            loss_reduction_pct=round(lower_capture * 100.0, 1),
            payback_years=lower_payback,
            npv_5yr_usd=round(lower_npv, 2),
            irr_pct=round((lower_annual_net / capex) * 100.0, 1),
            five_year_net_benefit_usd=round(lower_total_net_5yr, 2)
        )
    )

    # 3. Benefits Ramp Case (Year 1: 30%, Year 2: 50%, Year 3: 65%, Year 4: 75%, Year 5: 80%)
    ramp_rates = [0.30, 0.50, 0.65, 0.75, 0.80]
    ramp_annual_nets = [(baseline_loss * r) - opex for r in ramp_rates]
    ramp_cfs = [-capex] + ramp_annual_nets
    ramp_npv = calculate_npv(dr, ramp_cfs)
    
    # Cumulative cash flow for payback in ramp
    cum_cf = -capex
    ramp_payback = 5.0
    for yr, net in enumerate(ramp_annual_nets, 1):
        cum_cf += net
        if cum_cf >= 0:
            overshoot = cum_cf
            prev_deficit = net - overshoot
            ramp_payback = round((yr - 1) + (prev_deficit / net), 2)
            break
            
    ramp_total_net_5yr = sum(ramp_annual_nets) - capex
    scenarios.append(
        SensitivityScenario(
            scenario_name="Implementation Adoption Ramp (30% to 80%)",
            loss_reduction_pct=60.0,
            payback_years=ramp_payback,
            npv_5yr_usd=round(ramp_npv, 2),
            irr_pct=round((sum(ramp_annual_nets) / 5.0 / capex) * 100.0, 1),
            five_year_net_benefit_usd=round(ramp_total_net_5yr, 2)
        )
    )

    # 4. High Volatility Stress Test (High OpEx + 25% lower capture)
    stress_capture = base_capture * 0.75
    stress_opex = opex * 1.35
    stress_annual_net = (baseline_loss * stress_capture) - stress_opex
    stress_cfs = [-capex] + [stress_annual_net] * 5
    stress_npv = calculate_npv(dr, stress_cfs)
    stress_payback = calculate_payback_years(capex, stress_annual_net)
    stress_total_5yr = (stress_annual_net * 5) - capex

    scenarios.append(
        SensitivityScenario(
            scenario_name="Inflationary Stress Test (+35% OpEx)",
            loss_reduction_pct=round(stress_capture * 100.0, 1),
            payback_years=stress_payback,
            npv_5yr_usd=round(stress_npv, 2),
            irr_pct=round((stress_annual_net / capex) * 100.0, 1),
            five_year_net_benefit_usd=round(stress_total_5yr, 2)
        )
    )

    return FinancialResponse(
        inputs=params,
        base_case_payback_years=base_payback,
        base_case_5yr_npv_usd=round(base_npv, 2),
        base_case_roi_pct=base_roi_pct,
        scenarios=scenarios
    )

@router.get("", response_model=FinancialResponse)
def get_default_financials():
    return compute_financials(FinancialParams())
