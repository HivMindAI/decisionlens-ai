from typing import Literal

from pydantic import BaseModel, Field

ChangeUnit = Literal["financial_units", "percentage_points"]
EvidenceUnit = Literal["financial_units", "percent", "percentage_points"]
Direction = Literal[
    "increase",
    "decrease",
    "unchanged",
    "undefined",
    "not_applicable",
]
Severity = Literal["low", "medium", "high"]


class MonthlyKPI(BaseModel):
    period: str
    revenue: float
    cogs: float
    operating_expenses: float
    gross_profit: float
    operating_profit: float
    gross_margin_pct: float | None
    operating_margin_pct: float | None


class MetricChange(BaseModel):
    value: float | None
    previous_value: float | None
    absolute_change: float | None
    percent_change: float | None
    unit: ChangeUnit


class AnalysisChanges(BaseModel):
    revenue: MetricChange
    cogs: MetricChange
    operating_expenses: MetricChange
    gross_profit: MetricChange
    operating_profit: MetricChange
    gross_margin_pct: MetricChange
    operating_margin_pct: MetricChange


class LargestMeasuredContributor(BaseModel):
    metric: Literal["revenue", "cogs", "operating_expenses"]
    impact: float
    unit: Literal["financial_units"] = "financial_units"


class ProfitChangeDecomposition(BaseModel):
    period: str
    comparison_period: str
    delta_operating_profit: float
    revenue_impact: float
    cogs_impact: float
    operating_expenses_impact: float
    largest_measured_contributor: LargestMeasuredContributor


class EvidenceItem(BaseModel):
    id: str
    type: Literal["snapshot", "comparison", "decomposition"]
    metric: str
    period: str
    comparison_period: str | None = None
    value: float | None
    previous_value: float | None = None
    change: float | None = None
    unit: EvidenceUnit
    direction: Direction
    statement: str


class StatisticalAnomaly(BaseModel):
    id: str
    metric: Literal["revenue", "cogs", "operating_expenses", "operating_profit"]
    period: str
    comparison_period: str
    direction: Literal["increase", "decrease"]
    observed_change: float
    change_unit: Literal["percent", "financial_units"]
    historical_median_change: float
    historical_observation_count: int
    robust_z: float
    severity: Severity
    statement: str


class BusinessSignal(BaseModel):
    id: str
    type: Literal[
        "MARGIN_COMPRESSION",
        "COST_GROWTH_OUTPACING_REVENUE",
        "PROFIT_DETERIORATION",
        "PROFIT_RECOVERY",
        "REVENUE_DECLINE",
    ]
    severity: Severity
    period: str
    comparison_period: str
    metrics: list[str]
    measured_change: float
    change_unit: Literal["financial_units", "percent", "percentage_points"]
    classification: Literal[
        "profit_declined",
        "positive_to_loss",
        "loss_deepened",
        "profit_increased",
        "loss_to_positive",
        "loss_narrowed",
    ] | None = None
    statement: str
    evidence_ids: list[str]


class AnalysisSummaryResponse(BaseModel):
    status: Literal["ok"] = "ok"
    period_start: str
    period_end: str
    latest_period: str
    previous_period: str
    latest_snapshot: MonthlyKPI
    changes: AnalysisChanges
    profit_change_decomposition: ProfitChangeDecomposition
    evidence: list[EvidenceItem]
    anomalies: list[StatisticalAnomaly]
    signals: list[BusinessSignal]
    series: list[MonthlyKPI]
    warnings: list[str] = Field(default_factory=list)
