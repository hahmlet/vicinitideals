"""Pydantic schemas for LLM tool integration (Claude, etc.)."""

from decimal import Decimal
from typing import Optional, Literal

from pydantic import BaseModel, Field


class EvaluateDealRequest(BaseModel):
    """Request schema: LLM asks engine to evaluate a deal."""

    # Sources
    purchase_price: Decimal = Field(
        ..., description="Purchase price in USD"
    )
    debt_amount: Decimal = Field(
        ..., description="Loan amount in USD"
    )
    equity_amount: Decimal = Field(
        ..., description="Equity check in USD"
    )
    hard_costs: Decimal = Field(
        default=Decimal("0"), description="Hard costs (construction) in USD"
    )

    # Operations
    unit_count: int = Field(
        ..., description="Total units in the property"
    )
    revenue_per_unit_monthly: Decimal = Field(
        ..., description="Blended stabilized rent + ancillary per unit"
    )
    opex_per_unit_annual: Decimal = Field(
        default=Decimal("0"), description="Operating expenses per unit per year"
    )

    # Debt
    debt_interest_rate_pct: Decimal = Field(
        ..., description="Annual interest rate (e.g., 0.055 = 5.5%)"
    )
    debt_amortization_years: int = Field(
        default=30, description="Loan amortization period"
    )
    debt_dscr_minimum: Decimal = Field(
        default=Decimal("1.25"), description="Minimum DSCR requirement"
    )

    # Exit
    hold_period_years: int = Field(
        default=7, description="Expected hold period"
    )
    exit_cap_rate_pct: Decimal = Field(
        ..., description="Exit cap rate (e.g., 0.05 = 5%)"
    )

    # Assumptions
    initial_occupancy_pct: Decimal = Field(
        default=Decimal("0.82"), description="Post-lease-up occupancy"
    )
    stable_occupancy_pct: Decimal = Field(
        default=Decimal("0.95"), description="Stabilized occupancy"
    )
    revenue_growth_rate_pct: Decimal = Field(
        default=Decimal("0.025"), description="Annual rent growth"
    )
    opex_growth_rate_pct: Decimal = Field(
        default=Decimal("0.03"), description="Annual OpEx growth"
    )

    # Soft costs / contingency
    soft_costs: Decimal = Field(
        default=Decimal("0"), description="Soft costs (professional fees, permits) in USD"
    )
    contingency: Decimal = Field(
        default=Decimal("0"), description="Contingency reserve in USD"
    )
    closing_costs_pct: Decimal = Field(
        default=Decimal("0.018"), description="Closing costs as pct of purchase price"
    )

    # Timing (dates as ISO strings)
    close_date: str = Field(
        ..., description="Closing date (YYYY-MM-DD)"
    )
    construction_start: str = Field(
        ..., description="Construction start date (YYYY-MM-DD)"
    )
    lease_up_start: str = Field(
        ..., description="Lease-up start date (YYYY-MM-DD)"
    )
    stabilized_start: str = Field(
        ..., description="Stabilized operations date (YYYY-MM-DD)"
    )
    exit_date: str = Field(
        ..., description="Exit/sale date (YYYY-MM-DD)"
    )

    # Construction
    renovation_months: int = Field(
        default=7, description="Renovation duration in months"
    )
    lease_up_months: int = Field(
        default=4, description="Lease-up duration in months"
    )

    # Waterfall (optional)
    preferred_return_pct: Decimal = Field(
        default=Decimal("0.0"), description="LP preferred return rate"
    )
    gp_promote_pct_after_pref: Decimal = Field(
        default=Decimal("0.0"), description="GP carried interest after pref"
    )

    # Selling costs
    selling_costs_pct: Decimal = Field(
        default=Decimal("0.025"), description="Selling costs as pct of sale price"
    )


class EvaluateDealResponse(BaseModel):
    """Response schema: deal evaluation results."""

    irr_equity: Decimal = Field(
        ..., description="Equity IRR (e.g., 0.15 = 15%)"
    )
    moic_equity: Decimal = Field(
        ..., description="Equity MOIC (multiple on invested capital)"
    )

    dscr_average: Decimal = Field(
        ..., description="Average Debt Service Coverage Ratio"
    )
    dscr_minimum: Decimal = Field(
        ..., description="Minimum DSCR (covenant trigger point)"
    )

    ltc_max: Decimal = Field(
        ..., description="Max Loan-to-Cost ratio"
    )

    noi_stable: Decimal = Field(
        ..., description="Average NOI in stabilized operations"
    )

    profit: Decimal = Field(
        ..., description="Equity profit (returns - invested)"
    )

    validation_passed: bool = Field(
        ..., description="Does deal meet all constraints?"
    )
    validation_issues: list[str] = Field(
        default_factory=list,
        description="List of covenant breaches or red flags"
    )


class SensitivityRequest(BaseModel):
    """Request: Run one-way sensitivity on a variable."""

    variable: str = Field(
        ..., description="Variable to vary (e.g., 'exit_cap_rate_pct')"
    )
    low_value: Decimal = Field(
        ..., description="Low end of range"
    )
    high_value: Decimal = Field(
        ..., description="High end of range"
    )
    num_steps: int = Field(
        default=10, description="Number of steps between low and high"
    )
    base_deal: EvaluateDealRequest = Field(
        ..., description="Base deal to analyze"
    )


class SensitivityResponse(BaseModel):
    """Response: Sensitivity table."""

    variable: str
    results: list[dict] = Field(
        ..., description="[{value, irr, moic, dscr_min}, ...]"
    )


class StressTestRequest(BaseModel):
    """Request: Run named stress scenarios."""

    base_deal: EvaluateDealRequest = Field(
        ..., description="Base deal"
    )
    scenarios: dict[str, dict] = Field(
        ..., description={
            "base": {},
            "downside": {"exit_cap_rate_pct": 0.055},
            "severe_downside": {"exit_cap_rate_pct": 0.065},
            "upside": {"exit_cap_rate_pct": 0.045},
        }
    )


class StressTestResponse(BaseModel):
    """Response: Stress test grid."""

    scenarios: list[dict] = Field(
        ..., description="[{name, irr, moic, dscr_min, ltc, status}, ...]"
    )


# Example LLM tool definition (for Claude)
UNDERWRITING_TOOLS = [
    {
        "name": "evaluate_deal",
        "description": """Evaluate a multifamily real estate deal.

        Deterministically calculates:
        - Cashflow for each month (acquisition → lease-up → stabilized → exit)
        - NOI, debt service, and DSCR
        - Equity IRR and MOIC
        - Waterfall distributions (LP pref + GP promote)
        - Validation against DSCR, LTC, and other constraints

        Returns audited financial metrics and red flags.
        """,
        "input_schema": {
            "type": "object",
            "properties": EvaluateDealRequest.model_json_schema()[
                "properties"
            ],
            "required": EvaluateDealRequest.model_json_schema().get(
                "required", []
            ),
        },
    },
    {
        "name": "sensitivity_analysis",
        "description": """Run one-way sensitivity to understand model fragility.

        Varies one input (e.g., exit cap rate from 4% to 6%) while holding
        others constant. Returns IRR, MOIC, and DSCR for each step.

        Use to identify tipping points where deals break.
        """,
        "input_schema": {
            "type": "object",
            "properties": SensitivityRequest.model_json_schema()[
                "properties"
            ],
            "required": SensitivityRequest.model_json_schema().get(
                "required", []
            ),
        },
    },
    {
        "name": "stress_test",
        "description": """Run multiple named scenarios (base, downside, upside).

        Compare financial outcomes across different macro/micro assumptions.
        Returns grid of {scenario, IRR, MOIC, DSCR, LTC}.
        """,
        "input_schema": {
            "type": "object",
            "properties": StressTestRequest.model_json_schema()[
                "properties"
            ],
            "required": StressTestRequest.model_json_schema().get(
                "required", []
            ),
        },
    },
]
