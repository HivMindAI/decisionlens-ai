from __future__ import annotations

import math
from statistics import median

from app.models.analytics import (
    AnalysisChanges,
    BusinessSignal,
    EvidenceItem,
    MonthlyKPI,
    StatisticalAnomaly,
)

# Robust anomaly detection needs enough prior movements to form a credible baseline.
MIN_HISTORICAL_CHANGES = 6
ROBUST_Z_THRESHOLD = 3.5
ROBUST_Z_MEDIUM_THRESHOLD = 4.5
ROBUST_Z_HIGH_THRESHOLD = 6.0
ROBUST_Z_SCALE = 0.6745

# Monthly signal thresholds are deterministic heuristics, not probability estimates.
MARGIN_COMPRESSION_THRESHOLD_PP = 2.0
COST_GROWTH_SPREAD_THRESHOLD_PP = 5.0
REVENUE_DECLINE_THRESHOLD_PCT = 5.0
PROFIT_RECOVERY_MIN_SHARE_OF_REVENUE_PCT = 2.0

PERCENTAGE_ANOMALY_METRICS = ("revenue", "cogs", "operating_expenses")
ANOMALY_METRICS = (*PERCENTAGE_ANOMALY_METRICS, "operating_profit")
METRIC_LABELS = {
    "revenue": "Revenue",
    "cogs": "COGS",
    "operating_expenses": "Operating expenses",
    "operating_profit": "Operating profit",
}


def detect_latest_anomalies(
    series: list[MonthlyKPI],
    warnings: list[str],
) -> list[StatisticalAnomaly]:
    """Flag latest changes against prior changes using median and MAD.

    Revenue and cost metrics use percentage changes only when the prior value is
    positive. Operating profit uses absolute changes so zero/negative baselines
    never produce misleading relative changes. The latest change is never part
    of its own historical reference distribution.
    """
    anomalies: list[StatisticalAnomaly] = []
    latest = series[-1]
    previous = series[-2]

    for metric in ANOMALY_METRICS:
        historical_changes = [
            change
            for historical_previous, historical_current in zip(
                series[:-2], series[1:-1], strict=True
            )
            if (
                change := _anomaly_change(
                    metric,
                    historical_previous,
                    historical_current,
                )
            )
            is not None
        ]
        latest_change = _anomaly_change(metric, previous, latest)

        if latest_change is None:
            warnings.append(
                f"Anomaly detection for {metric} was skipped because the latest "
                "percentage change has a non-positive baseline."
            )
            continue

        if len(historical_changes) < MIN_HISTORICAL_CHANGES:
            warnings.append(
                f"Anomaly detection for {metric} was skipped because fewer than "
                f"{MIN_HISTORICAL_CHANGES} valid historical changes were available."
            )
            continue

        historical_median = median(historical_changes)
        absolute_deviations = [
            abs(change - historical_median) for change in historical_changes
        ]
        mad = median(absolute_deviations)

        if math.isclose(mad, 0.0, abs_tol=1e-12):
            if not math.isclose(latest_change, historical_median, abs_tol=1e-12):
                warnings.append(
                    f"Anomaly detection for {metric} was skipped because historical "
                    "MAD is zero; no robust score was fabricated."
                )
            continue

        robust_z = ROBUST_Z_SCALE * (latest_change - historical_median) / mad
        if abs(robust_z) < ROBUST_Z_THRESHOLD:
            continue

        change_unit = (
            "financial_units" if metric == "operating_profit" else "percent"
        )
        statement_unit = (
            "financial units" if change_unit == "financial_units" else "percent"
        )
        direction = "increase" if latest_change > 0 else "decrease"
        severity = _anomaly_severity(abs(robust_z))
        observed_change = _round(latest_change)
        median_change = _round(historical_median)
        score = _round(robust_z)
        label = METRIC_LABELS[metric]

        anomalies.append(
            StatisticalAnomaly(
                id=f"A{len(anomalies) + 1}",
                metric=metric,
                period=latest.period,
                comparison_period=previous.period,
                direction=direction,
                observed_change=observed_change,
                change_unit=change_unit,
                historical_median_change=median_change,
                historical_observation_count=len(historical_changes),
                robust_z=score,
                severity=severity,
                statement=(
                    f"{label} changed by {observed_change:.2f} {statement_unit} from "
                    f"{previous.period} to {latest.period}, versus a historical median "
                    f"change of {median_change:.2f}; the robust z-score was {score:.2f}."
                ),
            )
        )

    return anomalies


def generate_business_signals(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
    changes: AnalysisChanges,
    evidence: list[EvidenceItem],
) -> list[BusinessSignal]:
    signals: list[BusinessSignal] = []
    available_evidence_ids = {item.id for item in evidence}

    def evidence_ids(*requested_ids: str) -> list[str]:
        missing_ids = set(requested_ids) - available_evidence_ids
        if missing_ids:
            raise ValueError(
                f"Signal references unavailable evidence IDs: {sorted(missing_ids)}"
            )
        return list(requested_ids)

    operating_margin_change = changes.operating_margin_pct.absolute_change
    if (
        operating_margin_change is not None
        and operating_margin_change <= -MARGIN_COMPRESSION_THRESHOLD_PP
    ):
        magnitude = abs(operating_margin_change)
        signals.append(
            BusinessSignal(
                id=f"S{len(signals) + 1}",
                type="MARGIN_COMPRESSION",
                severity=_margin_severity(magnitude),
                period=latest.period,
                comparison_period=previous.period,
                metrics=["operating_margin_pct"],
                measured_change=operating_margin_change,
                change_unit="percentage_points",
                statement=(
                    f"Operating margin decreased by {magnitude:.2f} percentage points "
                    f"from {previous.period} to {latest.period}."
                ),
                evidence_ids=evidence_ids("E2"),
            )
        )

    revenue_change_pct = changes.revenue.percent_change
    if revenue_change_pct is not None:
        for metric, change, evidence_id, label in (
            ("cogs", changes.cogs, "E5", "COGS"),
            (
                "operating_expenses",
                changes.operating_expenses,
                "E6",
                "Operating expense",
            ),
        ):
            cost_change_pct = change.percent_change
            if cost_change_pct is None:
                continue
            spread = cost_change_pct - revenue_change_pct
            if spread < COST_GROWTH_SPREAD_THRESHOLD_PP:
                continue

            signals.append(
                BusinessSignal(
                    id=f"S{len(signals) + 1}",
                    type="COST_GROWTH_OUTPACING_REVENUE",
                    severity=_cost_spread_severity(spread),
                    period=latest.period,
                    comparison_period=previous.period,
                    metrics=[metric, "revenue"],
                    measured_change=_round(spread),
                    change_unit="percentage_points",
                    statement=(
                        f"{label} month-over-month change was {cost_change_pct:.2f} "
                        f"percent, {_round(spread):.2f} percentage points above the "
                        f"revenue change of {revenue_change_pct:.2f} percent."
                    ),
                    evidence_ids=evidence_ids(evidence_id, "E4"),
                )
            )

    profit_change = changes.operating_profit.absolute_change or 0.0
    if profit_change < 0:
        classification = _profit_deterioration_classification(latest, previous)
        signals.append(
            BusinessSignal(
                id=f"S{len(signals) + 1}",
                type="PROFIT_DETERIORATION",
                severity=(
                    "high"
                    if classification == "positive_to_loss"
                    else _profit_change_severity(profit_change, latest.revenue)
                ),
                period=latest.period,
                comparison_period=previous.period,
                metrics=["operating_profit"],
                measured_change=profit_change,
                change_unit="financial_units",
                classification=classification,
                statement=_profit_deterioration_statement(
                    latest,
                    previous,
                    profit_change,
                    classification,
                ),
                evidence_ids=evidence_ids("E3"),
            )
        )
    elif profit_change > 0 and _is_material_profit_recovery(
        latest,
        previous,
        profit_change,
    ):
        classification = _profit_recovery_classification(latest, previous)
        signals.append(
            BusinessSignal(
                id=f"S{len(signals) + 1}",
                type="PROFIT_RECOVERY",
                severity=(
                    "high"
                    if classification == "loss_to_positive"
                    else _profit_change_severity(profit_change, latest.revenue)
                ),
                period=latest.period,
                comparison_period=previous.period,
                metrics=["operating_profit"],
                measured_change=profit_change,
                change_unit="financial_units",
                classification=classification,
                statement=_profit_recovery_statement(
                    latest,
                    previous,
                    profit_change,
                    classification,
                ),
                evidence_ids=evidence_ids("E3"),
            )
        )

    if (
        revenue_change_pct is not None
        and revenue_change_pct <= -REVENUE_DECLINE_THRESHOLD_PCT
    ):
        signals.append(
            BusinessSignal(
                id=f"S{len(signals) + 1}",
                type="REVENUE_DECLINE",
                severity=_revenue_decline_severity(abs(revenue_change_pct)),
                period=latest.period,
                comparison_period=previous.period,
                metrics=["revenue"],
                measured_change=revenue_change_pct,
                change_unit="percent",
                statement=(
                    f"Revenue decreased by {abs(revenue_change_pct):.2f} percent "
                    f"from {previous.period} to {latest.period}."
                ),
                evidence_ids=evidence_ids("E4"),
            )
        )

    return signals


def _anomaly_change(
    metric: str,
    previous: MonthlyKPI,
    current: MonthlyKPI,
) -> float | None:
    previous_value = float(getattr(previous, metric))
    current_value = float(getattr(current, metric))

    if metric == "operating_profit":
        return current_value - previous_value
    if previous_value <= 0:
        return None
    return (current_value - previous_value) / previous_value * 100


def _anomaly_severity(absolute_score: float) -> str:
    if absolute_score >= ROBUST_Z_HIGH_THRESHOLD:
        return "high"
    if absolute_score >= ROBUST_Z_MEDIUM_THRESHOLD:
        return "medium"
    return "low"


def _margin_severity(magnitude: float) -> str:
    if magnitude >= 5.0:
        return "high"
    if magnitude >= 3.5:
        return "medium"
    return "low"


def _cost_spread_severity(spread: float) -> str:
    if spread >= 15.0:
        return "high"
    if spread >= 10.0:
        return "medium"
    return "low"


def _profit_change_severity(change: float, revenue: float) -> str:
    if revenue <= 0:
        return "high"
    magnitude_as_revenue_pct = abs(change) / revenue * 100
    if magnitude_as_revenue_pct >= 10.0:
        return "high"
    if magnitude_as_revenue_pct >= 5.0:
        return "medium"
    return "low"


def _revenue_decline_severity(magnitude: float) -> str:
    if magnitude >= 15.0:
        return "high"
    if magnitude >= 10.0:
        return "medium"
    return "low"


def _profit_deterioration_classification(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
) -> str:
    if previous.operating_profit > 0 and latest.operating_profit < 0:
        return "positive_to_loss"
    if previous.operating_profit < 0 and latest.operating_profit < previous.operating_profit:
        return "loss_deepened"
    return "profit_declined"


def _is_material_profit_recovery(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
    profit_change: float,
) -> bool:
    if previous.operating_profit < 0 < latest.operating_profit:
        return True
    if latest.revenue <= 0:
        return False
    return (
        profit_change / latest.revenue * 100
        >= PROFIT_RECOVERY_MIN_SHARE_OF_REVENUE_PCT
    )


def _profit_recovery_classification(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
) -> str:
    if previous.operating_profit < 0 < latest.operating_profit:
        return "loss_to_positive"
    if previous.operating_profit < 0 and latest.operating_profit <= 0:
        return "loss_narrowed"
    return "profit_increased"


def _profit_deterioration_statement(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
    change: float,
    classification: str,
) -> str:
    if classification == "positive_to_loss":
        return (
            f"Operating profit moved from {previous.operating_profit:.2f} to "
            f"{latest.operating_profit:.2f} financial units, a decline of "
            f"{abs(change):.2f}."
        )
    if classification == "loss_deepened":
        return (
            f"Operating loss deepened from {previous.operating_profit:.2f} to "
            f"{latest.operating_profit:.2f} financial units, a decline of "
            f"{abs(change):.2f}."
        )
    return (
        f"Operating profit decreased by {abs(change):.2f} financial units from "
        f"{previous.period} to {latest.period}."
    )


def _profit_recovery_statement(
    latest: MonthlyKPI,
    previous: MonthlyKPI,
    change: float,
    classification: str,
) -> str:
    if classification == "loss_to_positive":
        return (
            f"Operating profit moved from a loss of {abs(previous.operating_profit):.2f} "
            f"to a positive {latest.operating_profit:.2f} financial units."
        )
    if classification == "loss_narrowed":
        return (
            f"Operating loss narrowed by {change:.2f} financial units, from "
            f"{previous.operating_profit:.2f} to {latest.operating_profit:.2f}."
        )
    return (
        f"Operating profit increased by {change:.2f} financial units from "
        f"{previous.period} to {latest.period}."
    )


def _round(value: float) -> float:
    rounded = round(value, 2)
    return abs(rounded) if rounded == 0 else rounded
