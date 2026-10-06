from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.main import add_cors_middleware, get_allowed_origins


def make_cors_client() -> TestClient:
    test_app = FastAPI()

    @test_app.get("/probe")
    async def probe() -> dict[str, str]:
        return {"status": "ok"}

    add_cors_middleware(test_app)
    return TestClient(test_app)


def preflight(client: TestClient, origin: str):
    return client.options(
        "/probe",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


def test_local_origins_are_allowed_when_configuration_is_unset(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("DECISIONLENS_ALLOWED_ORIGINS", raising=False)
    origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

    assert get_allowed_origins() == origins

    client = make_cors_client()
    for origin in origins:
        response = preflight(client, origin)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_configured_production_origin_is_allowed(monkeypatch: MonkeyPatch) -> None:
    origin = "https://decisionlens.example.com"
    monkeypatch.setenv("DECISIONLENS_ALLOWED_ORIGINS", origin)

    response = preflight(make_cors_client(), origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unrelated_origin_is_not_allowed(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DECISIONLENS_ALLOWED_ORIGINS",
        "https://decisionlens.example.com",
    )

    response = preflight(make_cors_client(), "https://unrelated.example.com")

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_multiple_comma_separated_origins_are_parsed(monkeypatch: MonkeyPatch) -> None:
    origins = ["https://app.example.com", "https://preview.example.com"]
    monkeypatch.setenv(
        "DECISIONLENS_ALLOWED_ORIGINS",
        f" {origins[0]}, , {origins[1]}  ,",
    )

    assert get_allowed_origins() == origins

    client = make_cors_client()
    for origin in origins:
        response = preflight(client, origin)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
