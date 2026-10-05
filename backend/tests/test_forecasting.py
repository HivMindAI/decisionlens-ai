from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.forecasting import (
    available_models,
    backtest_model,
    linear_trend_forecast,
    naive_last_value_forecast,
    seasonal_naive_forecast,
    select_forecast_model,
)

client = TestClient(app)


def month_labels(count: int, *, start_year: int = 2024, start_month: int = 1) -> list[str]:
    labels: list[str] = []
    year = start_year
    month = start_month
    for _ in range(count):
        labels.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return labels


def make_csv(
    revenues: list[float],
    cogs_values: list[float],
    operating_expenses_values: list[float],
    *,
    start_year: int = 2024,
) -> bytes:
    assert len(revenues) == len(cogs_values) == len(operating_expenses_values)
    periods = month_labels(len(revenues), start_year=start_year)
    lines = ["date,revenue,cogs,operating_expenses"]
    for period, revenue, cogs, operating_expenses in zip(
        periods,
        revenues,
        cogs_values,
        operating_expenses_values,
        strict=True,
    ):
        lines.append(f"{period}-01,{revenue},{cogs},{operating_expenses}")
    return ("\n".join(lines) + "\n").encode()


def analyze(content: bytes):
    return client.post(
        "/api/v1/analysis/summary",
        files={"file": ("financials.csv", content, "text/csv")},
    )


def test_naive_last_value_forecast() -> None:
    assert naive_last_value_forecast([10.0, 20.0, 30.0], 3) == [30.0, 30.0, 30.0]


def test_linear_trend_forecast() -> None:
    assert linear_trend_forecast([10.0, 20.0, 30.0, 40.0], 3) == pytest.approx(
        [50.0, 60.0, 70.0]
    )


def test_seasonal_naive_requires_twenty_four_months() -> None:
    assert "SEASONAL_NAIVE" not in available_models(23)
    assert "SEASONAL_NAIVE" in available_models(24)
    with pytest.raises(ValueError, match="at least 24"):
        seasonal_naive_forecast([float(value) for value in range(23)], 3)
    assert seasonal_naive_forecast([float(value) for value in range(24)], 3) == [
        12.0,
        13.0,
        14.0,
    ]


def test_forecast_periods_are_next_three_calendar_months() -> None:
    response = analyze(make_csv([1000.0] * 12, [400.0] * 12, [300.0] * 12))

    assert response.status_code == 200
    forecast = response.json()["forecast"]
    assert forecast["horizon_months"] == 3
    assert [period["period"] for period in forecast["periods"]] == [
        "2025-01",
        "2025-02",
        "2025-03",
    ]


def test_model_selection_uses_lowest_backtest_mae() -> None:
    selected = select_forecast_model([float(value) for value in range(10, 130, 10)])

    assert selected.model == "LINEAR_TREND"
    assert selected.mae == pytest.approx(0.0)


def test_model_selection_tie_breaks_toward_simpler_model() -> None:
    selected = select_forecast_model([100.0] * 24)

    assert selected.model == "NAIVE_LAST_VALUE"
    assert selected.mae == 0.0


def test_backtesting_never_trains_on_target_or_future_values() -> None:
    result = backtest_model([1.0, 2.0, 3.0, 4.0, 5.0, 100.0], "LINEAR_TREND")

    assert result is not None
    final_fold = result.folds[-1]
    assert final_fold.target_index == 5
    assert final_fold.training_points == 5
    assert final_fold.prediction == pytest.approx(6.0)
    assert final_fold.actual == 100.0


def test_base_metrics_are_selected_and_forecast_independently() -> None:
    revenues = [100.0 + 10.0 * index for index in range(12)]
    response = analyze(make_csv(revenues, [30.0] * 12, [20.0] * 12))

    assert response.status_code == 200
    models = response.json()["forecast"]["models"]
    assert models["revenue"]["selected_model"] == "LINEAR_TREND"
    assert models["cogs"]["selected_model"] == "NAIVE_LAST_VALUE"
    assert models["operating_expenses"]["selected_model"] == "NAIVE_LAST_VALUE"


def test_derived_profit_and_margins_use_forecast_components() -> None:
    response = analyze(make_csv([1000.0] * 12, [400.0] * 12, [300.0] * 12))

    period = response.json()["forecast"]["periods"][0]
    assert period["gross_profit"] == 600.0
    assert period["operating_profit"] == 300.0
    assert period["gross_margin_pct"] == 60.0
    assert period["operating_margin_pct"] == 30.0


def test_zero_forecast_revenue_has_null_margins_and_safe_normalized_mae() -> None:
    response = analyze(make_csv([0.0] * 12, [20.0] * 12, [10.0] * 12))

    assert response.status_code == 200
    forecast = response.json()["forecast"]
    assert forecast["models"]["revenue"]["normalized_mae_pct"] is None
    assert all(period["revenue"]["value"] == 0.0 for period in forecast["periods"])
    assert all(period["gross_margin_pct"] is None for period in forecast["periods"])
    assert all(period["operating_margin_pct"] is None for period in forecast["periods"])
    assert len(
        [warning for warning in forecast["warnings"] if "margins are undefined" in warning]
    ) == 3


def test_negative_base_forecasts_are_bounded_at_zero_with_warning() -> None:
    revenues = [110.0 - 10.0 * index for index in range(12)]
    response = analyze(make_csv(revenues, [20.0] * 12, [10.0] * 12))

    assert response.status_code == 200
    forecast = response.json()["forecast"]
    assert forecast["models"]["revenue"]["selected_model"] == "LINEAR_TREND"
    assert [period["revenue"]["value"] for period in forecast["periods"]] == [
        0.0,
        0.0,
        0.0,
    ]
    assert len(
        [warning for warning in forecast["warnings"] if "bounded at zero" in warning]
    ) == 3


def test_negative_projected_operating_profit_remains_allowed() -> None:
    response = analyze(make_csv([100.0] * 12, [80.0] * 12, [50.0] * 12))

    assert response.status_code == 200
    assert all(
        period["operating_profit"] == -30.0
        for period in response.json()["forecast"]["periods"]
    )


def test_backtest_mae_and_normalized_mae_are_correct() -> None:
    result = backtest_model(
        [10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0, 17.0],
        "NAIVE_LAST_VALUE",
    )

    assert result is not None
    assert len(result.folds) == 6
    assert result.mae == pytest.approx(1.5)
    assert result.normalized_mae_pct == pytest.approx(10.0)


def test_forecast_ranges_reflect_mae_and_profit_range_uses_components() -> None:
    values = [10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0, 15.0, 14.0, 16.0, 15.0, 17.0]
    response = analyze(make_csv(values, [3.0] * 12, [2.0] * 12))

    assert response.status_code == 200
    forecast = response.json()["forecast"]
    first = forecast["periods"][0]
    revenue_mae = forecast["models"]["revenue"]["mae"]
    assert first["revenue"]["backtest_mae_range"]["low"] == pytest.approx(
        max(0.0, first["revenue"]["value"] - revenue_mae),
        abs=0.02,
    )
    assert first["revenue"]["backtest_mae_range"]["high"] == pytest.approx(
        first["revenue"]["value"] + revenue_mae,
        abs=0.02,
    )
    expected_profit_low = (
        first["revenue"]["backtest_mae_range"]["low"]
        - first["cogs"]["backtest_mae_range"]["high"]
        - first["operating_expenses"]["backtest_mae_range"]["high"]
    )
    expected_profit_high = (
        first["revenue"]["backtest_mae_range"]["high"]
        - first["cogs"]["backtest_mae_range"]["low"]
        - first["operating_expenses"]["backtest_mae_range"]["low"]
    )
    assert first["operating_profit_component_range"]["low"] == pytest.approx(
        expected_profit_low,
        abs=0.01,
    )
    assert first["operating_profit_component_range"]["high"] == pytest.approx(
        expected_profit_high,
        abs=0.01,
    )


def test_forecast_evidence_matches_final_forecast_period() -> None:
    response = analyze(make_csv([1000.0] * 12, [400.0] * 12, [300.0] * 12))

    body = response.json()
    final_period = body["forecast"]["periods"][-1]
    evidence = {item["id"]: item for item in body["evidence"]}
    assert evidence["E8"]["value"] == final_period["revenue"]["value"]
    assert evidence["E9"]["value"] == final_period["operating_profit"]
    assert evidence["E10"]["value"] == final_period["operating_margin_pct"]
    assert all(
        "project" in evidence[evidence_id]["statement"].lower()
        for evidence_id in ("E8", "E9", "E10")
    )
    assert body["forecast"]["models"]["revenue"]["selected_model"] in evidence[
        "E8"
    ]["statement"]


def test_twelve_month_dataset_forecasts_safely_without_seasonal_model() -> None:
    response = analyze(make_csv([100.0] * 12, [30.0] * 12, [20.0] * 12))

    assert response.status_code == 200
    assert len(response.json()["forecast"]["periods"]) == 3
    assert all(
        diagnostics["selected_model"] != "SEASONAL_NAIVE"
        for diagnostics in response.json()["forecast"]["models"].values()
    )


def test_twenty_four_month_dataset_can_select_seasonal_naive() -> None:
    seasonal_pattern = [100.0, 120.0, 90.0, 140.0, 80.0, 160.0, 70.0, 180.0, 60.0, 200.0, 50.0, 220.0]
    revenues = seasonal_pattern * 2
    response = analyze(
        make_csv(
            revenues,
            [30.0] * 24,
            [20.0] * 24,
            start_year=2023,
        )
    )

    assert response.status_code == 200
    forecast = response.json()["forecast"]
    assert forecast["models"]["revenue"]["selected_model"] == "SEASONAL_NAIVE"
    assert [period["revenue"]["value"] for period in forecast["periods"]] == [
        100.0,
        120.0,
        90.0,
    ]

