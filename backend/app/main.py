from typing import Annotated

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.datasets import (
    DatasetValidationResponse,
    ValidationErrorResponse,
    ValidationIssue,
)
from app.services.csv_validation import (
    CSVValidationError,
    MAX_UPLOAD_SIZE_BYTES,
    validate_csv_upload,
)

app = FastAPI(title="DecisionLens AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(CSVValidationError)
async def csv_validation_error_handler(
    _request: Request,
    exc: CSVValidationError,
) -> JSONResponse:
    payload = ValidationErrorResponse(
        error=ValidationIssue(
            code=exc.code,
            message=exc.message,
            field=exc.field,
            row=exc.row,
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(exclude_none=True),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "decisionlens-ai-api",
    }


@app.post(
    "/api/v1/datasets/validate",
    response_model=DatasetValidationResponse,
    responses={
        413: {"model": ValidationErrorResponse},
        415: {"model": ValidationErrorResponse},
        422: {"model": ValidationErrorResponse},
    },
)
async def validate_dataset(
    file: Annotated[UploadFile, File(description="Monthly financial data in CSV format")],
) -> DatasetValidationResponse:
    try:
        content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    finally:
        await file.close()

    return validate_csv_upload(file.filename, content)

