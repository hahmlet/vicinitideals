"""Sensitivity analysis, stress testing, and scenario management."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pandas as pd

from vicinitideals.engines.underwriting import (
    DealInputs,
    DealSummary,
    UnderwritingEngine,
)


@dataclass
class SensitivityResult:
    """One-way sensitivity outcome."""
    variable_name: str
    variable_value: Decimal
    irr: Decimal
    moic: Decimal
    dscr_min: Decimal


class SensitivityAnalyzer:
    """Generate one-way, multi-way, and tornado sensitivity tables."""

    @staticmethod
    def one_way_sensitivity(
        base_deal: DealInputs,
        variable: str,
        values: list[Decimal],
    ) -> list[SensitivityResult]:
        """
        Run one-way sensitivity: vary one input, hold others constant.

        Args:
          base_deal: baseline DealInputs
          variable: e.g., "exit_cap_rate_pct", "debt_interest_rate_pct"
          values: list of values to test

        Returns:
          list[SensitivityResult] with results for each value
        """
        results = []

        for value in values:
            # Clone deal and update variable
            deal_dict = {**base_deal.__dict__}
            deal_dict[variable] = value
            deal_copy = DealInputs(**deal_dict)

            # Evaluate
            engine = UnderwritingEngine(deal_copy)
            summary = engine.evaluate()

            results.append(
                SensitivityResult(
                    variable_name=variable,
                    variable_value=value,
                    irr=summary.irr_equity,
                    moic=summary.moic_equity,
                    dscr_min=summary.dscr_minimum,
                )
            )

        return results

    @staticmethod
    def tornado_analysis(
        base_deal: DealInputs,
        sensitivity_ranges: dict[str, tuple[Decimal, Decimal]],
        metric: str = "irr_equity",
    ) -> pd.DataFrame:
        """
        Generate tornado chart data: impact on metric by variable.

        Args:
          base_deal: baseline deal
          sensitivity_ranges: {"var_name": (low, high), ...}
          metric: "irr_equity", "moic_equity", "dscr_minimum", etc.

        Returns:
          DataFrame with tornado rows (sorted by impact)
        """
        base_engine = UnderwritingEngine(base_deal)
        base_summary = base_engine.evaluate()
        base_value = getattr(base_summary, metric)

        tornado_rows = []

        for var_name, (low_val, high_val) in sensitivity_ranges.items():
            try:
                # Low case
                deal_low_dict = {**base_deal.__dict__}
                deal_low_dict[var_name] = low_val
                deal_low = DealInputs(**deal_low_dict)
                summary_low = UnderwritingEngine(deal_low).evaluate()
                metric_low = getattr(summary_low, metric)

                # High case
                deal_high_dict = {**base_deal.__dict__}
                deal_high_dict[var_name] = high_val
                deal_high = DealInputs(**deal_high_dict)
                summary_high = UnderwritingEngine(deal_high).evaluate()
                metric_high = getattr(summary_high, metric)

                # Range
                swing_low = metric_low - base_value
                swing_high = metric_high - base_value
                max_swing = max(abs(float(swing_low)), abs(float(swing_high)))

                tornado_rows.append({
                    "variable": var_name,
                    "low_value": low_val,
                    "low_metric": metric_low,
                    "high_value": high_val,
                    "high_metric": metric_high,
                    "swing": max_swing,
                })
            except Exception as e:
                # Skip variables that fail
                continue

        df = pd.DataFrame(tornado_rows)
        if len(df) > 0:
            df = df.sort_values("swing", ascending=False)

        return df

    @staticmethod
    def scenario_grid(
        base_deal: DealInputs,
        scenarios: dict[str, dict[str, Decimal]],
    ) -> pd.DataFrame:
        """
        Run named scenarios (e.g., "base", "downside", "upside").

        Args:
          base_deal: baseline
          scenarios: {
            "base": {},
            "downside": {"exit_cap_rate_pct": 0.055, "debt_interest_rate_pct": 0.065},
            "upside": {"exit_cap_rate_pct": 0.045, "debt_interest_rate_pct": 0.045},
          }

        Returns:
          DataFrame with one row per scenario
        """
        results = []

        for scenario_name, overrides in scenarios.items():
            deal_dict = {**base_deal.__dict__}
            deal_dict.update(overrides)

            deal_scenario = DealInputs(**deal_dict)
            engine = UnderwritingEngine(deal_scenario)
            summary = engine.evaluate()

            results.append({
                "scenario": scenario_name,
                "irr": summary.irr_equity,
                "moic": summary.moic_equity,
                "dscr_min": summary.dscr_minimum,
                "ltc": summary.ltc_max,
                "profit": summary.profit,
                "validation": "✓" if summary.validation_passed else "✗",
            })

        return pd.DataFrame(results)


class BreakpointFinder:
    """Solve for specific thresholds (e.g., IRR floor, DSCR minimum)."""

    @staticmethod
    def find_breakeven_exit_cap(
        base_deal: DealInputs,
        target_irr: Decimal = Decimal("0.12"),  # 12% target
    ) -> Optional[Decimal]:
        """
        Binary search: what exit cap rate yields target IRR?

        Returns:
          exit_cap_rate as Decimal, or None if not achievable
        """
        low_cap = Decimal("0.03")  # 3%
        high_cap = Decimal("0.10")  # 10%
        tolerance = Decimal("0.0001")  # 0.01% tolerance

        for _ in range(50):  # Max iterations
            mid_cap = (low_cap + high_cap) / 2

            deal_dict = {**base_deal.__dict__}
            deal_dict["exit_cap_rate_pct"] = mid_cap
            deal_copy = DealInputs(**deal_dict)

            engine = UnderwritingEngine(deal_copy)
            summary = engine.evaluate()

            if abs(summary.irr_equity - target_irr) < tolerance:
                return mid_cap

            if summary.irr_equity < target_irr:
                high_cap = mid_cap
            else:
                low_cap = mid_cap

        return None  # Not achievable
