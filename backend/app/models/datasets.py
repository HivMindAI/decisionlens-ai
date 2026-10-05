from typing import Literal

from pydantic import BaseModel, Field


class DatasetValidationResponse(BaseModel):
    status: Literal["valid"] = "valid"
    row_count: int
    period_start: str
    period_end: str
    frequency: Literal["monthly"] = "monthly"
    required_columns: list[str]
    extra_columns: list[str]
    warnings: list[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None
    row: int | None = None


class ValidationErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: ValidationIssue

