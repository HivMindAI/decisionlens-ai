from typing import Literal

from pydantic import BaseModel, Field

ForecastModelName = Literal[
    "NAIVE_LAST_VALUE",
    "LINEAR_TREND",
    "SEASONAL_NAIVE",
]


class ForecastModelDiagnostics(BaseModel):
    selected_model: ForecastModelName
    backtest_points: int
    mae: float
    normalized_mae_pct: float | None


class ForecastModels(BaseModel):
    revenue: ForecastModelDiagnostics
    cogs: ForecastModelDiagnostics
    operating_expenses: ForecastModelDiagnostics


class ForecastRange(BaseModel):
    low: float
    high: float


class BaseMetricForecast(BaseModel):
    value: float
    backtest_mae_range: ForecastRange


class ForecastPeriod(BaseModel):
    period: str
    revenue: BaseMetricForecast
    cogs: BaseMetricForecast
    operating_expenses: BaseMetricForecast
    gross_profit: float
    operating_profit: float
    operating_profit_component_range: ForecastRange
    gross_margin_pct: float | None
    operating_margin_pct: float | None


class ForecastSummary(BaseModel):
    horizon_months: Literal[3] = 3
    models: ForecastModels
    periods: list[ForecastPeriod]
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

