"""Pydantic response/request schemas (Phase 0: health only)."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
