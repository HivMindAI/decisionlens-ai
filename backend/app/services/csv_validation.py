from __future__ import annotations

import math
import re
from io import BytesIO
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

from app.models.datasets import DatasetValidationResponse

MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
REQUIRED_COLUMNS = (
    "date",
    "revenue",
    "cogs",
    "operating_expenses",
)


class CSVValidationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str | None = None,
        row: int | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.row = row
        self.status_code = status_code


def normalize_header(header: object) -> str:
    """Normalize predictable CSV header variations without fuzzy matching."""
    return re.sub(r"\s+", "_", str(header).strip().lower())


def validate_csv_upload(filename: str | None, content: bytes) -> DatasetValidationResponse:
    _validate_file(filename, content)
    frame = _read_csv(content)
    frame = _normalize_and_validate_columns(frame)

    if frame.empty:
        raise CSVValidationError("EMPTY_FILE", "The CSV contains no data rows.")

    _validate_financial_values(frame)
    frame = _validate_and_sort_dates(frame)
    _validate_history(frame)

    extra_columns = [
        column for column in frame.columns if column not in REQUIRED_COLUMNS and column != "_period"
    ]

    return DatasetValidationResponse(
        row_count=len(frame),
        period_start=str(frame["_period"].iloc[0]),
        period_end=str(frame["_period"].iloc[-1]),
        required_columns=list(REQUIRED_COLUMNS),
        extra_columns=extra_columns,
    )


def _validate_file(filename: str | None, content: bytes) -> None:
    if not filename or Path(filename).suffix.lower() != ".csv":
        raise CSVValidationError(
            "INVALID_FILE_TYPE",
            "Upload a file with a .csv extension.",
            status_code=415,
        )

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise CSVValidationError(
            "FILE_TOO_LARGE",
            "The CSV exceeds the 5 MB upload limit.",
            status_code=413,
        )

    if not content or not content.strip():
        raise CSVValidationError("EMPTY_FILE", "The uploaded CSV is empty.")


def _read_csv(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    except EmptyDataError as exc:
        raise CSVValidationError("EMPTY_FILE", "The uploaded CSV is empty.") from exc
    except (ParserError, UnicodeDecodeError, ValueError) as exc:
        raise CSVValidationError(
            "MALFORMED_CSV",
            "The uploaded file could not be read as a valid CSV.",
        ) from exc


def _normalize_and_validate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized_columns = [normalize_header(column) for column in frame.columns]
    duplicate_columns = sorted(
        {column for column in normalized_columns if normalized_columns.count(column) > 1}
    )
    if duplicate_columns:
        raise CSVValidationError(
            "MALFORMED_CSV",
            "The CSV contains duplicate columns after header normalization.",
            field="headers",
        )

    frame = frame.copy()
    frame.columns = normalized_columns

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise CSVValidationError(
            "MISSING_REQUIRED_COLUMNS",
            f"Missing required columns: {', '.join(missing_columns)}.",
            field="headers",
        )

    return frame


def _validate_and_sort_dates(frame: pd.DataFrame) -> pd.DataFrame:
    date_values = frame["date"].astype("string")
    parsed_dates = pd.to_datetime(date_values, errors="coerce", format="mixed")
    invalid_dates = parsed_dates.isna()

    if invalid_dates.any():
        invalid_index = invalid_dates[invalid_dates].index[0]
        raise CSVValidationError(
            "INVALID_DATE",
            "Every date must be a valid calendar date.",
            field="date",
            row=int(invalid_index) + 2,
        )

    periods = parsed_dates.dt.to_period("M")
    duplicate_months = periods.duplicated(keep="first")
    if duplicate_months.any():
        duplicate_index = duplicate_months[duplicate_months].index[0]
        duplicate_period = periods.loc[duplicate_index]
        raise CSVValidationError(
            "DUPLICATE_MONTH",
            f"Calendar month {duplicate_period} appears more than once.",
            field="date",
            row=int(duplicate_index) + 2,
        )

    sorted_frame = frame.assign(_period=periods).sort_values("_period").reset_index(drop=True)
    return sorted_frame


def _validate_history(frame: pd.DataFrame) -> None:
    actual_periods = frame["_period"].tolist()
    expected_periods = list(
        pd.period_range(actual_periods[0], actual_periods[-1], freq="M")
    )
    actual_period_set = set(actual_periods)
    missing_periods = [period for period in expected_periods if period not in actual_period_set]

    if missing_periods:
        raise CSVValidationError(
            "MISSING_MONTH",
            f"Monthly history is missing {missing_periods[0]}.",
            field="date",
        )

    if len(frame) < 12:
        raise CSVValidationError(
            "INSUFFICIENT_HISTORY",
            "At least 12 monthly rows are required.",
            field="date",
        )


def _validate_financial_values(frame: pd.DataFrame) -> None:
    for column in REQUIRED_COLUMNS[1:]:
        numeric_values = pd.to_numeric(frame[column], errors="coerce")
        finite_values = numeric_values.map(
            lambda value: pd.notna(value) and math.isfinite(float(value))
        )

        if not finite_values.all():
            invalid_index = finite_values[~finite_values].index[0]
            raise CSVValidationError(
                "INVALID_NUMERIC_VALUE",
                f"Every {column} value must be a finite number.",
                field=column,
                row=int(invalid_index) + 2,
            )

        negative_values = numeric_values < 0
        if negative_values.any():
            invalid_index = negative_values[negative_values].index[0]
            raise CSVValidationError(
                "NEGATIVE_VALUE",
                f"{column} values must be greater than or equal to zero.",
                field=column,
                row=int(invalid_index) + 2,
            )
