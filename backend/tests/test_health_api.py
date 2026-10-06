"""API tests: health endpoint and OpenAPI/docs availability (Phase 0 criteria 4-5)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_returns_service_descriptor(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "FORENSIGHT AI"
    assert body["docs"] == "/docs"


def test_swagger_docs_are_served(client: TestClient):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.casefold()


def test_openapi_schema_lists_health(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "FORENSIGHT AI"
    assert "/api/health" in schema["paths"]


def test_openapi_description_carries_disclaimers(client: TestClient):
    schema = client.get("/openapi.json").json()
    description = schema["info"]["description"].casefold()
    assert "research/hackathon prototype" in description
    assert "does not establish who created or collected" in description
