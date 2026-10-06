"""Health endpoint router (Phase 0)."""

from __future__ import annotations

from fastapi import APIRouter

from app import schemas

router = APIRouter(tags=["health"])


@router.get("/health", response_model=schemas.HealthResponse, summary="Service health check")
def health() -> schemas.HealthResponse:
    return schemas.HealthResponse(status="ok")
