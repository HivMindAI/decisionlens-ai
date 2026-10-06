import os
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models.analytics import AnalysisSummaryResponse
from app.models.decisions import DecisionBriefResponse
from app.models.datasets import (
    DatasetValidationResponse,
    ValidationErrorResponse,
    ValidationIssue,
)
from app.models.simulation import WhatIfSimulationResponse
from app.services.analytics import build_analysis_summary
from app.services.csv_validation import (
    CSVValidationError,
    MAX_UPLOAD_SIZE_BYTES,
    load_validated_csv,
    validate_csv_upload,
)
from app.services.decisions import generate_decision_brief
from app.services.simulation import (
    ScenarioValidationError,
    build_what_if_simulation,
    parse_scenario_json,
)

LOCAL_DEVELOPMENT_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def get_allowed_origins() -> list[str]:
    configured_origins = os.getenv("DECISIONLENS_ALLOWED_ORIGINS")
    if configured_origins is None:
        return list(LOCAL_DEVELOPMENT_ORIGINS)

    return [
        origin.strip()
        for origin in configured_origins.split(",")
        if origin.strip()
    ]


def add_cors_middleware(application: FastAPI) -> None:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )


app = FastAPI(title="DecisionLens AI API", version="0.1.0")

add_cors_middleware(app)


@app.exception_handler(CSVValidationError)
async def csv_validation_error_handler(
    _request: Request,
    exc: CSVValidationError,
) -> JSONResponse:
    return _validation_error_response(exc)


@app.exception_handler(ScenarioValidationError)
async def scenario_validation_error_handler(
    _request: Request,
    exc: ScenarioValidationError,
) -> JSONResponse:
    return _validation_error_response(exc)


def _validation_error_response(
    exc: CSVValidationError | ScenarioValidationError,
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
    filename, content = await _read_upload(file)
    return validate_csv_upload(filename, content)


@app.post(
    "/api/v1/analysis/summary",
    response_model=AnalysisSummaryResponse,
    responses={
        413: {"model": ValidationErrorResponse},
        415: {"model": ValidationErrorResponse},
        422: {"model": ValidationErrorResponse},
    },
)
async def analysis_summary(
    file: Annotated[UploadFile, File(description="Monthly financial data in CSV format")],
) -> AnalysisSummaryResponse:
    filename, content = await _read_upload(file)
    frame = load_validated_csv(filename, content)
    return build_analysis_summary(frame)


@app.post(
    "/api/v1/decisions/brief",
    response_model=DecisionBriefResponse,
    responses={
        413: {"model": ValidationErrorResponse},
        415: {"model": ValidationErrorResponse},
        422: {"model": ValidationErrorResponse},
    },
)
async def decision_brief(
    file: Annotated[UploadFile, File(description="Monthly financial data in CSV format")],
) -> DecisionBriefResponse:
    filename, content = await _read_upload(file)
    frame = load_validated_csv(filename, content)
    analysis = build_analysis_summary(frame)
    return await generate_decision_brief(analysis)


@app.post(
    "/api/v1/simulations/what-if",
    response_model=WhatIfSimulationResponse,
    responses={
        413: {"model": ValidationErrorResponse},
        415: {"model": ValidationErrorResponse},
        422: {"model": ValidationErrorResponse},
    },
)
async def what_if_simulation(
    file: Annotated[UploadFile, File(description="Monthly financial data in CSV format")],
    scenario: Annotated[
        str,
        Form(description="JSON object containing scenario percentage adjustments"),
    ] = "{}",
) -> WhatIfSimulationResponse:
    filename, content = await _read_upload(file)
    adjustments = parse_scenario_json(scenario)
    frame = load_validated_csv(filename, content)
    analysis = build_analysis_summary(frame)
    return build_what_if_simulation(analysis.forecast, adjustments)


async def _read_upload(file: UploadFile) -> tuple[str | None, bytes]:
    filename = file.filename
    try:
        content = await file.read(MAX_UPLOAD_SIZE_BYTES + 1)
    finally:
        await file.close()

    return filename, content
