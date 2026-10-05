from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.forecasting import BaseMetricForecast, ForecastModels, ForecastRange

MIN_SCENARIO_ADJUSTMENT_PCT = -100.0
MAX_SCENARIO_ADJUSTMENT_PCT = 500.0


class ScenarioAdjustments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue_pct: float = Field(
        default=0.0,
        ge=MIN_SCENARIO_ADJUSTMENT_PCT,
        le=MAX_SCENARIO_ADJUSTMENT_PCT,
        allow_inf_nan=False,
    )
    cogs_pct: float = Field(
        default=0.0,
        ge=MIN_SCENARIO_ADJUSTMENT_PCT,
        le=MAX_SCENARIO_ADJUSTMENT_PCT,
        allow_inf_nan=False,
    )
    operating_expenses_pct: float = Field(
        default=0.0,
        ge=MIN_SCENARIO_ADJUSTMENT_PCT,
        le=MAX_SCENARIO_ADJUSTMENT_PCT,
        allow_inf_nan=False,
    )


class BaselineSimulationMetrics(BaseModel):
    revenue: BaseMetricForecast
    cogs: BaseMetricForecast
    operating_expenses: BaseMetricForecast
    gross_profit: float
    operating_profit: float
    operating_profit_component_range: ForecastRange
    gross_margin_pct: float | None
    operating_margin_pct: float | None


class ScenarioMetrics(BaseModel):
    revenue: float
    cogs: float
    operating_expenses: float
    gross_profit: float
    operating_profit: float
    gross_margin_pct: float | None
    operating_margin_pct: float | None


class ScenarioDifference(BaseModel):
    revenue_difference: float
    cogs_difference: float
    operating_expenses_difference: float
    gross_profit_difference: float
    operating_profit_difference: float
    gross_margin_difference_pp: float | None
    operating_margin_difference_pp: float | None


class SimulationPeriod(BaseModel):
    period: str
    baseline: BaselineSimulationMetrics
    scenario: ScenarioMetrics
    difference: ScenarioDifference


class SimulationSummary(BaseModel):
    final_period: str
    baseline_final_operating_profit: float
    scenario_final_operating_profit: float
    final_operating_profit_difference: float
    baseline_final_operating_margin_pct: float | None
    scenario_final_operating_margin_pct: float | None
    final_operating_margin_difference_pp: float | None
    baseline_3_month_operating_profit_total: float
    scenario_3_month_operating_profit_total: float
    three_month_operating_profit_difference: float


class ScenarioEvidenceItem(BaseModel):
    id: str
    type: Literal[
        "scenario_operating_profit",
        "scenario_operating_profit_difference",
        "scenario_operating_margin",
        "scenario_cumulative_operating_profit_difference",
    ]
    period: str
    value: float
    unit: Literal["financial_units", "percent", "percentage_points"]
    statement: str


class WhatIfSimulationResponse(BaseModel):
    status: Literal["ok"] = "ok"
    scenario: ScenarioAdjustments
    forecast_horizon_months: Literal[3] = 3
    baseline_forecast_models: ForecastModels
    periods: list[SimulationPeriod]
    summary: SimulationSummary
    scenario_evidence: list[ScenarioEvidenceItem]
    assumptions: list[str]
    limitations: list[str]
    warnings: list[str] = Field(default_factory=list)

