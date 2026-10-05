from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FinancialValues = tuple[float, float, float]


def make_analysis_csv(
    overrides: Mapping[str, FinancialValues] | None = None,
    *,
    reverse: bool = False,
    include_extra_column: bool = False,
) -> bytes:
    values_by_period = overrides or {}
    headers = ["date", "revenue", "cogs", "operating_expenses"]
    if include_extra_column:
        headers.append("customer_note")

    rows: list[list[str]] = []
    for month in range(1, 13):
        period = f"2024-{month:02d}"
        revenue, cogs, operating_expenses = values_by_period.get(
            period,
            (900.0, 350.0, 250.0),
        )
        row = [
            f"{period}-01",
            str(revenue),
            str(cogs),
            str(operating_expenses),
        ]
        if include_extra_column:
            row.append(f"note-{month}")
        rows.append(row)

    if reverse:
        rows.reverse()

    lines = [",".join(headers), *(",".join(row) for row in rows)]
    return ("\n".join(lines) + "\n").encode()


def clear_change_fixture(*, reverse: bool = False, extra: bool = False) -> bytes:
    return make_analysis_csv(
        {
            "2024-11": (1000.0, 400.0, 300.0),
            "2024-12": (1200.0, 450.0, 350.0),
        },
        reverse=reverse,
        include_extra_column=extra,
    )


def analyze(content: bytes):
    return client.post(
        "/api/v1/analysis/summary",
        files={"file": ("financials.csv", content, "text/csv")},
    )


def test_kpi_calculations_and_latest_snapshot() -> None:
    response = analyze(clear_change_fixture())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["period_start"] == "2024-01"
    assert body["period_end"] == "2024-12"
    assert body["latest_period"] == "2024-12"
    assert body["previous_period"] == "2024-11"
    assert body["latest_snapshot"] == {
        "period": "2024-12",
        "revenue": 1200.0,
        "cogs": 450.0,
        "operating_expenses": 350.0,
        "gross_profit": 750.0,
        "operating_profit": 400.0,
        "gross_margin_pct": 62.5,
        "operating_margin_pct": 33.33,
    }


def test_unsorted_input_produces_chronological_series() -> None:
    response = analyze(clear_change_fixture(reverse=True))

    assert response.status_code == 200
    body = response.json()
    periods = [item["period"] for item in body["series"]]
    assert periods == [f"2024-{month:02d}" for month in range(1, 13)]
    assert body["latest_period"] == "2024-12"
    assert body["previous_period"] == "2024-11"


def test_month_over_month_changes() -> None:
    response = analyze(clear_change_fixture())

    changes = response.json()["changes"]
    assert changes["revenue"] == {
        "value": 1200.0,
        "previous_value": 1000.0,
        "absolute_change": 200.0,
        "percent_change": 20.0,
        "unit": "financial_units",
    }
    assert changes["cogs"]["absolute_change"] == 50.0
    assert changes["cogs"]["percent_change"] == 12.5
    assert changes["operating_expenses"]["absolute_change"] == 50.0
    assert changes["operating_expenses"]["percent_change"] == pytest.approx(16.67)
    assert changes["gross_profit"]["absolute_change"] == 150.0
    assert changes["gross_profit"]["percent_change"] == 25.0
    assert changes["operating_profit"]["absolute_change"] == 100.0
    assert changes["operating_profit"]["percent_change"] == pytest.approx(33.33)
    assert changes["gross_margin_pct"]["absolute_change"] == 2.5
    assert changes["gross_margin_pct"]["percent_change"] is None
    assert changes["gross_margin_pct"]["unit"] == "percentage_points"
    assert changes["operating_margin_pct"]["absolute_change"] == 3.33
    assert changes["operating_margin_pct"]["unit"] == "percentage_points"


def test_profit_change_decomposition_identity_and_largest_contributor() -> None:
    response = analyze(clear_change_fixture())

    decomposition = response.json()["profit_change_decomposition"]
    assert decomposition["period"] == "2024-12"
    assert decomposition["comparison_period"] == "2024-11"
    assert decomposition["delta_operating_profit"] == 100.0
    assert decomposition["revenue_impact"] == 200.0
    assert decomposition["cogs_impact"] == -50.0
    assert decomposition["operating_expenses_impact"] == -50.0
    assert decomposition["delta_operating_profit"] == (
        decomposition["revenue_impact"]
        + decomposition["cogs_impact"]
        + decomposition["operating_expenses_impact"]
    )
    assert decomposition["largest_measured_contributor"] == {
        "metric": "revenue",
        "impact": 200.0,
        "unit": "financial_units",
    }


def test_negative_derived_operating_profit_is_allowed() -> None:
    content = make_analysis_csv(
        {
            "2024-11": (120.0, 80.0, 30.0),
            "2024-12": (100.0, 80.0, 50.0),
        }
    )

    response = analyze(content)

    assert response.status_code == 200
    latest = response.json()["latest_snapshot"]
    assert latest["gross_profit"] == 20.0
    assert latest["operating_profit"] == -30.0
    assert latest["operating_margin_pct"] == -30.0


def test_zero_revenue_returns_null_margins_and_warning() -> None:
    content = make_analysis_csv({"2024-12": (0.0, 100.0, 50.0)})

    response = analyze(content)

    assert response.status_code == 200
    body = response.json()
    latest = body["latest_snapshot"]
    assert latest["gross_profit"] == -100.0
    assert latest["operating_profit"] == -150.0
    assert latest["gross_margin_pct"] is None
    assert latest["operating_margin_pct"] is None
    assert body["changes"]["gross_margin_pct"]["absolute_change"] is None
    assert body["changes"]["operating_margin_pct"]["absolute_change"] is None
    assert any("revenue is zero" in warning for warning in body["warnings"])


def test_zero_previous_value_returns_null_percent_change() -> None:
    content = make_analysis_csv(
        {
            "2024-11": (100.0, 40.0, 60.0),
            "2024-12": (120.0, 40.0, 60.0),
        }
    )

    response = analyze(content)

    assert response.status_code == 200
    body = response.json()
    operating_profit_change = body["changes"]["operating_profit"]
    assert operating_profit_change["previous_value"] == 0.0
    assert operating_profit_change["value"] == 20.0
    assert operating_profit_change["absolute_change"] == 20.0
    assert operating_profit_change["percent_change"] is None
    assert any(
        "operating_profit" in warning and "previous value is zero" in warning
        for warning in body["warnings"]
    )


def test_negative_previous_operating_profit_has_no_percent_change() -> None:
    content = make_analysis_csv(
        {
            "2024-11": (100.0, 60.0, 60.0),
            "2024-12": (100.0, 60.0, 50.0),
        }
    )

    response = analyze(content)

    assert response.status_code == 200
    body = response.json()
    operating_profit_change = body["changes"]["operating_profit"]
    assert operating_profit_change["previous_value"] == -20.0
    assert operating_profit_change["value"] == -10.0
    assert operating_profit_change["absolute_change"] == 10.0
    assert operating_profit_change["percent_change"] is None
    assert any(
        "operating_profit" in warning
        and "previous value is zero or negative" in warning
        for warning in body["warnings"]
    )


def test_non_positive_previous_gross_profit_has_no_percent_change() -> None:
    content = make_analysis_csv(
        {
            "2024-11": (100.0, 120.0, 10.0),
            "2024-12": (100.0, 110.0, 10.0),
        }
    )

    response = analyze(content)

    assert response.status_code == 200
    body = response.json()
    gross_profit_change = body["changes"]["gross_profit"]
    assert gross_profit_change["previous_value"] == -20.0
    assert gross_profit_change["value"] == -10.0
    assert gross_profit_change["absolute_change"] == 10.0
    assert gross_profit_change["percent_change"] is None
    assert any(
        "gross_profit" in warning and "previous value is zero or negative" in warning
        for warning in body["warnings"]
    )


def test_evidence_matches_deterministic_calculations() -> None:
    response = analyze(clear_change_fixture())

    body = response.json()
    evidence = {item["id"]: item for item in body["evidence"]}
    assert list(evidence) == [
        "E1",
        "E2",
        "E3",
        "E4",
        "E5",
        "E6",
        "E7",
        "E8",
        "E9",
        "E10",
    ]
    assert evidence["E1"]["value"] == body["latest_snapshot"]["operating_profit"]
    assert evidence["E2"]["value"] == body["latest_snapshot"]["operating_margin_pct"]
    assert evidence["E3"]["change"] == body["changes"]["operating_profit"][
        "absolute_change"
    ]
    assert evidence["E4"]["change"] == body["changes"]["revenue"][
        "absolute_change"
    ]
    assert evidence["E5"]["change"] == body["changes"]["cogs"][
        "absolute_change"
    ]
    assert evidence["E6"]["change"] == body["changes"]["operating_expenses"][
        "absolute_change"
    ]
    assert evidence["E7"]["metric"] == "revenue_impact"
    assert evidence["E7"]["value"] == body["profit_change_decomposition"][
        "largest_measured_contributor"
    ]["impact"]
    assert "largest measured contributor" in evidence["E7"]["statement"].lower()
    assert "caused" not in " ".join(
        item["statement"].lower() for item in body["evidence"]
    )


def test_validation_error_propagates_through_analysis_endpoint() -> None:
    lines = ["date,revenue,cogs"]
    for month in range(1, 13):
        lines.append(f"2024-{month:02d}-01,1000,400")

    response = analyze(("\n".join(lines) + "\n").encode())

    assert response.status_code == 422
    assert response.json() == {
        "status": "error",
        "error": {
            "code": "MISSING_REQUIRED_COLUMNS",
            "message": "Missing required columns: operating_expenses.",
            "field": "headers",
        },
    }


def test_extra_csv_columns_do_not_affect_calculations() -> None:
    without_extra = analyze(clear_change_fixture()).json()
    with_extra = analyze(clear_change_fixture(extra=True)).json()

    assert with_extra["latest_snapshot"] == without_extra["latest_snapshot"]
    assert with_extra["changes"] == without_extra["changes"]
    assert with_extra["profit_change_decomposition"] == without_extra[
        "profit_change_decomposition"
    ]
    assert all("customer_note" not in month for month in with_extra["series"])
