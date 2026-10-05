from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_csv(
    revenues: list[float],
    cogs_values: list[float],
    operating_expenses_values: list[float],
) -> bytes:
    assert len(revenues) == len(cogs_values) == len(operating_expenses_values) == 12
    lines = ["date,revenue,cogs,operating_expenses"]
    for index, (revenue, cogs, operating_expenses) in enumerate(
        zip(revenues, cogs_values, operating_expenses_values, strict=True),
        start=1,
    ):
        lines.append(
            f"2024-{index:02d}-01,{revenue},{cogs},{operating_expenses}"
        )
    return ("\n".join(lines) + "\n").encode()


def make_latest_pair_csv(
    previous: tuple[float, float, float],
    latest: tuple[float, float, float],
    *,
    baseline: tuple[float, float, float] = (1000.0, 400.0, 300.0),
) -> bytes:
    rows = [baseline] * 10 + [previous, latest]
    return make_csv(
        [row[0] for row in rows],
        [row[1] for row in rows],
        [row[2] for row in rows],
    )


def values_from_percentage_changes(
    starting_value: float,
    changes: list[float],
) -> list[float]:
    values = [starting_value]
    for change in changes:
        values.append(round(values[-1] * (1 + change / 100), 6))
    return values


def analyze(content: bytes):
    return client.post(
        "/api/v1/analysis/summary",
        files={"file": ("financials.csv", content, "text/csv")},
    )


def anomaly_for(body: dict, metric: str) -> dict | None:
    return next(
        (anomaly for anomaly in body["anomalies"] if anomaly["metric"] == metric),
        None,
    )


def signal_for(body: dict, signal_type: str) -> dict | None:
    return next(
        (signal for signal in body["signals"] if signal["type"] == signal_type),
        None,
    )


def test_clear_operating_expense_anomaly_is_detected() -> None:
    operating_expenses = values_from_percentage_changes(
        100.0,
        [1.0, -1.0, 2.0, -2.0, 1.5, -1.5, 0.5, -0.5, 1.0, -1.0, 50.0],
    )
    response = analyze(make_csv([1000.0] * 12, [300.0] * 12, operating_expenses))

    assert response.status_code == 200
    anomaly = anomaly_for(response.json(), "operating_expenses")
    assert anomaly is not None
    assert anomaly["period"] == "2024-12"
    assert anomaly["comparison_period"] == "2024-11"
    assert anomaly["direction"] == "increase"
    assert anomaly["observed_change"] == pytest.approx(50.0, abs=0.02)
    assert anomaly["change_unit"] == "percent"
    assert anomaly["historical_observation_count"] == 10
    assert abs(anomaly["robust_z"]) >= 3.5


def test_stable_series_has_no_false_anomalies_or_signals() -> None:
    response = analyze(make_csv([1000.0] * 12, [400.0] * 12, [300.0] * 12))

    assert response.status_code == 200
    body = response.json()
    assert body["anomalies"] == []
    assert body["signals"] == []


def test_latest_observation_is_excluded_from_anomaly_baseline() -> None:
    revenues = values_from_percentage_changes(
        100.0,
        [1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 1.0, 2.0, 20.0],
    )
    response = analyze(make_csv(revenues, [30.0] * 12, [20.0] * 12))

    assert response.status_code == 200
    anomaly = anomaly_for(response.json(), "revenue")
    assert anomaly is not None
    assert anomaly["historical_observation_count"] == 10
    assert anomaly["historical_median_change"] == pytest.approx(1.5, abs=0.02)
    assert anomaly["observed_change"] == pytest.approx(20.0, abs=0.02)


def test_insufficient_valid_history_does_not_create_anomaly() -> None:
    revenues = [0.0, 100.0, 0.0, 100.0, 0.0, 100.0, 0.0, 100.0, 0.0, 100.0, 100.0, 110.0]
    response = analyze(make_csv(revenues, [20.0] * 12, [10.0] * 12))

    assert response.status_code == 200
    body = response.json()
    assert anomaly_for(body, "revenue") is None
    assert any(
        "revenue" in warning and "fewer than 6 valid historical changes" in warning
        for warning in body["warnings"]
    )


def test_zero_mad_declines_to_fabricate_anomaly_score() -> None:
    revenues = [100.0] * 11 + [120.0]
    response = analyze(make_csv(revenues, [30.0] * 12, [20.0] * 12))

    assert response.status_code == 200
    body = response.json()
    assert anomaly_for(body, "revenue") is None
    assert any(
        "revenue" in warning and "MAD is zero" in warning
        for warning in body["warnings"]
    )


def test_operating_profit_anomaly_uses_absolute_change() -> None:
    operating_profits = [100.0]
    for change in [1.0, -1.0, 2.0, -2.0, 1.5, -1.5, 0.5, -0.5, 1.0, -1.0, 50.0]:
        operating_profits.append(operating_profits[-1] + change)
    operating_expenses = [600.0 - profit for profit in operating_profits]
    response = analyze(make_csv([1000.0] * 12, [400.0] * 12, operating_expenses))

    assert response.status_code == 200
    anomaly = anomaly_for(response.json(), "operating_profit")
    assert anomaly is not None
    assert anomaly["observed_change"] == 50.0
    assert anomaly["change_unit"] == "financial_units"
    assert anomaly["historical_observation_count"] == 10


def test_margin_compression_signal() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 300.0),
            (1000.0, 400.0, 350.0),
        )
    )

    signal = signal_for(response.json(), "MARGIN_COMPRESSION")
    assert signal is not None
    assert signal["measured_change"] == -5.0
    assert signal["change_unit"] == "percentage_points"
    assert signal["metrics"] == ["operating_margin_pct"]


def test_cost_growth_outpaces_revenue_signal() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 300.0),
            (1020.0, 440.0, 300.0),
        )
    )

    signals = [
        signal
        for signal in response.json()["signals"]
        if signal["type"] == "COST_GROWTH_OUTPACING_REVENUE"
    ]
    cogs_signal = next(signal for signal in signals if "cogs" in signal["metrics"])
    assert cogs_signal["measured_change"] == 8.0
    assert cogs_signal["change_unit"] == "percentage_points"
    assert "COGS" in cogs_signal["statement"]


def test_profit_deterioration_signal_while_remaining_positive() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 300.0),
            (1000.0, 400.0, 350.0),
        )
    )

    signal = signal_for(response.json(), "PROFIT_DETERIORATION")
    assert signal is not None
    assert signal["measured_change"] == -50.0
    assert signal["classification"] == "profit_declined"


def test_positive_profit_to_loss_is_classified() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 500.0),
            (1000.0, 400.0, 650.0),
        )
    )

    signal = signal_for(response.json(), "PROFIT_DETERIORATION")
    assert signal is not None
    assert signal["classification"] == "positive_to_loss"
    assert signal["severity"] == "high"
    assert signal["measured_change"] == -150.0


def test_positive_profit_growth_creates_recovery_signal() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 500.0),
            (1000.0, 400.0, 450.0),
        )
    )

    signal = signal_for(response.json(), "PROFIT_RECOVERY")
    assert signal is not None
    assert signal["classification"] == "profit_increased"
    assert signal["measured_change"] == 50.0
    assert signal_for(response.json(), "PROFIT_DETERIORATION") is None


def test_loss_becoming_smaller_creates_recovery_signal() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 700.0),
            (1000.0, 400.0, 650.0),
        )
    )

    signal = signal_for(response.json(), "PROFIT_RECOVERY")
    assert signal is not None
    assert signal["classification"] == "loss_narrowed"
    assert signal["measured_change"] == 50.0
    assert signal_for(response.json(), "PROFIT_DETERIORATION") is None


def test_meaningful_revenue_decline_signal() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 300.0),
            (900.0, 400.0, 300.0),
        )
    )

    signal = signal_for(response.json(), "REVENUE_DECLINE")
    assert signal is not None
    assert signal["measured_change"] == -10.0
    assert signal["change_unit"] == "percent"


def test_negligible_movements_do_not_create_signals() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 300.0),
            (999.9, 399.96, 299.9),
        )
    )

    assert response.status_code == 200
    assert response.json()["signals"] == []


def test_signal_evidence_ids_exist_and_analytics_remain_stable() -> None:
    response = analyze(
        make_latest_pair_csv(
            (1000.0, 400.0, 300.0),
            (900.0, 500.0, 400.0),
        )
    )

    assert response.status_code == 200
    body = response.json()
    available_ids = {item["id"] for item in body["evidence"]}
    assert body["signals"]
    assert all(
        set(signal["evidence_ids"]).issubset(available_ids)
        for signal in body["signals"]
    )
    assert body["latest_snapshot"] == {
        "period": "2024-12",
        "revenue": 900.0,
        "cogs": 500.0,
        "operating_expenses": 400.0,
        "gross_profit": 400.0,
        "operating_profit": 0.0,
        "gross_margin_pct": 44.44,
        "operating_margin_pct": 0.0,
    }
    assert body["profit_change_decomposition"]["delta_operating_profit"] == -300.0

