from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from app.models.analytics import (
    AnalysisChanges,
    AnalysisSummaryResponse,
    EvidenceItem,
    LargestMeasuredContributor,
    MetricChange,
    MonthlyKPI,
    ProfitChangeDecomposition,
)

TWO_DECIMAL_PLACES = Decimal("0.01")
ONE_HUNDRED = Decimal("100")


def build_analysis_summary(frame: pd.DataFrame) -> AnalysisSummaryResponse:
    """Calculate deterministic KPIs and evidence from validated monthly data."""
    warnings: list[str] = []
    series = _calculate_monthly_series(frame, warnings)
    previous = series[-2]
    latest = series[-1]
    changes = _calculate_changes(latest, previous, warnings)
    decomposition = _decompose_operating_profit_change(latest, previous)
    evidence = _build_evidence(latest, previous, changes, decomposition)

    return AnalysisSummaryResponse(
        period_start=series[0].period,
        period_end=latest.period,
        latest_period=latest.period,
        previous_period=previous.period,
        latest_snapshot=latest,
        changes=changes,
        profit_change_decomposition=decomposition,
        evidence=evidence,
        series=series,
        warnings=warnings,
    )


def _calculate_monthly_series(
    frame: pd.DataFrame,
    warnings: list[str],
) -> list[MonthlyKPI]:
    series: list[MonthlyKPI] = []

    for _, row in frame.iterrows():
        period = str(row["_period"])
        revenue_raw = _decimal(row["revenue"])
        cogs_raw = _decimal(row["cogs"])
        operating_expenses_raw = _decimal(row["operating_expenses"])
        gross_profit_raw = revenue_raw - cogs_raw
        operating_profit_raw = gross_profit_raw - operating_expenses_raw

        revenue = _round_decimal(revenue_raw)
        cogs = _round_decimal(cogs_raw)
        operating_expenses = _round_decimal(operating_expenses_raw)
        gross_profit = _round_decimal(revenue - cogs)
        operating_profit = _round_decimal(gross_profit - operating_expenses)

        if revenue_raw == 0:
            gross_margin_pct = None
            operating_margin_pct = None
            warnings.append(
                f"Gross and operating margins are undefined for {period} because revenue is zero."
            )
        else:
            gross_margin_pct = _round_decimal(
                gross_profit_raw / revenue_raw * ONE_HUNDRED
            )
            operating_margin_pct = _round_decimal(
                operating_profit_raw / revenue_raw * ONE_HUNDRED
            )

        series.append(
            MonthlyKPI(
                period=period,
                revenue=float(revenue),
                cogs=float(cogs),
                operating_expenses=float(operating_expenses),
                gross_profit=float(gross_profit),
                operating_profit=float(operating_profit),
                gross_margin_pct=(
                    float(gross_margin_pct) if gross_margin_pct is not None else None
                ),
                operating_margin_pct=(
                    float(operating_margin_pct)
                    if operating_margin_pct is not None
                    else None
                ),
            )
        )

    return series


def _calculate_changes(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
    warnings: list[str],
) -> AnalysisChanges:
    return AnalysisChanges(
        revenue=_financial_change(
            "revenue", latest.revenue, previous.revenue, warnings
        ),
        cogs=_financial_change("cogs", latest.cogs, previous.cogs, warnings),
        operating_expenses=_financial_change(
            "operating_expenses",
            latest.operating_expenses,
            previous.operating_expenses,
            warnings,
        ),
        gross_profit=_financial_change(
            "gross_profit",
            latest.gross_profit,
            previous.gross_profit,
            warnings,
            require_positive_baseline=True,
        ),
        operating_profit=_financial_change(
            "operating_profit",
            latest.operating_profit,
            previous.operating_profit,
            warnings,
            require_positive_baseline=True,
        ),
        gross_margin_pct=_margin_change(
            latest.gross_margin_pct,
            previous.gross_margin_pct,
        ),
        operating_margin_pct=_margin_change(
            latest.operating_margin_pct,
            previous.operating_margin_pct,
        ),
    )


def _financial_change(
    metric: str,
    value: float,
    previous_value: float,
    warnings: list[str],
    *,
    require_positive_baseline: bool = False,
) -> MetricChange:
    current = _decimal(value)
    previous = _decimal(previous_value)
    absolute_change = _round_decimal(current - previous)

    if previous == 0 or (require_positive_baseline and previous < 0):
        percent_change = None
        invalid_baseline = (
            "zero or negative" if require_positive_baseline else "zero"
        )
        warnings.append(
            f"Percent change for {metric} is undefined because the previous value is "
            f"{invalid_baseline}."
        )
    else:
        percent_change = _round_decimal(
            (current - previous) / previous * ONE_HUNDRED
        )

    return MetricChange(
        value=float(current),
        previous_value=float(previous),
        absolute_change=float(absolute_change),
        percent_change=(float(percent_change) if percent_change is not None else None),
        unit="financial_units",
    )


def _margin_change(
    value: float | None,
    previous_value: float | None,
) -> MetricChange:
    if value is None or previous_value is None:
        absolute_change = None
    else:
        absolute_change = float(
            _round_decimal(_decimal(value) - _decimal(previous_value))
        )

    return MetricChange(
        value=value,
        previous_value=previous_value,
        absolute_change=absolute_change,
        percent_change=None,
        unit="percentage_points",
    )


def _decompose_operating_profit_change(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
) -> ProfitChangeDecomposition:
    revenue_impact = _round_decimal(
        _decimal(latest.revenue) - _decimal(previous.revenue)
    )
    cogs_impact = _round_decimal(-(_decimal(latest.cogs) - _decimal(previous.cogs)))
    operating_expenses_impact = _round_decimal(
        -(
            _decimal(latest.operating_expenses)
            - _decimal(previous.operating_expenses)
        )
    )
    delta_operating_profit = _round_decimal(
        revenue_impact + cogs_impact + operating_expenses_impact
    )
    impacts = {
        "revenue": revenue_impact,
        "cogs": cogs_impact,
        "operating_expenses": operating_expenses_impact,
    }
    contributor_metric, contributor_impact = max(
        impacts.items(),
        key=lambda item: abs(item[1]),
    )

    return ProfitChangeDecomposition(
        period=latest.period,
        comparison_period=previous.period,
        delta_operating_profit=float(delta_operating_profit),
        revenue_impact=float(revenue_impact),
        cogs_impact=float(cogs_impact),
        operating_expenses_impact=float(operating_expenses_impact),
        largest_measured_contributor=LargestMeasuredContributor(
            metric=contributor_metric,
            impact=float(contributor_impact),
        ),
    )


def _build_evidence(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
    changes: AnalysisChanges,
    decomposition: ProfitChangeDecomposition,
) -> list[EvidenceItem]:
    operating_margin_statement = (
        f"Operating margin for {latest.period} was "
        f"{latest.operating_margin_pct:.2f} percent."
        if latest.operating_margin_pct is not None
        else f"Operating margin for {latest.period} is undefined because revenue was zero."
    )
    contributor = decomposition.largest_measured_contributor
    contributor_label = {
        "revenue": "Revenue",
        "cogs": "COGS",
        "operating_expenses": "Operating expenses",
    }[contributor.metric]
    impact_description = _signed_description(contributor.impact)

    return [
        EvidenceItem(
            id="E1",
            type="snapshot",
            metric="operating_profit",
            period=latest.period,
            value=latest.operating_profit,
            unit="financial_units",
            direction="not_applicable",
            statement=(
                f"Operating profit for {latest.period} was "
                f"{latest.operating_profit:.2f} financial units."
            ),
        ),
        EvidenceItem(
            id="E2",
            type="snapshot",
            metric="operating_margin_pct",
            period=latest.period,
            value=latest.operating_margin_pct,
            unit="percent",
            direction=(
                "not_applicable"
                if latest.operating_margin_pct is not None
                else "undefined"
            ),
            statement=operating_margin_statement,
        ),
        _change_evidence(
            evidence_id="E3",
            metric="operating_profit",
            label="Operating profit",
            latest=latest,
            previous=previous,
            change=changes.operating_profit,
        ),
        _change_evidence(
            evidence_id="E4",
            metric="revenue",
            label="Revenue",
            latest=latest,
            previous=previous,
            change=changes.revenue,
        ),
        _change_evidence(
            evidence_id="E5",
            metric="cogs",
            label="COGS",
            latest=latest,
            previous=previous,
            change=changes.cogs,
        ),
        _change_evidence(
            evidence_id="E6",
            metric="operating_expenses",
            label="Operating expenses",
            latest=latest,
            previous=previous,
            change=changes.operating_expenses,
        ),
        EvidenceItem(
            id="E7",
            type="decomposition",
            metric=f"{contributor.metric}_impact",
            period=latest.period,
            comparison_period=previous.period,
            value=contributor.impact,
            change=contributor.impact,
            unit="financial_units",
            direction=_direction(contributor.impact),
            statement=(
                f"{contributor_label} was the largest measured contributor to the "
                f"operating-profit change, with {impact_description} arithmetic impact "
                f"of {abs(contributor.impact):.2f} financial units."
            ),
        ),
    ]


def _change_evidence(
    *,
    evidence_id: str,
    metric: str,
    label: str,
    latest: MonthlyKPI,
    previous: MonthlyKPI,
    change: MetricChange,
) -> EvidenceItem:
    absolute_change = change.absolute_change or 0.0
    direction = _direction(absolute_change)

    if direction == "increase":
        statement = (
            f"{label} increased by {abs(absolute_change):.2f} financial units "
            f"from {previous.period} to {latest.period}."
        )
    elif direction == "decrease":
        statement = (
            f"{label} decreased by {abs(absolute_change):.2f} financial units "
            f"from {previous.period} to {latest.period}."
        )
    else:
        statement = f"{label} was unchanged from {previous.period} to {latest.period}."

    return EvidenceItem(
        id=evidence_id,
        type="comparison",
        metric=metric,
        period=latest.period,
        comparison_period=previous.period,
        value=change.value,
        previous_value=change.previous_value,
        change=change.absolute_change,
        unit="financial_units",
        direction=direction,
        statement=statement,
    )


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _round_decimal(value: Decimal) -> Decimal:
    rounded = value.quantize(TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    return abs(rounded) if rounded == 0 else rounded


def _direction(change: float) -> str:
    if change > 0:
        return "increase"
    if change < 0:
        return "decrease"
    return "unchanged"


def _signed_description(value: float) -> str:
    if value > 0:
        return "a positive"
    if value < 0:
        return "a negative"
    return "a neutral"
