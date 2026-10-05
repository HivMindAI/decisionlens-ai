from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.analytics import BusinessSignal, EvidenceItem, StatisticalAnomaly
from app.models.forecasting import ForecastModels


class DecisionFocus(str, Enum):
    COST_CONTROL = "cost_control"
    REVENUE_ATTENTION = "revenue_attention"
    MARGIN_PRESSURE = "margin_pressure"
    PROFITABILITY = "profitability"
    FORECAST_RISK = "forecast_risk"
    STABLE_OUTLOOK = "stable_outlook"


class NextStepAction(str, Enum):
    REVIEW_OPERATING_EXPENSES = "REVIEW_OPERATING_EXPENSES"
    REVIEW_COGS = "REVIEW_COGS"
    INVESTIGATE_REVENUE_DECLINE = "INVESTIGATE_REVENUE_DECLINE"
    MONITOR_MARGIN_PRESSURE = "MONITOR_MARGIN_PRESSURE"
    REVIEW_PROFITABILITY = "REVIEW_PROFITABILITY"
    REVIEW_FORECAST_RISK = "REVIEW_FORECAST_RISK"
    NO_URGENT_ACTION = "NO_URGENT_ACTION"


class GeneratedDecisionBrief(BaseModel):
    """Strict provider output before application-owned text is attached."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    focus: DecisionFocus
    headline: str = Field(min_length=5, max_length=120)
    reasoning: str = Field(min_length=10, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)
    next_step: NextStepAction

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must not contain duplicates")
        return value


class DecisionBrief(GeneratedDecisionBrief):
    next_step_text: str


class DecisionContext(BaseModel):
    """Allowlisted deterministic facts that may be sent to a provider."""

    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceItem]
    signals: list[BusinessSignal]
    anomalies: list[StatisticalAnomaly]
    forecast_models: ForecastModels
    analysis_warnings: list[str] = Field(default_factory=list)
    forecast_warnings: list[str] = Field(default_factory=list)
    forecast_limitations: list[str] = Field(default_factory=list)


class DecisionGenerationMetadata(BaseModel):
    mode: Literal["llm", "deterministic_fallback"]
    ai_used: bool
    provider: str | None = None
    model: str | None = None
    fallback_reason: str | None = None


class DecisionBriefResponse(BaseModel):
    status: Literal["ok"] = "ok"
    decision_brief: DecisionBrief
    generation: DecisionGenerationMetadata
    supporting_evidence: list[EvidenceItem]
    limitations: list[str] = Field(default_factory=list)
