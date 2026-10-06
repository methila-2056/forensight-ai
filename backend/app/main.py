"""FORENSIGHT AI — FastAPI application entry point (Phase 0 skeleton)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config, terminology
from app.db import init_db
from app.routers import health


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=terminology.PRODUCT_NAME,
    version=config.APP_VERSION,
    description=(
        f"{terminology.PRODUCT_SUBTITLE}.\n\n"
        f"{terminology.PRODUCT_CONCEPT}\n\n"
        f"**Disclaimer:** {terminology.PROTOTYPE_DISCLAIMER}\n\n"
        f"**Integrity:** {terminology.INTEGRITY_DISCLAIMER}"
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=config.API_PREFIX)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": terminology.PRODUCT_NAME,
        "subtitle": terminology.PRODUCT_SUBTITLE,
        "version": config.APP_VERSION,
        "docs": "/docs",
        "health": f"{config.API_PREFIX}/health",
        "disclaimer": terminology.PROTOTYPE_DISCLAIMER,
    }
