from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_csv(
    *,
    revenue: float = 1000.0,
    cogs: float = 400.0,
    operating_expenses: float = 300.0,
) -> bytes:
    lines = ["date,revenue,cogs,operating_expenses"]
    for month in range(1, 13):
        lines.append(
            f"2024-{month:02d}-01,{revenue},{cogs},{operating_expenses}"
        )
    return ("\n".join(lines) + "\n").encode()


def simulate(content: bytes, scenario: dict | None = None):
    data = {} if scenario is None else {"scenario": json.dumps(scenario)}
    return client.post(
        "/api/v1/simulations/what-if",
        files={"file": ("financials.csv", content, "text/csv")},
        data=data,
    )


def simulate_raw(content: bytes, scenario: str):
    return client.post(
        "/api/v1/simulations/what-if",
        files={"file": ("financials.csv", content, "text/csv")},
        data={"scenario": scenario},
    )


def analyze(content: bytes):
    return client.post(
        "/api/v1/analysis/summary",
        files={"file": ("financials.csv", content, "text/csv")},
    )


def test_zero_adjustments_exactly_reproduce_baseline() -> None:
    response = simulate(
        make_csv(),
        {
            "revenue_pct": 0,
            "cogs_pct": 0,
            "operating_expenses_pct": 0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    for period in body["periods"]:
        assert period["scenario"] == {
            "revenue": period["baseline"]["revenue"]["value"],
            "cogs": period["baseline"]["cogs"]["value"],
            "operating_expenses": period["baseline"]["operating_expenses"]["value"],
            "gross_profit": period["baseline"]["gross_profit"],
            "operating_profit": period["baseline"]["operating_profit"],
            "gross_margin_pct": period["baseline"]["gross_margin_pct"],
            "operating_margin_pct": period["baseline"]["operating_margin_pct"],
        }
        assert all(
            value == 0.0 for value in period["difference"].values()
        )
    assert body["summary"]["three_month_operating_profit_difference"] == 0.0


def test_omitted_adjustments_default_to_zero() -> None:
    response = simulate(make_csv())

    assert response.status_code == 200
    assert response.json()["scenario"] == {
        "revenue_pct": 0.0,
        "cogs_pct": 0.0,
        "operating_expenses_pct": 0.0,
    }


def test_revenue_increase_applies_and_derived_values_are_recalculated() -> None:
    response = simulate(make_csv(), {"revenue_pct": 5})

    first = response.json()["periods"][0]
    assert first["scenario"] == {
        "revenue": 1050.0,
        "cogs": 400.0,
        "operating_expenses": 300.0,
        "gross_profit": 650.0,
        "operating_profit": 350.0,
        "gross_margin_pct": 61.9,
        "operating_margin_pct": 33.33,
    }
    assert first["difference"]["revenue_difference"] == 50.0
    assert first["difference"]["gross_profit_difference"] == 50.0
    assert first["difference"]["operating_profit_difference"] == 50.0
    assert first["difference"]["gross_margin_difference_pp"] == 1.9
    assert first["difference"]["operating_margin_difference_pp"] == 3.33


def test_operating_expense_reduction_applies_correctly() -> None:
    response = simulate(make_csv(), {"operating_expenses_pct": -8})

    first = response.json()["periods"][0]
    assert first["scenario"]["operating_expenses"] == 276.0
    assert first["scenario"]["operating_profit"] == 324.0
    assert first["difference"]["operating_expenses_difference"] == -24.0
    assert first["difference"]["operating_profit_difference"] == 24.0


def test_cogs_reduction_applies_correctly() -> None:
    response = simulate(make_csv(), {"cogs_pct": -4})

    first = response.json()["periods"][0]
    assert first["scenario"]["cogs"] == 384.0
    assert first["scenario"]["gross_profit"] == 616.0
    assert first["scenario"]["operating_profit"] == 316.0
    assert first["difference"]["cogs_difference"] == -16.0


def test_multiple_adjustments_and_three_month_summary() -> None:
    response = simulate(
        make_csv(),
        {
            "revenue_pct": 5,
            "cogs_pct": -4,
            "operating_expenses_pct": -8,
        },
    )

    assert response.status_code == 200
    body = response.json()
    first = body["periods"][0]
    assert first["scenario"] == {
        "revenue": 1050.0,
        "cogs": 384.0,
        "operating_expenses": 276.0,
        "gross_profit": 666.0,
        "operating_profit": 390.0,
        "gross_margin_pct": 63.43,
        "operating_margin_pct": 37.14,
    }
    assert first["difference"] == {
        "revenue_difference": 50.0,
        "cogs_difference": -16.0,
        "operating_expenses_difference": -24.0,
        "gross_profit_difference": 66.0,
        "operating_profit_difference": 90.0,
        "gross_margin_difference_pp": 3.43,
        "operating_margin_difference_pp": 7.14,
    }
    assert body["summary"] == {
        "final_period": "2025-03",
        "baseline_final_operating_profit": 300.0,
        "scenario_final_operating_profit": 390.0,
        "final_operating_profit_difference": 90.0,
        "baseline_final_operating_margin_pct": 30.0,
        "scenario_final_operating_margin_pct": 37.14,
        "final_operating_margin_difference_pp": 7.14,
        "baseline_3_month_operating_profit_total": 900.0,
        "scenario_3_month_operating_profit_total": 1170.0,
        "three_month_operating_profit_difference": 270.0,
    }


def test_negative_one_hundred_percent_revenue_is_safe() -> None:
    response = simulate(make_csv(), {"revenue_pct": -100})

    assert response.status_code == 200
    body = response.json()
    for period in body["periods"]:
        assert period["scenario"]["revenue"] == 0.0
        assert period["scenario"]["gross_profit"] == -400.0
        assert period["scenario"]["operating_profit"] == -700.0
        assert period["scenario"]["gross_margin_pct"] is None
        assert period["scenario"]["operating_margin_pct"] is None
        assert period["difference"]["gross_margin_difference_pp"] is None
        assert period["difference"]["operating_margin_difference_pp"] is None
    assert len(
        [warning for warning in body["warnings"] if "Scenario margins are undefined" in warning]
    ) == 3


def test_negative_projected_operating_profit_remains_valid() -> None:
    response = simulate(
        make_csv(revenue=100.0, cogs=80.0, operating_expenses=50.0),
        {"operating_expenses_pct": 10},
    )

    assert response.status_code == 200
    assert all(
        period["scenario"]["operating_profit"] == -35.0
        for period in response.json()["periods"]
    )


@pytest.mark.parametrize(
    ("scenario", "field"),
    [
        ({"revenue_pct": -100.01}, "revenue_pct"),
        ({"cogs_pct": 500.01}, "cogs_pct"),
    ],
)
def test_out_of_range_adjustments_are_rejected(scenario: dict, field: str) -> None:
    response = simulate(make_csv(), scenario)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SCENARIO_ADJUSTMENT"
    assert response.json()["error"]["field"] == field


@pytest.mark.parametrize(
    ("raw_scenario", "field"),
    [
        ('{"revenue_pct": "five"}', "revenue_pct"),
        ('{"operating_expenses_pct": NaN}', "operating_expenses_pct"),
    ],
)
def test_invalid_or_non_finite_adjustments_are_rejected(
    raw_scenario: str,
    field: str,
) -> None:
    response = simulate_raw(make_csv(), raw_scenario)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SCENARIO_ADJUSTMENT"
    assert response.json()["error"]["field"] == field


def test_scenario_evidence_matches_calculations() -> None:
    response = simulate(
        make_csv(),
        {
            "revenue_pct": 5,
            "cogs_pct": -4,
            "operating_expenses_pct": -8,
        },
    )

    body = response.json()
    evidence = {item["id"]: item for item in body["scenario_evidence"]}
    summary = body["summary"]
    assert list(evidence) == ["SE1", "SE2", "SE3", "SE4"]
    assert evidence["SE1"]["value"] == summary["scenario_final_operating_profit"]
    assert evidence["SE2"]["value"] == summary["final_operating_profit_difference"]
    assert evidence["SE3"]["value"] == summary["scenario_final_operating_margin_pct"]
    assert evidence["SE4"]["value"] == summary[
        "three_month_operating_profit_difference"
    ]
    assert all(
        "under this scenario" in item["statement"].lower()
        for item in evidence.values()
    )


def test_assumptions_distinguish_changed_and_unchanged_metrics_without_causal_claims() -> None:
    response = simulate(make_csv(), {"operating_expenses_pct": -8})

    body = response.json()
    assert body["assumptions"] == [
        "Revenue remains at its baseline forecast value.",
        "COGS remains at its baseline forecast value.",
        "Operating expenses are adjusted by -8.00% relative to each baseline forecast period.",
        "No causal relationship between scenario adjustments is modeled.",
    ]
    output_text = json.dumps(body).lower()
    assert "caused" not in output_text
    assert "will cause" not in output_text
    assert any("not a causal prediction" in item.lower() for item in body["limitations"])
    assert any("inherit uncertainty" in item.lower() for item in body["limitations"])


def test_simulation_does_not_mutate_baseline_forecast() -> None:
    content = make_csv()
    analysis_response = analyze(content)
    simulation_response = simulate(
        content,
        {
            "revenue_pct": 5,
            "cogs_pct": -4,
            "operating_expenses_pct": -8,
        },
    )

    assert analysis_response.status_code == 200
    assert simulation_response.status_code == 200
    analysis_forecast = analysis_response.json()["forecast"]
    simulation = simulation_response.json()
    assert simulation["baseline_forecast_models"] == analysis_forecast["models"]
    for forecast_period, simulation_period in zip(
        analysis_forecast["periods"],
        simulation["periods"],
        strict=True,
    ):
        baseline = simulation_period["baseline"]
        assert baseline["revenue"] == forecast_period["revenue"]
        assert baseline["cogs"] == forecast_period["cogs"]
        assert baseline["operating_expenses"] == forecast_period[
            "operating_expenses"
        ]
        assert baseline["gross_profit"] == forecast_period["gross_profit"]
        assert baseline["operating_profit"] == forecast_period["operating_profit"]
        assert baseline["operating_profit_component_range"] == forecast_period[
            "operating_profit_component_range"
        ]
        assert baseline["gross_margin_pct"] == forecast_period["gross_margin_pct"]
        assert baseline["operating_margin_pct"] == forecast_period[
            "operating_margin_pct"
        ]


def test_existing_validation_error_propagates() -> None:
    lines = ["date,revenue,cogs"]
    for month in range(1, 13):
        lines.append(f"2024-{month:02d}-01,1000,400")

    response = simulate(("\n".join(lines) + "\n").encode(), {})

    assert response.status_code == 422
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "MISSING_REQUIRED_COLUMNS",
            "message": "Missing required columns: operating_expenses.",
            "field": "headers",
        },
    }

