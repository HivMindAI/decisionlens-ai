from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from app.models.analytics import EvidenceItem, MonthlyKPI
from app.models.forecasting import (
    BaseMetricForecast,
    ForecastModelDiagnostics,
    ForecastModels,
    ForecastPeriod,
    ForecastRange,
    ForecastSummary,
)

FORECAST_HORIZON_MONTHS = 3
BACKTEST_WINDOW = 6
MIN_BACKTEST_POINTS = 3
SEASONAL_MIN_HISTORY = 24
MAE_TIE_TOLERANCE = 1e-9
TWO_DECIMAL_PLACES = Decimal("0.01")
ONE_HUNDRED = Decimal("100")

MODEL_PREFERENCE = (
    "NAIVE_LAST_VALUE",
    "LINEAR_TREND",
    "SEASONAL_NAIVE",
)
BASE_METRICS = ("revenue", "cogs", "operating_expenses")

FORECAST_LIMITATIONS = [
    "Forecasts extend historical monthly patterns and do not include external business factors.",
    "backtest_mae_range is an empirical error range based on recent one-step backtests, not a probabilistic confidence interval.",
    "The operating-profit component range is derived arithmetically from component ranges and is not a confidence interval.",
]


@dataclass(frozen=True)
class BacktestFold:
    target_index: int
    training_points: int
    prediction: float
    actual: float
    absolute_error: float


@dataclass(frozen=True)
class CandidateBacktest:
    model: str
    folds: tuple[BacktestFold, ...]
    mae: float
    normalized_mae_pct: float | None


def available_models(history_length: int) -> tuple[str, ...]:
    models = ["NAIVE_LAST_VALUE", "LINEAR_TREND"]
    if history_length >= SEASONAL_MIN_HISTORY:
        models.append("SEASONAL_NAIVE")
    return tuple(models)


def naive_last_value_forecast(values: list[float], horizon: int) -> list[float]:
    if not values:
        raise ValueError("Naive forecasting requires at least one observation.")
    return [float(values[-1])] * horizon


def linear_trend_forecast(values: list[float], horizon: int) -> list[float]:
    if len(values) < 2:
        raise ValueError("Linear trend forecasting requires at least two observations.")

    intercept, slope = _fit_linear_trend(values)
    return [intercept + slope * index for index in range(len(values), len(values) + horizon)]


def seasonal_naive_forecast(values: list[float], horizon: int) -> list[float]:
    if len(values) < SEASONAL_MIN_HISTORY:
        raise ValueError(
            f"Seasonal naive forecasting requires at least {SEASONAL_MIN_HISTORY} observations."
        )
    if horizon > 12:
        raise ValueError("Seasonal naive forecasting supports at most 12 future months.")

    first_source_index = len(values) - 12
    return [float(values[first_source_index + step]) for step in range(horizon)]


def backtest_model(values: list[float], model: str) -> CandidateBacktest | None:
    """Run recent rolling-origin one-step forecasts without future leakage."""
    if model not in available_models(len(values)):
        return None

    minimum_training_points = {
        "NAIVE_LAST_VALUE": 1,
        "LINEAR_TREND": 2,
        "SEASONAL_NAIVE": 12,
    }[model]
    target_indexes = list(range(minimum_training_points, len(values)))[
        -BACKTEST_WINDOW:
    ]
    folds: list[BacktestFold] = []

    for target_index in target_indexes:
        training_values = values[:target_index]
        prediction = _predict_next(model, training_values)
        actual = float(values[target_index])
        folds.append(
            BacktestFold(
                target_index=target_index,
                training_points=len(training_values),
                prediction=prediction,
                actual=actual,
                absolute_error=abs(prediction - actual),
            )
        )

    if len(folds) < MIN_BACKTEST_POINTS:
        return None

    mae = sum(fold.absolute_error for fold in folds) / len(folds)
    mean_absolute_actual = sum(abs(fold.actual) for fold in folds) / len(folds)
    normalized_mae_pct = (
        None
        if math.isclose(mean_absolute_actual, 0.0, abs_tol=1e-12)
        else mae / mean_absolute_actual * 100
    )

    return CandidateBacktest(
        model=model,
        folds=tuple(folds),
        mae=mae,
        normalized_mae_pct=normalized_mae_pct,
    )


def select_forecast_model(values: list[float]) -> CandidateBacktest:
    evaluations = [
        evaluation
        for model in available_models(len(values))
        if (evaluation := backtest_model(values, model)) is not None
    ]
    if not evaluations:
        raise ValueError("No forecasting model has enough backtest observations.")

    best = evaluations[0]
    for evaluation in evaluations[1:]:
        if evaluation.mae < best.mae - MAE_TIE_TOLERANCE:
            best = evaluation
    return best


def build_forecast(series: list[MonthlyKPI]) -> ForecastSummary:
    warnings: list[str] = []
    diagnostics: dict[str, ForecastModelDiagnostics] = {}
    metric_forecasts: dict[str, list[BaseMetricForecast]] = {}

    for metric in BASE_METRICS:
        values = [float(getattr(month, metric)) for month in series]
        selected = select_forecast_model(values)
        raw_forecasts = _forecast_with_model(
            values,
            selected.model,
            FORECAST_HORIZON_MONTHS,
        )
        diagnostics[metric] = ForecastModelDiagnostics(
            selected_model=selected.model,
            backtest_points=len(selected.folds),
            mae=_round(selected.mae),
            normalized_mae_pct=(
                _round(selected.normalized_mae_pct)
                if selected.normalized_mae_pct is not None
                else None
            ),
        )
        metric_forecasts[metric] = [
            _bounded_metric_forecast(
                metric,
                period_offset,
                raw_value,
                selected.mae,
                series[-1].period,
                warnings,
            )
            for period_offset, raw_value in enumerate(raw_forecasts, start=1)
        ]

    final_observed_period = pd.Period(series[-1].period, freq="M")
    forecast_periods: list[ForecastPeriod] = []
    for offset in range(1, FORECAST_HORIZON_MONTHS + 1):
        period = str(final_observed_period + offset)
        revenue = metric_forecasts["revenue"][offset - 1]
        cogs = metric_forecasts["cogs"][offset - 1]
        operating_expenses = metric_forecasts["operating_expenses"][offset - 1]
        gross_profit = _round(revenue.value - cogs.value)
        operating_profit = _round(gross_profit - operating_expenses.value)
        operating_profit_range = ForecastRange(
            low=_round(
                revenue.backtest_mae_range.low
                - cogs.backtest_mae_range.high
                - operating_expenses.backtest_mae_range.high
            ),
            high=_round(
                revenue.backtest_mae_range.high
                - cogs.backtest_mae_range.low
                - operating_expenses.backtest_mae_range.low
            ),
        )

        if revenue.value == 0:
            gross_margin_pct = None
            operating_margin_pct = None
            warnings.append(
                f"Forecast margins are undefined for {period} because projected revenue is zero."
            )
        else:
            gross_margin_pct = _round(gross_profit / revenue.value * 100)
            operating_margin_pct = _round(operating_profit / revenue.value * 100)

        forecast_periods.append(
            ForecastPeriod(
                period=period,
                revenue=revenue,
                cogs=cogs,
                operating_expenses=operating_expenses,
                gross_profit=gross_profit,
                operating_profit=operating_profit,
                operating_profit_component_range=operating_profit_range,
                gross_margin_pct=gross_margin_pct,
                operating_margin_pct=operating_margin_pct,
            )
        )

    return ForecastSummary(
        models=ForecastModels(
            revenue=diagnostics["revenue"],
            cogs=diagnostics["cogs"],
            operating_expenses=diagnostics["operating_expenses"],
        ),
        periods=forecast_periods,
        limitations=list(FORECAST_LIMITATIONS),
        warnings=warnings,
    )


def build_forecast_evidence(forecast: ForecastSummary) -> list[EvidenceItem]:
    final_period = forecast.periods[-1]
    revenue_model = forecast.models.revenue.selected_model
    component_models = {
        forecast.models.revenue.selected_model,
        forecast.models.cogs.selected_model,
        forecast.models.operating_expenses.selected_model,
    }
    component_model_description = ", ".join(sorted(component_models))

    evidence = [
        EvidenceItem(
            id="E8",
            type="forecast",
            metric="projected_revenue",
            period=final_period.period,
            value=final_period.revenue.value,
            unit="financial_units",
            direction="not_applicable",
            statement=(
                f"Revenue is projected at {final_period.revenue.value:.2f} financial "
                f"units for {final_period.period} using the {revenue_model} model selected "
                "by rolling backtest MAE."
            ),
        ),
        EvidenceItem(
            id="E9",
            type="forecast",
            metric="projected_operating_profit",
            period=final_period.period,
            value=final_period.operating_profit,
            unit="financial_units",
            direction="not_applicable",
            statement=(
                f"Operating profit is projected at {final_period.operating_profit:.2f} "
                f"financial units for {final_period.period}, derived from selected base "
                f"models: {component_model_description}."
            ),
        ),
    ]

    if final_period.operating_margin_pct is not None:
        evidence.append(
            EvidenceItem(
                id="E10",
                type="forecast",
                metric="projected_operating_margin_pct",
                period=final_period.period,
                value=final_period.operating_margin_pct,
                unit="percent",
                direction="not_applicable",
                statement=(
                    f"Operating margin is projected at "
                    f"{final_period.operating_margin_pct:.2f} percent for "
                    f"{final_period.period} from the component forecasts."
                ),
            )
        )

    return evidence


def _fit_linear_trend(values: list[float]) -> tuple[float, float]:
    count = len(values)
    mean_x = (count - 1) / 2
    mean_y = sum(values) / count
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    slope = (
        sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
        / denominator
    )
    intercept = mean_y - slope * mean_x
    return intercept, slope


def _predict_next(model: str, training_values: list[float]) -> float:
    if model == "NAIVE_LAST_VALUE":
        return naive_last_value_forecast(training_values, 1)[0]
    if model == "LINEAR_TREND":
        return linear_trend_forecast(training_values, 1)[0]
    if model == "SEASONAL_NAIVE":
        return float(training_values[-12])
    raise ValueError(f"Unknown forecasting model: {model}")


def _forecast_with_model(
    values: list[float],
    model: str,
    horizon: int,
) -> list[float]:
    if model == "NAIVE_LAST_VALUE":
        return naive_last_value_forecast(values, horizon)
    if model == "LINEAR_TREND":
        return linear_trend_forecast(values, horizon)
    if model == "SEASONAL_NAIVE":
        return seasonal_naive_forecast(values, horizon)
    raise ValueError(f"Unknown forecasting model: {model}")


def _bounded_metric_forecast(
    metric: str,
    period_offset: int,
    raw_value: float,
    mae: float,
    final_observed_period: str,
    warnings: list[str],
) -> BaseMetricForecast:
    period = str(pd.Period(final_observed_period, freq="M") + period_offset)
    bounded_value = raw_value
    if raw_value < 0:
        bounded_value = 0.0
        warnings.append(
            f"The unconstrained {metric} forecast for {period} was "
            f"{_round(raw_value):.2f} and was bounded at zero."
        )

    value = _round(bounded_value)
    return BaseMetricForecast(
        value=value,
        backtest_mae_range=ForecastRange(
            low=_round(max(0.0, bounded_value - mae)),
            high=_round(bounded_value + mae),
        ),
    )


def _round(value: float) -> float:
    rounded = Decimal(str(value)).quantize(
        TWO_DECIMAL_PLACES,
        rounding=ROUND_HALF_UP,
    )
    return float(abs(rounded) if rounded == 0 else rounded)

