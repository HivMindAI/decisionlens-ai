from __future__ import annotations

from collections.abc import Iterable

from fastapi.testclient import TestClient

from app.main import app
from app.services.csv_validation import MAX_UPLOAD_SIZE_BYTES

client = TestClient(app)


def month_labels(count: int, *, start_year: int = 2024, start_month: int = 1) -> list[str]:
    labels: list[str] = []
    year = start_year
    month = start_month

    for _ in range(count):
        labels.append(f"{year:04d}-{month:02d}-01")
        month += 1
        if month == 13:
            month = 1
            year += 1

    return labels


def make_csv(
    dates: Iterable[str] | None = None,
    *,
    headers: tuple[str, ...] = ("date", "revenue", "cogs", "operating_expenses"),
) -> bytes:
    date_values = list(dates or month_labels(12))
    rows = [",".join(headers)]

    for index, date_value in enumerate(date_values, start=1):
        values = {
            "date": date_value,
            "revenue": str(10_000 + index),
            "cogs": str(3_000 + index),
            "operating_expenses": str(2_000 + index),
            "notes": f"month-{index}",
        }
        normalized_headers = [header.strip().lower().replace(" ", "_") for header in headers]
        rows.append(",".join(values[header] for header in normalized_headers))

    return ("\n".join(rows) + "\n").encode()


def upload(content: bytes, *, filename: str = "financials.csv"):
    return client.post(
        "/api/v1/datasets/validate",
        files={"file": (filename, content, "text/csv")},
    )


def assert_error(response, *, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == code
    assert "message" in body["error"]


def replace_cell(content: bytes, row: int, column: int, value: str) -> bytes:
    lines = content.decode().splitlines()
    cells = lines[row].split(",")
    cells[column] = value
    lines[row] = ",".join(cells)
    return ("\n".join(lines) + "\n").encode()


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "decisionlens-ai-api",
    }


def test_valid_twelve_month_csv_with_normalized_headers_and_extra_column() -> None:
    content = make_csv(
        headers=("Date", "Revenue", "COGS", " Operating Expenses ", "notes")
    )

    response = upload(content)

    assert response.status_code == 200
    assert response.json() == {
        "status": "valid",
        "row_count": 12,
        "period_start": "2024-01",
        "period_end": "2024-12",
        "frequency": "monthly",
        "required_columns": [
            "date",
            "revenue",
            "cogs",
            "operating_expenses",
        ],
        "extra_columns": ["notes"],
        "warnings": [],
    }


def test_unsorted_valid_csv_is_accepted_and_summarized_chronologically() -> None:
    content = make_csv(reversed(month_labels(12)))

    response = upload(content)

    assert response.status_code == 200
    body = response.json()
    assert body["period_start"] == "2024-01"
    assert body["period_end"] == "2024-12"
    assert body["row_count"] == 12


def test_missing_required_column() -> None:
    content = make_csv(headers=("date", "revenue", "operating_expenses"))

    response = upload(content)

    assert_error(response, status_code=422, code="MISSING_REQUIRED_COLUMNS")
    assert response.json()["error"]["field"] == "headers"


def test_unparseable_date() -> None:
    content = replace_cell(make_csv(), row=1, column=0, value="not-a-date")

    response = upload(content)

    assert_error(response, status_code=422, code="INVALID_DATE")
    assert response.json()["error"]["field"] == "date"


def test_non_numeric_financial_value() -> None:
    content = replace_cell(make_csv(), row=3, column=1, value="not-a-number")

    response = upload(content)

    assert_error(response, status_code=422, code="INVALID_NUMERIC_VALUE")
    assert response.json()["error"]["field"] == "revenue"


def test_negative_financial_value() -> None:
    content = replace_cell(make_csv(), row=4, column=2, value="-1")

    response = upload(content)

    assert_error(response, status_code=422, code="NEGATIVE_VALUE")
    assert response.json()["error"]["field"] == "cogs"


def test_duplicate_month() -> None:
    content = replace_cell(make_csv(), row=12, column=0, value="2024-01-31")

    response = upload(content)

    assert_error(response, status_code=422, code="DUPLICATE_MONTH")


def test_missing_month_in_sequence() -> None:
    dates = month_labels(13)
    del dates[5]

    response = upload(make_csv(dates))

    assert_error(response, status_code=422, code="MISSING_MONTH")


def test_fewer_than_twelve_months() -> None:
    response = upload(make_csv(month_labels(11)))

    assert_error(response, status_code=422, code="INSUFFICIENT_HISTORY")


def test_empty_file() -> None:
    response = upload(b"")

    assert_error(response, status_code=422, code="EMPTY_FILE")


def test_non_csv_upload() -> None:
    response = upload(make_csv(), filename="financials.txt")

    assert_error(response, status_code=415, code="INVALID_FILE_TYPE")


def test_malformed_csv() -> None:
    content = (
        b"date,revenue,cogs,operating_expenses\n"
        b'2024-01-01,"10000,3000,2000\n'
    )

    response = upload(content)

    assert_error(response, status_code=422, code="MALFORMED_CSV")


def test_file_larger_than_five_megabytes() -> None:
    content = b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)

    response = upload(content)

    assert_error(response, status_code=413, code="FILE_TOO_LARGE")

