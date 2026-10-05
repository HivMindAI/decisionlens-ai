from __future__ import annotations

import json
import re
from collections.abc import Iterable

from pydantic import ValidationError

from app.models.analytics import (
    AnalysisSummaryResponse,
    BusinessSignal,
    EvidenceItem,
    StatisticalAnomaly,
)
from app.models.decisions import (
    DecisionBrief,
    DecisionBriefResponse,
    DecisionContext,
    DecisionFocus,
    DecisionGenerationMetadata,
    GeneratedDecisionBrief,
    NextStepAction,
)
from app.services.llm_provider import (
    ProviderFailure,
    ProviderSetup,
    provider_setup_from_environment,
)

ACTION_TEXT: dict[NextStepAction, str] = {
    NextStepAction.REVIEW_OPERATING_EXPENSES: (
        "Review controllable operating expenses and use the simulator to test potential reductions."
    ),
    NextStepAction.REVIEW_COGS: (
        "Review the components of COGS and use the simulator to test potential changes."
    ),
    NextStepAction.INVESTIGATE_REVENUE_DECLINE: (
        "Investigate the recent revenue decline before assuming the historical forecast will continue."
    ),
    NextStepAction.MONITOR_MARGIN_PRESSURE: (
        "Monitor operating-margin pressure and review the verified cost and revenue evidence."
    ),
    NextStepAction.REVIEW_PROFITABILITY: (
        "Review the verified drivers of operating profitability and test explicit assumptions in the simulator."
    ),
    NextStepAction.REVIEW_FORECAST_RISK: (
        "Review the forecast diagnostics and treat projected profitability as uncertain."
    ),
    NextStepAction.NO_URGENT_ACTION: (
        "Continue monitoring the verified metrics and reassess when new monthly data is available."
    ),
}

DECISION_LIMITATIONS = (
    "This brief is decision support, not professional financial advice.",
    "Historical patterns and forecasts do not guarantee future outcomes.",
    "Evidence reflects only the validated financial fields in the uploaded dataset.",
    "Next steps are constrained by the available evidence and do not assert causality.",
)

ACTION_EVIDENCE_METRICS: dict[NextStepAction, set[str]] = {
    NextStepAction.REVIEW_OPERATING_EXPENSES: {
        "operating_expenses",
        "operating_expenses_impact",
    },
    NextStepAction.REVIEW_COGS: {"cogs", "cogs_impact"},
    NextStepAction.INVESTIGATE_REVENUE_DECLINE: {"revenue"},
    NextStepAction.MONITOR_MARGIN_PRESSURE: {
        "operating_margin_pct",
        "projected_operating_margin_pct",
    },
    NextStepAction.REVIEW_PROFITABILITY: {
        "operating_profit",
        "projected_operating_profit",
        "operating_margin_pct",
        "projected_operating_margin_pct",
    },
}

EVIDENCE_ID_PATTERN = re.compile(r"\bE\d+\b", re.IGNORECASE)
NUMBER_WORD_PATTERN = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|"
    r"billion|first|second|third|half|quarter)\b",
    re.IGNORECASE,
)


class GeneratedBriefInvalid(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_decision_context(analysis: AnalysisSummaryResponse) -> DecisionContext:
    """Project analytics onto an allowlist that contains no uploaded rows or extra columns."""
    return DecisionContext(
        evidence=analysis.evidence,
        signals=analysis.signals,
        anomalies=analysis.anomalies,
        forecast_models=analysis.forecast.models,
        analysis_warnings=analysis.warnings,
        forecast_warnings=analysis.forecast.warnings,
        forecast_limitations=analysis.forecast.limitations,
    )


async def generate_decision_brief(
    analysis: AnalysisSummaryResponse,
    *,
    provider_setup: ProviderSetup | None = None,
) -> DecisionBriefResponse:
    context = build_decision_context(analysis)
    setup = provider_setup or provider_setup_from_environment()

    if setup.provider is None:
        return _fallback_response(
            analysis,
            reason=setup.fallback_reason or "llm_not_configured",
            provider=setup.provider_name,
            model=setup.model,
        )

    try:
        content = await setup.provider.generate(context)
    except ProviderFailure as exc:
        return _fallback_response(
            analysis,
            reason=exc.code,
            provider=setup.provider_name or setup.provider.name,
            model=setup.model or setup.provider.model,
        )
    except Exception:
        return _fallback_response(
            analysis,
            reason="provider_unavailable",
            provider=setup.provider_name or setup.provider.name,
            model=setup.model or setup.provider.model,
        )

    try:
        generated = _validate_provider_content(content, context)
    except GeneratedBriefInvalid as exc:
        return _fallback_response(
            analysis,
            reason=exc.code,
            provider=setup.provider_name or setup.provider.name,
            model=setup.model or setup.provider.model,
        )

    brief = _attach_action_text(generated)
    return DecisionBriefResponse(
        decision_brief=brief,
        generation=DecisionGenerationMetadata(
            mode="llm",
            ai_used=True,
            provider=setup.provider_name or setup.provider.name,
            model=setup.model or setup.provider.model,
        ),
        supporting_evidence=_supporting_evidence(
            context.evidence,
            brief.evidence_ids,
        ),
        limitations=list(DECISION_LIMITATIONS),
    )


def _validate_provider_content(
    content: str,
    context: DecisionContext,
) -> GeneratedDecisionBrief:
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        raise GeneratedBriefInvalid("malformed_provider_json") from None

    if not isinstance(payload, dict):
        raise GeneratedBriefInvalid("invalid_provider_output")

    try:
        generated = GeneratedDecisionBrief.model_validate(payload)
    except ValidationError:
        raise GeneratedBriefInvalid("invalid_provider_output") from None

    if _contains_numeric_claim(generated.headline) or _contains_numeric_claim(
        generated.reasoning
    ):
        raise GeneratedBriefInvalid("unsupported_numeric_narrative")

    evidence_by_id = {item.id: item for item in context.evidence}
    if any(evidence_id not in evidence_by_id for evidence_id in generated.evidence_ids):
        raise GeneratedBriefInvalid("unknown_evidence_id")

    selected_evidence = [evidence_by_id[item] for item in generated.evidence_ids]
    if not _action_matches_evidence(generated.next_step, selected_evidence):
        raise GeneratedBriefInvalid("action_evidence_mismatch")

    return generated


def _contains_numeric_claim(text: str) -> bool:
    without_evidence_ids = EVIDENCE_ID_PATTERN.sub("", text)
    return bool(
        re.search(r"[\d%$€£¥]", without_evidence_ids)
        or NUMBER_WORD_PATTERN.search(without_evidence_ids)
    )


def _action_matches_evidence(
    action: NextStepAction,
    evidence: list[EvidenceItem],
) -> bool:
    if action == NextStepAction.NO_URGENT_ACTION:
        return True
    if action == NextStepAction.REVIEW_FORECAST_RISK:
        return any(item.type == "forecast" for item in evidence)
    allowed_metrics = ACTION_EVIDENCE_METRICS.get(action, set())
    return any(item.metric in allowed_metrics for item in evidence)


def _fallback_response(
    analysis: AnalysisSummaryResponse,
    *,
    reason: str,
    provider: str | None,
    model: str | None,
) -> DecisionBriefResponse:
    generated = _deterministic_fallback(analysis)
    brief = _attach_action_text(generated)
    return DecisionBriefResponse(
        decision_brief=brief,
        generation=DecisionGenerationMetadata(
            mode="deterministic_fallback",
            ai_used=False,
            provider=provider,
            model=model,
            fallback_reason=reason,
        ),
        supporting_evidence=_supporting_evidence(
            analysis.evidence,
            brief.evidence_ids,
        ),
        limitations=list(DECISION_LIMITATIONS),
    )


def _deterministic_fallback(
    analysis: AnalysisSummaryResponse,
) -> GeneratedDecisionBrief:
    available_ids = {item.id for item in analysis.evidence}
    deterioration = _first_signal(analysis.signals, "PROFIT_DETERIORATION")

    if deterioration and deterioration.classification == "positive_to_loss":
        return _fallback_brief(
            focus=DecisionFocus.PROFITABILITY,
            headline="Operating profitability needs immediate review",
            reasoning=(
                "A transition from operating profit to loss makes profitability the "
                "clearest issue for review."
            ),
            evidence_ids=_available(["E3", "E1", "E2"], available_ids),
            next_step=NextStepAction.REVIEW_PROFITABILITY,
        )

    contributor = analysis.profit_change_decomposition.largest_measured_contributor.metric
    cost_signals = [
        signal
        for signal in analysis.signals
        if signal.type == "COST_GROWTH_OUTPACING_REVENUE"
    ]
    matching_cost_signal = next(
        (signal for signal in cost_signals if contributor in signal.metrics),
        None,
    )
    if matching_cost_signal is not None and contributor == "operating_expenses":
        return _cost_fallback(
            matching_cost_signal,
            available_ids,
            metric="operating_expenses",
        )
    if matching_cost_signal is not None and contributor == "cogs":
        return _cost_fallback(
            matching_cost_signal,
            available_ids,
            metric="cogs",
        )

    revenue_decline = _first_signal(analysis.signals, "REVENUE_DECLINE")
    if revenue_decline is not None and contributor == "revenue":
        return _revenue_fallback(revenue_decline, available_ids)

    if deterioration is not None:
        return _fallback_brief(
            focus=DecisionFocus.PROFITABILITY,
            headline="Operating profitability deserves attention",
            reasoning=(
                "Verified evidence shows profitability deterioration, making its measured "
                "drivers the most relevant focus."
            ),
            evidence_ids=_available(["E3", "E1", "E2"], available_ids),
            next_step=NextStepAction.REVIEW_PROFITABILITY,
        )

    if cost_signals:
        strongest_cost_signal = max(
            cost_signals,
            key=lambda item: (_severity_rank(item.severity), abs(item.measured_change)),
        )
        metric = (
            "operating_expenses"
            if "operating_expenses" in strongest_cost_signal.metrics
            else "cogs"
        )
        return _cost_fallback(strongest_cost_signal, available_ids, metric=metric)

    if revenue_decline is not None:
        return _revenue_fallback(revenue_decline, available_ids)

    margin_compression = _first_signal(analysis.signals, "MARGIN_COMPRESSION")
    if margin_compression is not None:
        return _fallback_brief(
            focus=DecisionFocus.MARGIN_PRESSURE,
            headline="Operating margin pressure deserves monitoring",
            reasoning=(
                "The verified margin signal indicates deterioration that should be tracked "
                "alongside its measured cost and revenue drivers."
            ),
            evidence_ids=_available([*margin_compression.evidence_ids, "E3"], available_ids),
            next_step=NextStepAction.MONITOR_MARGIN_PRESSURE,
        )

    anomaly_brief = _fallback_from_anomalies(analysis.anomalies, available_ids)
    if anomaly_brief is not None:
        return anomaly_brief

    final_forecast = analysis.forecast.periods[-1]
    if final_forecast.operating_profit <= 0:
        return _fallback_brief(
            focus=DecisionFocus.FORECAST_RISK,
            headline="Forecast profitability warrants review",
            reasoning=(
                "The selected forecast indicates profitability risk and should be considered "
                "with its backtest diagnostics and limitations."
            ),
            evidence_ids=_available(["E9", "E10", "E8"], available_ids),
            next_step=NextStepAction.REVIEW_FORECAST_RISK,
        )

    return _fallback_brief(
        focus=DecisionFocus.STABLE_OUTLOOK,
        headline="No urgent issue is evident in the verified signals",
        reasoning=(
            "The verified signals do not identify a material deterioration requiring "
            "immediate escalation, so continued monitoring is appropriate."
        ),
        evidence_ids=_available(["E1", "E9"], available_ids),
        next_step=NextStepAction.NO_URGENT_ACTION,
    )


def _cost_fallback(
    signal: BusinessSignal,
    available_ids: set[str],
    *,
    metric: str,
) -> GeneratedDecisionBrief:
    if metric == "operating_expenses":
        return _fallback_brief(
            focus=DecisionFocus.COST_CONTROL,
            headline="Operating-expense pressure is the clearest focus",
            reasoning=(
                "Verified cost and profitability evidence identifies operating expenses as "
                "the most relevant controllable area to review."
            ),
            evidence_ids=_available(
                [*signal.evidence_ids, "E7", "E3"],
                available_ids,
            ),
            next_step=NextStepAction.REVIEW_OPERATING_EXPENSES,
        )
    return _fallback_brief(
        focus=DecisionFocus.COST_CONTROL,
        headline="COGS pressure is the clearest focus",
        reasoning=(
            "Verified cost and profitability evidence identifies COGS as the most relevant "
            "cost area to review."
        ),
        evidence_ids=_available([*signal.evidence_ids, "E7", "E3"], available_ids),
        next_step=NextStepAction.REVIEW_COGS,
    )


def _revenue_fallback(
    signal: BusinessSignal,
    available_ids: set[str],
) -> GeneratedDecisionBrief:
    return _fallback_brief(
        focus=DecisionFocus.REVENUE_ATTENTION,
        headline="Recent revenue deterioration deserves investigation",
        reasoning=(
            "Verified revenue evidence shows deterioration that is the clearest measured "
            "driver requiring attention."
        ),
        evidence_ids=_available([*signal.evidence_ids, "E7", "E3"], available_ids),
        next_step=NextStepAction.INVESTIGATE_REVENUE_DECLINE,
    )


def _fallback_from_anomalies(
    anomalies: list[StatisticalAnomaly],
    available_ids: set[str],
) -> GeneratedDecisionBrief | None:
    ordered = sorted(
        anomalies,
        key=lambda item: (_severity_rank(item.severity), abs(item.robust_z)),
        reverse=True,
    )
    for anomaly in ordered:
        if anomaly.metric == "operating_expenses" and anomaly.direction == "increase":
            return _fallback_brief(
                focus=DecisionFocus.COST_CONTROL,
                headline="Operating-expense movement warrants review",
                reasoning=(
                    "The verified anomaly indicates unusual operating-expense pressure "
                    "relative to the historical pattern."
                ),
                evidence_ids=_available(["E6", "E7"], available_ids),
                next_step=NextStepAction.REVIEW_OPERATING_EXPENSES,
            )
        if anomaly.metric == "cogs" and anomaly.direction == "increase":
            return _fallback_brief(
                focus=DecisionFocus.COST_CONTROL,
                headline="COGS movement warrants review",
                reasoning=(
                    "The verified anomaly indicates unusual COGS pressure relative to the "
                    "historical pattern."
                ),
                evidence_ids=_available(["E5", "E7"], available_ids),
                next_step=NextStepAction.REVIEW_COGS,
            )
        if anomaly.metric == "revenue" and anomaly.direction == "decrease":
            return _fallback_brief(
                focus=DecisionFocus.REVENUE_ATTENTION,
                headline="Revenue movement warrants investigation",
                reasoning=(
                    "The verified anomaly indicates unusual revenue deterioration relative "
                    "to the historical pattern."
                ),
                evidence_ids=_available(["E4", "E7"], available_ids),
                next_step=NextStepAction.INVESTIGATE_REVENUE_DECLINE,
            )
        if anomaly.metric == "operating_profit" and anomaly.direction == "decrease":
            return _fallback_brief(
                focus=DecisionFocus.PROFITABILITY,
                headline="Operating-profit movement warrants review",
                reasoning=(
                    "The verified anomaly indicates unusual profitability deterioration "
                    "relative to the historical pattern."
                ),
                evidence_ids=_available(["E3", "E1"], available_ids),
                next_step=NextStepAction.REVIEW_PROFITABILITY,
            )
    return None


def _fallback_brief(
    *,
    focus: DecisionFocus,
    headline: str,
    reasoning: str,
    evidence_ids: list[str],
    next_step: NextStepAction,
) -> GeneratedDecisionBrief:
    return GeneratedDecisionBrief(
        focus=focus,
        headline=headline,
        reasoning=reasoning,
        evidence_ids=evidence_ids[:5],
        next_step=next_step,
    )


def _available(requested: Iterable[str], available_ids: set[str]) -> list[str]:
    selected: list[str] = []
    for evidence_id in requested:
        if evidence_id in available_ids and evidence_id not in selected:
            selected.append(evidence_id)
    return selected[:5]


def _first_signal(
    signals: list[BusinessSignal],
    signal_type: str,
) -> BusinessSignal | None:
    return next((signal for signal in signals if signal.type == signal_type), None)


def _severity_rank(severity: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}[severity]


def _attach_action_text(generated: GeneratedDecisionBrief) -> DecisionBrief:
    return DecisionBrief(
        **generated.model_dump(),
        next_step_text=ACTION_TEXT[generated.next_step],
    )


def _supporting_evidence(
    evidence: list[EvidenceItem],
    evidence_ids: list[str],
) -> list[EvidenceItem]:
    evidence_by_id = {item.id: item for item in evidence}
    return [evidence_by_id[evidence_id] for evidence_id in evidence_ids]
