from __future__ import annotations

import json
import math
from decimal import Decimal, ROUND_HALF_UP
from json import JSONDecodeError

from app.models.forecasting import ForecastSummary
from app.models.simulation import (
    MAX_SCENARIO_ADJUSTMENT_PCT,
    MIN_SCENARIO_ADJUSTMENT_PCT,
    BaselineSimulationMetrics,
    ScenarioAdjustments,
    ScenarioDifference,
    ScenarioEvidenceItem,
    ScenarioMetrics,
    SimulationPeriod,
    SimulationSummary,
    WhatIfSimulationResponse,
)

TWO_DECIMAL_PLACES = Decimal("0.01")
ONE_HUNDRED = Decimal("100")
SCENARIO_FIELDS = (
    "revenue_pct",
    "cogs_pct",
    "operating_expenses_pct",
)
SCENARIO_LABELS = {
    "revenue_pct": "Revenue",
    "cogs_pct": "COGS",
    "operating_expenses_pct": "Operating expenses",
}
SCENARIO_VERBS = {
    "revenue_pct": ("remains", "is"),
    "cogs_pct": ("remains", "is"),
    "operating_expenses_pct": ("remain", "are"),
}


class ScenarioValidationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.row = None
        self.status_code = status_code


def parse_scenario_json(raw_scenario: str) -> ScenarioAdjustments:
    try:
        payload = json.loads(raw_scenario)
    except (JSONDecodeError, TypeError) as exc:
        raise ScenarioValidationError(
            "INVALID_SCENARIO",
            "The scenario form field must contain a valid JSON object.",
            field="scenario",
        ) from exc

    if not isinstance(payload, dict):
        raise ScenarioValidationError(
            "INVALID_SCENARIO",
            "The scenario form field must contain a JSON object.",
            field="scenario",
        )

    unknown_fields = sorted(set(payload) - set(SCENARIO_FIELDS))
    if unknown_fields:
        raise ScenarioValidationError(
            "INVALID_SCENARIO",
            f"Unknown scenario field: {unknown_fields[0]}.",
            field=unknown_fields[0],
        )

    validated_values: dict[str, float] = {}
    for field in SCENARIO_FIELDS:
        raw_value = payload.get(field, 0.0)
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise ScenarioValidationError(
                "INVALID_SCENARIO_ADJUSTMENT",
                f"{field} must be a numeric percentage.",
                field=field,
            )

        try:
            value = float(raw_value)
        except (OverflowError, ValueError) as exc:
            raise ScenarioValidationError(
                "INVALID_SCENARIO_ADJUSTMENT",
                f"{field} must be a finite numeric percentage.",
                field=field,
            ) from exc
        if not math.isfinite(value):
            raise ScenarioValidationError(
                "INVALID_SCENARIO_ADJUSTMENT",
                f"{field} must be finite.",
                field=field,
            )
        if value < MIN_SCENARIO_ADJUSTMENT_PCT or value > MAX_SCENARIO_ADJUSTMENT_PCT:
            raise ScenarioValidationError(
                "INVALID_SCENARIO_ADJUSTMENT",
                f"{field} must be between -100 and 500 percent.",
                field=field,
            )
        validated_values[field] = value

    return ScenarioAdjustments(**validated_values)


def build_what_if_simulation(
    baseline_forecast: ForecastSummary,
    adjustments: ScenarioAdjustments,
) -> WhatIfSimulationResponse:
    warnings = list(baseline_forecast.warnings)
    periods: list[SimulationPeriod] = []

    for baseline_period in baseline_forecast.periods:
        scenario_revenue = _adjust(
            baseline_period.revenue.value,
            adjustments.revenue_pct,
        )
        scenario_cogs = _adjust(
            baseline_period.cogs.value,
            adjustments.cogs_pct,
        )
        scenario_operating_expenses = _adjust(
            baseline_period.operating_expenses.value,
            adjustments.operating_expenses_pct,
        )
        scenario_gross_profit = _round(scenario_revenue - scenario_cogs)
        scenario_operating_profit = _round(
            scenario_gross_profit - scenario_operating_expenses
        )

        if scenario_revenue == 0:
            scenario_gross_margin_pct = None
            scenario_operating_margin_pct = None
            warnings.append(
                f"Scenario margins are undefined for {baseline_period.period} because "
                "scenario revenue is zero."
            )
        else:
            scenario_gross_margin_pct = _round(
                scenario_gross_profit / scenario_revenue * 100
            )
            scenario_operating_margin_pct = _round(
                scenario_operating_profit / scenario_revenue * 100
            )

        scenario_metrics = ScenarioMetrics(
            revenue=scenario_revenue,
            cogs=scenario_cogs,
            operating_expenses=scenario_operating_expenses,
            gross_profit=scenario_gross_profit,
            operating_profit=scenario_operating_profit,
            gross_margin_pct=scenario_gross_margin_pct,
            operating_margin_pct=scenario_operating_margin_pct,
        )
        difference = ScenarioDifference(
            revenue_difference=_round(
                scenario_revenue - baseline_period.revenue.value
            ),
            cogs_difference=_round(scenario_cogs - baseline_period.cogs.value),
            operating_expenses_difference=_round(
                scenario_operating_expenses
                - baseline_period.operating_expenses.value
            ),
            gross_profit_difference=_round(
                scenario_gross_profit - baseline_period.gross_profit
            ),
            operating_profit_difference=_round(
                scenario_operating_profit - baseline_period.operating_profit
            ),
            gross_margin_difference_pp=_margin_difference(
                scenario_gross_margin_pct,
                baseline_period.gross_margin_pct,
            ),
            operating_margin_difference_pp=_margin_difference(
                scenario_operating_margin_pct,
                baseline_period.operating_margin_pct,
            ),
        )
        periods.append(
            SimulationPeriod(
                period=baseline_period.period,
                baseline=BaselineSimulationMetrics(
                    revenue=baseline_period.revenue,
                    cogs=baseline_period.cogs,
                    operating_expenses=baseline_period.operating_expenses,
                    gross_profit=baseline_period.gross_profit,
                    operating_profit=baseline_period.operating_profit,
                    operating_profit_component_range=(
                        baseline_period.operating_profit_component_range
                    ),
                    gross_margin_pct=baseline_period.gross_margin_pct,
                    operating_margin_pct=baseline_period.operating_margin_pct,
                ),
                scenario=scenario_metrics,
                difference=difference,
            )
        )

    summary = _build_summary(periods)
    return WhatIfSimulationResponse(
        scenario=adjustments,
        baseline_forecast_models=baseline_forecast.models,
        periods=periods,
        summary=summary,
        scenario_evidence=_build_scenario_evidence(periods, summary),
        assumptions=_build_assumptions(adjustments),
        limitations=[
            "This is a deterministic what-if scenario based on the baseline forecast, not a causal prediction or guarantee of business outcomes.",
            "Scenario results inherit uncertainty from the baseline forecast.",
            "Empirical MAE ranges are preserved only for baseline metrics; no scenario confidence intervals are produced.",
            *baseline_forecast.limitations,
        ],
        warnings=warnings,
    )


def _build_summary(periods: list[SimulationPeriod]) -> SimulationSummary:
    final_period = periods[-1]
    baseline_total = _round(
        sum(period.baseline.operating_profit for period in periods)
    )
    scenario_total = _round(
        sum(period.scenario.operating_profit for period in periods)
    )
    return SimulationSummary(
        final_period=final_period.period,
        baseline_final_operating_profit=final_period.baseline.operating_profit,
        scenario_final_operating_profit=final_period.scenario.operating_profit,
        final_operating_profit_difference=(
            final_period.difference.operating_profit_difference
        ),
        baseline_final_operating_margin_pct=(
            final_period.baseline.operating_margin_pct
        ),
        scenario_final_operating_margin_pct=(
            final_period.scenario.operating_margin_pct
        ),
        final_operating_margin_difference_pp=(
            final_period.difference.operating_margin_difference_pp
        ),
        baseline_3_month_operating_profit_total=baseline_total,
        scenario_3_month_operating_profit_total=scenario_total,
        three_month_operating_profit_difference=_round(
            scenario_total - baseline_total
        ),
    )


def _build_scenario_evidence(
    periods: list[SimulationPeriod],
    summary: SimulationSummary,
) -> list[ScenarioEvidenceItem]:
    final_period = periods[-1]
    difference = summary.final_operating_profit_difference
    if difference > 0:
        difference_statement = (
            f"Under this scenario, projected operating profit is {difference:.2f} "
            f"financial units higher than the baseline forecast for {final_period.period}."
        )
    elif difference < 0:
        difference_statement = (
            f"Under this scenario, projected operating profit is {abs(difference):.2f} "
            f"financial units lower than the baseline forecast for {final_period.period}."
        )
    else:
        difference_statement = (
            f"Under this scenario, projected operating profit equals the baseline "
            f"forecast for {final_period.period}."
        )

    evidence = [
        ScenarioEvidenceItem(
            id="SE1",
            type="scenario_operating_profit",
            period=final_period.period,
            value=summary.scenario_final_operating_profit,
            unit="financial_units",
            statement=(
                f"Under this scenario, operating profit is projected at "
                f"{summary.scenario_final_operating_profit:.2f} financial units for "
                f"{final_period.period}."
            ),
        ),
        ScenarioEvidenceItem(
            id="SE2",
            type="scenario_operating_profit_difference",
            period=final_period.period,
            value=difference,
            unit="financial_units",
            statement=difference_statement,
        ),
    ]

    if summary.scenario_final_operating_margin_pct is not None:
        evidence.append(
            ScenarioEvidenceItem(
                id="SE3",
                type="scenario_operating_margin",
                period=final_period.period,
                value=summary.scenario_final_operating_margin_pct,
                unit="percent",
                statement=(
                    f"Under this scenario, operating margin is projected at "
                    f"{summary.scenario_final_operating_margin_pct:.2f} percent for "
                    f"{final_period.period}."
                ),
            )
        )

    evidence.append(
        ScenarioEvidenceItem(
            id="SE4",
            type="scenario_cumulative_operating_profit_difference",
            period=final_period.period,
            value=summary.three_month_operating_profit_difference,
            unit="financial_units",
            statement=(
                f"Under this scenario, cumulative projected operating profit is "
                f"{summary.three_month_operating_profit_difference:.2f} financial units "
                "different from baseline across the three forecast months."
            ),
        )
    )
    return evidence


def _build_assumptions(adjustments: ScenarioAdjustments) -> list[str]:
    assumptions: list[str] = []
    for field in SCENARIO_FIELDS:
        label = SCENARIO_LABELS[field]
        unchanged_verb, adjusted_verb = SCENARIO_VERBS[field]
        adjustment = float(getattr(adjustments, field))
        if adjustment == 0:
            assumptions.append(
                f"{label} {unchanged_verb} at its baseline forecast value."
            )
        else:
            assumptions.append(
                f"{label} {adjusted_verb} adjusted by {adjustment:+.2f}% relative to each baseline "
                "forecast period."
            )
    assumptions.append("No causal relationship between scenario adjustments is modeled.")
    return assumptions


def _adjust(baseline_value: float, adjustment_pct: float) -> float:
    baseline = Decimal(str(baseline_value))
    adjustment = Decimal(str(adjustment_pct))
    return _round_decimal(baseline * (Decimal("1") + adjustment / ONE_HUNDRED))


def _margin_difference(
    scenario_margin: float | None,
    baseline_margin: float | None,
) -> float | None:
    if scenario_margin is None or baseline_margin is None:
        return None
    return _round(scenario_margin - baseline_margin)


def _round(value: float) -> float:
    return _round_decimal(Decimal(str(value)))


def _round_decimal(value: Decimal) -> float:
    rounded = value.quantize(TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    return float(abs(rounded) if rounded == 0 else rounded)
